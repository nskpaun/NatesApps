import Foundation

/// Timings of one model call.
public struct GenerationStats: Equatable, Sendable {
    public var promptTokens: Int
    public var promptMs: Int
    public var outputTokens: Int
    public var outputMs: Int
    public var prefixReused: Bool

    public init(promptTokens: Int = 0, promptMs: Int = 0, outputTokens: Int = 0, outputMs: Int = 0, prefixReused: Bool = false) {
        self.promptTokens = promptTokens
        self.promptMs = promptMs
        self.outputTokens = outputTokens
        self.outputMs = outputMs
        self.prefixReused = prefixReused
    }

    public var tokensPerSecond: Double { outputMs > 0 ? Double(outputTokens) * 1000 / Double(outputMs) : 0 }
}

/// The on-device language model, as `ReplyWriter` needs it. The app's `LlamaEngine` (LFM3 on
/// llama.cpp) implements it; tests use a scripted fake.
///
/// `prime` and `generate` block and are never called at the same time: `ReplyWriter` keeps them on
/// one thread. `cancel` may be called from any thread to stop the call in progress.
public protocol TextModel: AnyObject, Sendable {
    /// Evaluates `prefix` ahead of time so the first `generate` that shares it starts sooner.
    func prime(_ prefix: String) throws
    /// Completes `prefix` + `suffix`, constrained by the GBNF `grammar`. `onText` receives the
    /// output as it is written; returning false stops it.
    func generate(
        prefix: String, suffix: String, grammar: String, maxTokens: Int, temperature: Float,
        onText: (String) -> Bool
    ) throws -> GenerationStats
    func cancel()
}

public struct ReplyUpdate: Equatable, Sendable {
    public var replies: [Reply]
    public var done: Bool
    public var stats: GenerationStats?
}

/// Asks the model for replies and streams them out one at a time as each line is finished.
/// Ported from the Android `llm/ReplyWriter.kt`.
public final class ReplyWriter: @unchecked Sendable {
    /// Room for the bracketed line and four replies of `maxReplyChars` characters.
    static let maxOutputTokens = 160
    /// How many times the model is asked before settling for fewer than four distinct replies.
    static let maxAttempts = 3
    /// The sampling the prompt was tuned with. LFM3's own recommendation (0.1) made the four
    /// replies too alike.
    public static let temperature: Float = 0.7
    /// For a second try or for "more replies": looser, to get different ones.
    static let retryTemperature: Float = 1.0
    /// The yes/no decision should be the model's single most likely answer.
    static let decisionTemperature: Float = 0.01

    private let model: TextModel
    /// All model calls run here, one at a time: the engine is not thread-safe. Not a dispatch
    /// queue: its threads have 512 KB stacks, and llama.cpp overflows them.
    private let queue = ModelThread(name: "quicktalk-llm")
    private let log: @Sendable (String) -> Void

    public init(model: TextModel, log: @escaping @Sendable (String) -> Void = { _ in }) {
        self.model = model
        self.log = log
    }

