package com.natesapps.fastchat.glasses

import android.app.Activity
import android.content.Context
import android.util.Log
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.selectors.AutoDeviceSelector
import com.meta.wearable.dat.core.session.DeviceSession
import com.meta.wearable.dat.core.session.DeviceSessionState
import com.meta.wearable.dat.core.types.Device
import com.meta.wearable.dat.core.types.DeviceCompatibility
import com.meta.wearable.dat.core.types.DeviceIdentifier
import com.meta.wearable.dat.core.types.DeviceSessionError
import com.meta.wearable.dat.core.types.DonState
import com.meta.wearable.dat.core.types.LinkState
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
import com.natesapps.fastchat.core.Reply
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

/** How often to try again while registered glasses exist but no session is open. */
private const val RETRY_MS = 5_000L

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
        /** The glasses the Meta AI app has shared with FastChat, as "name: state" lines. */
        val devices: List<String> = emptyList(),
        /** What the wearer should do next when no session can be opened. */
        val hint: String? = null,
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

    /** Latest state of each pair of glasses Meta AI has shared with this app. */
    private val seen = mutableMapOf<DeviceIdentifier, Device>()
    private val metadataJobs = mutableMapOf<DeviceIdentifier, Job>()

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
            Wearables.registrationState.collect { registration ->
                if (registration != RegistrationState.REGISTERED) {
                    endSession()
                    _status.update { it.copy(stage = Stage.NOT_REGISTERED, devices = emptyList(), hint = null) }
                } else {
                    connectIfPossible()
                }
            }
        }
        // Follow every pair of glasses Meta AI shares with us. A pair shows up in the list before
        // it is linked (or while it is folded in its case), so the session can only be opened
        // once its own state says it is connected: watch that, not just the list.
        scope.launch {
            Wearables.devices.collect { ids ->
                (metadataJobs.keys - ids).forEach { gone ->
                    metadataJobs.remove(gone)?.cancel()
                    seen.remove(gone)
                }
                ids.forEach { id ->
                    metadataJobs.getOrPut(id) {
                        launch {
                            Wearables.devicesMetadata[id]?.collect { device ->
                                seen[id] = device
                                connectIfPossible()
                            }
                        }
                    }
                }
                connectIfPossible()
            }
        }
        // Some reasons a session cannot open (glasses not worn yet, busy with another app) are
        // not reported as a state change, so keep trying while there is something to connect to.
        scope.launch {
            while (true) {
                delay(RETRY_MS)
                connectIfPossible()
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

    /**
     * Opens a session if we are registered, none is open, and display glasses are connected;
     * otherwise publishes what is missing so the app can tell the wearer.
     */
    private fun connectIfPossible() {
        if (!started || Wearables.registrationState.value != RegistrationState.REGISTERED) return
        val devices = seen.values.toList()
        val described = devices.map(::describe)
        if (described != _status.value.devices) Log.i(TAG, "glasses: $described")
        _status.update { it.copy(devices = described) }
        if (session != null) return

        val displays = devices.filter { it.isDisplayCapable() }
        val hint = when {
            // The list can be ahead of the per-device state; let the toolkit decide then.
            devices.isEmpty() && Wearables.devices.value.isNotEmpty() -> null
            devices.isEmpty() ->
                "Meta AI has not shared any glasses with FastChat. In the Meta AI app, check that the glasses " +
                    "are connected and that the Device Access Toolkit is installed on them (Dev Mode)."
            displays.isEmpty() ->
                "FastChat needs Meta Ray-Ban Display glasses. Meta AI only shared: ${devices.joinToString { it.name }}."
            displays.any { it.compatibility == DeviceCompatibility.DEVICE_UPDATE_REQUIRED } ->
                "${displays.first().name} needs a firmware update in the Meta AI app."
            displays.none { it.linkState == LinkState.CONNECTED } ->
                "${displays.first().name} is not connected. Open the glasses and put them on."
            else -> null
        }
        _status.update { it.copy(hint = hint) }
        if (hint == null) connect() else setStage(Stage.NO_GLASSES)
    }

    private fun describe(device: Device): String {
        val state = buildList {
            add(if (device.linkState == LinkState.CONNECTED) "connected" else "not connected")
            if (!device.isDisplayCapable()) add("no display")
            if (device.donState == DonState.DONNED) add("on your face")
            if (device.donState == DonState.DOFFED) add("not being worn")
            if (device.compatibility == DeviceCompatibility.DEVICE_UPDATE_REQUIRED) add("needs an update")
        }
        return "${device.name}: ${state.joinToString(", ")}"
    }

    /** Tries to open a session with the first connected display-capable glasses. */
    private fun connect() {
        if (!started || session != null) return
        Wearables.createSession(AutoDeviceSelector(filter = { it.isDisplayCapable() })).fold(
            onSuccess = { created ->
                session = created
                Log.i(TAG, "session created")
                setStage(Stage.CONNECTING)
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
                        Log.i(TAG, "session $state")
                        when (state) {
                            DeviceSessionState.STARTED -> attach(created)
                            DeviceSessionState.STOPPED -> {
                                // The retry loop opens a new one when the glasses are back.
                                endSession()
                                setStage(Stage.NO_GLASSES)
                            }
                            else -> Unit
                        }
                    }
                }
                created.start()
            },
            onFailure = { error, _ ->
                setStage(Stage.NO_GLASSES)
                report("Could not start on the glasses: ${error.description}")
            },
        )
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
                            text(reply?.label() ?: "…", style = TextStyle.BODY, flexGrow = 1f, flexShrink = 1f)
                        }
                    } else if (reply != null) {
                        flexBox(
                            padding = 10,
                            background = FlexBoxBackground.CARD,
                            onClick = { _inputs.tryEmit(GlassesInput.Pick(direction)) },
                        ) {
                            text(reply.label(), style = TextStyle.BODY)
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

    /** The emoji first, so the eye can find a reply without reading it. */
    private fun Reply.label(): String = if (emoji.isEmpty()) text else "$emoji  $text"

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
