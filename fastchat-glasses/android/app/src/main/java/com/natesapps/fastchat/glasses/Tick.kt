package com.natesapps.fastchat.glasses

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.util.Log
import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.sin

/**
 * A soft click in the glasses' own speakers each time the highlight moves to another reply.
 *
 * It stands in for a vibration: the toolkit gives apps no way to buzz the Neural Band or the
 * glasses, and the phone is in someone else's hand. The glasses are a Bluetooth speaker as well
 * as a display, so a sound sent only to them is heard by the wearer alone. If no Bluetooth
 * speaker is connected nothing is played: the tick must never come out of the phone.
 */
class Tick(context: Context) {

    private val audio = context.getSystemService(AudioManager::class.java)

    /** The click, ready to replay: built once, kept loaded so each tick starts at once. */
    private val track: AudioTrack? = runCatching {
        val samples = waveform()
        AudioTrack.Builder()
            .setAudioAttributes(
                // Media, not a "system sound": those are muted whenever the phone is on silent,
                // and media is the volume the glasses' own controls adjust.
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(SAMPLE_RATE)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(samples.size * Short.SIZE_BYTES)
            .build()
            .also { it.write(samples, 0, samples.size) }
    }.onFailure { Log.w("FastChatGlasses", "tick unavailable", it) }.getOrNull()

    /** Plays the click in the glasses. Does nothing if they are not connected as a speaker. */
    fun play() {
        val track = track ?: return
        val glasses = audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS).firstOrNull { it.type in BLUETOOTH_SPEAKERS } ?: return
        runCatching {
            track.setPreferredDevice(glasses)
            if (track.playState == AudioTrack.PLAYSTATE_PLAYING) track.stop()
            track.reloadStaticData()
            track.play()
        }
    }

    /**
     * A short, quiet click: a 1.5 kHz tone that dies away in about 25 ms, after a moment of
     * silence so a Bluetooth link waking up does not swallow its start.
     */
    private fun waveform(): ShortArray {
        val lead = SAMPLE_RATE * LEAD_MS / 1000
        val body = SAMPLE_RATE * CLICK_MS / 1000
        return ShortArray(lead + body) { index ->
            if (index < lead) return@ShortArray 0
            val t = (index - lead) / SAMPLE_RATE.toDouble()
            (sin(2 * PI * TONE_HZ * t) * exp(-t / DECAY_S) * Short.MAX_VALUE * LEVEL).toInt().toShort()
        }
    }

    private companion object {
        const val SAMPLE_RATE = 44_100
        const val LEAD_MS = 20
        const val CLICK_MS = 60
        const val TONE_HZ = 1_500.0
        const val DECAY_S = 0.012
        const val LEVEL = 0.5

        val BLUETOOTH_SPEAKERS = setOf(
            AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
            AudioDeviceInfo.TYPE_BLE_HEADSET,
            AudioDeviceInfo.TYPE_BLE_SPEAKER,
        )
    }
}
