import Foundation
import QuickTalkCore
import QuickTalkLLMC

/// The on-device language model: LFM3 through llama.cpp, via the plain C interface in
/// `android/app/src/main/cpp/llm_c_api.h` (the same engine the Android app runs).
///
/// `prime` and `generate` block and must not overlap; `ReplyWriter` keeps them on one thread.
/// `cancel` may be called from any thread to stop the call in progress.
public final class LlamaEngine: TextModel, @unchecked Sendable {

    public struct Failure: LocalizedError {
        public let message: String
        public var errorDescription: String? { message }
    }

    // The sampling the prompt was tuned with (see ReplyWriter.temperature).
    static let topP: Float = 0.8
    static let topK: Int32 = 20
    static let presencePenalty: Float = 1.5

    private let handle: OpaquePointer

    /// Loads the GGUF at `path`. Takes a few seconds; throws if the file cannot be loaded.
    public init(path: String, contextTokens: Int32 = 4096, threads: Int32 = LlamaEngine.defaultThreads()) throws {
        var error: UnsafeMutablePointer<CChar>?
        guard let handle = qt_engine_load(path, contextTokens, threads, &error) else {
            throw Failure(message: Self.take(error) ?? "Could not load the model")
        }
        self.handle = handle
    }

    static func load(path: String) async throws -> LlamaEngine {
        try await withCheckedThrowingContinuation { (result: CheckedContinuation<LlamaEngine, Error>) in
            let loader = Thread {
                do { result.resume(returning: try LlamaEngine(path: path)) }
                catch { result.resume(throwing: error) }
            }
            loader.name = "quicktalk-load-llm"
            loader.stackSize = 8 * 1024 * 1024
            loader.start()
        }
    }

    deinit { qt_engine_free(handle) }

    /// Leave two cores for audio and the UI; more than six threads stops paying off.
    public static func defaultThreads() -> Int32 {
        Int32(min(max(ProcessInfo.processInfo.activeProcessorCount - 2, 2), 6))
    }

    public func prime(_ prefix: String) throws {
        var error: UnsafeMutablePointer<CChar>?
        if !qt_engine_prime(handle, prefix, &error) {
            throw Failure(message: Self.take(error) ?? "Priming the model failed")
        }
    }

    public func generate(
        prefix: String, suffix: String, grammar: String, maxTokens: Int, temperature: Float,
        onText: (String) -> Bool
    ) throws -> GenerationStats {
        let params = qt_gen_params(
            temperature: temperature, top_p: Self.topP, top_k: Self.topK,
            presence_penalty: Self.presencePenalty, max_tokens: Int32(maxTokens)
        )
        var stats = qt_stats()
        var error: UnsafeMutablePointer<CChar>?
        // The callback is a C function pointer, so the Swift closure travels in `context`.
        let ok = withoutActuallyEscaping(onText) { sink -> Bool in
            var box = Sink(sink)
            return withUnsafeMutablePointer(to: &box) { pointer in
                qt_engine_generate(handle, prefix, suffix, grammar, params, { text, length, context in
                    guard let text, let context else { return false }
                    let sink = context.assumingMemoryBound(to: Sink.self).pointee
                    let bytes = UnsafeRawBufferPointer(start: text, count: Int(length))
                    return sink.call(String(decoding: bytes, as: UTF8.self))
                }, pointer, &stats, &error)
            }
        }
        if !ok { throw Failure(message: Self.take(error) ?? "The model failed") }
        return GenerationStats(
            promptTokens: Int(stats.prompt_tokens), promptMs: Int(stats.prompt_ms),
            outputTokens: Int(stats.output_tokens), outputMs: Int(stats.output_ms),
            prefixReused: stats.prefix_reused
        )
    }

    public func cancel() { qt_engine_cancel(handle) }

    private struct Sink {
        let call: (String) -> Bool
        init(_ call: @escaping (String) -> Bool) { self.call = call }
    }

    private static func take(_ error: UnsafeMutablePointer<CChar>?) -> String? {
        guard let error else { return nil }
        defer { qt_free_string(error) }
        return String(cString: error)
    }
}
