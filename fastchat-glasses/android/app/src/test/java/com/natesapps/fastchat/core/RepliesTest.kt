package com.natesapps.fastchat.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RepliesTest {

    @Test
    fun `only finished lines count while the model is still writing`() {
        val soFar = "1. 👍 Yes, I'd love to.\n2. 🙅 No, not tod"
        assertEquals(listOf(Reply("👍", "Yes, I'd love to.")), ReplyParser.parse(soFar, finished = false))
        assertEquals(
            listOf(Reply("👍", "Yes, I'd love to."), Reply("🙅", "No, not tod")),
            ReplyParser.parse(soFar, finished = true),
        )
    }

    @Test
    fun `a complete answer yields four replies, each with its emoji`() {
        val text = "1. 👍 Yes, please.\n2. ❌ No, thank you.\n3. ❓ What kind?\n4. ☀️ Maybe later."
        assertEquals(
            listOf(
                Reply("👍", "Yes, please."),
                Reply("❌", "No, thank you."),
                Reply("❓", "What kind?"),
                Reply("☀️", "Maybe later."),
            ),
            ReplyParser.parse(text, finished = true),
        )
    }

    @Test
    fun `a reply without an emoji still parses, and one word is never mistaken for an emoji`() {
        assertEquals(
            listOf(Reply("", "I am not sure."), Reply("", "Yes."), Reply("", "2 sugars, please.")),
            ReplyParser.parse("1. I am not sure.\n2. Yes.\n3. 2 sugars, please.", finished = true),
        )
    }

    @Test
    fun `quotes, stray lines and extra replies are cleaned up`() {
        val text = "Here are some replies:\n1. 🙂 \"Sounds good.\"\n\n2) Not really.\n3. \n4. 🤔 Why?\n5. Extra\n6. More\n"
        assertEquals(
            listOf(Reply("🙂", "Sounds good."), Reply("", "Not really."), Reply("🤔", "Why?"), Reply("", "Extra")),
            ReplyParser.parse(text, finished = true),
        )
    }

    @Test
    fun `nothing parses from an empty or unnumbered answer`() {
        assertTrue(ReplyParser.parse("", finished = true).isEmpty())
        assertTrue(ReplyParser.parse("I am not sure what to say.", finished = true).isEmpty())
    }

    @Test
    fun `stray emoji, asterisks and quotes never reach the voice`() {
        assertEquals(
            listOf(Reply("🎬", "The Godfather?"), Reply("😊", "Thank you so much!")),
            ReplyParser.parse("1. 🎬 *The Godfather*?\n2. 😊 Thank you so much! 🎉", finished = true),
        )
    }

    @Test
    fun `the hidden line about the situation is not a reply`() {
        val text = "(They are asking if I am hungry. I can say yes, say no, or ask what there is.)\n" +
            "1. 😋 Yes, I'm starving.\n2. 🙅 No, I just ate.\n"
        assertEquals(
            listOf(Reply("😋", "Yes, I'm starving."), Reply("🙅", "No, I just ate.")),
            ReplyParser.parse(text, finished = false),
        )
    }

    @Test
    fun `the conversation is sent as chat turns, with the other person as the user`() {
        val history = listOf(
            Turn(Speaker.PARTNER, "How was your weekend?"),
            Turn(Speaker.ME, "It was good."),
            Turn(Speaker.PARTNER, "What did you do?"),
        )
        assertEquals(
            "<|im_start|>user\nHow was your weekend?<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>It was good.<|im_end|>\n" +
                "<|im_start|>user\nWhat did you do?<|im_end|>\n" +
                // Thinking is off: the model's turn opens with an empty think block.
                "<|im_start|>assistant\n<think></think>",
            ReplyPrompt.turnBlock(history),
        )
    }

    @Test
    fun `a line the wearer did not answer is dropped, and the wearer's own lines are joined`() {
        val history = listOf(
            Turn(Speaker.PARTNER, "Hello?"),
            Turn(Speaker.PARTNER, "Are you there?"),
            Turn(Speaker.ME, "Yes"),
            Turn(Speaker.ME, "Please give me a moment"),
            Turn(Speaker.PARTNER, "Sure."),
        )
        assertEquals(
            "<|im_start|>user\nAre you there?<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>Yes Please give me a moment<|im_end|>\n" +
                "<|im_start|>user\nSure.<|im_end|>\n" +
                "<|im_start|>assistant\n<think></think>",
            ReplyPrompt.turnBlock(history),
        )
    }

    @Test
    fun `the fixed part of the prompt names the wearer and teaches by example`() {
        val block = ReplyPrompt.systemBlock(Persona(name = "Sam"))
        assertTrue(block.startsWith("<|startoftext|><|im_start|>system\nYou are Sam."))
        // Every example answer has the hidden line followed by four replies.
        val answers = block.split("<|im_start|>assistant\n<think></think>").drop(1)
        assertTrue(answers.size >= 8)
        for (answer in answers) {
            assertTrue(answer.startsWith("(They "))
            assertEquals(4, ReplyParser.parse(answer.substringBefore("<|im_end|>"), finished = true).size)
        }
        assertTrue(ReplyPrompt.systemBlock(Persona()).contains("You are a person."))
    }

    @Test
    fun `the grammar asks for the hidden line and then exactly four emoji replies`() {
        assertEquals(
            "root ::= \"(They \" [^\\n\\r()]{5,70} \" I can \" [^\\n\\r()]{5,110} \")\\n\" " +
                "\"1. \" line \"\\n\" \"2. \" line \"\\n\" \"3. \" line \"\\n\" \"4. \" line\n" +
                "line ::= emoji \" \" [^\\n\\r<(]{2,50}\n" +
                "emoji ::= [\\U0001F300-\\U0001FAFF\\u2600-\\u27BF] [\\uFE0F]?\n",
            ReplyPrompt.GRAMMAR,
        )
    }

    @Test
    fun `replies that sound the same count as the same`() {
        assertEquals(ReplyParser.sameWords("No thanks, I'm fine."), ReplyParser.sameWords("no thanks  im fine"))
    }
}
