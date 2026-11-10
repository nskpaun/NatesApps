package com.natesapps.fastchat

import android.app.Application
import android.util.Log
import com.natesapps.fastchat.core.Effect
import com.natesapps.fastchat.core.Event
import com.natesapps.fastchat.core.GlassesInput
import com.natesapps.fastchat.core.State
import com.natesapps.fastchat.core.reduce
import com.natesapps.fastchat.core.screenFor
import com.natesapps.fastchat.glasses.GlassesLink
import com.natesapps.fastchat.llm.LlamaEngine
import com.natesapps.fastchat.llm.ReplyWriter
import com.natesapps.fastchat.models.ModelStore
import com.natesapps.fastchat.models.Models
import com.natesapps.fastchat.speech.Ears
import com.natesapps.fastchat.speech.Voice
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private const val TAG = "FastChat"

/**
 * The app's one long-lived object: owns the models, the glasses link and the running
 * conversation, and carries out the [Effect]s the conversation state machine asks for.
 * Everything here runs on the main thread; the heavy work is pushed to other threads inside
 * [Ears], [ReplyWriter] and [Voice].
 */
class FastChat(private val app: Application) {

    /** Where the app is on the way to being usable. */
    sealed interface Setup {
        /** Models are not on the phone yet. */
        data class NeedsDownload(val missingBytes: Long, val problem: String? = null) : Setup
        data class Downloading(val doneBytes: Long, val totalBytes: Long) : Setup
        /** Models are being loaded into memory; [what] names the one in progress. */
        data class Loading(val what: String) : Setup
        data class LoadFailed(val problem: String) : Setup
        data object Ready : Setup
    }

    private val scope = MainScope()

    val settings = SettingsStore(app)
    val models = ModelStore(File(app.getExternalFilesDir(null) ?: app.filesDir, "models"))
    val glasses = GlassesLink(app, scope)

    private val _setup = MutableStateFlow<Setup>(Setup.NeedsDownload(0))
    val setup: StateFlow<Setup> = _setup.asStateFlow()

    private val _conversation = MutableStateFlow(State())
    val conversation: StateFlow<State> = _conversation.asStateFlow()

    private val _hearingSpeech = MutableStateFlow(false)
    val hearingSpeech: StateFlow<Boolean> = _hearingSpeech.asStateFlow()

    /** Timings of the latest reply generation, shown in Settings. */
    private val _lastStats = MutableStateFlow<LlamaEngine.Stats?>(null)
    val lastStats: StateFlow<LlamaEngine.Stats?> = _lastStats.asStateFlow()

    private val _voiceCount = MutableStateFlow(0)
    val voiceCount: StateFlow<Int> = _voiceCount.asStateFlow()

    private var ears: Ears? = null
    private var writer: ReplyWriter? = null
    private var voice: Voice? = null

    private var downloadJob: Job? = null
    private var loadJob: Job? = null
    private var listenJob: Job? = null
    private var writeJob: Job? = null
    private var speakJob: Job? = null

    init {
        scope.launch { glasses.inputs.collect { dispatch(Event.Input(it)) } }
        scope.launch {
            settings.settings.map { it.simulatedGlasses }.distinctUntilChanged().collect(glasses::setSimulated)
        }
        // Re-evaluate the persona part of the prompt as soon as it changes, not on the next reply.
        scope.launch {
            settings.settings.map { it.persona }.distinctUntilChanged().collect { persona ->
                runCatching { writer?.prime(persona) }
            }
        }
        refreshSetup()
    }

    // ---- Setup -------------------------------------------------------------------------------

    private fun refreshSetup() {
        val missing = models.missing()
        if (missing.isEmpty()) load() else _setup.value = Setup.NeedsDownload(missing.sumOf { it.bytes })
    }

