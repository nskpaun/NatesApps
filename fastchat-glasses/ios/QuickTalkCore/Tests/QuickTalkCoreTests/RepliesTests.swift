import XCTest
@testable import QuickTalkCore

/// Ported from the Android app's `RepliesTest.kt`. The prompt strings must match Android's exactly.
final class RepliesTests: XCTestCase {

    func testOnlyFinishedLinesCountWhileTheModelIsStillWriting() {
        let soFar = "1. 👍 Yes, I'd love to.\n2. 🙅 No, not tod"
        XCTAssertEqual(ReplyParser.parse(soFar, finished: false), [Reply("👍", "Yes, I'd love to.")])
        XCTAssertEqual(ReplyParser.parse(soFar, finished: true), [Reply("👍", "Yes, I'd love to."), Reply("🙅", "No, not tod")])
    }

    func testACompleteAnswerYieldsFourRepliesEachWithItsEmoji() {
        let text = "1. 👍 Yes, please.\n2. ❌ No, thank you.\n3. ❓ What kind?\n4. ☀️ Maybe later."
        XCTAssertEqual(ReplyParser.parse(text, finished: true), [
            Reply("👍", "Yes, please."), Reply("❌", "No, thank you."), Reply("❓", "What kind?"), Reply("☀️", "Maybe later."),
        ])
    }

    func testAReplyWithoutAnEmojiStillParsesAndOneWordIsNeverMistakenForAnEmoji() {
        XCTAssertEqual(
            ReplyParser.parse("1. I am not sure.\n2. Yes.\n3. 2 sugars, please.", finished: true),
            [Reply("", "I am not sure."), Reply("", "Yes."), Reply("", "2 sugars, please.")]
        )
    }

    func testQuotesStrayLinesAndExtraRepliesAreCleanedUp() {
        let text = "Here are some replies:\n1. 🙂 \"Sounds good.\"\n\n2) Not really.\n3. \n4. 🤔 Why?\n5. Extra\n6. More\n"
        XCTAssertEqual(ReplyParser.parse(text, finished: true), [
            Reply("🙂", "Sounds good."), Reply("", "Not really."), Reply("🤔", "Why?"), Reply("", "Extra"),
        ])
    }

    func testNothingParsesFromAnEmptyOrUnnumberedAnswer() {
        XCTAssertTrue(ReplyParser.parse("", finished: true).isEmpty)
        XCTAssertTrue(ReplyParser.parse("I am not sure what to say.", finished: true).isEmpty)
    }

    func testStrayEmojiAsterisksAndQuotesNeverReachTheVoice() {
        XCTAssertEqual(
            ReplyParser.parse("1. 🎬 *The Godfather*?\n2. 😊 Thank you so much! 🎉", finished: true),
            [Reply("🎬", "The Godfather?"), Reply("😊", "Thank you so much!")]
        )
    }

    func testTheHiddenLineAboutTheSituationIsNotAReply() {
        let text = "(They are asking if I am hungry. I can say yes, say no, or ask what there is.)\n" +
            "1. 😋 Yes, I'm starving.\n2. 🙅 No, I just ate.\n"
        XCTAssertEqual(ReplyParser.parse(text, finished: false), [Reply("😋", "Yes, I'm starving."), Reply("🙅", "No, I just ate.")])
    }

    func testTheConversationIsSentAsChatTurnsWithTheOtherPersonAsTheUser() {
        let history = [Turn(.partner, "How was your weekend?"), Turn(.me, "It was good."), Turn(.partner, "What did you do?")]
        XCTAssertEqual(
            ReplyPrompt.turnBlock(history),
            "<|im_start|>user\nHow was your weekend?<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>It was good.<|im_end|>\n" +
                "<|im_start|>user\nWhat did you do?<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>"
        )
    }

