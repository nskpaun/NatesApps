import AVFoundation
import Combine
import MWDATCore
import MWDATDisplay
import MWDATInputs
#if DEBUG
import MWDATMockDevice
#endif
import OSLog
import QuickTalkCore
import UIKit

@MainActor
final class GlassesLink: ObservableObject, GlassesOutput {
    @Published private(set) var registered = false
    @Published private(set) var available = false
    @Published private(set) var ready = false
    @Published private(set) var inputsReady = false
    @Published private(set) var devices: [String] = []
    @Published private(set) var issue: String?
    #if DEBUG
    @Published private(set) var mock: (any MockGlasses)?
    #endif

    var onInput: (GlassesInput) -> Void = { _ in }
    var onClosed: () -> Void = {}
    let logger = Logger(subsystem: "com.natesapps.quicktalk", category: "Glasses")

    private var wearables: (any WearablesInterface)?
    private var registeredDevices: [Device] = []
    private let deviceListeners = ListenerTokenBag()
    private let sessionListeners = ListenerTokenBag()
    private var registrationTask: Task<Void, Never>?
    private var devicesTask: Task<Void, Never>?
    private var sessionTask: Task<Void, Never>?
    private var sessionErrorTask: Task<Void, Never>?
    private var inputTask: Task<Void, Never>?
    private var drawTask: Task<Void, Never>?
    private var closeTask: Task<Void, Never>?
    private var wanted = false
    private var session: DeviceSession?
    private var display: MWDATDisplay.Display?
    private var screen: GlassesScreen?
    private var dial = Dial()
    private var dialRelease: ContinuousClock.Instant?
    private var tickPlayer: AVAudioPlayer?

    init(wearables configuredWearables: (any WearablesInterface)? = nil) {
        do {
            let wearables: any WearablesInterface
            if let configuredWearables {
                wearables = configuredWearables
            } else {
                try Wearables.configure()
                wearables = Wearables.shared
            }
            self.wearables = wearables
            registered = wearables.registrationState == .registered
            observeDevices(wearables.devices)
            registrationTask = Task { [weak self] in
                for await state in wearables.registrationStateStream() {
                    guard let self, !Task.isCancelled else { break }
                    self.registered = state == .registered
                    self.reconcile()
                }
            }
            devicesTask = Task { [weak self] in
                for await ids in wearables.devicesStream() {
                    guard let self, !Task.isCancelled else { break }
                    self.observeDevices(ids)
                }
            }
        } catch {
            issue = error.localizedDescription
        }
    }

    func register() async {
        guard let wearables else { return }
        do {
            issue = nil
            try await wearables.startRegistration()
        } catch { issue = error.localizedDescription }
    }

    func unregister() async {
        guard let wearables else { return }
        do {
            issue = nil
            try await wearables.startUnregistration()
        } catch { issue = error.localizedDescription }
    }

    func handle(_ url: URL) async {
        guard url.scheme == "quicktalk", let wearables else { return }
        do {
            _ = try await wearables.handleUrl(url)
        } catch { issue = error.localizedDescription }
    }

    func setWanted(_ wanted: Bool) {
        guard wanted != self.wanted else { return }
        self.wanted = wanted
        reconcile()
    }

    func show(_ screen: GlassesScreen) {
        guard self.screen != screen else { return }
        self.screen = screen
        scheduleDrawing()
    }

    private func observeDevices(_ ids: [DeviceIdentifier]) {
        deviceListeners.clear()
        registeredDevices = ids.compactMap { wearables?.deviceForIdentifier($0) }
            .filter { $0.supportsDisplay() }
        for device in registeredDevices {
            device.addDeviceStateListener { [weak self] _ in
                Task { @MainActor [weak self] in self?.reconcile() }
            }.store(in: deviceListeners)
        }
        reconcile()
    }

    private func reconcile() {
        devices = registeredDevices.map { device in
            let name = device.nameOrId()
            switch device.compatibility() {
            case .deviceUpdateRequired: return "\(name) · Update glasses"
            case .sdkUpdateRequired: return "\(name) · Update QuickTalk"
            default: break
            }
            switch device.linkState {
            case .connected: return "\(name) · Connected"
            case .connecting: return "\(name) · Connecting"
            case .disconnected: return "\(name) · Disconnected"
            }
        }
        let eligible = registeredDevices.filter {
            $0.linkState == .connected && $0.compatibility() != .deviceUpdateRequired &&
                $0.compatibility() != .sdkUpdateRequired
        }
        #if DEBUG
        let device = if let mock { eligible.first { $0.identifier == mock.deviceIdentifier } } else { eligible.first }
        #else
        let device = eligible.first
        #endif
        available = device != nil
        guard wanted, registered, let wearables else {
            if session != nil { disconnect() }
            return
        }
        if let session, let device, session.deviceId == device.identifier { return }
        disconnect()
        guard let device else { return }
        do {
            let selector = SpecificDeviceSelector(device: device.identifier)
            let session = try wearables.createSession(deviceSelector: selector)
            self.session = session
            let states = session.stateStream()
            sessionTask = Task { [weak self] in
                for await state in states {
                    guard let self, self.session === session, !Task.isCancelled else { break }
                    switch state {
                    case .started: self.startDisplay(session)
                    case .paused: self.ready = false
                    case .stopped: self.sessionStopped(session)
                    default: break
                    }
                }
            }
            let errors = session.errorStream()
            sessionErrorTask = Task { [weak self] in
                for await error in errors {
                    guard let self, self.session === session, !Task.isCancelled else { break }
                    self.issue = error.localizedDescription
                }
            }
            try session.start()
            issue = nil
        } catch {
            disconnect()
            issue = error.localizedDescription
        }
    }

