package com.natesapps.fastchat.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.VolumeOff
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.natesapps.fastchat.FastChat
import com.natesapps.fastchat.Settings
import com.natesapps.fastchat.core.Dpad
import com.natesapps.fastchat.core.GlassesInput
import com.natesapps.fastchat.core.Phase
import com.natesapps.fastchat.core.State
import com.natesapps.fastchat.glasses.GlassesLink
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun FastChatScreen(
    fastChat: FastChat,
    onStart: () -> Unit,
    onConnectGlasses: () -> Unit,
    onDisconnectGlasses: () -> Unit,
) {
    val setup by fastChat.setup.collectAsStateWithLifecycle()
    val settings by fastChat.settings.settings.collectAsStateWithLifecycle()
    val glasses by fastChat.glasses.status.collectAsStateWithLifecycle()
    var showSettings by rememberSaveable { mutableStateOf(false) }
    BackHandler(enabled = showSettings) { showSettings = false }

    Surface(color = Ink, modifier = Modifier.fillMaxSize()) {
        BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding(), contentAlignment = Alignment.TopCenter) {
            // On a wide screen (landscape, or the Fold opened) the simulated glasses sit beside
            // the conversation instead of squeezing it.
            val sideBySide = glasses.simulated && !showSettings && setup == FastChat.Setup.Ready && maxWidth >= 600.dp
            Box(
                Modifier.widthIn(max = if (sideBySide) 1040.dp else 560.dp).fillMaxSize()
                    .padding(horizontal = 24.dp, vertical = 16.dp),
            ) {
                when {
                    showSettings -> SettingsScreen(
                        fastChat = fastChat,
                        settings = settings,
                        glasses = glasses,
                        onBack = { showSettings = false },
                        onConnectGlasses = onConnectGlasses,
                        onDisconnectGlasses = onDisconnectGlasses,
                    )
                    setup == FastChat.Setup.Ready -> TalkScreen(
                        fastChat = fastChat,
                        name = settings.name.trim(),
                        glasses = glasses,
                        sideBySide = sideBySide,
                        onStart = onStart,
                        onSettings = { showSettings = true },
                    )
                    else -> SetupScreen(setup, onDownload = fastChat::download, onRetry = fastChat::load)
                }
            }
        }
    }
}

// ---- Setup -----------------------------------------------------------------------------------

@Composable
private fun SetupScreen(setup: FastChat.Setup, onDownload: () -> Unit, onRetry: () -> Unit) {
    Column(
        Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
    ) {
        Text("FastChat Glasses", style = MaterialTheme.typography.displaySmall)
        when (setup) {
            is FastChat.Setup.NeedsDownload -> {
                Text(
                    "Everything runs on this phone: listening, writing replies and speaking. " +
                        "Nothing said in a conversation leaves it.",
                    style = MaterialTheme.typography.bodyLarge,
                )
                Text(
                    "First it needs to download its models, ${gigabytes(setup.missingBytes)}. Use Wi-Fi.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = Muted,
                )
                setup.problem?.let { Text(it, color = Alert, style = MaterialTheme.typography.bodyMedium) }
                Button(onClick = onDownload, modifier = Modifier.fillMaxWidth().height(56.dp)) {
                    Text(if (setup.problem == null) "Download models" else "Try again")
                }
            }

            is FastChat.Setup.Downloading -> {
                Text("Downloading models", style = MaterialTheme.typography.titleLarge)
                LinearProgressIndicator(
                    progress = { if (setup.totalBytes > 0) setup.doneBytes.toFloat() / setup.totalBytes else 0f },
                    modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)),
                    trackColor = Line,
                )
                Text(
                    "${gigabytes(setup.doneBytes)} of ${gigabytes(setup.totalBytes)}. " +
                        "You can leave this screen; the download picks up where it stopped.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Muted,
                )
            }

            is FastChat.Setup.Loading -> Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                CircularProgressIndicator(Modifier.size(28.dp), strokeWidth = 3.dp)
                Text("Loading: ${setup.what}", style = MaterialTheme.typography.bodyLarge)
            }

            is FastChat.Setup.LoadFailed -> {
                Text("The models could not be loaded.", style = MaterialTheme.typography.titleLarge)
                Text(setup.problem, color = Alert, style = MaterialTheme.typography.bodyMedium)
                Button(onClick = onRetry, modifier = Modifier.fillMaxWidth().height(56.dp)) { Text("Try again") }
            }

            FastChat.Setup.Ready -> Unit
        }
    }
}