    fun download() {
        if (downloadJob?.isActive == true) return
        downloadJob = scope.launch {
            _setup.value = Setup.Downloading(models.presentBytes(), models.totalBytes)
            try {
                models.download { progress ->
                    _setup.value = Setup.Downloading(progress.doneBytes, progress.totalBytes)
                }
                refreshSetup()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "download failed", e)
                _setup.value = Setup.NeedsDownload(
                    models.missing().sumOf { it.bytes },
                    problem = e.message ?: "The download failed",
                )
            }
        }
    }

    /** Loads the three models into memory. Takes several seconds the first time. */
    fun load() {
        if (loadJob?.isActive == true || _setup.value == Setup.Ready) return
        loadJob = scope.launch {
            try {
                _setup.value = Setup.Loading("Speech recognition")
                val loadedEars = withContext(Dispatchers.Default) { Ears(app, models) }
                scope.launch { loadedEars.hearingSpeech.collect { _hearingSpeech.value = it } }

                _setup.value = Setup.Loading("Voice")
                val loadedVoice = withContext(Dispatchers.Default) { Voice(app, models) }

                _setup.value = Setup.Loading("Reply writer (Bonsai)")
                val loadedWriter = withContext(Dispatchers.Default) {
                    ReplyWriter(LlamaEngine.load(models.path(Models.LLM)))
                }
                loadedWriter.prime(settings.settings.value.persona)

                ears = loadedEars
                voice = loadedVoice
                writer = loadedWriter
                _voiceCount.value = loadedVoice.voiceCount
                _setup.value = Setup.Ready
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                Log.e(TAG, "loading models failed", e)
                _setup.value = Setup.LoadFailed(e.message ?: e.javaClass.simpleName)
            }
        }
    }

    // ---- Conversation ------------------------------------------------------------------------

    /** Starts listening. Does nothing until the models are loaded. */
    fun start() {
        if (_setup.value == Setup.Ready) dispatch(Event.Start)
    }

    fun stop() = dispatch(Event.Stop)

    /** A gesture made on the phone instead of the glasses (the on-screen d-pad). */
    fun input(input: GlassesInput) = dispatch(Event.Input(input))

    /**
     * Test hook (debug builds, see MainActivity): behaves as if the partner had just said [text],
     * so the reply flow can be driven from `adb` without anyone speaking.
     */
    fun debugHeard(text: String) {
        if (_setup.value != Setup.Ready) return
        listenJob?.cancel()
        dispatch(Event.Heard(text))
    }

    /** Test hook: performs [input] through the simulated glasses when they are on. */
    fun debugGesture(input: GlassesInput) {
        if (glasses.mockGlasses.value != null) glasses.simulate(input) else input(input)
    }

    private fun dispatch(event: Event) {
        val step = reduce(_conversation.value, event)
        _conversation.value = step.state
        glasses.show(screenFor(step.state))
        step.effects.forEach(::perform)
    }

    private fun perform(effect: Effect) {
        when (effect) {
            Effect.StartListening -> {
                listenJob?.cancel()
                listenJob = scope.launch {
                    try {
                        val heard = checkNotNull(ears).listen()
                        dispatch(Event.Heard(heard))
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        Log.e(TAG, "listening failed", e)
                        dispatch(Event.Problem(e.message ?: "The microphone failed"))
                        dispatch(Event.Stop)
                    }
                }
            }

            Effect.StopListening -> listenJob?.cancel()

            is Effect.Generate -> {
                writeJob?.cancel()
                writeJob = scope.launch {
                    try {
                        val persona = settings.settings.value.persona
                        checkNotNull(writer).replies(persona, effect.history, effect.avoid).collect { update ->
                            update.stats?.let {
                                _lastStats.value = it
                                Log.i(TAG, "replies: prompt ${it.promptTokens} tok in ${it.promptMs} ms" +
                                    (if (it.prefixReused) " (persona cached)" else "") +
                                    ", output ${it.outputTokens} tok in ${it.outputMs} ms = ${it.tokensPerSecond} tok/s")
                            }
                            if (update.done && update.replies.isEmpty()) {
                                dispatch(Event.GenerationFailed(effect.generation, "The model wrote no replies"))
                            } else {
                                dispatch(Event.Replies(effect.generation, update.replies, update.done))
                            }
                        }
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        Log.e(TAG, "writing replies failed", e)
                        dispatch(Event.GenerationFailed(effect.generation, e.message ?: "The model failed"))
                    }
                }
            }

            Effect.CancelGeneration -> writeJob?.cancel()

            is Effect.Speak -> {
                speakJob?.cancel()
                speakJob = scope.launch {
                    try {
                        val current = settings.settings.value
                        checkNotNull(voice).speak(effect.text, current.voice, current.speed, current.volume)
                    } catch (e: CancellationException) {
                        throw e // stopped on purpose: the state machine has already moved on
                    } catch (e: Exception) {
                        Log.e(TAG, "speaking failed", e)
                        dispatch(Event.Problem(e.message ?: "The voice failed"))
                    }
                    dispatch(Event.SpeechFinished)
                }
            }

            Effect.StopSpeaking -> speakJob?.cancel()
        }
    }

    /** Plays a sample of the chosen voice, from Settings. */
    fun previewVoice() {
        val loaded = voice ?: return
        if (speakJob?.isActive == true) return
        speakJob = scope.launch {
            val current = settings.settings.value
            runCatching { loaded.speak("Hi, this is how I sound.", current.voice, current.speed, current.volume) }
        }
    }
}
