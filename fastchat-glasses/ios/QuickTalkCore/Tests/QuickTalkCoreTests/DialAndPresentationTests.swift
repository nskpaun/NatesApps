import XCTest
@testable import QuickTalkCore

/// Ported from the Android app's `DialTest.kt`.
final class DialTests: XCTestCase {

    /// Feeds one drag made of these changes in x and returns the steps each one produced.
    func drag(_ dial: inout Dial, _ moves: Float...) -> [Int] {
        dial.start()
        return moves.map { dial.move($0) }
    }

    func testEveryFullStepOfTravelToTheRightTurnsOneStepClockwise() {
        var dial = Dial(stepSize: 0.08)
        XCTAssertEqual(drag(&dial, 0.03, 0.03, 0.03, 0.06, 0.10), [0, 0, 1, 0, 2])
        XCTAssertTrue(dial.turned)
    }

    func testOneFullWristTurnAsTheBandReportsItCanReachAllFourReplies() {
        var dial = Dial()
        dial.start()
        let steps = (0..<20).map { _ in dial.move(0.01) }.reduce(0, +)
        XCTAssertEqual(steps, 4)
    }

    func testTravelToTheLeftTurnsTheOtherWay() {
        var dial = Dial(stepSize: 0.08)
        XCTAssertEqual(drag(&dial, -0.09, -0.08), [-1, -1])
    }

    func testTheWristHasToComeAWholeStepBackBeforeTheHighlightMovesBack() {
        var dial = Dial(stepSize: 0.08)
        XCTAssertEqual(drag(&dial, 0.09, -0.02, 0.02, -0.03, -0.07), [1, 0, 0, 0, -1])
    }

    func testASmallWobbleTurnsNothing() {
        var dial = Dial(stepSize: 0.08)
        XCTAssertEqual(drag(&dial, 0.02, -0.015, 0.01), [0, 0, 0])
        XCTAssertFalse(dial.turned)
    }

    func testEachNewPinchStartsFromNothing() {
        var dial = Dial(stepSize: 0.08)
        _ = drag(&dial, 0.06)
        XCTAssertEqual(drag(&dial, 0.06), [0])
        XCTAssertFalse(dial.turned)
    }
}

/// Ported from the Android app's `PresentationTest.kt`.
final class PresentationTests: XCTestCase {
    let replies = [
        Reply("🙂", "Yes, please."), Reply("☕", "Coffee instead."),
        Reply("🤫", "Somewhere quiet."), Reply("✋", "Not now."),
    ]

    func lunch() -> ConversationState {
        reduce(reduce(ConversationState(), .start).state, .heard("Lunch?")).state
    }

    func testTheFirstReplyChangesTheCueFromGeneratingToThumbSwipeBeforeGenerationIsDone() {
        var state = lunch()
        XCTAssertEqual(screenFor(state).cue, .generating)
        for count in 1...4 {
            state = reduce(state, .replies(generation: state.generation, replies: Array(replies.prefix(count)), done: count == 4)).state
            let screen = screenFor(state)
            XCTAssertEqual(screen.cue, .swipeThumb)
            guard case .choices(let choices) = screen else { return XCTFail("expected choices") }
            for position in Dpad.allCases {
                let expected: Reply? = position.rawValue < count ? replies[position.rawValue] : nil
                XCTAssertEqual(choices.replies[position.rawValue], expected)
            }
        }
    }

    func testPinchCueAndExactSelectedWordsSurviveLaterRepliesArriving() {
        var state = lunch()
        state = reduce(state, .replies(generation: state.generation, replies: Array(replies.prefix(1)), done: false)).state
        state = reduce(state, .input(.highlight(.up))).state
        XCTAssertEqual(screenFor(state).cue, .pinch)
        state = reduce(state, .replies(generation: state.generation, replies: Array(replies.prefix(3)), done: false)).state
        XCTAssertEqual(screenFor(state).cue, .pinch)
        XCTAssertEqual(state.phase.choosing?.focus, .up)
        state = reduce(state, .input(.confirm)).state
        XCTAssertEqual(state.phase, .speaking(replies[0].text))
        XCTAssertEqual(screenFor(state).cue, .speaking)
    }

    func testThePartnerSeesOneStableWearerTurnThroughoutGeneratingChoosingAndSpeaking() {
        XCTAssertEqual(partnerTurn(.listening, glassesReady: true), .yourTurn)
        let phases: [Phase] = [
            .choosing(Choosing(heard: "Lunch?", replies: [], done: false)),
            .choosing(Choosing(heard: "Lunch?", replies: Array(replies.prefix(1)), done: false)),
            .choosing(Choosing(heard: "Lunch?", replies: replies, done: true, focus: .right)),
            .choosing(Choosing(heard: nil, replies: quickPhrases, done: true)),
            .speaking("Coffee instead."),
        ]
        for phase in phases {
            XCTAssertEqual(partnerTurn(phase, glassesReady: true), .wearersTurn)
            XCTAssertEqual(partnerTurn(phase, glassesReady: false), .reconnecting)
        }
        XCTAssertEqual(partnerTurn(.listening, glassesReady: false), .reconnecting)
        XCTAssertEqual(partnerTurn(.off, glassesReady: false), .paused)
    }

    func testHearingActivityAndReturningToListeningClearTheSelectionCue() {
        let listening = ConversationState(phase: .listening)
        XCTAssertEqual(screenFor(listening).cue, .listening)
        XCTAssertEqual(screenFor(listening, hearingSpeech: true).cue, .hearing)
        XCTAssertEqual(screenFor(ConversationState()).cue, .quiet)
        let cleared = reduce(ConversationState(phase: .choosing(Choosing(heard: "Lunch?", replies: replies, done: true, focus: .up))), .input(.back)).state
        XCTAssertNil(cleared.phase.choosing?.focus)
        XCTAssertEqual(screenFor(cleared).cue, .swipeThumb)
    }
}