    func testALineTheWearerDidNotAnswerIsDroppedAndTheWearersOwnLinesAreJoined() {
        let history = [
            Turn(.partner, "Hello?"), Turn(.partner, "Are you there?"),
            Turn(.me, "Yes"), Turn(.me, "Please give me a moment"),
            Turn(.partner, "Sure."),
        ]
        XCTAssertEqual(
            ReplyPrompt.turnBlock(history),
            "<|im_start|>user\nAre you there?<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>Yes Please give me a moment<|im_end|>\n" +
                "<|im_start|>user\nSure.<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>"
        )
    }

    func testTheFixedPartOfThePromptNamesTheWearerAndTeachesByExample() {
        let block = ReplyPrompt.systemBlock(Persona(name: "Sam"))
        XCTAssertTrue(block.hasPrefix("<|startoftext|><|im_start|>system\nYou are Sam."))
        let answers = block.components(separatedBy: "<|im_start|>assistant\n<think></think>").dropFirst()
        XCTAssertGreaterThanOrEqual(answers.count, 8)
        for answer in answers {
            XCTAssertTrue(answer.hasPrefix("(They "))
            XCTAssertEqual(ReplyParser.parse(answer.components(separatedBy: "<|im_end|>")[0], finished: true).count, 4)
        }
        XCTAssertTrue(ReplyPrompt.systemBlock(Persona()).contains("You are a person."))
    }

    func testTheGrammarAsksForTheHiddenLineAndThenExactlyFourEmojiReplies() {
        XCTAssertEqual(
            ReplyPrompt.grammar,
            #"root ::= "(They " [^\n\r()]{5,70} " I can " [^\n\r()]{5,110} ")\n" "# +
                #""1. " line "\n" "2. " line "\n" "3. " line "\n" "4. " line"# + "\n" +
                #"line ::= emoji " " [^\n\r<(]{2,50}"# + "\n" +
                #"emoji ::= [\U0001F300-\U0001FAFF☀-➿] [️]?"# + "\n"
        )
    }

    func testTheWearersFactsAreSentOnlyWhenAskedForRightBeforeTheLineBeingAnswered() {
        let history = [Turn(.partner, "Hi!"), Turn(.me, "Hello."), Turn(.partner, "Do you have any pets?")]
        XCTAssertFalse(ReplyPrompt.turnBlock(history).contains("Facts about you"))
        XCTAssertEqual(
            ReplyPrompt.turnBlock(history, facts: " I have a dog, Biscuit. "),
            "<|im_start|>user\nHi!<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>Hello.<|im_end|>\n" +
                "<|im_start|>system\nFacts about you, in case they help you answer: I have a dog, Biscuit.<|im_end|>\n" +
                "<|im_start|>user\nDo you have any pets?<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>"
        )
        XCTAssertFalse(ReplyPrompt.systemBlock(Persona(name: "Sam", about: "I have a dog, Biscuit.")).contains("Biscuit"))
    }

    func testTheDecisionPromptHoldsTheFactsAndAsksForOneWord() {
        let block = PersonaCheck.systemBlock(Persona(name: "Sam", about: "I'm 34. I have a dog, Biscuit."))
        XCTAssertTrue(block.hasPrefix("<|startoftext|><|im_start|>system\nFacts about Sam: I'm 34. I have a dog, Biscuit."))
        XCTAssertTrue(block.contains("<|im_start|>user\nHow old are you?<|im_end|>\n<|im_start|>assistant\n<think></think>yes<|im_end|>\n"))
        XCTAssertEqual(
            PersonaCheck.turnBlock(" Is this seat taken?\n"),
            "<|im_start|>user\nIs this seat taken?<|im_end|>\n<|im_start|>assistant\n<think></think>"
        )
        XCTAssertEqual(PersonaCheck.grammar, "root ::= \"yes\" | \"no\"\n")
        XCTAssertTrue(PersonaCheck.saysYes("yes"))
        XCTAssertFalse(PersonaCheck.saysYes("no"))
        XCTAssertFalse(PersonaCheck.saysYes(""))
    }

    func testRepliesThatSoundTheSameCountAsTheSame() {
        XCTAssertEqual(ReplyParser.sameWords("No thanks, I'm fine."), ReplyParser.sameWords("no thanks  im fine"))
    }
}
