import XCTest
@testable import QuickTalkCore

/// Ears that hand out queued utterances, and otherwise wait until cancelled.
@MainActor
final class FakeListener: Listener {
    var queued: [String] = []
    var listens = 0
    var failure: Error?

    func listen() async throws -> String {
        listens += 1
        if let failure { throw failure }
        if !queued.isEmpty { return queued.removeFirst() }
        while true {
            try await Task.sleep(nanoseconds: 1_000_000)
        }
    }
}

@MainActor
final class FakeVoice: VoiceOutput {
    var said: [String] = []
    var finishImmediately = true

    func speak(_ text: String) async throws {
        said.append(text)
        while !finishImmediately { try await Task.sleep(nanoseconds: 1_000_000) }
    }
}

final class FakeWriter: ReplySource, @unchecked Sendable {
    var answers: [[ReplyUpdate]] = []
    var requests: [(history: [Turn], avoid: [String])] = []

    func replies(history: [Turn], avoid: [String]) -> AsyncThrowingStream<ReplyUpdate, Error> {
        requests.append((history, avoid))
        // Like ReplyWriter, always ends with a `done` update, empty if nothing was scripted.
        let updates = answers.isEmpty ? [ReplyUpdate(replies: [], done: true)] : answers.removeFirst()
        return AsyncThrowingStream { continuation in
            for update in updates { continuation.yield(update) }
            continuation.finish()
        }
    }
}

@MainActor
final class FakeGlasses: GlassesOutput {
    var wanted = false
    var screens: [GlassesScreen] = []
    var ticks = 0
    func setWanted(_ wanted: Bool) { self.wanted = wanted }
    func show(_ screen: GlassesScreen) { screens.append(screen) }
    func tick() { ticks += 1 }
}

@MainActor
final class ConversationRunnerTests: XCTestCase {
    let four = [Reply("👍", "Yes."), Reply("🙅", "No."), Reply("❓", "Why?"), Reply("🤷", "Maybe.")]

    var listener: FakeListener!
    var voice: FakeVoice!
    var writer: FakeWriter!
    var glasses: FakeGlasses!
    var runner: ConversationRunner!

    override func setUp() async throws {
        listener = FakeListener()
        voice = FakeVoice()
        writer = FakeWriter()
        glasses = FakeGlasses()
        runner = ConversationRunner(listener: listener, writer: writer, voice: voice, glasses: glasses)
    }

    /// Lets the runner's tasks run until `condition` holds.
    func until(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        for _ in 0..<2000 where !condition() { try? await Task.sleep(nanoseconds: 1_000_000) }
        XCTAssertTrue(condition(), "timed out", file: file, line: line)
    }

    func testAWholeTurnRunsThroughTheRealPieces() async {
        listener.queued = ["Lunch?"]
        writer.answers = [[
            ReplyUpdate(replies: Array(four.prefix(2)), done: false),
            ReplyUpdate(replies: four, done: true, stats: GenerationStats(outputTokens: 40)),
        ]]
        runner.start()
        XCTAssertTrue(glasses.wanted)

        await until { runner.state.phase.choosing?.done == true }
        XCTAssertEqual(writer.requests.first?.history, [Turn(.partner, "Lunch?")])
        XCTAssertEqual(runner.lastStats?.outputTokens, 40)
        XCTAssertEqual(glasses.screens.last?.cue, .swipeThumb)

        runner.input(.highlight(.right))
        XCTAssertEqual(glasses.ticks, 1)
        runner.input(.highlight(.right)) // landing on the same reply again is not a move
        XCTAssertEqual(glasses.ticks, 1)

        runner.input(.confirm)
        await until { runner.state.phase == .listening && listener.listens == 2 }
        XCTAssertEqual(voice.said, ["No."])
        XCTAssertEqual(runner.state.history.last, Turn(.me, "No."))
    }

    func testStoppingReleasesTheGlassesAndSilencesTheVoice() async {
        voice.finishImmediately = false
        runner.start()
        runner.debugHeard("Coffee?")
        runner.input(.confirm) // nothing highlighted: asks for more, which come back empty
        await until { runner.state.phase.choosing?.isQuickPhrases == true }
        XCTAssertEqual(runner.state.problem, "The model wrote no replies")

        runner.input(.highlight(.up))
        runner.input(.confirm)
        await until { voice.said == ["Yes"] }
        runner.stop()
        XCTAssertFalse(glasses.wanted)
        XCTAssertEqual(runner.state.phase, .off)
        try? await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(runner.state.phase, .off) // the cancelled speech does not come back as "finished"
    }

    func testAMicrophoneFailureStopsTheConversationAndSaysWhy() async {
        struct Broken: LocalizedError { var errorDescription: String? { "No microphone access" } }
        listener.failure = Broken()
        runner.start()
        await until { runner.state.phase == .off }
        XCTAssertEqual(runner.state.problem, "No microphone access")
    }

    func testTheTickCanBeSwitchedOff() async {
        runner.tickEnabled = { false }
        writer.answers = [[ReplyUpdate(replies: four, done: true)]]
        runner.start()
        runner.debugHeard("Lunch?")
        await until { runner.state.phase.choosing?.done == true }
        runner.input(.turn(clockwise: true))
        XCTAssertEqual(runner.state.phase.choosing?.focus, .up)
        XCTAssertEqual(glasses.ticks, 0)
    }
}
