import AVFoundation
import QuickTalkCore

@MainActor
final class PhoneAudio: Listener, VoiceOutput {
    let models: SpeechModels
    var hearingChanged: (Bool) -> Void = { _ in }
    var voice: () -> Int = { 0 }
    var speed: () -> Float = { 1 }
    var volume: () -> Float = { 1 }

    private var audioOwner: UUID?

    init(_ models: SpeechModels) { self.models = models }

    func listen() async throws -> String {
        let granted = await AVAudioApplication.requestRecordPermission()
        try Task.checkCancellation()
        guard granted else { throw SpeechFailure.microphonePermission }

        await models.resetListener()
        try Task.checkCancellation()

        let owner = try usePhoneAudio()
        defer {
            if audioOwner == owner { hearingChanged(false) }
            releasePhoneAudio(owner)
        }
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0,
              let output = AVAudioFormat(standardFormatWithSampleRate: Double(SpeechModels.sampleRate), channels: 1),
              let converter = AVAudioConverter(from: format, to: output) else {
            throw SpeechFailure.microphone
        }
        let pipe = AsyncStream<[Float]>.makeStream(bufferingPolicy: .bufferingNewest(32))
        input.installTap(onBus: 0, bufferSize: 2_048, format: format,
                         block: Self.audioTap(converter: converter, output: output, samples: pipe.continuation))
        defer {
            input.removeTap(onBus: 0)
            engine.stop()
            pipe.continuation.finish()
        }
        try engine.start()
        for await buffer in pipe.stream {
            try Task.checkCancellation()
            let result = await models.accept(buffer)
            try Task.checkCancellation()
            hearingChanged(result.detectingSpeech)
            if let text = result.text { return text }
        }
        throw CancellationError()
    }

    func speak(_ text: String) async throws {
        let audio = try await models.synthesize(text, voice: voice(), speed: speed())
        try Task.checkCancellation()
        let owner = try usePhoneAudio()
        defer { releasePhoneAudio(owner) }
        let player = try AVAudioPlayer(data: Self.wave(audio))
        let level = min(1, max(0, volume()))
        player.volume = level == 0 ? 0 : pow(10, -1.5 * (1 - level))
        guard player.play() else { throw SpeechFailure.voice }
        defer { player.stop() }
        while player.isPlaying {
            try await Task.sleep(for: .milliseconds(30))
        }
    }

    private func usePhoneAudio() throws -> UUID {
        let owner = UUID()
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
        try session.setActive(true)
        audioOwner = owner
        do {
            try session.overrideOutputAudioPort(.speaker)
            if let mic = session.availableInputs?.first(where: { $0.portType == .builtInMic }) {
                try session.setPreferredInput(mic)
            }
        } catch {
            releasePhoneAudio(owner)
            throw error
        }
        return owner
    }

    private func releasePhoneAudio(_ owner: UUID) {
        guard audioOwner == owner else { return }
        audioOwner = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private nonisolated static func audioTap(
        converter: AVAudioConverter, output: AVAudioFormat, samples: AsyncStream<[Float]>.Continuation
    ) -> AVAudioNodeTapBlock {
        { input, _ in
            let capacity = AVAudioFrameCount(ceil(Double(input.frameLength) * output.sampleRate / input.format.sampleRate)) + 16
            guard let converted = AVAudioPCMBuffer(pcmFormat: output, frameCapacity: capacity) else { return }
            // AVAudioConverter invokes the input callback synchronously for each tapped buffer.
            let source = ConverterInput(input)
            var error: NSError?
            let result = converter.convert(to: converted, error: &error) { _, status in
                guard let input = source.take() else {
                    status.pointee = .noDataNow
                    return nil
                }
                status.pointee = .haveData
                return input
            }
            guard result != .error, converted.frameLength > 0, let channel = converted.floatChannelData?[0] else { return }
            samples.yield(Array(UnsafeBufferPointer(start: channel, count: Int(converted.frameLength))))
        }
    }

    private final class ConverterInput: @unchecked Sendable {
        private var buffer: AVAudioPCMBuffer?

        init(_ buffer: AVAudioPCMBuffer) { self.buffer = buffer }

        func take() -> AVAudioPCMBuffer? {
            defer { buffer = nil }
            return buffer
        }
    }

    static func wave(_ audio: SpeechModels.Audio) -> Data {
        let bytes = UInt32(audio.samples.count * MemoryLayout<Int16>.size)
        var data = Data()
        func add<T: FixedWidthInteger>(_ value: T) {
            withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) }
        }
        data.append(contentsOf: "RIFF".utf8)
        add(bytes + 36)
        data.append(contentsOf: "WAVEfmt ".utf8)
        add(UInt32(16))
        add(UInt16(1))
        add(UInt16(1))
        add(UInt32(audio.rate))
        add(UInt32(audio.rate) * 2)
        add(UInt16(2))
        add(UInt16(16))
        data.append(contentsOf: "data".utf8)
        add(bytes)
        let pcm = audio.samples.map { Int16(min(1, max(-1, $0)) * Float(Int16.max)).littleEndian }
        pcm.withUnsafeBytes { data.append(contentsOf: $0) }
        return data
    }
}