    private func startDisplay(_ session: DeviceSession) {
        if let display {
            if display.state == .started {
                ready = true
                scheduleDrawing()
            } else if display.state == .stopped {
                display.start()
            }
            return
        }
        do {
            let display = try session.addDisplay()
            self.display = display
            display.statePublisher.listen { [weak self, weak display] state in
                Task { @MainActor [weak self, weak display] in
                    guard let self, let display, self.display === display else { return }
                    if state == .started {
                        self.closeTask?.cancel()
                        self.ready = true
                        self.scheduleDrawing()
                    } else if state == .stopped, self.ready {
                        self.ready = false
                        self.sessionStopped(session)
                    }
                }
            }.store(in: sessionListeners)
            display.start()
            if display.state == .started {
                ready = true
                scheduleDrawing()
            }
        } catch {
            issue = error.localizedDescription
            return
        }

        if let inputs = try? session.addInputs(configuration: .init(sources: [.captouch, .neuralBand, .neuralBandDrag])) {
            inputsReady = inputs.state == .active
            inputs.statePublisher.listen { [weak self, weak session] state in
                Task { @MainActor [weak self, weak session] in
                    guard let self, let session, self.session === session else { return }
                    self.inputsReady = state == .active
                    self.scheduleDrawing()
                }
            }.store(in: sessionListeners)
            inputTask = Task { [weak self] in
                for await event in inputs.events {
                    guard let self, self.session === session, !Task.isCancelled else { break }
                    self.handleInput(event)
                }
            }
        }
    }

    private func sessionStopped(_ session: DeviceSession) {
        ready = false
        closeTask?.cancel()
        closeTask = Task { [weak self] in
            // Link state may arrive shortly after the display closes.
            try? await Task.sleep(for: .milliseconds(400))
            guard let self, self.session === session, self.wanted, !Task.isCancelled else { return }
            let connected = self.registeredDevices.first { $0.identifier == session.deviceId }?.linkState == .connected
            self.disconnect()
            if connected { self.onClosed() } else { self.reconcile() }
        }
    }

    private func disconnect() {
        closeTask?.cancel()
        sessionTask?.cancel()
        sessionErrorTask?.cancel()
        inputTask?.cancel()
        drawTask?.cancel()
        drawTask = nil
        sessionListeners.clear()
        let display = self.display
        let session = self.session
        self.display = nil
        self.session = nil
        ready = false
        inputsReady = false
        dial.start()
        dialRelease = nil
        display?.stop()
        session?.stop()
    }

    private func handleInput(_ event: InputEvent) {
        guard wanted else { return }
        switch event {
        case let .nav(direction, _, _):
            let position: Dpad = switch direction {
            case .up: .up
            case .right: .right
            case .down: .down
            case .left: .left
            }
            onInput(.highlight(position))
        case .select:
            if let dialRelease, dialRelease.duration(to: .now) < .milliseconds(500) { return }
            onInput(.confirm)
        case .back:
            onInput(.back)
        case let .drag(action, _, _, dx, _, _, _):
            switch action {
            case .down: dial.start()
            case .move:
                guard dx.isFinite, abs(dx) <= 1 else { return }
                let steps = dial.move(dx)
                for _ in 0..<abs(steps) { onInput(.turn(clockwise: steps > 0)) }
            case .up:
                if dial.turned { dialRelease = .now }
            }
        default: break
        }
    }

    private func scheduleDrawing() {
        guard wanted, ready, let display, drawTask == nil else { return }
        drawTask = Task { [weak self] in
            var previous: GlassesScreen?
            var wasUsingInputs: Bool?
            var tick = 0
            var previousFrame = -1
            while let self, self.display === display, self.ready, !Task.isCancelled {
                guard let screen = self.screen else { break }
                let changed = previous != screen || wasUsingInputs != self.inputsReady
                if changed { tick = 0 }
                let animate = self.inputsReady && !UIAccessibility.isReduceMotionEnabled
                let frame = switch (animate, screen.cue) {
                case (true, .generating): tick % 3
                case (true, .hearing), (true, .speaking): tick % 2
                case (true, .pinch), (true, .swipeThumb): tick % 8 == 1 ? 1 : 0
                default: 0
                }
                do {
                    if self.inputsReady && (changed || frame != previousFrame) {
                        let bitmap = GlassesRenderer.render(screen, frame: frame)
                        try await display.send(FlexBox(alignment: .center, crossAlignment: .center) {
                            MWDATDisplay.Image(image: bitmap, sizePreset: .fill)
                        })
                    } else if !self.inputsReady && (previous != screen || wasUsingInputs != false) {
                        try await display.send(self.focusable(screen))
                    }
                } catch {
                    guard !Task.isCancelled, self.display === display else { break }
                    self.logger.debug("Display update failed: \(error.localizedDescription, privacy: .public)")
                    try? await Task.sleep(for: .milliseconds(400))
                    continue
                }
                previous = screen
                wasUsingInputs = self.inputsReady
                previousFrame = frame
                tick = (tick + 1) % 24
                try? await Task.sleep(for: .milliseconds(200))
            }
            if let self, self.display === display { self.drawTask = nil }
        }
    }

