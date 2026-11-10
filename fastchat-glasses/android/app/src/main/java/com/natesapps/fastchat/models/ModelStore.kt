package com.natesapps.fastchat.models

import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

/** One file a model needs, and where to get it. */
data class ModelFile(
    /** Path under the models folder, e.g. `speech-to-text/encoder.int8.onnx`. */
    val path: String,
    val url: String,
    val bytes: Long,
    /** Hex SHA-256, checked after download when known. */
    val sha256: String? = null,
)

/**
 * The on-device models. Everything runs locally once these files are on the phone; they are too
 * big for the APK (about 1.9 GB together), so the app downloads them on first run.
 */
object Models {
    private const val LFM3 = "https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF/resolve/main"
    private const val PARAKEET = "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/main"
    private const val SUPERTONIC = "https://huggingface.co/csukuangfj2/sherpa-onnx-supertonic-3-tts-int8-2026-05-11/resolve/main"

    /**
     * Reply writer: Liquid AI's LFM3-1.7B, the 4-bit file trained to recover what 4-bit
     * quantization loses. About ten times faster on a phone CPU than the 9B model it replaced.
     */
    val LLM = ModelFile(
        "llm/LFM3-1.7B-QAD-Q4_0.gguf",
        "$LFM3/LFM3-1.7B-QAD-Q4_0.gguf",
        1_049_615_680,
        "43a7d09a0e9cba91b63eb7052488b9564569bddfd65754d2e426465e572a7452",
    )

    /** Finds where an utterance starts and ends: Silero VAD. */
    val VAD = ModelFile(
        "speech-to-text/silero_vad.onnx",
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
        643_854,
        "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6",
    )

    /** Speech to text: NVIDIA Parakeet TDT 0.6b v2 (English), int8. */
    val STT_ENCODER = ModelFile(
        "speech-to-text/encoder.int8.onnx", "$PARAKEET/encoder.int8.onnx", 652_282_309,
        "92a10bd9c23936ea0566c29f963bc57c2a5df4261b6a8921c39abea66557ca8b",
    )
    val STT_DECODER = ModelFile(
        "speech-to-text/decoder.int8.onnx", "$PARAKEET/decoder.int8.onnx", 7_257_753,
        "4d097bae3bac5c96018d5293ba39f1b657296102b142affda40378f38b020f41",
    )
    val STT_JOINER = ModelFile(
        "speech-to-text/joiner.int8.onnx", "$PARAKEET/joiner.int8.onnx", 1_739_080,
        "77a29f3e5ac7d37074e0af465391b80f314015d5b97f0f90c6c7767f1d56f428",
    )
    val STT_TOKENS = ModelFile("speech-to-text/tokens.txt", "$PARAKEET/tokens.txt", 9_384)

    /** Text to speech: Supertonic 3, int8. Works on raw characters, so no word is ever dropped. */
    val TTS_DURATION = ModelFile(
        "text-to-speech/duration_predictor.int8.onnx", "$SUPERTONIC/duration_predictor.int8.onnx", 3_700_147,
        "c3eb91414d5ff8a7a239b7fe9e34e7e2bf8a8140d8375ffb14718b1c639325db",
    )
    val TTS_TEXT_ENCODER = ModelFile(
        "text-to-speech/text_encoder.int8.onnx", "$SUPERTONIC/text_encoder.int8.onnx", 36_416_150,
        "c7befd5ea8c3119769e8a6c1486c4edc6a3bc8365c67621c881bbb774b9902ff",
    )
    val TTS_VECTOR_ESTIMATOR = ModelFile(
        "text-to-speech/vector_estimator.int8.onnx", "$SUPERTONIC/vector_estimator.int8.onnx", 78_400_833,
        "20cd86fa5c6effedfda0e7cffe5b0569ca401c440a0c3a1d72bf39286c0db3fd",
    )
    val TTS_VOCODER = ModelFile(
        "text-to-speech/vocoder.int8.onnx", "$SUPERTONIC/vocoder.int8.onnx", 25_991_073,
        "e923d60f53f95eb1ce235f1dc33ec56d9c057823c96fa6f8acf98f32b0da6152",
    )
    val TTS_CONFIG = ModelFile("text-to-speech/tts.json", "$SUPERTONIC/tts.json", 8_253)
    val TTS_INDEXER = ModelFile(
        "text-to-speech/unicode_indexer.bin", "$SUPERTONIC/unicode_indexer.bin", 262_144,
        "8402ca48e5189a8950138580b0fff64db6f072f24ac07cd54ba8b2fbb9883b30",
    )
    val TTS_VOICES = ModelFile(
        "text-to-speech/voice.bin", "$SUPERTONIC/voice.bin", 517_168,
        "67d5209b0ee8ce6c74105ffbe12fe6a7628aea3b4ba2fcb308a4a67938a93ce8",
    )

