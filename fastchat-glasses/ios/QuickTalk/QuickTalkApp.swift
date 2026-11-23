import AVFoundation
import OSLog
import QuickTalkCore
import SwiftUI

@main
struct QuickTalkApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var app = QuickTalkModel()

    var body: some Scene {
        WindowGroup {
            QuickTalkView(app: app, glasses: app.glasses)
                .onOpenURL { url in Task { await app.glasses.handle(url) } }
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    guard let url = activity.webpageURL else { return }
                    Task { await app.glasses.handle(url) }
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .background { app.pause() }
                }
                .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { note in
                    if note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt == AVAudioSession.InterruptionType.began.rawValue {
                        app.pause()
                    }
                }
        }
    }
}

@MainActor
final class QuickTalkModel: ObservableObject {
    @Published private(set) var state = ConversationState()
    @Published private(set) var downloaded: Int64 = 0
    @Published private(set) var downloading = false
    @Published private(set) var loading = false
    @Published private(set) var issue: String?
    @Published private(set) var voiceCount = 10

    @Published var name = UserDefaults.standard.string(forKey: "name") ?? "" {
        didSet { UserDefaults.standard.set(name, forKey: "name") }
    }
    @Published var about = UserDefaults.standard.string(forKey: "about") ?? "" {
        didSet { UserDefaults.standard.set(about, forKey: "about") }
    }
    @Published var voice = UserDefaults.standard.integer(forKey: "voice") {
        didSet { UserDefaults.standard.set(voice, forKey: "voice") }
    }
    @Published var speed = (UserDefaults.standard.object(forKey: "speed") as? Double) ?? 1 {
        didSet { UserDefaults.standard.set(speed, forKey: "speed") }
    }
    @Published var volume = (UserDefaults.standard.object(forKey: "volume") as? Double) ?? 1 {
        didSet { UserDefaults.standard.set(volume, forKey: "volume") }
    }
    @Published var tick = (UserDefaults.standard.object(forKey: "tick") as? Bool) ?? true {
        didSet { UserDefaults.standard.set(tick, forKey: "tick") }
    }

    let glasses = GlassesLink()
    private let store = ModelStore()
    private let logger = Logger(subsystem: "com.natesapps.quicktalk", category: "Conversation")
    private var runner: ConversationRunner?
    private var audio: PhoneAudio?
    private var setupTask: Task<Void, Never>?
    private var startTask: Task<Void, Never>?
    private var previewTask: Task<Void, Never>?

    var modelsReady: Bool { downloaded == ModelStore.totalBytes }
    var active: Bool { state.phase != .off }
    private var persona: Persona { .init(name: name, about: about) }

    init() {
        downloaded = store.presentBytes()
        if downloaded > 0 { try? store.prepareDirectory() }
        glasses.onInput = { [weak self] input in self?.runner?.input(input) }
        glasses.onClosed = { [weak self] in self?.pause() }
    }

    func download() {
        guard !downloading, !modelsReady else { return }
        downloading = true
        issue = nil
        setupTask = Task { [weak self, store] in
            guard let self else { return }
            defer {
                self.downloaded = store.presentBytes()
                self.downloading = false
                self.setupTask = nil
            }
            do {
                try await store.download { [weak self] count in
                    Task { @MainActor [weak self] in
                        guard let self, self.downloading else { return }
                        // All files have to be verified on disk before Start is enabled.
                        self.downloaded = min(ModelStore.totalBytes - 1, max(self.downloaded, count))
                    }
                }
            } catch {
                if !Task.isCancelled { self.issue = error.localizedDescription }
            }
        }
    }

    func cancelDownload() { setupTask?.cancel() }

    func start() {
        guard modelsReady, !active, !loading else { return }
        issue = nil
        previewTask?.cancel()
        loading = true
        startTask = Task { [weak self] in
            guard let self else { return }
            defer { self.loading = false; self.startTask = nil }
            do {
                let runner = try await self.loadConversation()
                try Task.checkCancellation()
                runner.start()
            } catch {
                if !Task.isCancelled { self.issue = error.localizedDescription }
            }
        }
    }

    func pause() {
        startTask?.cancel()
        previewTask?.cancel()
        if active { runner?.stop() }
    }

    func previewVoice() {
        guard modelsReady, !active, !loading, previewTask == nil else { return }
        issue = nil
        loading = true
        previewTask = Task { [weak self] in
            guard let self else { return }
            defer { self.loading = false; self.previewTask = nil }
            do {
                _ = try await self.loadConversation()
                try Task.checkCancellation()
                try await self.audio?.speak("Hello, this is my QuickTalk voice.")
            } catch {
                if !Task.isCancelled { self.issue = error.localizedDescription }
            }
        }
    }

    private func loadConversation() async throws -> ConversationRunner {
        if let runner { return runner }
        let store = store
        let logger = logger
        let models = try await Task.detached(priority: .userInitiated) { try SpeechModels(store: store) }.value
        try Task.checkCancellation()
        let engine = try await LlamaEngine.load(path: store.path("llm/LFM3-1.7B-QAD-Q4_0.gguf"))
        try Task.checkCancellation()
        let writer = ReplyWriter(model: engine) { message in logger.debug("\(message, privacy: .private)") }
        try await writer.prime(persona)
        try Task.checkCancellation()

        let audio = PhoneAudio(models)
        audio.voice = { [weak self] in self?.voice ?? 0 }
        audio.speed = { [weak self] in Float(self?.speed ?? 1) }
        audio.volume = { [weak self] in Float(self?.volume ?? 1) }
        let replies = PersonaReplies(writer) { [weak self] in self?.persona ?? .init() }
        let runner = ConversationRunner(listener: audio, writer: replies, voice: audio, glasses: glasses)
        runner.onChange = { [weak self] runner in
            self?.state = runner.state
            UIApplication.shared.isIdleTimerDisabled = runner.state.phase != .off
        }
        runner.log = { message in logger.error("\(message, privacy: .private)") }
        runner.tickEnabled = { [weak self] in self?.tick ?? false }
        audio.hearingChanged = { [weak runner] in runner?.setHearingSpeech($0) }
        self.audio = audio
        self.runner = runner
        voiceCount = max(1, models.voiceCount)
        if !(0..<voiceCount).contains(voice) { voice = 0 }
        return runner
    }
}