    private func focusable(_ screen: GlassesScreen) -> FlexBox {
        FlexBox(spacing: 6, alignment: .center, crossAlignment: .stretch) {
            switch screen {
            case .status(let status):
                MWDATDisplay.Text(status.title, style: .heading)
                if let detail = status.detail { MWDATDisplay.Text(detail) }
                if status.offersQuickPhrases {
                    MWDATDisplay.Button(label: "Quick phrases", onClick: click(.confirm, for: screen))
                } else if status.activity == .speaking {
                    MWDATDisplay.Button(label: "Stop speaking", onClick: click(.back, for: screen))
                }
            case .choices(let choices):
                if choices.replies.allSatisfy({ $0 == nil }) {
                    MWDATDisplay.Text("Finding replies", style: .heading)
                }
                for position in Dpad.allCases {
                    if let reply = choices.replies[position.rawValue] {
                        MWDATDisplay.Button(label: "\(reply.emoji) \(reply.text)", onClick: click(.highlight(position), for: screen))
                    }
                }
                MWDATDisplay.Button(label: "Listen again", onClick: click(.back, for: screen))
            }
        }
    }

    private func click(_ input: GlassesInput, for snapshot: GlassesScreen) -> @Sendable () -> Void {
        { [weak self] in
            Task { @MainActor [weak self] in
                guard let self, self.wanted, self.ready, !self.inputsReady else { return }
                if case .highlight(let position) = input {
                    guard case .choices(let old) = snapshot, case .choices(let current) = self.screen,
                          current.heard == old.heard, current.quick == old.quick,
                          current.replies[position.rawValue] == old.replies[position.rawValue] else { return }
                    self.onInput(input)
                    self.onInput(.confirm)
                } else if self.screen == snapshot {
                    self.onInput(input)
                }
            }
        }
    }

    func tick() {
        let route = AVAudioSession.sharedInstance().currentRoute.outputs
        guard route.contains(where: {
            let name = $0.portName.lowercased()
            return $0.portType == .bluetoothA2DP && (name.contains("ray-ban") || name.contains("ray ban"))
        }) else { return }
        let sampleRate: Int32 = 16_000
        let samples = (0..<640).map { index in
            Float(sin(Double(index) * 0.55) * exp(-Double(index) / 80) * 0.18)
        }
        tickPlayer = try? AVAudioPlayer(data: PhoneAudio.wave(.init(samples: samples, rate: sampleRate)))
        tickPlayer?.play()
    }

    #if DEBUG
    func setMockEnabled(_ enabled: Bool) async {
        if enabled {
            guard mock == nil else { return }
            let kit = MockDeviceKit.shared
            kit.enable()
            do {
                let glasses = try kit.pairGlasses(model: .metaRayBanDisplay)
                mock = glasses
                glasses.powerOn()
                glasses.unfold()
                glasses.don()
                issue = nil
            } catch {
                await kit.disable()
                issue = error.localizedDescription
            }
        } else if let mock {
            disconnect()
            self.mock = nil
            mock.doff()
            mock.powerOff()
            await MockDeviceKit.shared.unpairDevice(mock)
            await MockDeviceKit.shared.disable()
        }
        if let wearables { observeDevices(wearables.devices) }
    }

    func simulate(_ input: GlassesInput) {
        guard let kit = mock?.services.input else { return }
        switch input {
        case .highlight(.up): kit.navUp(source: .neuralBand)
        case .highlight(.right): kit.navRight(source: .neuralBand)
        case .highlight(.down): kit.navDown(source: .neuralBand)
        case .highlight(.left): kit.navLeft(source: .neuralBand)
        case .confirm: kit.select(source: .neuralBand)
        case .back: kit.back(source: .neuralBand)
        case .turn(let clockwise):
            let distance: Float = clockwise ? 0.055 : -0.055
            kit.drag(action: .down, x: 0, y: 0, dx: 0, dy: 0)
            kit.drag(action: .move, x: distance, y: 0, dx: distance, dy: 0)
            kit.drag(action: .up, x: distance, y: 0, dx: 0, dy: 0)
        }
    }
    #endif
}
