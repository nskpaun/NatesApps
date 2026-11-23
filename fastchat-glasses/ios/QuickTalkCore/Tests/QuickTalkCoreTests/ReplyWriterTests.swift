import XCTest
@testable import QuickTalkCore

/// A model that writes scripted answers a few characters at a time, and records what it was asked.
final class ScriptedModel: TextModel, @unchecked Sendable {
    struct Call { let prefix: String; let suffix: String; let grammar: String; let temperature: Float }

    private let lock = NSLock()
    private var answers: [String]
    private(set) var calls: [Call] = []
    private(set) var primed: [String] = []
    private(set) var cancelCount = 0

    init(_ answers: [String]) { self.answers = answers }

    func prime(_ prefix: String) throws {
        lock.lock(); primed.append(prefix); lock.unlock()
    }

    func generate(prefix: String, suffix: String, grammar: String, maxTokens: Int, temperature: Float,
                  onText: (String) -> Bool) throws -> GenerationStats {
        lock.lock()
        calls.append(Call(prefix: prefix, suffix: suffix, grammar: grammar, temperature: temperature))
        let answer = answers.isEmpty ? "" : answers.removeFirst()
        lock.unlock()
        var index = answer.startIndex
        while index < answer.endIndex {
            let end = answer.index(index, offsetBy: 3, limitedBy: answer.endIndex) ?? answer.endIndex
            if !onText(String(answer[index..<end])) { break }
            index = end
        }
        return GenerationStats(outputTokens: 10, outputMs: 100)
    }

    func cancel() {
        lock.lock(); cancelCount += 1; lock.unlock()
    }
}

final class ReplyWriterTests: XCTestCase {
    let hungry = "(They are asking if I am hungry. I can say yes or no.)\n" +
        "1. 😋 Yes, I'm starving.\n2. 🙅 No, I just ate.\n3. ❓ What is there?\n4. ☕ Just a drink."

    func collect(_ stream: AsyncThrowingStream<ReplyUpdate, Error>) async throws -> [ReplyUpdate] {
        var updates: [ReplyUpdate] = []
        for try await update in stream { updates.append(update) }
        return updates
    }

    func testRepliesStreamOutOneAtATimeThenFinish() async throws {
        let model = ScriptedModel([hungry])
        let writer = ReplyWriter(model: model)
        let updates = try await collect(writer.replies(persona: Persona(name: "Sam"), history: [Turn(.partner, "Hungry?")], avoid: []))

        // The last line has no newline after it, so it arrives with the final update.
        XCTAssertEqual(updates.map(\.replies.count), [1, 2, 3, 4])
        XCTAssertEqual(updates.map(\.done), [false, false, false, true])
        XCTAssertEqual(updates.last?.replies.first, Reply("😋", "Yes, I'm starving."))
        XCTAssertEqual(updates.last?.stats?.outputTokens, 10)
        // No facts to consult, so the only call is the reply prompt, at the tuned temperature.
        XCTAssertEqual(model.calls.count, 1)
        XCTAssertEqual(model.calls[0].grammar, ReplyPrompt.grammar)
        XCTAssertEqual(model.calls[0].temperature, ReplyWriter.temperature)
    }

    func testRepeatsAndRefusedRepliesAreDroppedAndTheModelIsAskedAgainMoreLoosely() async throws {
        let first = "(They x x x x. I can x x x x.)\n1. 😋 Yes, I'm starving.\n2. 😋 yes im starving\n3. 🙅 No, I just ate.\n4. ❓ What is there?"
        let second = "(They x x x x. I can x x x x.)\n1. 🍕 Pizza, please.\n2. ☕ Just a drink.\n3. 🙂 Maybe.\n4. 🙃 Later."
        let model = ScriptedModel([first, second])
        let writer = ReplyWriter(model: model)
        let updates = try await collect(writer.replies(persona: Persona(), history: [Turn(.partner, "Hungry?")], avoid: ["No, I just ate."]))

        XCTAssertEqual(updates.last?.replies.map(\.text), ["Yes, I'm starving.", "What is there?", "Pizza, please.", "Just a drink."])
        XCTAssertEqual(model.calls.map(\.temperature), [1.0, 1.0])
    }

    func testFactsAreLookedUpOnlyWhenTheDecisionSaysSo() async throws {
        let persona = Persona(name: "Sam", about: "I have a dog, Biscuit.")
        let model = ScriptedModel(["yes", hungry])
        let writer = ReplyWriter(model: model)
        _ = try await collect(writer.replies(persona: persona, history: [Turn(.partner, "Any pets?")], avoid: []))
        XCTAssertEqual(model.calls[0].grammar, PersonaCheck.grammar)
        XCTAssertTrue(model.calls[1].suffix.contains("Facts about you, in case they help you answer: I have a dog, Biscuit."))

        let noModel = ScriptedModel(["no", hungry])
        _ = try await collect(ReplyWriter(model: noModel).replies(persona: persona, history: [Turn(.partner, "Hi!")], avoid: []))
        XCTAssertFalse(noModel.calls[1].suffix.contains("Biscuit"))
    }

    func testPrimingEvaluatesBothFixedPromptsOnlyWhenThereAreFacts() async throws {
        let model = ScriptedModel([])
        try await ReplyWriter(model: model).prime(Persona(name: "Sam"))
        XCTAssertEqual(model.primed, [ReplyPrompt.systemBlock(Persona(name: "Sam"))])

        let withFacts = ScriptedModel([])
        let persona = Persona(name: "Sam", about: "I'm 34.")
        try await ReplyWriter(model: withFacts).prime(persona)
        XCTAssertEqual(withFacts.primed, [PersonaCheck.systemBlock(persona), ReplyPrompt.systemBlock(persona)])
    }

    func testStoppingEarlyCancelsTheModel() async throws {
        let model = ScriptedModel([hungry])
        let writer = ReplyWriter(model: model)
        let task = Task {
            for try await update in writer.replies(persona: Persona(), history: [Turn(.partner, "Hungry?")], avoid: []) {
                if !update.replies.isEmpty { break }
            }
        }
        try await task.value
        XCTAssertEqual(model.cancelCount, 1)
    }
}
