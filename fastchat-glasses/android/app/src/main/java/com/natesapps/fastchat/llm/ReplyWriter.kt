package com.natesapps.fastchat.llm

import android.util.Log
import com.natesapps.fastchat.core.Persona
import com.natesapps.fastchat.core.PersonaCheck
import com.natesapps.fastchat.core.REPLY_COUNT
import com.natesapps.fastchat.core.Reply
import com.natesapps.fastchat.core.ReplyParser
import com.natesapps.fastchat.core.ReplyPrompt
import com.natesapps.fastchat.core.Speaker
import com.natesapps.fastchat.core.Turn
import java.util.concurrent.Executors
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.channels.trySendBlocking
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.job
import kotlinx.coroutines.withContext

/** Room for the bracketed line and four replies of [com.natesapps.fastchat.core.MAX_REPLY_CHARS] characters. */
private const val MAX_OUTPUT_TOKENS = 160

/** How many times the model is asked before settling for fewer than four distinct replies. */
private const val MAX_ATTEMPTS = 3

/** Sampling temperature for a second try or for "more replies": looser, to get different ones. */
private const val RETRY_TEMPERATURE = 1.0f

/** The yes/no decision should be the model's single most likely answer, not a roll of the dice. */
private const val DECISION_TEMPERATURE = 0.01f

/** Asks the model for replies and streams them out one at a time as each line is finished. */
class ReplyWriter(private val engine: LlamaEngine) {

    data class Update(val replies: List<Reply>, val done: Boolean, val stats: LlamaEngine.Stats? = null)

    /** All model calls run here, one at a time: the engine is not thread-safe. */
    private val modelThread = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "fastchat-llm")
    }.asCoroutineDispatcher()

    /** Evaluates the fixed parts of both prompts ahead of the first reply. */
    suspend fun prime(persona: Persona) = withContext(modelThread) {
        if (persona.about.isNotBlank()) engine.prime(PersonaCheck.systemBlock(persona))
        engine.prime(ReplyPrompt.systemBlock(persona))
    }

    /**
     * Whether answering the last thing the other person said needs the wearer's own facts: one
     * short model call with a one-word answer. Without any facts there is nothing to decide.
     */
    private fun needsFacts(persona: Persona, history: List<Turn>): Boolean {
        val said = history.lastOrNull { it.speaker == Speaker.PARTNER }?.text
        if (persona.about.isBlank() || said == null) return false
        val answer = StringBuilder()
        val stats = engine.generate(
            prefix = PersonaCheck.systemBlock(persona),
            suffix = PersonaCheck.turnBlock(said),
            grammar = PersonaCheck.GRAMMAR,
            maxTokens = 2,
            temperature = DECISION_TEMPERATURE,
        ) { piece -> answer.append(piece); true }
        val yes = PersonaCheck.saysYes(answer.toString())
        Log.i("FastChat", "about you: ${if (yes) "needed" else "not needed"}, decided in ${stats.promptMs + stats.outputMs} ms")
        return yes
    }

    /**
     * Emits the list of finished replies each time it grows, then a final update with
     * `done = true`. Cancelling the collector stops the model within a token.
     *
     * Replies in [avoid] (already offered and turned down) are never emitted. Telling a small
     * model what not to say does not work, so repeats are dropped here instead and the model is
     * simply asked again, more loosely, until there are four distinct replies.
     */
    fun replies(persona: Persona, history: List<Turn>, avoid: List<String>): Flow<Update> = channelFlow {
        withContext(modelThread) {
            // Stops a long prompt evaluation; between tokens the callback's `isActive` does it.
            val stopper = coroutineContext.job.invokeOnCompletion { cause ->
                if (cause is CancellationException) engine.cancel()
            }
            try {
                val unwanted = avoid.map(ReplyParser::sameWords).toSet()
                val facts = if (needsFacts(persona, history)) persona.about else null
                var kept = emptyList<Reply>()
                var stats: LlamaEngine.Stats? = null
                var attempt = 0
                while (isActive && kept.size < REPLY_COUNT && attempt < MAX_ATTEMPTS) {
                    val earlier = kept
                    val text = StringBuilder()
                    stats = engine.generate(
                        prefix = ReplyPrompt.systemBlock(persona),
                        suffix = ReplyPrompt.turnBlock(history, facts),
                        grammar = ReplyPrompt.GRAMMAR,
                        maxTokens = MAX_OUTPUT_TOKENS,
                        temperature = if (attempt == 0 && avoid.isEmpty()) LlamaEngine.TEMPERATURE else RETRY_TEMPERATURE,
                    ) { piece ->
                        text.append(piece)
                        val soFar = distinct(earlier + ReplyParser.parse(text.toString(), finished = false), unwanted)
                        if (soFar.size > kept.size) {
                            kept = soFar
                            trySendBlocking(Update(kept, done = false))
                        }
                        isActive && kept.size < REPLY_COUNT
                    }
                    kept = distinct(earlier + ReplyParser.parse(text.toString(), finished = true), unwanted)
                    attempt++
                }
                if (isActive) trySendBlocking(Update(kept, done = true, stats))
            } finally {
                stopper.dispose()
            }
        }
    }

    /** [replies] in order, without repeats of each other or of anything in [unwanted]. */
    private fun distinct(replies: List<Reply>, unwanted: Set<String>): List<Reply> =
        replies.filter { ReplyParser.sameWords(it.text) !in unwanted }
            .distinctBy { ReplyParser.sameWords(it.text) }
            .take(REPLY_COUNT)
}