// ---- Talk ------------------------------------------------------------------------------------

/** The screen the conversation partner sees while holding the phone. */
@Composable
private fun TalkScreen(
    fastChat: FastChat,
    name: String,
    glasses: GlassesLink.Status,
    sideBySide: Boolean,
    onStart: () -> Unit,
    onSettings: () -> Unit,
) {
    val conversation by fastChat.conversation.collectAsStateWithLifecycle()
    val hearing by fastChat.hearingSpeech.collectAsStateWithLifecycle()
    val running = conversation.phase != Phase.Off

    Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
        Column(Modifier.weight(1f).fillMaxHeight()) {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                GlassesChip(glasses, onClick = onSettings, modifier = Modifier.weight(1f, fill = false))
                IconButton(onClick = onSettings) {
                    Icon(Icons.Default.Settings, contentDescription = "Settings", tint = Muted)
                }
            }

            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                PhaseView(conversation, name, hearing)
            }

            conversation.problem?.let {
                Text(it, color = Alert, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(bottom = 12.dp))
            }
            (glasses.hint ?: glasses.problem.takeIf { glasses.stage != GlassesLink.Stage.READY })?.let {
                Text(it, color = Alert, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(bottom = 12.dp))
            }
            if (glasses.simulated && !sideBySide) SimulatedGlasses(fastChat, Modifier.fillMaxWidth().padding(bottom = 16.dp))
            VolumeControl(fastChat, Modifier.padding(bottom = 8.dp))

            if (running) {
                OutlinedButton(onClick = fastChat::stop, modifier = Modifier.fillMaxWidth().height(56.dp)) { Text("Pause") }
            } else {
                Button(onClick = onStart, modifier = Modifier.fillMaxWidth().height(64.dp)) {
                    Text("Start conversation", style = MaterialTheme.typography.titleLarge)
                }
            }
        }
        if (sideBySide) SimulatedGlasses(fastChat, Modifier.width(340.dp).align(Alignment.CenterVertically))
    }
}

@Composable
private fun PhaseView(conversation: State, name: String, hearing: Boolean) {
    val who = name.ifEmpty { "I" }
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        when (val phase = conversation.phase) {
            Phase.Off -> {
                Text("FastChat", style = MaterialTheme.typography.displaySmall)
                Text(
                    "Press Start, then hand this phone to the person you are talking with.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = Muted,
                    textAlign = TextAlign.Center,
                )
            }

            Phase.Listening -> {
                MicOrb(hearing)
                Text(
                    if (name.isEmpty()) "Go ahead, I'm listening" else "Talk to $name",
                    style = MaterialTheme.typography.displaySmall,
                    textAlign = TextAlign.Center,
                )
                Text(
                    "Speak normally. $who will answer through this phone.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = Muted,
                    textAlign = TextAlign.Center,
                )
            }

            is Phase.Choosing -> {
                phase.heard?.let {
                    Text("“$it”", style = MaterialTheme.typography.bodyLarge, color = Muted, textAlign = TextAlign.Center)
                }
                Text(
                    if (name.isEmpty()) "Choosing a reply…" else "$name is choosing a reply…",
                    style = MaterialTheme.typography.headlineMedium,
                    textAlign = TextAlign.Center,
                )
            }

            is Phase.Speaking -> Text(
                phase.text,
                style = MaterialTheme.typography.displaySmall,
                color = Signal,
                textAlign = TextAlign.Center,
            )
        }
    }
}

@Composable
private fun MicOrb(hearing: Boolean) {
    val scale by animateFloatAsState(if (hearing) 1.15f else 1f, label = "mic")
    Box(
        Modifier.size(112.dp).scale(scale).clip(CircleShape).background(if (hearing) Signal else Panel)
            .border(2.dp, if (hearing) Signal else Line, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            Icons.Default.Mic,
            contentDescription = if (hearing) "Hearing speech" else "Waiting for speech",
            tint = if (hearing) Ink else Muted,
            modifier = Modifier.size(48.dp),
        )
    }
}

