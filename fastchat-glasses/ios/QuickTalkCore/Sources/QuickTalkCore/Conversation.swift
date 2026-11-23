/// The conversation as a pure state machine: `reduce` takes the current `ConversationState` and a
/// `ConversationEvent` and returns the next state plus the `ConversationEffect`s to run. Nothing
/// here touches audio, the model or the glasses, so the whole flow is unit-tested.
///
/// One turn: listening → (partner speaks) → choosing (replies arrive one by one) → (highlight a
/// reply, then pinch) → speaking → listening.
///
/// Ported from the Android app's `core/Conversation.kt`; the two must behave the same.

/// The four positions replies are shown in, in clockwise order starting at the top. Replies are
/// assigned to them in this order.
public enum Dpad: Int, CaseIterable, Sendable {
    case up, right, down, left

    /// The next position going round: clockwise, or the other way.
    public func turned(clockwise: Bool) -> Dpad {
        let count = Dpad.allCases.count
        return Dpad(rawValue: (rawValue + (clockwise ? 1 : count - 1)) % count)!
    }
}

/// Nothing is said until a highlighted reply is confirmed with a thumb/index pinch (or temple tap).
public enum GlassesInput: Equatable, Sendable {
    /// A swipe: highlight the reply in that direction.
    case highlight(Dpad)
    /// One step of the pinch-and-turn dial: move the highlight round to the next reply.
    case turn(clockwise: Bool)
    /// A thumb/index pinch: say the highlighted reply. With nothing highlighted it asks for other
    /// replies while choosing, and opens the quick phrases while listening.
    case confirm
    /// Back: clear the highlight; with none, drop the replies (or stop speaking) and listen again.
    case back
}

public enum Speaker: Sendable { case partner, me }

/// One thing the wearer could say. `emoji` is shown beside it on the glasses so the choice can be
/// read at a glance; only `text` is spoken. `emoji` may be empty.
public struct Reply: Equatable, Hashable, Sendable {
    public var emoji: String
    public var text: String
    public init(_ emoji: String, _ text: String) {
        self.emoji = emoji
        self.text = text
    }
}

public struct Turn: Equatable, Sendable {
    public var speaker: Speaker
    public var text: String
    public init(_ speaker: Speaker, _ text: String) {
        self.speaker = speaker
        self.text = text
    }
}

/// Replies on the glasses. `heard` is what the partner said, or nil for quick phrases. `replies`
/// fills up while the model writes; `done` turns true when it has finished. `focus` is the
/// highlighted reply, the one a pinch would say; nil when none is.
public struct Choosing: Equatable, Sendable {
    public var heard: String?
    public var replies: [Reply]
    public var done: Bool
    public var round: Int
    public var focus: Dpad?

    public init(heard: String?, replies: [Reply], done: Bool, round: Int = 0, focus: Dpad? = nil) {
        self.heard = heard
        self.replies = replies
        self.done = done
        self.round = round
        self.focus = focus
    }

    public var isQuickPhrases: Bool { heard == nil }

    public func reply(_ position: Dpad) -> Reply? {
        replies.indices.contains(position.rawValue) ? replies[position.rawValue] : nil
    }
}

public enum Phase: Equatable, Sendable {
    /// Conversation not running.
    case off
    /// Microphone open, waiting for the partner to say something.
    case listening
    case choosing(Choosing)
    /// The picked reply is being spoken from the phone.
    case speaking(String)

    public var choosing: Choosing? {
        if case .choosing(let choosing) = self { return choosing }
        return nil
    }
}

public struct ConversationState: Equatable, Sendable {
    public var phase: Phase
    public var history: [Turn]
    /// Id of the current reply request; updates carrying an older id are dropped.
    public var generation: Int
    /// Replies already offered for the current partner turn, so "more" does not repeat them.
    public var offered: [String]
    /// Last problem worth showing on the phone, cleared when the next turn starts.
    public var problem: String?

    public init(
        phase: Phase = .off,
        history: [Turn] = [],
        generation: Int = 0,
        offered: [String] = [],
        problem: String? = nil
    ) {
        self.phase = phase
        self.history = history
        self.generation = generation
        self.offered = offered
        self.problem = problem
    }
}

public enum ConversationEvent: Equatable, Sendable {
    case start
    case stop
    case heard(String)
    case replies(generation: Int, replies: [Reply], done: Bool)
    case generationFailed(generation: Int, message: String)
    case input(GlassesInput)
    case speechFinished
    case problem(String)
}

public enum ConversationEffect: Equatable, Sendable {
    case startListening
    case stopListening
    case generate(generation: Int, history: [Turn], avoid: [String])
    case cancelGeneration
    case speak(String)
    case stopSpeaking
}

public struct Step: Equatable, Sendable {
    public var state: ConversationState
    public var effects: [ConversationEffect]
    public init(_ state: ConversationState, _ effects: [ConversationEffect] = []) {
        self.state = state
        self.effects = effects
    }
}