    /** Smallest first, so a failed download is noticed before the big ones start. */
    val ALL: List<ModelFile> = listOf(
        VAD, STT_TOKENS, STT_JOINER, STT_DECODER, TTS_CONFIG, TTS_INDEXER, TTS_VOICES, TTS_DURATION,
        TTS_VOCODER, TTS_TEXT_ENCODER, TTS_VECTOR_ESTIMATOR, STT_ENCODER, LLM,
    )
}

/**
 * The models folder on the phone. A file counts as present when it exists with exactly the
 * expected size; downloads go to a `.part` file first and resume where they stopped.
 */
class ModelStore(val dir: File, private val files: List<ModelFile> = Models.ALL) {

    data class Progress(val file: ModelFile, val doneBytes: Long, val totalBytes: Long)

    fun file(model: ModelFile): File = File(dir, model.path)

    fun path(model: ModelFile): String = file(model).absolutePath

    fun has(model: ModelFile): Boolean = file(model).let { it.isFile && it.length() == model.bytes }

    fun missing(): List<ModelFile> = files.filterNot(::has)

    val totalBytes: Long get() = files.sumOf { it.bytes }

    /** Bytes already on the phone, counting partly downloaded files. */
    fun presentBytes(): Long = files.sumOf { model ->
        if (has(model)) model.bytes else part(model).length().coerceAtMost(model.bytes)
    }

    private fun part(model: ModelFile): File = File(dir, model.path + ".part")

    /**
     * Downloads whatever is missing, reporting overall progress. Safe to cancel and call again:
     * it picks up from the bytes already saved.
     */
    suspend fun download(onProgress: (Progress) -> Unit) = withContext(Dispatchers.IO) {
        for (model in missing()) {
            fetch(model) { onProgress(Progress(model, presentBytes(), totalBytes)) }
        }
    }

    private suspend fun fetch(model: ModelFile, tick: () -> Unit) = withContext(Dispatchers.IO) {
        val part = part(model)
        part.parentFile?.mkdirs()
        if (part.length() > model.bytes) part.delete()

        if (part.length() < model.bytes) {
            val offset = part.length()
            val connection = open(model.url, offset)
            try {
                // 206 means the server honoured the range; a plain 200 restarts from the beginning.
                val resumed = connection.responseCode == HttpURLConnection.HTTP_PARTIAL
                if (!resumed && connection.responseCode != HttpURLConnection.HTTP_OK) {
                    throw IOException("${model.path}: server answered ${connection.responseCode}")
                }
                RandomAccessFile(part, "rw").use { out ->
                    if (resumed) out.seek(offset) else out.setLength(0)
                    connection.inputStream.use { input ->
                        val buffer = ByteArray(1 shl 16)
                        var sinceTick = 0L
                        while (true) {
                            coroutineContext.ensureActive()
                            val read = input.read(buffer)
                            if (read < 0) break
                            out.write(buffer, 0, read)
                            sinceTick += read
                            if (sinceTick >= PROGRESS_STEP_BYTES) {
                                sinceTick = 0
                                tick()
                            }
                        }
                    }
                }
            } finally {
                connection.disconnect()
            }
        }

        if (part.length() != model.bytes) {
            throw IOException("${model.path}: got ${part.length()} bytes, expected ${model.bytes}")
        }
        if (model.sha256 != null && sha256(part) != model.sha256) {
            part.delete()
            throw IOException("${model.path}: the download was corrupted, please try again")
        }
        val target = file(model)
        target.delete()
        if (!part.renameTo(target)) throw IOException("${model.path}: could not save the file")
        tick()
    }

    /** Opens [url] from byte [offset], following redirects by hand so the Range header survives. */
    private fun open(url: String, offset: Long): HttpURLConnection {
        var next = url
        repeat(MAX_REDIRECTS) {
            val connection = URL(next).openConnection() as HttpURLConnection
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 20_000
            connection.readTimeout = 30_000
            connection.setRequestProperty("User-Agent", "FastChatGlasses")
            if (offset > 0) connection.setRequestProperty("Range", "bytes=$offset-")
            if (connection.responseCode !in 300..399) return connection
            val location = connection.getHeaderField("Location")
            connection.disconnect()
            next = URL(URL(next), location ?: throw IOException("Redirect without a location")).toString()
        }
        throw IOException("Too many redirects for $url")
    }

    private suspend fun sha256(file: File): String = withContext(Dispatchers.IO) {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(1 shl 20)
            while (true) {
                coroutineContext.ensureActive()
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        digest.digest().joinToString("") { "%02x".format(it) }
    }

    private companion object {
        const val MAX_REDIRECTS = 5
        const val PROGRESS_STEP_BYTES = 4L shl 20
    }
}
