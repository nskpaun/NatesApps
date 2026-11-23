// Keep these paths, sizes and hashes in sync with the Android model catalogue.

extension ModelStore {
    static let catalog: [ModelFile] = [
        .init(path: "speech-to-text/silero_vad.onnx", url: "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx", bytes: 643_854, sha256: "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"),
        .init(path: "speech-to-text/tokens.txt", url: "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/tokens.txt", bytes: 9_384),
        .init(path: "speech-to-text/joiner.int8.onnx", url: "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/joiner.int8.onnx", bytes: 1_739_080, sha256: "77a29f3e5ac7d37074e0af465391b80f314015d5b97f0f90c6c7767f1d56f428"),
        .init(path: "speech-to-text/decoder.int8.onnx", url: "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/decoder.int8.onnx", bytes: 7_257_753, sha256: "4d097bae3bac5c96018d5293ba39f1b657296102b142affda40378f38b020f41"),
        .init(path: "text-to-speech/tts.json", url: "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main/tts.json", bytes: 8_253),
        .init(path: "text-to-speech/unicode_indexer.bin", url: "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main/unicode_indexer.bin", bytes: 262_144, sha256: "8402ca48e5189a8950138580b0fff64db6f072f24ac07cd54ba8b2fbb9883b30"),
        .init(path: "text-to-speech/voice.bin", url: "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main/voice.bin", bytes: 517_168, sha256: "67d5209b0ee8ce6c74105ffbe12fe6a7628aea3b4ba2fcb308a4a67938a93ce8"),
        .init(path: "text-to-speech/duration_predictor.int8.onnx", url: "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main/duration_predictor.int8.onnx", bytes: 3_700_147, sha256: "c3eb91414d5ff8a7a239b7fe9e34e7e2bf8a8140d8375ffb14718b1c639325db"),
        .init(path: "text-to-speech/vocoder.int8.onnx", url: "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main/vocoder.int8.onnx", bytes: 25_991_073, sha256: "e923d60f53f95eb1ce235f1dc33ec56d9c057823c96fa6f8acf98f32b0da6152"),
        .init(path: "text-to-speech/text_encoder.int8.onnx", url: "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main/text_encoder.int8.onnx", bytes: 36_416_150, sha256: "c7befd5ea8c3119769e8a6c1486c4edc6a3bc8365c67621c881bbb774b9902ff"),
        .init(path: "text-to-speech/vector_estimator.int8.onnx", url: "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main/vector_estimator.int8.onnx", bytes: 78_400_833, sha256: "20cd86fa5c6effedfda0e7cffe5b0569ca401c440a0c3a1d72bf39286c0db3fd"),
        .init(path: "speech-to-text/encoder.int8.onnx", url: "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main/encoder.int8.onnx", bytes: 652_282_309, sha256: "92a10bd9c23936ea0566c29f963bc57c2a5df4261b6a8921c39abea66557ca8b"),
        .init(path: "llm/LFM3-1.7B-QAD-Q4_0.gguf", url: "https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF/resolve/main/LFM3-1.7B-QAD-Q4_0.gguf", bytes: 1_049_615_680, sha256: "43a7d09a0e9cba91b63eb7052488b9564569bddfd65754d2e426465e572a7452"),
    ]
}