/// How many turns of the conversation the model is shown.
public let historyTurns = 8

/// Fixed replies offered on a pinch while listening; no model needed, so they are instant.
public let quickPhrases: [Reply] = [
    Reply("✅", "Yes"),
    Reply("❌", "No"),
    Reply("🙏", "Thank you"),
    Reply("⏳", "Please give me a moment"),
]

private func appending(_ history: [Turn], _ turn: Turn) -> [Turn] {
    Array((history + [turn]).suffix(historyTurns))
}

public func reduce(_ state: ConversationState, _ event: ConversationEvent) -> Step {
    let phase = state.phase
    switch event {
    case .start:
        guard phase == .off else { return Step(state) }
        var next = state
        next.problem = nil
        return listen(next)

    case .stop:
        var next = state
        next.phase = .off
        next.offered = []
        return Step(next, [.stopListening, .cancelGeneration, .stopSpeaking])

    case .heard(let raw):
        let text = raw.trimmed
        guard phase == .listening, !text.isEmpty else { return Step(state) }
        let history = appending(state.history, Turn(.partner, text))
        let generation = state.generation + 1
        var next = state
        next.phase = .choosing(Choosing(heard: text, replies: [], done: false))
        next.history = history
        next.generation = generation
        next.offered = []
        next.problem = nil
        return Step(next, [.generate(generation: generation, history: history, avoid: [])])

    case .replies(let generation, let replies, let done):
        guard var choosing = phase.choosing, !choosing.isQuickPhrases, generation == state.generation else {
            return Step(state)
        }
        choosing.replies = Array(replies.prefix(Dpad.allCases.count))
        choosing.done = done
        var next = state
        next.phase = .choosing(choosing)
        return Step(next)

    case .generationFailed(let generation, let message):
        guard phase.choosing != nil, generation == state.generation else { return Step(state) }
        // The wearer must never be left with nothing to say: fall back to the fixed phrases.
        var next = state
        next.phase = .choosing(Choosing(heard: nil, replies: quickPhrases, done: true))
        next.problem = message
        return Step(next)

    case .input(let input):
        return onInput(state, input)

    case .speechFinished:
        if case .speaking = phase { return listen(state) }
        return Step(state)

    case .problem(let message):
        var next = state
        next.problem = message
        return Step(next)
    }
}

private func listen(_ state: ConversationState) -> Step {
    var next = state
    next.phase = .listening
    next.offered = []
    return Step(next, [.startListening])
}

private func onInput(_ state: ConversationState, _ input: GlassesInput) -> Step {
    switch state.phase {
    case .off:
        return Step(state)

    case .listening:
        guard input == .confirm else { return Step(state) }
        var next = state
        next.phase = .choosing(Choosing(heard: nil, replies: quickPhrases, done: true))
        return Step(next, [.stopListening])

    case .choosing(var phase):
        switch input {
        // A reply can be highlighted as soon as it is on screen, without waiting for the rest.
        case .highlight(let direction):
            guard phase.reply(direction) != nil else { return Step(state) }
            phase.focus = direction
            var next = state
            next.phase = .choosing(phase)
            return Step(next)

        case .turn(let clockwise):
            // Round to the next reply that exists; the first turn starts at the top (or, going
            // the other way, at the left).
            var target = phase.focus?.turned(clockwise: clockwise) ?? (clockwise ? .up : .left)
            for _ in Dpad.allCases where phase.reply(target) == nil {
                target = target.turned(clockwise: clockwise)
            }
            guard phase.reply(target) != nil else { return Step(state) }
            phase.focus = target
            var next = state
            next.phase = .choosing(phase)
            return Step(next)

        case .confirm:
            if let focus = phase.focus, let text = phase.reply(focus)?.text {
                var next = state
                next.phase = .speaking(text)
                next.history = appending(state.history, Turn(.me, text))
                next.offered = []
                return Step(next, [.cancelGeneration, .speak(text)])
            }
            // Nothing highlighted: a pinch asks for something else.
            if phase.isQuickPhrases { return listen(state) }
            var offered = state.offered
            for text in phase.replies.map(\.text) where !offered.contains(text) {
                offered.append(text)
            }
            let generation = state.generation + 1
            phase.replies = []
            phase.done = false
            phase.round += 1
            var next = state
            next.phase = .choosing(phase)
            next.generation = generation
            next.offered = offered
            return Step(next, [.cancelGeneration, .generate(generation: generation, history: state.history, avoid: offered)])

        case .back:
            if phase.focus != nil {
                phase.focus = nil
                var next = state
                next.phase = .choosing(phase)
                return Step(next)
            }
            var step = listen(state)
            step.effects.insert(.cancelGeneration, at: 0)
            return step
        }

    case .speaking:
        guard input == .back else { return Step(state) }
        var step = listen(state)
        step.effects.insert(.stopSpeaking, at: 0)
        return step
    }
}
