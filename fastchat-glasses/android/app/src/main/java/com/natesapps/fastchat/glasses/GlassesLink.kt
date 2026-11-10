package com.natesapps.fastchat.glasses

import android.app.Activity
import android.content.Context
import android.util.Log
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.selectors.AutoDeviceSelector
import com.meta.wearable.dat.core.session.DeviceSession
import com.meta.wearable.dat.core.session.DeviceSessionState
import com.meta.wearable.dat.core.types.DeviceSessionError
import com.meta.wearable.dat.core.types.RegistrationState
import com.meta.wearable.dat.display.Display
import com.meta.wearable.dat.display.addDisplay
import com.meta.wearable.dat.display.removeDisplay
import com.meta.wearable.dat.display.types.DisplayState
import com.meta.wearable.dat.display.views.Alignment
import com.meta.wearable.dat.display.views.ContentScope
import com.meta.wearable.dat.display.views.Direction
import com.meta.wearable.dat.display.views.FlexBoxBackground
import com.meta.wearable.dat.display.views.IconName
import com.meta.wearable.dat.display.views.TextColor
import com.meta.wearable.dat.display.views.TextStyle
import com.meta.wearable.dat.inputs.addInputs
import com.meta.wearable.dat.inputs.removeInputs
import com.meta.wearable.dat.inputs.types.InputEvent
import com.meta.wearable.dat.inputs.types.InputSource
import com.meta.wearable.dat.inputs.types.InputsConfiguration
import com.meta.wearable.dat.inputs.types.InputsError
import com.meta.wearable.dat.inputs.types.InputsState
import com.meta.wearable.dat.inputs.types.NavDirection
import com.meta.wearable.dat.mockdevice.MockDeviceKit
import com.meta.wearable.dat.mockdevice.api.GlassesModel
import com.meta.wearable.dat.mockdevice.api.MockGlasses
import com.natesapps.fastchat.core.Dpad
import com.natesapps.fastchat.core.GlassesInput
import com.natesapps.fastchat.core.GlassesScreen
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

private const val TAG = "FastChatGlasses"

/** Wait before reconnecting after the glasses end a session, so a dead link is not hammered. */
private const val RECONNECT_DELAY_MS = 3_000L

/**
 * Everything that talks to the Meta Ray-Ban Display glasses through Meta's Wearables Device Access
 * Toolkit: registration with the Meta AI app, the device session, the Display capability that
 * draws [GlassesScreen]s, and the Inputs capability that turns Neural Band (or temple touchpad)
 * swipes into [GlassesInput]s.
 *
 * Call everything from the main thread; [scope] must dispatch on it.
 *
 * Two input modes, picked automatically:
 * - **D-pad** (Inputs capability active): a swipe up/right/down/left says that reply, a pinch asks
 *   for more, back cancels. One gesture per reply.
 * - **Tap** (Inputs not granted to this app, see the README): replies are drawn as focusable
 *   cards; the wearer moves focus and taps, which the Display capability reports on its own.
 */
class GlassesLink(private val appContext: Context, private val scope: CoroutineScope) {

    enum class Stage {
        /** Bluetooth permission not granted yet, so the toolkit is not running. */
        NOT_STARTED,
        /** The app is not connected to the Meta AI app yet. */
        NOT_REGISTERED,
        /** Registered, but no display glasses are connected. */
        NO_GLASSES,
        CONNECTING,
        /** The display is up and showing our content. */
        READY,
    }

    data class Status(
        val stage: Stage = Stage.NOT_STARTED,
        /** True when d-pad swipes reach the app; false means tap mode. */
        val dpad: Boolean = false,
        val simulated: Boolean = false,
        val problem: String? = null,
    )

    private val _status = MutableStateFlow(Status())
    val status: StateFlow<Status> = _status.asStateFlow()

    private val _inputs = MutableSharedFlow<GlassesInput>(extraBufferCapacity = 16)
    val inputs: SharedFlow<GlassesInput> = _inputs.asSharedFlow()