@Composable
private fun GlassesChip(glasses: GlassesLink.Status, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val ready = glasses.stage == GlassesLink.Stage.READY
    Row(
        modifier.clip(RoundedCornerShape(50)).background(Panel).clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(Modifier.size(10.dp).clip(CircleShape).background(if (ready) Signal else Alert))
        Text(glassesSummary(glasses), style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

private fun glassesSummary(glasses: GlassesLink.Status): String {
    val state = when (glasses.stage) {
        GlassesLink.Stage.NOT_STARTED, GlassesLink.Stage.NOT_REGISTERED -> "Glasses not connected"
        GlassesLink.Stage.NO_GLASSES -> "No glasses in range"
        GlassesLink.Stage.CONNECTING -> "Connecting to glasses…"
        GlassesLink.Stage.READY -> if (glasses.dpad) "Glasses ready · swipe to pick" else "Glasses ready · tap to pick"
    }
    return if (glasses.simulated) "Simulated · $state" else state
}

/** The simulated glasses: what their display shows, and buttons standing in for the band. */
@Composable
private fun SimulatedGlasses(fastChat: FastChat, modifier: Modifier = Modifier) {
    val mock by fastChat.glasses.mockGlasses.collectAsStateWithLifecycle()
    Row(
        modifier.clip(RoundedCornerShape(20.dp)).background(Panel).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(170.dp).clip(RoundedCornerShape(12.dp)).background(Ink)) {
            mock?.let { glasses ->
                key(glasses) {
                    AndroidView(
                        factory = { context -> glasses.services.display.createPreviewView(context) },
                        modifier = Modifier.fillMaxSize(),
                    )
                }
            }
        }
        Column(
            Modifier.weight(1f),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            val swipe = { direction: Dpad -> fastChat.glasses.simulate(GlassesInput.Highlight(direction)) }
            PadKey("▲", "Swipe up") { swipe(Dpad.UP) }
            Row(horizontalArrangement = Arrangement.spacedBy(40.dp)) {
                PadKey("◀", "Swipe left") { swipe(Dpad.LEFT) }
                PadKey("▶", "Swipe right") { swipe(Dpad.RIGHT) }
            }
            PadKey("▼", "Swipe down") { swipe(Dpad.DOWN) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = { fastChat.glasses.simulate(GlassesInput.Turn(clockwise = false)) }) { Text("⟲") }
                TextButton(onClick = { fastChat.glasses.simulate(GlassesInput.Confirm) }) { Text("Tap") }
                TextButton(onClick = { fastChat.glasses.simulate(GlassesInput.Turn(clockwise = true)) }) { Text("⟳") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = { fastChat.glasses.simulate(GlassesInput.Back) }) { Text("Back") }
            }
        }
    }
}

@Composable
private fun PadKey(glyph: String, description: String, onClick: () -> Unit) {
    Box(
        Modifier.size(44.dp).clip(CircleShape).background(Line).clickable(onClickLabel = description, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Text(glyph, color = Paper) }
}

// ---- Settings --------------------------------------------------------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SettingsScreen(
    fastChat: FastChat,
    settings: Settings,
    glasses: GlassesLink.Status,
    onBack: () -> Unit,
    onConnectGlasses: () -> Unit,
    onDisconnectGlasses: () -> Unit,
) {
    val voiceCount by fastChat.voiceCount.collectAsStateWithLifecycle()
    val stats by fastChat.lastStats.collectAsStateWithLifecycle()
    val update = fastChat.settings::update

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
            Text("Settings", style = MaterialTheme.typography.titleLarge)
        }

        Section("About you")
        OutlinedTextField(
            value = settings.name,
            onValueChange = { name -> update { it.copy(name = name) } },
            label = { Text("Your name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = settings.about,
            onValueChange = { about -> update { it.copy(about = about) } },
            label = { Text("About you") },
            supportingText = { Text("Your age, work, family, pets, what you like. Used only when someone asks about you. This never leaves the phone.") },
            minLines = 3,
            modifier = Modifier.fillMaxWidth(),
        )

        Section("Voice")
        if (voiceCount > 0) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                repeat(voiceCount) { index ->
                    FilterChip(
                        selected = settings.voice == index,
                        onClick = { update { it.copy(voice = index) }; fastChat.previewVoice() },
                        label = { Text("Voice ${index + 1}") },
                    )
                }
            }
        } else {
            Text("Voices appear once the models have loaded.", color = Muted, style = MaterialTheme.typography.bodyMedium)
        }
        Text("Speaker volume", style = MaterialTheme.typography.bodyMedium)
        VolumeControl(fastChat, playSample = true)
        Text("Speed: ${String.format(Locale.US, "%.1f", settings.speed)}×", style = MaterialTheme.typography.bodyMedium)
        Slider(
            value = settings.speed,
            onValueChange = { speed -> update { it.copy(speed = speed) } },
            valueRange = 0.7f..1.5f,
            steps = 7,
        )
        OutlinedButton(onClick = fastChat::previewVoice, enabled = voiceCount > 0) { Text("Play a sample") }

        Section("Glasses")
        Text(glassesSummary(glasses), style = MaterialTheme.typography.bodyLarge)
        glasses.devices.forEach { Text(it, color = Muted, style = MaterialTheme.typography.bodyMedium) }
        glasses.hint?.let { Text(it, color = Alert, style = MaterialTheme.typography.bodyMedium) }
        glasses.problem?.let { Text(it, color = Alert, style = MaterialTheme.typography.bodyMedium) }
        if (!glasses.simulated) {
            val registered = glasses.stage > GlassesLink.Stage.NOT_REGISTERED
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (registered) {
                    OutlinedButton(onClick = onDisconnectGlasses) { Text("Disconnect from Meta AI") }
                } else {
                    Button(onClick = onConnectGlasses) { Text("Connect through Meta AI") }
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Tick when the highlight moves", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "A soft click in the glasses' speakers, heard only by you. Apps cannot make the band vibrate.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Muted,
                )
            }
            Switch(checked = settings.tick, onCheckedChange = { on -> update { it.copy(tick = on) } })
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Simulated glasses", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Try the whole flow on the phone, with the display and d-pad on screen.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Muted,
                )
            }
            Switch(
                checked = settings.simulatedGlasses,
                onCheckedChange = { on -> update { it.copy(simulatedGlasses = on) } },
            )
        }

        stats?.let {
            Section("Last replies")
            Text(
                "${it.outputTokens} tokens at ${String.format(Locale.US, "%.1f", it.tokensPerSecond)} per second, " +
                    "after ${String.format(Locale.US, "%.1f", it.promptMs / 1000f)} s reading the conversation.",
                style = MaterialTheme.typography.bodyMedium,
                color = Muted,
            )
        }
        Spacer(Modifier.height(24.dp))
    }
}

/**
 * How loud the voice is from the phone's speaker. It is the app's own control because the phone's
 * volume keys move the glasses' volume while they are connected.
 */
@Composable
private fun VolumeControl(fastChat: FastChat, modifier: Modifier = Modifier, playSample: Boolean = false) {
    val settings by fastChat.settings.settings.collectAsStateWithLifecycle()
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(
            if (settings.volume == 0f) Icons.AutoMirrored.Filled.VolumeOff else Icons.AutoMirrored.Filled.VolumeUp,
            contentDescription = "Speaker volume",
            tint = Muted,
        )
        Slider(
            value = settings.volume,
            onValueChange = { volume -> fastChat.settings.update { it.copy(volume = volume) } },
            onValueChangeFinished = { if (playSample) fastChat.previewVoice() },
            modifier = Modifier.weight(1f),
        )
        Text("${(settings.volume * 100).roundToInt()}%", style = MaterialTheme.typography.bodyMedium, color = Muted)
    }
}

@Composable
private fun Section(title: String) {
    Text(title, style = MaterialTheme.typography.labelLarge, color = Signal, modifier = Modifier.padding(top = 16.dp))
}

private fun gigabytes(bytes: Long): String = String.format(Locale.US, "%.1f GB", bytes / 1e9)
