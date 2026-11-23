import XCTest
@testable import QuickTalkCore

/// Ported from the Android app's `ConversationTest.kt`, test for test.
final class ConversationTests: XCTestCase {

    let four = [
        Reply("👍", "Yes, I'd love to."),
        Reply("🙅", "No, not today."),
        Reply("❓", "Where would we go?"),
        Reply("🤷", "Maybe later."),
    ]

    /// Feeds `events` through the reducer, returning the final state and every effect in order.
    func run(_ events: ConversationEvent..., from: ConversationState = ConversationState()) -> (ConversationState, [ConversationEffect]) {
        var state = from
        var effects: [ConversationEffect] = []
        for event in events {
            let step = reduce(state, event)
            state = step.state
            effects += step.effects
        }
        return (state, effects)
    }

    func highlight(_ direction: Dpad) -> ConversationEvent { .input(.highlight(direction)) }
    func turn(_ clockwise: Bool) -> ConversationEvent { .input(.turn(clockwise: clockwise)) }
    let tap = ConversationEvent.input(.confirm)
    let back = ConversationEvent.input(.back)

    func choosing() -> ConversationState {
        run(.start, .heard("Do you want to get lunch?"), .replies(generation: 1, replies: four, done: true)).0
    }

    func focusOf(_ state: ConversationState) -> Dpad? { state.phase.choosing?.focus }

    func choices(_ state: ConversationState) -> GlassesScreen.Choices? {
        if case .choices(let choices) = screenFor(state) { return choices }
        return nil
    }

    func testAFullTurnListensOffersRepliesSpeaksTheTappedOneAndListensAgain() {
        let (state, effects) = run(
            .start,
            .heard("Do you want to get lunch?"),
            .replies(generation: 1, replies: Array(four.prefix(2)), done: false),
            .replies(generation: 1, replies: four, done: true),
            highlight(.down),
            tap,
            .speechFinished
        )
        XCTAssertEqual(state.phase, .listening)
        XCTAssertEqual(state.history, [Turn(.partner, "Do you want to get lunch?"), Turn(.me, "Where would we go?")])
        XCTAssertEqual(effects, [
            .startListening,
            .generate(generation: 1, history: [Turn(.partner, "Do you want to get lunch?")], avoid: []),
            .cancelGeneration,
            .speak("Where would we go?"),
            .startListening,
        ])
    }

    func testASwipeOnlyHighlightsNothingIsSaidUntilTheTap() {
        let (state, effects) = run(highlight(.right), from: choosing())
        XCTAssertEqual(focusOf(state), .right)
        XCTAssertTrue(effects.isEmpty)
        XCTAssertEqual(focusOf(run(highlight(.left), from: state).0), .left)
    }

    func testEachDirectionHoldsTheReplyInItsSlot() {
        let expected: [(Dpad, Reply)] = [(.up, four[0]), (.right, four[1]), (.down, four[2]), (.left, four[3])]
        for (direction, reply) in expected {
            XCTAssertEqual(run(highlight(direction), tap, from: choosing()).0.phase, .speaking(reply.text))
        }
    }

    func testTheEmojiIsShownOnTheGlassesButNeverSpokenOrSentBackToTheModel() {
        let (state, effects) = run(highlight(.up), tap, from: choosing())
        XCTAssertEqual(effects.last, .speak("Yes, I'd love to."))
        XCTAssertEqual(state.history.last, Turn(.me, "Yes, I'd love to."))
        XCTAssertEqual(choices(choosing())?.replies[0], four[0])
    }

    func testTurningTheDialMovesTheHighlightRoundTheRepliesBothWays() {
        let start = choosing()
        var state = start
        let clockwise = (1...5).map { _ -> Dpad? in state = run(turn(true), from: state).0; return focusOf(state) }
        XCTAssertEqual(clockwise, [.up, .right, .down, .left, .up])

        state = start
        let anticlockwise = (1...3).map { _ -> Dpad? in state = run(turn(false), from: state).0; return focusOf(state) }
        XCTAssertEqual(anticlockwise, [.left, .down, .right])

        XCTAssertEqual(run(tap, from: state).0.phase, .speaking(four[1].text))
    }

    func testTheDialSkipsSlotsWhoseReplyHasNotBeenWrittenYet() {
        var state = run(.start, .heard("Coffee?"), .replies(generation: 1, replies: Array(four.prefix(2)), done: false)).0
        let seen = (1...4).map { _ -> Dpad? in state = run(turn(true), from: state).0; return focusOf(state) }
        XCTAssertEqual(seen, [.up, .right, .up, .right])

        let empty = run(.start, .heard("Coffee?")).0
        XCTAssertNil(focusOf(run(turn(true), from: empty).0))
    }

    func testAReplyCanBeHighlightedAndSaidWhileTheOthersAreStillBeingWritten() {
        let (state, effects) = run(
            .start,
            .heard("Coffee?"),
            .replies(generation: 1, replies: Array(four.prefix(1)), done: false),
            highlight(.up),
            .replies(generation: 1, replies: Array(four.prefix(3)), done: false),
            tap
        )
        XCTAssertEqual(state.phase, .speaking(four[0].text))
        XCTAssertTrue(effects.contains(.cancelGeneration))
    }

    func testSwipingTowardsASlotThatHasNoReplyYetDoesNothing() {
        let before = run(.start, .heard("Coffee?"), .replies(generation: 1, replies: Array(four.prefix(1)), done: false)).0
        let (after, effects) = run(highlight(.left), from: before)
        XCTAssertEqual(before, after)
        XCTAssertTrue(effects.isEmpty)
    }

