/// What the glasses should be showing, derived from the conversation state.
public enum GlassesScreen: Equatable, Sendable {
    /// A status line. `offersQuickPhrases` is true while a pinch would open the quick phrases.
    case status(Status)
    /// Four reply slots, one per position in `Dpad` order.
    case choices(Choices)

    public struct Status: Equatable, Sendable {
        public var title: String
        public var detail: String?
        public var offersQuickPhrases: Bool
        public var activity: GlassesCue

        public init(_ title: String, detail: String? = nil, offersQuickPhrases: Bool = false, activity: GlassesCue = .quiet) {
            self.title = title
            self.detail = detail
            self.offersQuickPhrases = offersQuickPhrases
            self.activity = activity
        }
    }

    /// A nil slot is still being written. `heard` is what the partner said, nil for the quick
    /// phrases (`quick`). `done` is false while the model is still writing. `focus` is the
    /// highlighted slot, if any.
    public struct Choices: Equatable, Sendable {
        public var heard: String?
        public var replies: [Reply?]
        public var done: Bool
        public var quick: Bool
        public var focus: Dpad?

        public init(heard: String?, replies: [Reply?], done: Bool, quick: Bool, focus: Dpad? = nil) {
            self.heard = heard
            self.replies = replies
            self.done = done
            self.quick = quick
            self.focus = focus
        }
    }

    /// The first completed reply is enough to start choosing; the other slots can still be empty.
    public var cue: GlassesCue {
        switch self {
        case .status(let status):
            return status.activity
        case .choices(let choices):
            if choices.focus != nil { return .pinch }
            if choices.replies.contains(where: { $0 != nil }) { return .swipeThumb }
            return .generating
        }
    }
}

public enum GlassesCue: Sendable { case quiet, listening, hearing, generating, swipeThumb, pinch, speaking }

/// Longest stretch of the partner's words echoed above the replies.
let heardPreviewChars = 70

public func screenFor(_ state: ConversationState, hearingSpeech: Bool = false) -> GlassesScreen {
    switch state.phase {
    case .off:
        return .status(.init("Paused"))
    case .listening:
        return .status(.init("Listening", offersQuickPhrases: true, activity: hearingSpeech ? .hearing : .listening))
    case .choosing(let phase):
        return .choices(.init(
            heard: phase.heard.map(preview),
            replies: Dpad.allCases.map(phase.reply),
            done: phase.done,
            quick: phase.isQuickPhrases,
            focus: phase.focus
        ))
    case .speaking(let text):
        return .status(.init("Speaking", detail: text, activity: .speaking))
    }
}

/// The end of a long utterance matters most: it is usually the question.
private func preview(_ heard: String) -> String {
    if heard.count <= heardPreviewChars { return heard }
    let tail = String(heard.suffix(heardPreviewChars - 1))
    return "…" + String(tail.drop(while: { $0.isWhitespace }))
}

/// The partner only needs to know whether to speak, wait, or resume the conversation.
public enum PartnerTurn: Sendable { case yourTurn, wearersTurn, reconnecting, paused }

public func partnerTurn(_ phase: Phase, glassesReady: Bool) -> PartnerTurn {
    if phase == .off { return .paused }
    if !glassesReady { return .reconnecting }
    if phase == .listening { return .yourTurn }
    return .wearersTurn
}
