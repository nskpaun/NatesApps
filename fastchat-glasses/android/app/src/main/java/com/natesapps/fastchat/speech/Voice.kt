package com.natesapps.fastchat.speech

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.SystemClock
import android.util.Log
import com.k2fsa.sherpa.onnx.GenerationConfig
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsSupertonicModelConfig
import com.natesapps.fastchat.models.ModelStore
import com.natesapps.fastchat.models.Models
import java.util.concurrent.Executors
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

/** Denoising steps: more sounds a little cleaner, fewer starts speaking sooner. */
private const val SYNTHESIS_STEPS = 6

/**
 * The wearer's voice: Supertonic 3 text-to-speech, synthesised on the phone and played from the
 * phone's own loudspeaker so the conversation partner hears it.
 */
class Voice(private val context: Context, models: ModelStore) {

    private val tts = OfflineTts(
        config = OfflineTtsConfig(
            model = OfflineTtsModelConfig(
                supertonic = OfflineTtsSupertonicModelConfig(
                    durationPredictor = models.path(Models.TTS_DURATION),
                    textEncoder = models.path(Models.TTS_TEXT_ENCODER),
                    vectorEstimator = models.path(Models.TTS_VECTOR_ESTIMATOR),
                    vocoder = models.path(Models.TTS_VOCODER),
                    ttsJson = models.path(Models.TTS_CONFIG),
                    unicodeIndexer = models.path(Models.TTS_INDEXER),
                    voiceStyle = models.path(Models.TTS_VOICES),
                ),
                numThreads = 4,
            ),
        ),
    )

    /** How many voices the model has; a voice is chosen by its index, 0 until [voiceCount]. */
    val voiceCount: Int = tts.numSpeakers()

    private val sampleRate = tts.sampleRate()

    /** Synthesis runs here, one sentence at a time. */
    private val synthThread = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "fastchat-tts")
    }.asCoroutineDispatcher()

    /**
     * Says [text] aloud and returns when it has finished playing. Cancelling cuts the audio off.
     * [speed] is a rate multiplier (1.0 is natural pace).
     */
    suspend fun speak(text: String, voice: Int, speed: Float) = withContext(synthThread) {
        val start = SystemClock.elapsedRealtime()
        val audio = tts.generateWithConfig(
            text,
            GenerationConfig(
                sid = voice.coerceIn(0, voiceCount - 1),
                speed = speed,
                numSteps = SYNTHESIS_STEPS,
                extra = mapOf("lang" to "en"),
            ),
        )
        Log.i("FastChat", "voice: ${audio.samples.size * 1000L / sampleRate} ms of audio at $sampleRate Hz, " +
            "synthesised in ${SystemClock.elapsedRealtime() - start} ms")
        ensureActive()
        play(audio.samples)
    }

    private suspend fun play(samples: FloatArray) {
        if (samples.isEmpty()) return
        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(sampleRate)
                    .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(samples.size * Float.SIZE_BYTES)
            .build()
        try {
            // The glasses are also a Bluetooth speaker, and would otherwise take the audio: the
            // reply has to come out of the phone the partner is holding.
            context.getSystemService(AudioManager::class.java)
                .getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                .firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
                ?.let(track::setPreferredDevice)

            track.write(samples, 0, samples.size, AudioTrack.WRITE_BLOCKING)
            track.play()
            val durationMs = samples.size * 1000L / sampleRate
            val deadline = System.currentTimeMillis() + durationMs + 1_000
            while (track.playbackHeadPosition < samples.size && System.currentTimeMillis() < deadline) {
                delay(20)
            }
        } finally {
            withContext(NonCancellable) {
                runCatching { track.pause() }
                track.release()
            }
        }
    }
}