    /** The simulated glasses, when on: the phone UI previews their display and drives their d-pad. */
    private val _mockGlasses = MutableStateFlow<MockGlasses?>(null)
    val mockGlasses: StateFlow<MockGlasses?> = _mockGlasses.asStateFlow()

    private val screen = MutableStateFlow<GlassesScreen>(GlassesScreen.Status("FastChat"))
    private val display = MutableStateFlow<Display?>(null)
    private val displayStarted = MutableStateFlow(false)

    private var started = false

    /** True once the toolkit is running (after [start], or with the simulated glasses on). */
    val isStarted: Boolean get() = started

    private var session: DeviceSession? = null
    private var sessionJob: Job? = null
    private var reconnectJob: Job? = null

    /** Starts the toolkit. Needs the Bluetooth permission, so call it once that is granted. */
    fun start() {
        if (started) return
        val failure = Wearables.initialize(appContext).errorOrNull()
        if (failure != null) {
            report("Glasses toolkit failed to start: ${failure.description}")
            return
        }
        started = true
        observe()
    }

    private fun observe() {
        scope.launch {
            combine(Wearables.registrationState, Wearables.devices) { registration, devices ->
                registration to devices
            }.collect { (registration, devices) ->
                if (registration != RegistrationState.REGISTERED) {
                    endSession()
                    setStage(Stage.NOT_REGISTERED)
                } else if (session == null) {
                    if (devices.isEmpty()) setStage(Stage.NO_GLASSES) else connect()
                }
            }
        }
        scope.launch {
            Wearables.registrationErrorStream.collect { error -> report(error.description) }
        }
        // Draw the current screen whenever it changes, and again whenever the display comes up or
        // the input mode flips (the same screen is laid out differently for d-pad and tap).
        scope.launch {
            combine(screen, display, displayStarted, status) { screen, display, up, status ->
                Triple(screen, display.takeIf { up }, status.dpad)
            }.distinctUntilChanged().conflate().collect { (screen, display, dpad) ->
                display ?: return@collect
                display.sendContent { render(screen, dpad) }.onFailure { error, _ ->
                    Log.w(TAG, "sendContent failed: ${error.description}")
                }
            }
        }
    }

    /** Opens the Meta AI app so the wearer can connect FastChat to their glasses. */
    fun register(activity: Activity) {
        if (started) Wearables.startRegistration(activity)
    }

    fun unregister(activity: Activity) {
        if (started) Wearables.startUnregistration(activity)
    }

    /** Shows [next] on the glasses (now, or as soon as the display is up). */
    fun show(next: GlassesScreen) {
        screen.value = next
    }

    /** Tries to open a session with the first connected display-capable glasses. */
    fun connect() {
        if (!started || session != null) return
        reconnectJob?.cancel()
        setStage(Stage.CONNECTING)
        Wearables.createSession(AutoDeviceSelector(filter = { it.isDisplayCapable() })).fold(
            onSuccess = { created ->
                session = created
                sessionJob = scope.launch {
                    launch {
                        created.errors.collect { error ->
                            report(
                                if (error == DeviceSessionError.DAT_APP_ON_THE_GLASSES_UPDATE_REQUIRED) {
                                    "Update the Device Access Toolkit app on the glasses (Meta AI app → Dev Mode)."
                                } else {
                                    error.description
                                },
                            )
                        }
                    }
                    created.state.collect { state ->
                        when (state) {
                            DeviceSessionState.STARTED -> attach(created)
                            DeviceSessionState.STOPPED -> {
                                endSession()
                                setStage(Stage.NO_GLASSES)
                                reconnectLater()
                            }
                            else -> Unit
                        }
                    }
                }
                created.start()
            },
            onFailure = { error, _ ->
                setStage(Stage.NO_GLASSES)
                if (error != DeviceSessionError.NO_ELIGIBLE_DEVICE) report(error.description)
            },
        )
    }

