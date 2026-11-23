import Foundation
import QuickTalkSpeechC

actor SpeechModels {
    static let sampleRate: Int32 = 16_000

    struct Recognition: Sendable {
        let detectingSpeech: Bool
        let text: String?
    }

    struct Audio: Sendable {
        let samples: [Float]
        let rate: Int32
    }

    private let models: Handles
    nonisolated let voiceCount: Int

    init(store: ModelStore) throws {
        models = try Handles(store)
        voiceCount = Int(SherpaOnnxOfflineTtsNumSpeakers(models.voice))
    }

    func resetListener() {
        SherpaOnnxVoiceActivityDetectorReset(models.vad)
    }

    func accept(_ samples: [Float]) -> Recognition {
        SherpaOnnxVoiceActivityDetectorAcceptWaveform(models.vad, samples, Int32(samples.count))
        let detectingSpeech = SherpaOnnxVoiceActivityDetectorDetected(models.vad) != 0
        while !Task.isCancelled, SherpaOnnxVoiceActivityDetectorEmpty(models.vad) == 0 {
            guard let segment = SherpaOnnxVoiceActivityDetectorFront(models.vad) else { break }
            SherpaOnnxVoiceActivityDetectorPop(models.vad)
            defer { SherpaOnnxDestroySpeechSegment(segment) }
            let data = Array(UnsafeBufferPointer(start: segment.pointee.samples, count: Int(segment.pointee.n)))
            let text = transcribe(data)
            if !text.isEmpty { return .init(detectingSpeech: false, text: text) }
        }
        return .init(detectingSpeech: detectingSpeech, text: nil)
    }

    func synthesize(_ text: String, voice: Int, speed: Float) throws -> Audio {
        try Task.checkCancellation()
        var config = SherpaOnnxGenerationConfig()
        config.sid = Int32(max(0, min(voice, voiceCount - 1)))
        config.speed = speed
        config.num_steps = 6
        let audio = #"{"lang":"en"}"#.withCString { language in
            config.extra = language
            return SherpaOnnxOfflineTtsGenerateWithConfig(models.voice, text, &config, nil, nil)
        }
        guard let audio else { throw SpeechFailure.voice }
        defer { SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio) }
        try Task.checkCancellation()
        let info = audio.pointee
        let samples = Array(UnsafeBufferPointer(start: info.samples, count: Int(info.n)))
        guard info.sample_rate > 0, let peak = samples.map({ abs($0) }).max() else {
            throw SpeechFailure.voice
        }
        return .init(samples: peak < 0.01 ? samples : samples.map { $0 * (0.95 / peak) }, rate: info.sample_rate)
    }

    private func transcribe(_ samples: [Float]) -> String {
        guard let stream = SherpaOnnxCreateOfflineStream(models.recognizer) else { return "" }
        defer { SherpaOnnxDestroyOfflineStream(stream) }
        let peak = samples.reduce(Float(0)) { max($0, abs($1)) }
        let audio = peak >= 0.01 && peak < 0.5 ? samples.map { $0 * (0.7 / peak) } : samples
        SherpaOnnxAcceptWaveformOffline(stream, Self.sampleRate, audio, Int32(audio.count))
        SherpaOnnxDecodeOfflineStream(models.recognizer, stream)
        guard let result = SherpaOnnxGetOfflineStreamResult(stream) else { return "" }
        defer { SherpaOnnxDestroyOfflineRecognizerResult(result) }
        guard let text = result.pointee.text else { return "" }
        return String(cString: text).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // Only the speech actor accesses the model handles after initialization.
    private final class Handles: @unchecked Sendable {
        let vad: OpaquePointer
        let recognizer: OpaquePointer
        let voice: OpaquePointer

        init(_ store: ModelStore) throws {
            let strings = ModelStrings(store)
            var vadConfig = SherpaOnnxVadModelConfig()
            vadConfig.sample_rate = SpeechModels.sampleRate
            vadConfig.num_threads = 1
            vadConfig.silero_vad.model = strings.path("speech-to-text/silero_vad.onnx")
            vadConfig.silero_vad.threshold = 0.5
            vadConfig.silero_vad.min_silence_duration = 0.7
            vadConfig.silero_vad.min_speech_duration = 0.25
            vadConfig.silero_vad.max_speech_duration = 20
            vadConfig.silero_vad.window_size = 512

            var stt = SherpaOnnxOfflineRecognizerConfig()
            stt.feat_config.sample_rate = SpeechModels.sampleRate
            stt.feat_config.feature_dim = 80
            stt.model_config.transducer.encoder = strings.path("speech-to-text/encoder.int8.onnx")
            stt.model_config.transducer.decoder = strings.path("speech-to-text/decoder.int8.onnx")
            stt.model_config.transducer.joiner = strings.path("speech-to-text/joiner.int8.onnx")
            stt.model_config.tokens = strings.path("speech-to-text/tokens.txt")
            stt.model_config.model_type = strings.copy("nemo_transducer")
            stt.model_config.num_threads = 4
            stt.decoding_method = strings.copy("greedy_search")

            var tts = SherpaOnnxOfflineTtsConfig()
            tts.model.supertonic.duration_predictor = strings.path("text-to-speech/duration_predictor.int8.onnx")
            tts.model.supertonic.text_encoder = strings.path("text-to-speech/text_encoder.int8.onnx")
            tts.model.supertonic.vector_estimator = strings.path("text-to-speech/vector_estimator.int8.onnx")
            tts.model.supertonic.vocoder = strings.path("text-to-speech/vocoder.int8.onnx")
            tts.model.supertonic.tts_json = strings.path("text-to-speech/tts.json")
            tts.model.supertonic.unicode_indexer = strings.path("text-to-speech/unicode_indexer.bin")
            tts.model.supertonic.voice_style = strings.path("text-to-speech/voice.bin")
            tts.model.num_threads = 4
            tts.max_num_sentences = 1
            tts.silence_scale = 0.2

            defer { withExtendedLifetime(strings) {} }
            guard let vad = SherpaOnnxCreateVoiceActivityDetector(&vadConfig, 30) else {
                throw SpeechFailure.models
            }
            guard let recognizer = SherpaOnnxCreateOfflineRecognizer(&stt) else {
                SherpaOnnxDestroyVoiceActivityDetector(vad)
                throw SpeechFailure.models
            }
            guard let voice = SherpaOnnxCreateOfflineTts(&tts) else {
                SherpaOnnxDestroyOfflineRecognizer(recognizer)
                SherpaOnnxDestroyVoiceActivityDetector(vad)
                throw SpeechFailure.models
            }
            self.vad = vad
            self.recognizer = recognizer
            self.voice = voice
        }

        deinit {
            SherpaOnnxDestroyOfflineTts(voice)
            SherpaOnnxDestroyOfflineRecognizer(recognizer)
            SherpaOnnxDestroyVoiceActivityDetector(vad)
        }
    }

    private final class ModelStrings {
        let store: ModelStore
        private var buffers: [UnsafeMutablePointer<CChar>] = []

        init(_ store: ModelStore) { self.store = store }

        func path(_ name: String) -> UnsafePointer<CChar>? { copy(store.path(name)) }

        func copy(_ value: String) -> UnsafePointer<CChar>? {
            guard let buffer = strdup(value) else { return nil }
            buffers.append(buffer)
            return UnsafePointer(buffer)
        }

        deinit { buffers.forEach { free($0) } }
    }
}

enum SpeechFailure: LocalizedError {
    case models, microphonePermission, microphone, voice

    var errorDescription: String? {
        switch self {
        case .models: "The speech models could not be loaded."
        case .microphonePermission: "Allow QuickTalk to use the microphone in Settings."
        case .microphone: "The iPhone microphone is unavailable."
        case .voice: "QuickTalk could not play the reply."
        }
    }
}
