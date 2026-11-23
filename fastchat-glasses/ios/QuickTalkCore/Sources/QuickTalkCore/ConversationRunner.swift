import Foundation

/// Hears the partner: returns the next utterance once they stop talking. Cancelling the task stops
/// listening. The app's implementation is Silero VAD + Parakeet through sherpa-onnx.
@MainActor
public protocol Listener: AnyObject {
    func listen() async throws -> String
}

/// Says a reply aloud from the phone. Returns when it has finished; cancelling the task stops it.
@MainActor
public protocol VoiceOutput: AnyObject {
    func speak(_ text: String) async throws
}

/// Writes replies: a `ReplyWriter` with the wearer's persona bound in (`PersonaReplies`).
public protocol ReplySource: AnyObject {
    func replies(history: [Turn], avoid: [String]) -> AsyncThrowingStream<ReplyUpdate, Error>
}

/// `ReplyWriter` as a `ReplySource`, reading the persona from Settings at each request.
public final class PersonaReplies: ReplySource {
    private let writer: ReplyWriter
    private let persona: () -> Persona

    public init(_ writer: ReplyWriter, persona: @escaping () -> Persona) {
        self.writer = writer
        self.persona = persona
    }

    public func replies(history: [Turn], avoid: [String]) -> AsyncThrowingStream<ReplyUpdate, Error> {
        writer.replies(persona: persona(), history: history, avoid: avoid)
    }
}

/// The glasses as the conversation sees them.
@MainActor
public protocol GlassesOutput: AnyObject {
    /// QuickTalk is on the glasses only while a conversation is running.
    func setWanted(_ wanted: Bool)
    func show(_ screen: GlassesScreen)
    /// A soft click in the glasses' speakers: the highlight landed on another reply.
    func tick()
}

/// Runs the conversation: feeds events through `reduce` and carries out the effects it asks for.
/// Ported from the Android `FastChat.kt` (its conversation half). Everything here runs on the
/// main actor; the heavy work happens inside the `Listener`, `ReplySource` and `Speaker`.
@MainActor
public final class ConversationRunner {
    public private(set) var state = ConversationState()
    public private(set) var hearingSpeech = false
    public private(set) var lastStats: GenerationStats?

    /// Called after every change of `state` (or of `hearingSpeech`).
    public var onChange: (ConversationRunner) -> Void = { _ in }
    /// Whether to click on each move of the highlight; read at the moment it moves.
    public var tickEnabled: () -> Bool = { true }
    public var log: (String) -> Void = { _ in }

    private let listener: Listener
    private let writer: ReplySource
    private let voice: VoiceOutput
    private let glasses: GlassesOutput

    private var listenTask: Task<Void, Never>?
    private var writeTask: Task<Void, Never>?
    private var speakTask: Task<Void, Never>?

    public init(listener: Listener, writer: ReplySource, voice: VoiceOutput, glasses: GlassesOutput) {
        self.listener = listener
        self.writer = writer
        self.voice = voice
        self.glasses = glasses
    }

    public func start() { dispatch(.start) }
    public func stop() { dispatch(.stop) }
    /// A gesture from the glasses, the band, or the on-screen d-pad.
    public func input(_ input: GlassesInput) { dispatch(.input(input)) }
    public func problem(_ message: String) { dispatch(.problem(message)) }

    /// The listener heard speech start or stop; only changes the cue on the glasses.
    public func setHearingSpeech(_ hearing: Bool) {
        guard hearing != hearingSpeech else { return }
        hearingSpeech = hearing
        glasses.show(screenFor(state, hearingSpeech: hearing))
        onChange(self)
    }

    /// Test hook: behaves as if the partner had just said `text`.
    public func debugHeard(_ text: String) {
        listenTask?.cancel()
        dispatch(.heard(text))
    }

    /// Test hook: forgets the conversation so far.
    public func debugReset() {
        state.history = []
        onChange(self)
    }

    func dispatch(_ event: ConversationEvent) {
        let before = state
        let step = reduce(before, event)
        state = step.state
        if let focus = step.state.phase.choosing?.focus, focus != before.phase.choosing?.focus, tickEnabled() {
            glasses.tick()
        }
        glasses.setWanted(step.state.phase != .off)
        glasses.show(screenFor(step.state, hearingSpeech: hearingSpeech))
        onChange(self)
        step.effects.forEach(perform)
    }

    private func perform(_ effect: ConversationEffect) {
        switch effect {
        case .startListening:
            listenTask?.cancel()
            listenTask = Task { [weak self, listener] in
                do {
                    let heard = try await listener.listen()
                    guard !Task.isCancelled else { return }
                    self?.dispatch(.heard(heard))
                } catch is CancellationError {
                } catch {
                    guard !Task.isCancelled else { return }
                    self?.log("listening failed: \(error)")
                    self?.dispatch(.problem(Self.describe(error, or: "The microphone failed")))
                    self?.dispatch(.stop)
                }
            }

        case .stopListening:
            listenTask?.cancel()

        case .generate(let generation, let history, let avoid):
            writeTask?.cancel()
            writeTask = Task { [weak self, writer] in
                do {
                    for try await update in writer.replies(history: history, avoid: avoid) {
                        guard let self, !Task.isCancelled else { return }
                        if let stats = update.stats { self.lastStats = stats }
                        if update.done && update.replies.isEmpty {
                            self.dispatch(.generationFailed(generation: generation, message: "The model wrote no replies"))
                        } else {
                            self.dispatch(.replies(generation: generation, replies: update.replies, done: update.done))
                        }
                    }
                } catch is CancellationError {
                } catch {
                    guard !Task.isCancelled else { return }
                    self?.log("writing replies failed: \(error)")
                    self?.dispatch(.generationFailed(generation: generation, message: Self.describe(error, or: "The model failed")))
                }
            }

        case .cancelGeneration:
            writeTask?.cancel()

        case .speak(let text):
            speakTask?.cancel()
            speakTask = Task { [weak self, voice] in
                do {
                    try await voice.speak(text)
                } catch {
                    // Stopped on purpose: the state machine has already moved on.
                    if error is CancellationError || Task.isCancelled { return }
                    self?.log("speaking failed: \(error)")
                    self?.dispatch(.stop)
                    self?.dispatch(.problem(Self.describe(error, or: "The voice failed")))
                    return
                }
                guard !Task.isCancelled else { return }
                self?.dispatch(.speechFinished)
            }

        case .stopSpeaking:
            speakTask?.cancel()
        }
    }

    private static func describe(_ error: Error, or fallback: String) -> String {
        (error as? LocalizedError)?.errorDescription ?? fallback
    }
}
