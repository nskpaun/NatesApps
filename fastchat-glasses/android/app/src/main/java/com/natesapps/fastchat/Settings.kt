package com.natesapps.fastchat

import android.content.Context
import androidx.core.content.edit
import com.natesapps.fastchat.core.Persona
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** The wearer's choices, kept in SharedPreferences. */
data class Settings(
    val name: String = "",
    val about: String = "",
    /** Speaker id of the text-to-speech voice. */
    val voice: Int = DEFAULT_VOICE,
    /** Speaking rate; 1.0 is the voice's natural pace. */
    val speed: Float = 1.0f,
    /** Use the toolkit's simulated glasses instead of a real pair. */
    val simulatedGlasses: Boolean = false,
) {
    val persona: Persona get() = Persona(name, about)

    companion object {
        const val DEFAULT_VOICE = 0
    }
}

class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    private val _settings = MutableStateFlow(read())
    val settings: StateFlow<Settings> = _settings.asStateFlow()

    fun update(change: (Settings) -> Settings) {
        val next = change(_settings.value)
        _settings.value = next
        prefs.edit {
            putString("name", next.name)
            putString("about", next.about)
            putInt("voice", next.voice)
            putFloat("speed", next.speed)
            putBoolean("simulatedGlasses", next.simulatedGlasses)
        }
    }

    private fun read() = Settings(
        name = prefs.getString("name", "").orEmpty(),
        about = prefs.getString("about", "").orEmpty(),
        voice = prefs.getInt("voice", Settings.DEFAULT_VOICE),
        speed = prefs.getFloat("speed", 1.0f),
        simulatedGlasses = prefs.getBoolean("simulatedGlasses", false),
    )
}
