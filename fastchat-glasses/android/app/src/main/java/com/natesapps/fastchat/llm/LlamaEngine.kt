package com.natesapps.fastchat.llm

import java.io.Closeable

/**
 * The on-device language model: LFM3 through llama.cpp (see `src/main/cpp`).
 *
 * Calls block and must not overlap; [ReplyWriter] keeps them on one thread. [cancel] is the
 * exception: it may be called from any thread to stop the call in progress.
 */
class LlamaEngine private constructor(private var handle: Long) : Closeable {

    data class Stats(
        val promptTokens: Int,
        val promptMs: Long,
        val outputTokens: Int,
        val outputMs: Long,
        val prefixReused: Boolean,
    ) {
        val tokensPerSecond: Float get() = if (outputMs > 0) outputTokens * 1000f / outputMs else 0f
    }

    /** Receives generated text as it is written; return false to stop. */
    fun interface TextSink {
        fun onText(utf8: ByteArray): Boolean
    }

    /** Evaluates [prefix] ahead of time so the first [generate] that shares it starts sooner. */
    fun prime(prefix: String) = nativePrime(handle, prefix.toByteArray())

    /**
     * Completes [prefix] + [suffix], constrained by the GBNF [grammar]. The state after [prefix]
     * is cached, so keep everything that rarely changes in it.
     */
    fun generate(
        prefix: String,
        suffix: String,
        grammar: String,
        maxTokens: Int,
        temperature: Float = TEMPERATURE,
        onText: (String) -> Boolean,
    ): Stats {
        val stats = nativeGenerate(
            handle, prefix.toByteArray(), suffix.toByteArray(), grammar.toByteArray(),
            temperature, TOP_P, TOP_K, PRESENCE_PENALTY, maxTokens,
        ) { bytes -> onText(String(bytes, Charsets.UTF_8)) }
        return Stats(stats[0].toInt(), stats[1], stats[2].toInt(), stats[3], stats[4] == 1L)
    }

    fun cancel() {
        if (handle != 0L) nativeCancel(handle)
    }

    override fun close() {
        if (handle != 0L) nativeFree(handle)
        handle = 0
    }

    companion object {
        // The sampling the prompt was tuned with. LFM3's own recommendation (temperature 0.1) was
        // tried and made the four replies too alike.
        const val TEMPERATURE = 0.7f
        private const val TOP_P = 0.8f
        private const val TOP_K = 20
        private const val PRESENCE_PENALTY = 1.5f

        init {
            System.loadLibrary("fastchat_llm")
        }

        /** Loads the GGUF at [path]. Takes a few seconds; throws if the file cannot be loaded. */
        fun load(path: String, contextTokens: Int = 4096, threads: Int = defaultThreads()): LlamaEngine =
            LlamaEngine(nativeLoad(path.toByteArray(), contextTokens, threads))

        /** Leave two cores for audio and the UI; more than six threads stops paying off. */
        fun defaultThreads(): Int = (Runtime.getRuntime().availableProcessors() - 2).coerceIn(2, 6)

        @JvmStatic private external fun nativeLoad(path: ByteArray, contextTokens: Int, threads: Int): Long
        @JvmStatic private external fun nativePrime(handle: Long, prefix: ByteArray)
        @JvmStatic private external fun nativeGenerate(
            handle: Long, prefix: ByteArray, suffix: ByteArray, grammar: ByteArray,
            temperature: Float, topP: Float, topK: Int, presencePenalty: Float, maxTokens: Int,
            sink: TextSink,
        ): LongArray
        @JvmStatic private external fun nativeCancel(handle: Long)
        @JvmStatic private external fun nativeFree(handle: Long)
    }
}
