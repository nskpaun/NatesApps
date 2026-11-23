import MWDATCore
import QuickTalkCore
import XCTest
@testable import QuickTalk

final class OfflineTurnTests: XCTestCase {
    @MainActor
    func testOfflineConversationOnPhone() async throws {
        let store = ModelStore()
        guard store.presentBytes() == ModelStore.totalBytes else {
            throw XCTSkip("Install the QuickTalk models in the app before running this test.")
        }

        let models = try await Task.detached { try SpeechModels(store: store) }.value
        let partner = try await models.synthesize("Would you like a cup of coffee?", voice: 0, speed: 1)
        let samples = resample(partner)
        let microphone = Array(repeating: Float(0), count: 4_096) + samples + Array(repeating: 0, count: 20_480)
        var heard: String?
        for start in stride(from: 0, to: microphone.count, by: 512) {
            let next = Array(microphone[start..<min(start + 512, microphone.count)])
            let result = await models.accept(next)
            if let text = result.text {
                heard = text
                break
            }
        }
        let transcript = try XCTUnwrap(heard, "Silero and Parakeet should recognize the sample utterance")
        XCTAssertTrue(transcript.localizedCaseInsensitiveContains("coffee"), "Unexpected transcript: \(transcript)")

        let engine = try await LlamaEngine.load(path: store.path("llm/LFM3-1.7B-QAD-Q4_0.gguf"))
        let writer = ReplyWriter(model: engine)
        try await writer.prime(.init())
        var state = reduce(.init(), .start).state
        state = reduce(state, .heard(transcript)).state
        let generation = state.generation
        XCTAssertNotNil(state.phase.choosing)
        for try await update in writer.replies(persona: .init(), history: state.history, avoid: []) {
            state = reduce(state, .replies(generation: generation, replies: update.replies, done: update.done)).state
        }
        let reply = try XCTUnwrap(state.phase.choosing?.reply(.up))
        let frame = GlassesRenderer.render(screenFor(state), frame: 0)
        XCTAssertEqual(frame.size.width, 600)
        XCTAssertEqual(frame.size.height, 400)

        state = reduce(state, .input(.highlight(.up))).state
        state = reduce(state, .input(.confirm)).state
        XCTAssertEqual(state.phase, .speaking(reply.text))
        let spoken = try await models.synthesize(reply.text, voice: 0, speed: 1)
        XCTAssertGreaterThan(spoken.samples.count, Int(spoken.rate) / 10)
        XCTAssertEqual(reduce(state, .speechFinished).state.phase, .listening)
    }

    @MainActor
    func testMetaDisplaySessionAndNeuralBandEvents() async throws {
        let glasses = GlassesLink(wearables: Wearables.shared)
        await glasses.setMockEnabled(true)
        addTeardownBlock {
            await glasses.setMockEnabled(false)
        }
        let paired = try await wait { glasses.registered && glasses.available }
        XCTAssertTrue(paired, glasses.issue ?? "The Meta display mock should connect")
        guard paired else { return }

        var received: [GlassesInput] = []
        glasses.onInput = { received.append($0) }
        glasses.setWanted(true)
        glasses.show(.choices(.init(heard: "Coffee?", replies: [.init("☕", "Yes, please."), nil, nil, nil],
                                    done: true, quick: false)))
        let active = try await wait { glasses.ready && glasses.inputsReady }
        XCTAssertTrue(active, glasses.issue ?? "The simulated display and Inputs should start")
        guard active else { return }

        glasses.simulate(.highlight(.up))
        glasses.simulate(.confirm)
        let delivered = try await wait { received.count >= 2 }
        XCTAssertTrue(delivered)
        XCTAssertEqual(received, [.highlight(.up), .confirm])

        glasses.simulate(.turn(clockwise: true))
        glasses.simulate(.confirm)
        let turned = try await wait { received.count >= 3 }
        XCTAssertTrue(turned)
        try await Task.sleep(for: .milliseconds(550))
        XCTAssertEqual(received, [.highlight(.up), .confirm, .turn(clockwise: true)])

        glasses.simulate(.confirm)
        let confirmed = try await wait { received.count >= 4 }
        XCTAssertTrue(confirmed)
        XCTAssertEqual(received.last, .confirm)
        glasses.setWanted(false)
        XCTAssertFalse(glasses.ready)
    }

    @MainActor
    private func wait(_ condition: () -> Bool) async throws -> Bool {
        let deadline = ContinuousClock.now.advanced(by: .seconds(10))
        while !condition(), ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }
        return condition()
    }

    private func resample(_ audio: SpeechModels.Audio) -> [Float] {
        let step = Double(audio.rate) / Double(SpeechModels.sampleRate)
        return (0..<Int(Double(audio.samples.count - 1) / step)).map { target in
            let position = Double(target) * step
            let start = Int(position)
            let fraction = Float(position) - Float(start)
            return audio.samples[start] * (1 - fraction) + audio.samples[start + 1] * fraction
        }
    }
}