    func testATapWithNothingHighlightedAsksForNewRepliesAndRemembersTheOldOnes() {
        let (state, effects) = run(tap, from: choosing())
        let phase = state.phase.choosing!
        XCTAssertTrue(phase.replies.isEmpty)
        XCTAssertEqual(phase.round, 1)
        XCTAssertEqual(effects.last, .generate(generation: 2, history: state.history, avoid: four.map(\.text)))

        let second = ["Sure.", "I can't.", "What time?", "Let me think."].map { Reply("🙂", $0) }
        let (again, againEffects) = run(.replies(generation: 2, replies: second, done: true), tap, from: state)
        guard case .generate(_, _, let avoid) = againEffects.last else { return XCTFail("expected generate") }
        XCTAssertEqual(avoid, (four + second).map(\.text))
        XCTAssertNil(focusOf(again))
    }

    func testRepliesFromASupersededRequestAreIgnored() {
        let afterMore = run(tap, from: choosing()).0
        let state = run(.replies(generation: 1, replies: four, done: true), from: afterMore).0
        XCTAssertTrue(state.phase.choosing!.replies.isEmpty)
    }

    func testBackFirstClearsTheHighlightThenDropsTheRepliesAndListensAgain() {
        let highlighted = run(highlight(.up), from: choosing()).0
        let (cleared, noEffects) = run(back, from: highlighted)
        XCTAssertNil(focusOf(cleared))
        XCTAssertTrue(noEffects.isEmpty)

        let (state, effects) = run(back, from: cleared)
        XCTAssertEqual(state.phase, .listening)
        XCTAssertEqual(effects, [.cancelGeneration, .startListening])
        XCTAssertEqual(state.history.count, 1)
    }

    func testATapWhileListeningOffersQuickPhrasesAndASecondTapGoesBack() {
        let (quick, effects) = run(.start, tap)
        let phase = quick.phase.choosing!
        XCTAssertTrue(phase.isQuickPhrases)
        XCTAssertEqual(phase.replies, quickPhrases)
        XCTAssertEqual(effects.last, .stopListening)

        XCTAssertEqual(run(highlight(.up), tap, from: quick).0.phase, .speaking("Yes"))

        let (listening, backEffects) = run(tap, from: quick)
        XCTAssertEqual(listening.phase, .listening)
        XCTAssertEqual(backEffects, [.startListening])
    }

    func testSwipesAndTurnsWhileListeningDoNothing() {
        let listening = run(.start).0
        XCTAssertEqual(run(highlight(.up), turn(true), from: listening).0, listening)
    }

    func testSpeechHeardWhileRepliesAreShowingDoesNotReplaceThem() {
        let before = choosing()
        let (after, effects) = run(.heard("Hello? Are you there?"), from: before)
        XCTAssertEqual(before, after)
        XCTAssertTrue(effects.isEmpty)
    }

    func testIfTheModelFailsTheWearerStillGetsQuickPhrases() {
        let state = run(.start, .heard("Hi"), .generationFailed(generation: 1, message: "out of memory")).0
        XCTAssertEqual(state.phase.choosing?.replies, quickPhrases)
        XCTAssertEqual(state.problem, "out of memory")
    }

    func testBackWhileSpeakingStopsTheVoice() {
        let speaking = run(highlight(.up), tap, from: choosing()).0
        let (state, effects) = run(back, from: speaking)
        XCTAssertEqual(state.phase, .listening)
        XCTAssertEqual(effects, [.stopSpeaking, .startListening])
    }

    func testStopShutsEverythingDownFromAnyPhase() {
        let (state, effects) = run(.stop, from: choosing())
        XCTAssertEqual(state.phase, .off)
        XCTAssertEqual(effects, [.stopListening, .cancelGeneration, .stopSpeaking])
    }

    func testBlankSpeechIsIgnoredAndHistoryIsCapped() {
        XCTAssertEqual(run(.start, .heard("   ")).0.phase, .listening)

        var state = run(.start).0
        for i in 0..<historyTurns {
            state = run(
                .heard("question \(i)"),
                .replies(generation: state.generation + 1, replies: four, done: true),
                highlight(.up),
                tap,
                .speechFinished,
                from: state
            ).0
        }
        XCTAssertEqual(state.history.count, historyTurns)
        XCTAssertEqual(state.history.last, Turn(.me, four[0].text))
    }

    func testTheGlassesScreenFollowsThePhaseAndCarriesTheHighlight() {
        XCTAssertEqual(screenFor(run(.start).0), .status(.init("Listening", offersQuickPhrases: true, activity: .listening)))

        let partial = run(.start, .heard("Lunch?"), .replies(generation: 1, replies: Array(four.prefix(2)), done: false)).0
        XCTAssertEqual(screenFor(partial), .choices(.init(heard: "Lunch?", replies: [four[0], four[1], nil, nil], done: false, quick: false)))

        let highlighted = run(highlight(.right), from: choosing()).0
        XCTAssertEqual(choices(highlighted)?.focus, .right)

        let speaking = run(tap, from: highlighted).0
        XCTAssertEqual(screenFor(speaking), .status(.init("Speaking", detail: four[1].text, activity: .speaking)))
    }

    func testALongUtteranceIsPreviewedByItsEnding() {
        let long = "So I was thinking about the weekend and all the things we could do. " +
            "Would you rather go to the beach or stay home and watch a film?"
        let heard = choices(run(.start, .heard(long)).0)!.heard!
        XCTAssertTrue(heard.hasPrefix("…"))
        XCTAssertTrue(heard.hasSuffix("watch a film?"))
        XCTAssertLessThanOrEqual(heard.count, 70)
        XCTAssertNil(choices(run(.start, tap).0)!.heard)
    }
}
