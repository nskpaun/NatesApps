package com.natesapps.fastchat.core

/** Who the replies are written for; set by the wearer in Settings. */
data class Persona(val name: String = "", val about: String = "")

/** Longest reply the grammar allows, in characters. Keeps each one to a line on the glasses. */
const val MAX_REPLY_CHARS = 50

const val REPLY_COUNT = 4

/**
 * Builds the model prompt and reads the replies back out of the model's answer.
 *
 * The model (LFM3) is run as an ordinary chatbot playing the wearer: the other person's words are
 * the chat's "user" messages and the model answers as the wearer. Before the four replies it
 * writes one bracketed line, never shown, saying what the other person is doing and what the
 * wearer can do about it. A small model asked straight for "four replies" often answers as the
 * wrong person ("I'm sorry I scratched your car"); having it state who did what first, in its own
 * words, fixes most of that. The worked examples teach the format, the length and the perspective.
 */
object ReplyPrompt {

    private const val BOS = "<|startoftext|>"

    /** Opens the model's turn with thinking switched off (an empty think block). */
    private const val GENERATE = "<|im_start|>assistant\n<think></think>"

    /**
     * GBNF grammar the sampler is constrained to: the bracketed line, then exactly four numbered
     * lines, each an emoji, a space and a short sentence. With it the output always parses and
     * never runs long, whatever the model would otherwise have added.
     */
    val GRAMMAR: String = buildString {
        append("root ::= \"(They \" [^\\n\\r()]{5,70} \" I can \" [^\\n\\r()]{5,110} \")\\n\" ")
        append((1..REPLY_COUNT).joinToString(" \"\\n\" ") { "\"$it. \" line" })
        append("\n")
        append("line ::= emoji \" \" [^\\n\\r<(]{2,$MAX_REPLY_CHARS}\n")
        // One pictograph, optionally followed by the "show as emoji" variation selector.
        append("emoji ::= [\\U0001F300-\\U0001FAFF\\u2600-\\u27BF] [\\uFE0F]?\n")
    }

    fun system(persona: Persona): String = buildString {
        val name = persona.name.trim()
        append(if (name.isEmpty()) "You are a person" else "You are $name")
        append(". You are talking face to face with another person, and each message is something they say to you.\n")
        append("First write, in brackets, what they are doing and $REPLY_COUNT different things you can do about it. ")
        append("Then write the $REPLY_COUNT short replies you would say to them, one for each, each starting with one emoji.")
    }

    /**
     * Worked examples, one per kind of thing people say: an apology, a yes/no question, an open
     * question, news, an offer, thanks, a compliment. They are part of the cached prefix, so they
     * cost nothing per turn.
     */
    private val EXAMPLES: List<Pair<String, String>> = listOf(
        "Sorry I'm late, the traffic was terrible." to
            "(They are apologizing to me for being late. I can forgive them, be annoyed, ask what happened, or move on.)\n" +
            "1. 😊 That's okay, don't worry.\n2. 😠 I waited a long time.\n3. ❓ What happened?\n4. 🍽️ Let's go and eat.",
        "Are you hungry?" to
            "(They are asking if I am hungry. I can say yes, say no, ask what there is, or ask for a drink.)\n" +
            "1. 😋 Yes, I'm starving.\n2. 🙅 No, I just ate.\n3. ❓ What is there to eat?\n4. ☕ I'd just like a drink.",
        "What do you want to drink?" to
            "(They are asking what I want to drink. I can ask for water, coffee, or juice, or say nothing.)\n" +
            "1. 💧 Just water, please.\n2. ☕ A coffee would be great.\n3. 🧃 Some juice, if you have it.\n4. 🙅 Nothing for me, thanks.",
        "I got the job!" to
            "(They are telling me their good news. I can congratulate them, be sad they are leaving, ask when they start, or suggest a party.)\n" +
            "1. 🎉 Congratulations, that's wonderful!\n2. 😟 Oh, I'll miss you here.\n3. ❓ When do you start?\n4. 🥂 We should celebrate.",
        "Do you want me to carry your bag?" to
            "(They are offering to carry my bag. I can accept, refuse, check it is not too heavy for them, or say later.)\n" +
            "1. 🙏 Yes please, thank you.\n2. 🙅 No thanks, I've got it.\n3. ❓ Are you sure it's not too heavy?\n4. 😌 Maybe in a minute.",
        "Thanks for helping me move yesterday." to
            "(They are thanking me for helping them move. I can say you're welcome, say it was hard, ask about their new place, or joke that they owe me.)\n" +
            "1. 😊 You're welcome, happy to help.\n2. 😩 It was hard work, honestly.\n3. ❓ How is the new place?\n4. 🍕 You owe me a pizza.",
        "Where do you want to sit?" to
            "(They are asking where I want to sit. I can pick the window, the door, or outside, or say I don't mind.)\n" +
            "1. 🪟 By the window.\n2. 🚪 Near the door.\n3. ☀️ Outside, if it's warm.\n4. 🤷 Anywhere is fine.",
        "I love your shoes!" to
            "(They are complimenting my shoes. I can thank them, be modest, say where I got them, or say they are comfortable.)\n" +
            "1. 😊 Thank you!\n2. 😅 They're really old.\n3. 🛍️ I got them in town.\n4. 👟 They're very comfortable.",
        "I broke your mug, I'm really sorry." to
            "(They are apologizing for breaking my mug. I can forgive them, be upset, ask how it happened, or ask them to replace it.)\n" +
            "1. 😊 It's fine, it was only a mug.\n2. 😢 Oh no, I loved that mug.\n3. ❓ How did it happen?\n4. ☕ You can buy me a new one.",
    )

