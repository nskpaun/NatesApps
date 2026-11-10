package com.natesapps.fastchat.speech

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.SystemClock
import android.util.Log
import androidx.core.content.edit
import com.k2fsa.sherpa.onnx.GenerationConfig
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsSupertonicModelConfig
import com.natesapps.fastchat.models.ModelStore
import com.natesapps.fastchat.models.Models
import java.util.concurrent.Executors
import kotlin.math.abs
import kotlin.math.pow
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

    private val audio = context.getSystemService(AudioManager::class.java)
    private val prefs = context.getSharedPreferences("voice", Context.MODE_PRIVATE)

    init {
        // If the app was killed in the middle of a sentence, put the alarm volume back now.
        restoreAlarmVolume()
    }

    /**
     * Says [text] aloud and returns when it has finished playing. Cancelling cuts the audio off.
     * [speed] is a rate multiplier (1.0 is natural pace); [volume] runs from 0 (silent) to 1 (as
     * loud as the phone's speaker goes).
     */
    suspend fun speak(text: String, voice: Int, speed: Float, volume: Float) = withContext(synthThread) {
        val start = SystemClock.elapsedRealtime()
        val generated = tts.generateWithConfig(
            text,
            GenerationConfig(
                sid = voice.coerceIn(0, voiceCount - 1),
                speed = speed,
                numSteps = SYNTHESIS_STEPS,
                extra = mapOf("lang" to "en"),
            ),
        )
        Log.i("FastChat", "voice: ${generated.samples.size * 1000L / sampleRate} ms of audio at $sampleRate Hz, " +
            "synthesised in ${SystemClock.elapsedRealtime() - start} ms, volume $volume")
        ensureActive()
        play(fullScale(generated.samples), volume)
    }

    private suspend fun play(samples: FloatArray, volume: Float) {
        if (samples.isEmpty()) return
        val track = AudioTrack.Builder()
            .setAudioAttributes(
                // The alarm channel, not media. While the glasses are connected the phone's media
                // volume keys move the glasses' volume, so the loudspeaker's own media volume is
                // whatever it was last left at (often nearly silent) and nothing in an app can
                // change it. The alarm channel always includes the loudspeaker, its volume can be
                // set, and it is not muted by silent mode: a person's voice should not be.
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
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
            // The glasses are also a Bluetooth speaker: the reply has to come out of the phone the
            // partner is holding, and only there.
            audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                .firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
                ?.let(track::setPreferredDevice)

            // Loudness is set by the app's own volume control: open the channel fully for the
            // length of the sentence and scale the sound itself.
            raiseAlarmVolume()
            track.setVolume(gain(volume))
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
                restoreAlarmVolume()
            }
        }
    }

    /** Turns the alarm channel up to full, remembering where the wearer had it. */
    private fun raiseAlarmVolume() {
        runCatching {
            if (!prefs.contains(SAVED_ALARM_VOLUME)) {
                prefs.edit { putInt(SAVED_ALARM_VOLUME, audio.getStreamVolume(AudioManager.STREAM_ALARM)) }
            }
            audio.setStreamVolume(AudioManager.STREAM_ALARM, audio.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)
        }
    }

    private fun restoreAlarmVolume() {
        val saved = prefs.getInt(SAVED_ALARM_VOLUME, -1)
        if (saved < 0) return
        runCatching { audio.setStreamVolume(AudioManager.STREAM_ALARM, saved, 0) }
        prefs.edit { remove(SAVED_ALARM_VOLUME) }
    }

    /** Brings quiet synthesis up to full scale, so the volume control means the same every time. */
    private fun fullScale(samples: FloatArray): FloatArray {
        val peak = samples.maxOfOrNull { abs(it) } ?: return samples
        if (peak < 0.01f) return samples
        val scale = 0.95f / peak
        return FloatArray(samples.size) { samples[it] * scale }
    }

    private companion object {
        const val SAVED_ALARM_VOLUME = "alarmVolumeToRestore"

        /** The bottom of the volume control is this much quieter than the top. */
        const val VOLUME_RANGE_DB = 30f

        /** Maps the 0..1 control to a gain, in even loudness steps rather than even voltage. */
        fun gain(volume: Float): Float {
            val v = volume.coerceIn(0f, 1f)
            return if (v == 0f) 0f else 10f.pow(-VOLUME_RANGE_DB * (1f - v) / 20f)
        }
    }
}