    /// Evaluates the fixed parts of both prompts ahead of the first reply.
    public func prime(_ persona: Persona) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            queue.async { [model] in
                do {
                    if !persona.about.trimmed.isEmpty { try model.prime(PersonaCheck.systemBlock(persona)) }
                    try model.prime(ReplyPrompt.systemBlock(persona))
                    continuation.resume()
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    /// Emits the list of finished replies each time it grows, then a final update with
    /// `done == true`. Ending the stream early (the consumer's task is cancelled) stops the model
    /// within a token.
    ///
    /// Replies in `avoid` (already offered and turned down) are never emitted. Telling a small
    /// model what not to say does not work, so repeats are dropped here instead and the model is
    /// simply asked again, more loosely, until there are four distinct replies.
    public func replies(persona: Persona, history: [Turn], avoid: [String]) -> AsyncThrowingStream<ReplyUpdate, Error> {
        AsyncThrowingStream { continuation in
            let cancelled = Flag()
            continuation.onTermination = { [model] termination in
                if case .cancelled = termination {
                    cancelled.set()
                    model.cancel()
                }
            }
            queue.async { [self] in
                do {
                    let unwanted = Set(avoid.map(ReplyParser.sameWords))
                    let facts = try needsFacts(persona, history) ? persona.about : nil
                    var kept: [Reply] = []
                    var stats: GenerationStats?
                    var attempt = 0
                    while !cancelled.isSet, kept.count < replyCount, attempt < Self.maxAttempts {
                        let earlier = kept
                        var text = ""
                        stats = try model.generate(
                            prefix: ReplyPrompt.systemBlock(persona),
                            suffix: ReplyPrompt.turnBlock(history, facts: facts),
                            grammar: ReplyPrompt.grammar,
                            maxTokens: Self.maxOutputTokens,
                            temperature: attempt == 0 && avoid.isEmpty ? Self.temperature : Self.retryTemperature
                        ) { piece in
                            text += piece
                            let soFar = Self.distinct(earlier + ReplyParser.parse(text, finished: false), unwanted)
                            if soFar.count > kept.count {
                                kept = soFar
                                continuation.yield(ReplyUpdate(replies: kept, done: false))
                            }
                            return !cancelled.isSet && kept.count < replyCount
                        }
                        kept = Self.distinct(earlier + ReplyParser.parse(text, finished: true), unwanted)
                        attempt += 1
                    }
                    if !cancelled.isSet { continuation.yield(ReplyUpdate(replies: kept, done: true, stats: stats)) }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// Whether answering the last thing the other person said needs the wearer's own facts: one
    /// short model call with a one-word answer. Without any facts there is nothing to decide.
    private func needsFacts(_ persona: Persona, _ history: [Turn]) throws -> Bool {
        guard !persona.about.trimmed.isEmpty, let said = history.last(where: { $0.speaker == .partner })?.text else {
            return false
        }
        var answer = ""
        let stats = try model.generate(
            prefix: PersonaCheck.systemBlock(persona),
            suffix: PersonaCheck.turnBlock(said),
            grammar: PersonaCheck.grammar,
            maxTokens: 2,
            temperature: Self.decisionTemperature
        ) { piece in
            answer += piece
            return true
        }
        let yes = PersonaCheck.saysYes(answer)
        log("about you: \(yes ? "needed" : "not needed"), decided in \(stats.promptMs + stats.outputMs) ms")
        return yes
    }

    /// `replies` in order, without repeats of each other or of anything in `unwanted`.
    static func distinct(_ replies: [Reply], _ unwanted: Set<String>) -> [Reply] {
        var seen = unwanted
        var out: [Reply] = []
        for reply in replies {
            let key = ReplyParser.sameWords(reply.text)
            if seen.insert(key).inserted { out.append(reply) }
            if out.count == replyCount { break }
        }
        return out
    }
}

/// One long-lived thread with a large stack that runs jobs in order.
final class ModelThread: @unchecked Sendable {
    /// What llama.cpp's graph evaluation and grammar sampler comfortably fit in.
    static let stackSize = 8 << 20

    private let condition = NSCondition()
    private var jobs: [() -> Void] = []

    init(name: String) {
        let thread = Thread { [condition] in
            while true {
                condition.lock()
                while self.jobs.isEmpty { condition.wait() }
                let job = self.jobs.removeFirst()
                condition.unlock()
                job()
            }
        }
        thread.name = name
        thread.stackSize = Self.stackSize
        thread.qualityOfService = .userInitiated
        thread.start()
    }

    func async(_ job: @escaping () -> Void) {
        condition.lock()
        jobs.append(job)
        condition.signal()
        condition.unlock()
    }
}

/// A thread-safe one-way switch.
final class Flag: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    var isSet: Bool { lock.lock(); defer { lock.unlock() }; return value }
    func set() { lock.lock(); value = true; lock.unlock() }
}
