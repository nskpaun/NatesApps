package com.natesapps.fastchat.speech

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import android.util.Log
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineTransducerModelConfig
import com.k2fsa.sherpa.onnx.SileroVadModelConfig
import com.k2fsa.sherpa.onnx.Vad
import com.k2fsa.sherpa.onnx.VadModelConfig
import com.natesapps.fastchat.models.ModelStore
import com.natesapps.fastchat.models.Models
import kotlin.math.abs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

private const val SAMPLE_RATE = 16_000

/** Samples per read; also the window size Silero VAD expects at 16 kHz. */
private const val WINDOW = 512

/**
 * Hears the conversation partner: the phone's microphone feeds a voice-activity detector, and
 * each stretch of speech it finds is transcribed on the phone by Parakeet.
 */
class Ears(private val context: Context, models: ModelStore) {

    private val vad = Vad(
        config = VadModelConfig(
            sileroVadModelConfig = SileroVadModelConfig(
                model = models.path(Models.VAD),
                threshold = 0.5f,
                // A pause this long ends the utterance. Shorter cuts people off mid-sentence;
                // longer makes every reply feel late.
                minSilenceDuration = 0.7f,
                minSpeechDuration = 0.25f,
                windowSize = WINDOW,
                // Parakeet is at its best on clips under about 20 seconds.
                maxSpeechDuration = 20f,
            ),
            sampleRate = SAMPLE_RATE,
            numThreads = 1,
        ),
    )

    private val recognizer = OfflineRecognizer(
        config = OfflineRecognizerConfig(
            featConfig = FeatureConfig(sampleRate = SAMPLE_RATE, featureDim = 80),
            modelConfig = OfflineModelConfig(
                transducer = OfflineTransducerModelConfig(
                    encoder = models.path(Models.STT_ENCODER),
                    decoder = models.path(Models.STT_DECODER),
                    joiner = models.path(Models.STT_JOINER),
                ),
                tokens = models.path(Models.STT_TOKENS),
                modelType = "nemo_transducer",
                numThreads = 4,
            ),
        ),
    )

    private val _hearingSpeech = MutableStateFlow(false)

    /** True while someone is talking, for the phone's microphone indicator. */
    val hearingSpeech: StateFlow<Boolean> = _hearingSpeech.asStateFlow()

    /**
     * Opens the microphone and returns the next thing someone says, transcribed. Suspends until
     * there is something; cancel to stop listening. Needs the RECORD_AUDIO permission.
     */
    @SuppressLint("MissingPermission")
    suspend fun listen(): String = withContext(Dispatchers.IO) {
        val bufferBytes = maxOf(
            AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT),
            WINDOW * 2 * 8,
        )
        val recorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferBytes,
        )
        check(recorder.state == AudioRecord.STATE_INITIALIZED) { "The microphone is not available" }
        // The glasses are a Bluetooth headset too; the partner is talking to the phone.
        builtIn(AudioManager.GET_DEVICES_INPUTS, AudioDeviceInfo.TYPE_BUILTIN_MIC)?.let(recorder::setPreferredDevice)

        try {
            vad.reset()
            recorder.startRecording()
            nextUtterance(recorder) { ensureActive() }
        } finally {
            _hearingSpeech.value = false
            runCatching { recorder.stop() }
            recorder.release()
        }
    }

    /** Reads the microphone until the detector has a finished stretch of speech with words in it. */
    private fun nextUtterance(recorder: AudioRecord, checkCancelled: () -> Unit): String {
        val pcm = ShortArray(WINDOW)
        while (true) {
            checkCancelled()
            val read = recorder.read(pcm, 0, WINDOW)
            if (read < 0) error("The microphone stopped (error $read)")
            if (read == 0) continue
            vad.acceptWaveform(FloatArray(read) { pcm[it] / 32768f })
            _hearingSpeech.value = vad.isSpeechDetected()

            while (!vad.empty()) {
                val samples = vad.front().samples
                vad.pop()
                val text = transcribe(samples)
                if (text.isNotBlank()) return text
            }
        }
    }

    private fun transcribe(samples: FloatArray): String {
        val stream = recognizer.createStream()
        try {
            val start = SystemClock.elapsedRealtime()
            stream.acceptWaveform(normalised(samples), SAMPLE_RATE)
            recognizer.decode(stream)
            val text = recognizer.getResult(stream).text.trim()
            Log.i("FastChat", "heard ${samples.size * 1000L / SAMPLE_RATE} ms of speech, " +
                "transcribed in ${SystemClock.elapsedRealtime() - start} ms")
            return text
        } finally {
            stream.release()
        }
    }

    /** Parakeet does badly on very quiet audio, so quiet speech is brought up to a normal level. */
    private fun normalised(samples: FloatArray): FloatArray {
        val peak = samples.maxOfOrNull { abs(it) } ?: return samples
        if (peak < 0.01f || peak >= 0.5f) return samples // silence, or already loud enough
        val gain = 0.7f / peak
        return FloatArray(samples.size) { samples[it] * gain }
    }

    private fun builtIn(direction: Int, type: Int): AudioDeviceInfo? =
        context.getSystemService(AudioManager::class.java).getDevices(direction).firstOrNull { it.type == type }
}
