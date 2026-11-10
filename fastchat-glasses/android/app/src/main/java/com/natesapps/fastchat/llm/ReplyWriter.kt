package com.natesapps.fastchat.llm

import com.natesapps.fastchat.core.Persona
import com.natesapps.fastchat.core.ReplyParser
import com.natesapps.fastchat.core.ReplyPrompt
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

/** Enough for four replies of [com.natesapps.fastchat.core.MAX_REPLY_CHARS] characters each. */
private const val MAX_OUTPUT_TOKENS = 120

/** Asks the model for replies and streams them out one at a time as each line is finished. */
class ReplyWriter(private val engine: LlamaEngine) {

    data class Update(val replies: List<String>, val done: Boolean, val stats: LlamaEngine.Stats? = null)

    /** All model calls run here, one at a time: the engine is not thread-safe. */
    private val modelThread = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "fastchat-llm")
    }.asCoroutineDispatcher()

    /** Evaluates the persona part of the prompt ahead of the first reply. */
    suspend fun prime(persona: Persona) = withContext(modelThread) {
        engine.prime(ReplyPrompt.systemBlock(persona))
    }

    /**
     * Emits the list of finished replies each time it grows, then a final update with
     * `done = true`. Cancelling the collector stops the model within a token.
     */
    fun replies(persona: Persona, history: List<Turn>, avoid: List<String>): Flow<Update> = channelFlow {
        withContext(modelThread) {
            // Stops a long prompt evaluation; between tokens the callback's `isActive` does it.
            val stopper = coroutineContext.job.invokeOnCompletion { cause ->
                if (cause is CancellationException) engine.cancel()
            }
            try {
                if (!isActive) return@withContext
                val text = StringBuilder()
                var shown = 0
                val stats = engine.generate(
                    prefix = ReplyPrompt.systemBlock(persona),
                    suffix = ReplyPrompt.turnBlock(history, avoid),
                    grammar = ReplyPrompt.GRAMMAR,
                    maxTokens = MAX_OUTPUT_TOKENS,
                ) { piece ->
                    text.append(piece)
                    val replies = ReplyParser.parse(text.toString(), finished = false)
                    if (replies.size > shown) {
                        shown = replies.size
                        trySendBlocking(Update(replies, done = false))
                    }
                    isActive
                }
                if (isActive) {
                    trySendBlocking(Update(ReplyParser.parse(text.toString(), finished = true), done = true, stats))
                }
            } finally {
                stopper.dispose()
            }
        }
    }
}