    private fun reconnectLater() {
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(RECONNECT_DELAY_MS)
            val registered = Wearables.registrationState.value == RegistrationState.REGISTERED
            if (registered && Wearables.devices.value.isNotEmpty()) connect()
        }
    }

    /** Adds the Display and Inputs capabilities; only legal once the session has STARTED. */
    private fun CoroutineScope.attach(session: DeviceSession) {
        if (display.value != null) return
        session.addDisplay().fold(
            onSuccess = { added ->
                display.value = added
                launch {
                    added.state.collect { state ->
                        val up = state == DisplayState.STARTED
                        displayStarted.value = up
                        if (up) {
                            _status.update { it.copy(stage = Stage.READY, problem = null) }
                        }
                    }
                }
            },
            onFailure = { error, _ -> report("Display unavailable: ${error.description}") },
        )

        session.addInputs(
            // The band's swipes and pinches, plus the temple touchpad as a fallback surface.
            // Back is consumed so a stray back gesture cannot end the session mid-conversation.
            InputsConfiguration(
                sources = setOf(InputSource.NEURAL_BAND, InputSource.CAPTOUCH),
                consumeBack = true,
            ),
        ).fold(
            onSuccess = { inputs ->
                launch {
                    inputs.state.collect { state ->
                        _status.update { it.copy(dpad = state == InputsState.ACTIVE) }
                    }
                }
                launch {
                    inputs.errors.collect { error ->
                        if (error == null) return@collect
                        Log.w(TAG, "inputs: ${error.description}")
                        if (error == InputsError.PERMISSION_DENIED) {
                            report("D-pad gestures are not enabled for this app yet, so replies are tap-to-pick.")
                        }
                    }
                }
                launch {
                    inputs.events.collect { event ->
                        when (event) {
                            is InputEvent.Nav -> _inputs.tryEmit(GlassesInput.Pick(event.direction.toDpad()))
                            is InputEvent.Select -> _inputs.tryEmit(GlassesInput.More)
                            is InputEvent.Back -> _inputs.tryEmit(GlassesInput.Back)
                            else -> Unit
                        }
                    }
                }
            },
            onFailure = { error, _ ->
                Log.w(TAG, "inputs would not attach: ${error.description}")
            },
        )
    }

    private fun endSession() {
        val ending = session ?: return
        session = null
        sessionJob?.cancel()
        sessionJob = null
        display.value = null
        displayStarted.value = false
        _status.update { it.copy(dpad = false) }
        if (ending.state.value != DeviceSessionState.STOPPED) {
            ending.removeInputs()
            ending.removeDisplay()
            ending.stop()
        }
    }

    /** Stops showing content and closes the session, e.g. when the app is closed. */
    fun disconnect() {
        reconnectJob?.cancel()
        endSession()
        if (started && _status.value.stage > Stage.NO_GLASSES) setStage(Stage.NO_GLASSES)
    }

    // ---- Simulated glasses -------------------------------------------------------------------

    /**
     * Swaps the real glasses for the toolkit's simulated Meta Ray-Ban Display, so the whole flow
     * can be tried on the phone alone. The simulated pair goes through exactly the same session,
     * display and inputs code as the real one.
     */
    fun setSimulated(on: Boolean) {
        if (on == (_mockGlasses.value != null)) return
        val kit = MockDeviceKit.getInstance(appContext)
        if (on) {
            disconnect()
            kit.enable() // also initialises the toolkit and reports it as registered
            if (!started) {
                started = true
                observe()
            }
            kit.pairGlasses(GlassesModel.META_RAYBAN_DISPLAY).fold(
                onSuccess = { glasses ->
                    glasses.powerOn()
                    glasses.unfold()
                    glasses.don()
                    _mockGlasses.value = glasses
                    _status.update { it.copy(simulated = true, problem = null) }
                },
                onFailure = { error, _ ->
                    kit.disable()
                    report("Simulated glasses failed to start: ${error.description}")
                },
            )
        } else {
            disconnect()
            _mockGlasses.value?.let { glasses ->
                glasses.doff()
                glasses.powerOff()
            }
            _mockGlasses.value = null
            kit.disable()
            _status.update { it.copy(simulated = false) }
        }
    }

    /** Performs [input] on the simulated glasses, as if the wearer had made the gesture. */
    fun simulate(input: GlassesInput) {
        val kit = _mockGlasses.value?.services?.input ?: return
        val band = InputSource.NEURAL_BAND
        when (input) {
            is GlassesInput.Pick -> when (input.direction) {
                Dpad.UP -> kit.navUp(band)
                Dpad.RIGHT -> kit.navRight(band)
                Dpad.DOWN -> kit.navDown(band)
                Dpad.LEFT -> kit.navLeft(band)
            }
            GlassesInput.More -> kit.select(band)
            GlassesInput.Back -> kit.back(band)
        }
    }

    // ---- Drawing -----------------------------------------------------------------------------

    private fun ContentScope.render(screen: GlassesScreen, dpad: Boolean) {
        when (screen) {
            is GlassesScreen.Status -> flexBox(
                direction = Direction.COLUMN,
                gap = 12,
                alignment = Alignment.CENTER,
                crossAlignment = Alignment.CENTER,
                padding = 24,
            ) {
                text(screen.title, style = TextStyle.HEADING)
                screen.detail?.let { text(it, style = TextStyle.BODY) }
                if (screen.offersQuickPhrases) {
                    if (dpad) {
                        text("Pinch for quick phrases", style = TextStyle.META, color = TextColor.SECONDARY)
                    } else {
                        button("Quick phrases", onClick = { _inputs.tryEmit(GlassesInput.More) })
                    }
                }
            }

            is GlassesScreen.Choices -> flexBox(direction = Direction.COLUMN, gap = 8, padding = 12) {
                screen.heard?.let { text("“$it”", style = TextStyle.META, color = TextColor.SECONDARY) }
                screen.replies.forEachIndexed { slot, reply ->
                    val direction = Dpad.entries[slot]
                    if (dpad) {
                        flexBox(
                            direction = Direction.ROW,
                            gap = 12,
                            crossAlignment = Alignment.CENTER,
                            padding = 10,
                            background = FlexBoxBackground.CARD,
                        ) {
                            icon(direction.caret())
                            text(reply ?: "…", style = TextStyle.BODY, flexGrow = 1f, flexShrink = 1f)
                        }
                    } else if (reply != null) {
                        flexBox(
                            padding = 10,
                            background = FlexBoxBackground.CARD,
                            onClick = { _inputs.tryEmit(GlassesInput.Pick(direction)) },
                        ) {
                            text(reply, style = TextStyle.BODY)
                        }
                    }
                }
                val hint = when {
                    !screen.done -> "Writing replies…"
                    !dpad -> null
                    screen.quick -> "Swipe to say · Pinch to go back"
                    else -> "Swipe to say · Pinch for more"
                }
                hint?.let { text(it, style = TextStyle.META, color = TextColor.SECONDARY) }
                if (!dpad && screen.done) {
                    button(if (screen.quick) "Back" else "More replies", onClick = { _inputs.tryEmit(GlassesInput.More) })
                }
            }
        }
    }

    private fun Dpad.caret(): IconName = when (this) {
        Dpad.UP -> IconName.CARET_UP
        Dpad.RIGHT -> IconName.CARET_RIGHT
        Dpad.DOWN -> IconName.CARET_DOWN
        Dpad.LEFT -> IconName.CARET_LEFT
    }

    private fun NavDirection.toDpad(): Dpad = when (this) {
        NavDirection.UP -> Dpad.UP
        NavDirection.RIGHT -> Dpad.RIGHT
        NavDirection.DOWN -> Dpad.DOWN
        NavDirection.LEFT -> Dpad.LEFT
    }

    private fun setStage(stage: Stage) {
        _status.update { it.copy(stage = stage) }
    }

    private fun report(problem: String) {
        Log.w(TAG, problem)
        _status.update { it.copy(problem = problem) }
    }
}
