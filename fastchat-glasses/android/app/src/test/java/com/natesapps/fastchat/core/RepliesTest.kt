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
    fun `the prompt carries the conversation, the persona and the rejected replies`() {
        val history = listOf(
            Turn(Speaker.PARTNER, "How was your weekend?"),
            Turn(Speaker.ME, "It was good."),
            Turn(Speaker.PARTNER, "What did you do?"),
        )
        val prompt = ReplyPrompt.build(
            Persona(name = "Sam", about = "I love sailing."),
            history,
            avoid = listOf("Not much."),
        )

        assertTrue(prompt.startsWith("<|im_start|>system\n"))
        assertTrue("Sam" in prompt)
        assertTrue("I love sailing." in prompt)
        assertTrue("Them: How was your weekend?\nMe: It was good.\nThem: What did you do?\n" in prompt)
        assertTrue("- Not much.\n" in prompt)
        // Thinking is off: the assistant turn opens with an empty think block.
        assertTrue(prompt.endsWith("<|im_start|>assistant\n<think>\n\n</think>\n\n"))
    }

    @Test
    fun `the prompt has no persona or avoid section when there is nothing to put in them`() {
        val prompt = ReplyPrompt.build(Persona(), listOf(Turn(Speaker.PARTNER, "Hi")), avoid = emptyList())
        assertFalse("About " in prompt)
        assertFalse("did not want" in prompt)
    }

    @Test
    fun `the grammar asks for exactly four numbered lines, each starting with an emoji`() {
        assertEquals(
            "root ::= \"1. \" line \"\\n\" \"2. \" line \"\\n\" \"3. \" line \"\\n\" \"4. \" line\n" +
                "line ::= emoji \" \" [^\\n\\r]{2,70}\n" +
                "emoji ::= [\\U0001F300-\\U0001FAFF\\u2600-\\u27BF] [\\uFE0F]?\n",
            ReplyPrompt.GRAMMAR,
        )
    }
}
