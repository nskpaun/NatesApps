package com.natesapps.fastchat.core

/** Who the replies are written for; set by the wearer in Settings. */
data class Persona(val name: String = "", val about: String = "")

/** Longest reply the grammar allows, in characters. Keeps each one to a line or two on the glasses. */
const val MAX_REPLY_CHARS = 70

const val REPLY_COUNT = 4

/**
 * Builds the model prompt (ChatML, the format Qwen-family models such as Bonsai use) and reads the
 * replies back out of the model's numbered-list answer.
 */
object ReplyPrompt {

    /**
     * GBNF grammar the sampler is constrained to: exactly four numbered lines. With it the output
     * always parses and never runs long, whatever the model would otherwise have added.
     */
    val GRAMMAR: String = buildString {
        append("root ::= ")
        append((1..REPLY_COUNT).joinToString(" \"\\n\" ") { "\"$it. \" line" })
        append("\n")
        append("line ::= [^\\n\\r]{2,$MAX_REPLY_CHARS}\n")
    }

    fun system(persona: Persona): String = buildString {
        val who = persona.name.trim().ifEmpty { "the user" }
        append("You write replies for $who, who cannot speak and talks through an app. ")
        append("Someone is talking to them face to face. ")
        append("Write exactly $REPLY_COUNT different things $who might want to say next, ")
        append("in the first person, as natural spoken English.\n")
        append("Rules:\n")
        append("- Each reply is one short sentence, 10 words at most.\n")
        append("- Make the $REPLY_COUNT replies mean different things, so there is a real choice: ")
        append("for example one that agrees or says yes, one that disagrees or says no, ")
        append("one that asks a question back, and one that is neutral or changes the subject.\n")
        append("- Answer what was actually said. Never invent facts about $who.\n")
        append("- Output only a numbered list, 1 to $REPLY_COUNT, one reply per line.")
        val about = persona.about.trim()
        if (about.isNotEmpty()) {
            append("\n\nAbout $who (use this to make replies sound like them):\n")
            append(about)
        }
    }

    fun user(history: List<Turn>, avoid: List<String>): String = buildString {
        append("Conversation so far:\n")
        for (turn in history) {
            append(if (turn.speaker == Speaker.PARTNER) "Them: " else "Me: ")
            append(turn.text.replace('\n', ' '))
            append('\n')
        }
        if (avoid.isNotEmpty()) {
            append("\nI did not want any of these, so write $REPLY_COUNT new ones that are different:\n")
            for (reply in avoid) append("- ").append(reply).append('\n')
        }
        append("\nWrite $REPLY_COUNT replies I could say now.")
    }

    /**
     * The part of the prompt that only changes when the persona does. The model evaluates it once
     * and keeps a snapshot, so each reply only pays for [turnBlock].
     */
    fun systemBlock(persona: Persona): String =
        "<|im_start|>system\n${system(persona).trim()}<|im_end|>\n"

    /**
     * The part of the prompt that changes every turn. The assistant turn opens with an empty think
     * block, which is how the Qwen chat template switches thinking off: replies must start
     * appearing immediately.
     */
    fun turnBlock(history: List<Turn>, avoid: List<String>): String =
        "<|im_start|>user\n${user(history, avoid).trim()}<|im_end|>\n" +
            "<|im_start|>assistant\n<think>\n\n</think>\n\n"

    fun build(persona: Persona, history: List<Turn>, avoid: List<String>): String =
        systemBlock(persona) + turnBlock(history, avoid)
}

object ReplyParser {
    private val numbered = Regex("""^\s*(\d+)\s*[.)]\s*(.*)$""")

    /**
     * Replies finished so far in [text], the model's output up to now. A line counts once the
     * newline after it has arrived, or once [finished] says the model has stopped, so a reply is
     * never shown (or spoken) half written.
     */
    fun parse(text: String, finished: Boolean): List<String> {
        val lines = text.split('\n')
        val complete = if (finished) lines else lines.dropLast(1)
        return complete
            .mapNotNull { line -> numbered.find(line)?.groupValues?.get(2) }
            .map(::clean)
            .filter { it.isNotEmpty() }
            .take(REPLY_COUNT)
    }

    private fun clean(reply: String): String =
        reply.trim().trim('"', '\u201C', '\u201D').trim()
}