    private fun them(text: String) = "<|im_start|>user\n${text.trim()}<|im_end|>\n"

    private fun me(text: String) = "<|im_start|>assistant\n<think></think>${text.trim()}<|im_end|>\n"

    /**
     * The part of the prompt that only changes when the wearer's name does: the instructions and
     * the worked examples. The model evaluates it once and keeps a snapshot, so each reply only
     * pays for [turnBlock].
     */
    fun systemBlock(persona: Persona): String = buildString {
        append(BOS).append("<|im_start|>system\n").append(system(persona)).append("<|im_end|>\n")
        for ((said, answer) in EXAMPLES) append(them(said)).append(me(answer))
    }

    /**
     * The part of the prompt that changes every turn: the conversation so far as real chat turns
     * (their words as the user, the wearer's spoken replies as the model), then the model's turn.
     *
     * A chat alternates, so lines in a row from one speaker become one turn. For the wearer they
     * are joined. For the other person only the last is kept: an earlier line is one the wearer
     * chose not to answer, and a small model shown both tries to answer both.
     */
    fun turnBlock(history: List<Turn>): String = buildString {
        var index = 0
        while (index < history.size) {
            val speaker = history[index].speaker
            val run = mutableListOf<String>()
            while (index < history.size && history[index].speaker == speaker) {
                run += history[index].text.replace('\n', ' ').trim()
                index++
            }
            append(if (speaker == Speaker.PARTNER) them(run.last()) else me(run.joinToString(" ")))
        }
        append(GENERATE)
    }

    fun build(persona: Persona, history: List<Turn>): String = systemBlock(persona) + turnBlock(history)
}

object ReplyParser {
    private val numbered = Regex("""^\s*(\d+)\s*[.)]\s*(.*)$""")

    /**
     * Replies finished so far in [text], the model's output up to now. A line counts once the
     * newline after it has arrived, or once [finished] says the model has stopped, so a reply is
     * never shown (or spoken) half written.
     */
    fun parse(text: String, finished: Boolean): List<Reply> {
        val lines = text.split('\n')
        val complete = if (finished) lines else lines.dropLast(1)
        return complete
            .mapNotNull { line -> numbered.find(line)?.groupValues?.get(2) }
            .map(::reply)
            .filter { it.text.isNotEmpty() }
            .take(REPLY_COUNT)
    }

    /** Splits "👍 Yes, I would." into its emoji and its words; a line without an emoji is fine. */
    private fun reply(line: String): Reply {
        val trimmed = line.trim()
        val first = trimmed.substringBefore(' ')
        return if (first.isNotEmpty() && first != trimmed && isEmoji(first)) {
            Reply(first, clean(trimmed.substring(first.length)))
        } else {
            Reply("", clean(trimmed))
        }
    }

    /** Pictographs and symbols only: nothing a sentence would start with. */
    private fun isEmoji(token: String): Boolean = token.codePoints().allMatch { it >= 0x2190 }

    /**
     * The words only: no stray emoji, asterisks or quotation marks. What is left is spoken aloud,
     * and a voice has nothing sensible to do with any of those.
     */
    private fun clean(reply: String): String {
        val words = StringBuilder()
        reply.codePoints().forEach { if (it < 0x2190 && it != '*'.code) words.appendCodePoint(it) }
        return words.toString().trim().trim('"', '\u201C', '\u201D').trim()
    }

    /** The same reply, as far as a listener could tell: used to drop repeats. */
    fun sameWords(reply: String): String = reply.lowercase().filter { it.isLetterOrDigit() }
}
