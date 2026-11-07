package com.natesapps.nightarray

import androidx.activity.compose.BackHandler
import androidx.compose.animation.*
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.systemGestureExclusion
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.roundToInt

private val PANEL_TABS = listOf("view" to "View", "finish" to "Finish", "tools" to "Tools", "dock" to "Dock", "parts" to "Parts")

@Composable
fun StudioScreen(app: AppState, scene: Scene) {
    val host = app.host
    // Only a group scene.json knows opens the sheet; Back closes it before leaving the Studio.
    val sheet = host.picked?.let { scene.group(it) }
    BackHandler(enabled = sheet != null) { host.closeSheet() }
    BoxWithConstraints(Modifier.fillMaxSize().background(C.bg).testTag("studio")) {
        val wide = maxWidth > maxHeight && maxWidth >= 600.dp
        // Panels scale with the screen so the model always keeps roughly half of it, even on small phones.
        val sheetMax = (maxHeight * .5f).coerceIn(220.dp, 380.dp)
        val panelMax = (maxHeight * .34f).coerceIn(150.dp, 268.dp)
        if (wide) {
            Row(Modifier.fillMaxSize()) {
                Stage(app, scene, Modifier.weight(1f).fillMaxHeight(), wide = true)
                Box(Modifier.width(1.dp).fillMaxHeight().background(C.line))
                Column(Modifier.width(352.dp).fillMaxHeight().background(C.panel).statusBarsPadding().navigationBarsPadding()) {
                    AnimatedContent(sheet, transitionSpec = { fadeIn(tween(260)) togetherWith fadeOut(tween(160)) }, label = "side") { g ->
                        if (g != null) PartSheet(app, scene, g, Modifier.fillMaxSize(), handle = false)
                        else Column(Modifier.fillMaxSize()) {
                            ModeBar(app, Modifier.padding(horizontal = 14.dp).padding(top = 12.dp, bottom = 4.dp))
                            PanelTabs(app, collapsible = false)
                            Hairline()
                            val scroll = rememberScrollState()
                            Box(Modifier.weight(1f)) {
                                Column(Modifier.fillMaxSize().verticalScroll(scroll).padding(18.dp)) {
                                    PanelContent(app, scene, app.studioPanel ?: "view")
                                }
                                MoreBelow(scroll, C.panel)
                            }
                        }
                    }
                }
            }
        } else {
            Column(Modifier.fillMaxSize()) {
                Stage(app, scene, Modifier.weight(1f).fillMaxWidth(), wide = false)
                AnimatedContent(
                    sheet, transitionSpec = { (slideInVertically { it / 3 } + fadeIn(tween(240))) togetherWith fadeOut(tween(140)) using SizeTransform(clip = true) },
                    label = "dock",
                ) { g ->
                    if (g != null) PartSheet(app, scene, g, Modifier.fillMaxWidth().background(C.panel).heightIn(max = sheetMax), handle = true)
                    else ControlDock(app, scene, panelMax)
                }
            }
        }
    }
}

/** The 3D view: the matching still underneath, the shared WebView on top, and light chrome over both. */
@Composable
private fun Stage(app: AppState, scene: Scene, modifier: Modifier, wide: Boolean) {
    val host = app.host
    val st = host.state
    val ready = host.status == LiveStatus.Ready
    // The still and the live frame don't frame the station identically, so a long cross-fade (against the canvas'
    // .65 s fade-in in index.html) shows two stations at once. A short linear fade-out roughly halves that overlap
    // without dipping to black; going back to the still (an error) stays gentle.
    val stillA by animateFloatAsState(if (ready) 0f else 1f, if (ready) tween(280, easing = LinearEasing) else tween(450), label = "still")
    // In the phone layout the stage runs edge to edge, and a one-finger horizontal drag orbits: keep a drag that
    // starts at a screen edge from being taken as system Back (the vertical middle band, where the model sits; the
    // system honours at most 200 dp per edge, so Back still works above and below it). Where the stage doesn't reach a
    // screen edge (the wide layout, between the rail and the panel) this is a no-op, so it isn't limited to the phone
    // layout: a split-screen window can get the wide Studio without the side rail.
    val exclusionMax = with(LocalDensity.current) { 200.dp.toPx() }
    Box(modifier.background(C.bg)) {
        if (stillA > 0.01f) {
            val ctx = LocalContext.current
            val names = stillsFor(st, host.lastCamera, host.dockStep)
            val path = remember(names) { firstExisting(ctx, names.map { "renders/$it" }) }
            Crossfade(path, Modifier.fillMaxSize().graphicsLayer { alpha = stillA }, animationSpec = tween(450), label = "stillx") { p ->
                // (nearly) the whole station stays in view, as the live renderer frames it
                Still(listOf(p?.removePrefix("renders/") ?: names.first()), Modifier.fillMaxSize(), contentScale = CoverWidth(.85f), sketchMode = st.mode,
                    sketchHighlight = st.isolate ?: st.selected, sketchFinish = st.finish, sketchDockStep = host.dockStep,
                    description = "Still render matching the current view")
            }
        }
        ViewerSlot(host, Modifier.fillMaxSize().systemGestureExclusion { c ->
            val h = c.size.height.toFloat()
            val band = minOf(h * .6f, exclusionMax)
            Rect(0f, h / 2 - band / 2, c.size.width.toFloat(), h / 2 + band / 2)
        }.testTag("viewer"))
        // top scrim for legibility of the chrome
        Box(Modifier.fillMaxWidth().height(150.dp).background(Brush.verticalGradient(listOf(C.bg.copy(alpha = .8f), Color.Transparent))))
        Column(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Tracked("Studio", size = 14.sp, tracking = .3f)
                    Spacer(Modifier.height(4.dp))
                    StatusLine(host)
                }
                IconCircle(Icons.Outlined.RestartAlt, "Reset view", { host.resetView() }, Modifier.testTag("reset"))
                Spacer(Modifier.width(10.dp))
                IconCircle(Icons.Outlined.DarkMode, "Night shift", { app.startNight() }, Modifier.testTag("studio-night"))
            }
            st.isolate?.let { iso ->
                Spacer(Modifier.height(10.dp))
                Notice("Isolated · ${scene.group(iso)?.name ?: prettyId(iso)}", Modifier.testTag("isolate-notice"), action = "Show all") { host.setIsolate(null) }
            }
        }
        Column(Modifier.align(Alignment.BottomStart).padding(start = 14.dp, end = 14.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (!wide) DockStepBadge(host, scene, Modifier)
            LiveNotice(app)
        }
    }
}

/** Work / Stow / Standalone: the primary control, always in reach. */
@Composable
private fun ModeBar(app: AppState, modifier: Modifier = Modifier) {
    Segmented(MODE_TABS, app.host.state.mode, { app.host.setMode(it) }, modifier.fillMaxWidth(), tagPrefix = "mode")
}

@Composable
private fun StatusLine(host: ViewerHost) {
    val (dot, text) = when (host.status) {
        LiveStatus.Ready -> C.amber to "Live · ${modeLabel(host.state.mode)} · ${STYLES.first { it.first == host.state.style }.second}"
        LiveStatus.Loading, LiveStatus.Idle -> C.muted to "Still · live view loading"
        LiveStatus.Error -> C.warn to "Still image"
    }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.testTag("status-line")) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(dot))
        Spacer(Modifier.width(7.dp))
        MicroLabel(text, color = C.muted, tracking = .22f, maxLines = 1, weight = FontWeight.Light, fitToWidth = true)
    }
}

private fun modeLabel(m: String) = MODE_TABS.firstOrNull { it.first == m }?.second ?: m

@Composable
private fun LiveNotice(app: AppState) {
    val host = app.host
    val ctx = LocalContext.current
    // A page that loads but never reports `ready` (a stalled GPU process, a viewer bug) gets a way out after a while.
    var slow by remember { mutableStateOf(false) }
    // keyed on the load too: Retry goes Loading → Loading within one click, and must restart the wait
    LaunchedEffect(host.status, host.loadGeneration) { slow = false; if (host.status == LiveStatus.Loading) { kotlinx.coroutines.delay(20_000); slow = true } }
    AnimatedVisibility(host.status == LiveStatus.Error || host.status == LiveStatus.Loading, enter = fadeIn(), exit = fadeOut()) {
        if (host.status == LiveStatus.Error) {
            val bundled = remember { AssetIndex.exists(ctx, "viewer/index.html") }
            Notice("Still image · ${host.errorMessage ?: "live view stopped"}", Modifier.testTag("live-notice"), dot = C.warn,
                action = if (bundled) "Retry" else null, small = true) { host.retry(ctx) }
        } else {
            Notice(if (slow) "Still image · the live view is taking a while" else "Still image · starting the live view", Modifier.testTag("live-notice"),
                dot = C.muted, small = true, action = if (slow) "Retry" else null) { host.retry(ctx) }
        }
    }
}

/** While the dock sequence plays, a small caption on the stage says which step you're watching. */
@Composable
private fun DockStepBadge(host: ViewerHost, scene: Scene, modifier: Modifier) {
    val n = dockStepNumber(host.dockStep)
    AnimatedVisibility(n > 0 && host.dockPlaying, modifier, enter = fadeIn() + slideInVertically { it / 2 }, exit = fadeOut()) {
        val step = dockUiSteps(scene).getOrNull(n - 1)
        if (step != null) Notice("${step.n} · ${step.title} — ${if (host.dockStep == "lift") scene.dockSteps.firstOrNull { it.step == "lift" }?.caption ?: step.caption else step.caption}")
    }
}

// ------------------------------------------------------------------------------------------------
// Control dock (phone): tab row always visible, content expands above it and shrinks the stage.
// ------------------------------------------------------------------------------------------------

@Composable
private fun ControlDock(app: AppState, scene: Scene, contentMax: androidx.compose.ui.unit.Dp) {
    Column(Modifier.fillMaxWidth().background(C.panel).testTag("controls")) {
        Hairline()
        ModeBar(app, Modifier.padding(horizontal = 14.dp).padding(top = 12.dp))
        AnimatedVisibility(app.studioPanel != null, enter = expandVertically(tween(280)) + fadeIn(tween(280)), exit = shrinkVertically(tween(240)) + fadeOut(tween(160))) {
            val tab = app.studioPanel ?: "view"
            val scroll = rememberScrollState()
            Box {
                Column(Modifier.fillMaxWidth().heightIn(max = contentMax).verticalScroll(scroll).padding(horizontal = 18.dp).padding(top = 16.dp, bottom = 6.dp)) {
                    AnimatedContent(tab, transitionSpec = { fadeIn(tween(220)) togetherWith fadeOut(tween(120)) }, label = "tab") { t -> Column { PanelContent(app, scene, t) } }
                }
                MoreBelow(scroll, C.panel)
            }
        }
        PanelTabs(app, collapsible = true)
    }
}

@Composable
private fun PanelTabs(app: AppState, collapsible: Boolean) {
    val cur = app.studioPanel ?: if (collapsible) null else "view"
    Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        // Equal cells while the labels fit; at large font scales each tab takes the width it needs and the row scrolls.
        BoxWithConstraints(Modifier.weight(1f)) {
            val cell = maxOf(maxWidth / PANEL_TABS.size, 56.dp)
            Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically) {
                PANEL_TABS.forEach { (id, label) ->
                    val on = cur == id
                    Column(
                        Modifier.widthIn(min = cell).heightIn(min = 52.dp).semantics { selected = on }.testTag("panel-$id").clip(RoundedCornerShape(10.dp))
                            .clickable(role = Role.Tab) { app.studioPanel = if (on && collapsible) null else id }.padding(horizontal = 4.dp, vertical = 8.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
                    ) {
                        Tracked(label, size = 10.sp, color = if (on) C.amber else C.ink.copy(alpha = .75f), weight = if (on) FontWeight.Normal else FontWeight.Light, tracking = .22f, maxLines = 1)
                        Spacer(Modifier.height(6.dp))
                        val w by androidx.compose.animation.core.animateDpAsState(if (on) 16.dp else 0.dp, tween(240), label = "tabw")
                        Box(Modifier.width(w).height(1.5.dp).background(C.amber))
                    }
                }
            }
        }
        if (collapsible) {
            val open = app.studioPanel != null
            val rot by animateFloatAsState(if (open) 180f else 0f, tween(260), label = "chev")
            IconCircle(Icons.Outlined.ExpandLess, if (open) "Hide controls" else "Show controls",
                { app.studioPanel = if (open) null else "view" }, Modifier.padding(start = 2.dp).graphicsLayer { rotationZ = rot }.testTag("panel-toggle"),
                size = 34.dp, background = C.panel2)
        }
    }
}

@Composable
private fun PanelContent(app: AppState, scene: Scene, tab: String) {
    when (tab) {
        "finish" -> FinishPanel(app)
        "tools" -> ToolsPanel(app)
        "dock" -> DockPanel(app, scene)
        "parts" -> PartsPanel(app, scene)
        else -> ViewPanel(app)
    }
}

@Composable
private fun Label(text: String, modifier: Modifier = Modifier) = MicroLabel(text, modifier.padding(bottom = 10.dp), color = C.muted, tracking = .26f, weight = FontWeight.Light)

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ViewPanel(app: AppState) {
    val host = app.host
    Label("Style")
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        STYLES.forEach { (id, label) -> Chip(label, host.state.style == id, { host.setStyle(id) }, Modifier.testTag("style-$id")) }
    }
    Spacer(Modifier.height(18.dp))
    Label("Camera")
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        CAMERAS.forEach { (id, label) -> Chip(label, host.lastCamera == id, { host.camera(id) }, Modifier.testTag("camera-$id")) }
    }
}

@Composable
private fun FinishPanel(app: AppState) {
    val host = app.host
    Label("Metal finish")
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        FINISHES.forEach { (id, label) ->
            val on = host.state.finish == id
            val shape = RoundedCornerShape(14.dp)
            Column(
                Modifier.weight(1f).semantics { selected = on }.testTag("finish-$id").clip(shape)
                    .border(1.dp, if (on) C.amber.copy(alpha = .8f) else C.line, shape).background(if (on) C.amberSoft.copy(alpha = .5f) else C.panel2.copy(alpha = .5f))
                    .clickable(role = Role.Tab) { host.setFinish(id) }.padding(10.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                BrushedSwatch(id, Modifier.fillMaxWidth().height(34.dp))
                Spacer(Modifier.height(8.dp))
                MicroLabel(label, color = if (on) C.amber else C.ink.copy(alpha = .8f), tracking = .12f, maxLines = 2,
                    align = androidx.compose.ui.text.style.TextAlign.Center, weight = FontWeight.Light)
            }
        }
    }
    Spacer(Modifier.height(18.dp))
    LabeledSlider("Amber lighting", host.state.amber, { host.setAmber(it) }, if (host.state.amber < .02f) "Off" else "${(host.state.amber * 100).roundToInt()} %",
        sliderTag = "amber-slider")
    AmberLine(Modifier.fillMaxWidth().height(14.dp), alpha = host.state.amber.coerceAtLeast(.05f))
}

@Composable
private fun ToolsPanel(app: AppState) {
    val host = app.host
    val st = host.state
    LabeledSlider("Explode", st.explode, { host.setExplode(it) }, if (st.explode < .01f) "Assembled" else "${(st.explode * 100).roundToInt()} %", sliderTag = "explode-slider")
    Spacer(Modifier.height(6.dp))
    ToggleRow("Section", st.sectionOn, { host.setSection(it) }, Modifier.testTag("section-toggle"), sub = "Cut the station open with a clipping plane")
    AnimatedVisibility(st.sectionOn) {
        Column {
            Spacer(Modifier.height(6.dp))
            Segmented(listOf("x" to "Across (X)", "z" to "Front–back (Z)"), st.sectionAxis, { host.setSection(true, axis = it) }, Modifier.fillMaxWidth(), tagPrefix = "axis")
            Spacer(Modifier.height(8.dp))
            LabeledSlider("Plane position", st.sectionT, { host.setSection(true, t = it) }, "${(st.sectionT * 100).roundToInt()} %", sliderTag = "section-slider")
        }
    }
    Hairline(Modifier.padding(vertical = 4.dp))
    ToggleRow("Dimensions", st.dims, { host.setDims(it) }, Modifier.testTag("dims-toggle"), sub = "Overall size, display, seam, work offset")
    ToggleRow("Auto-rotate", st.autorotate, { host.setAutorotate(it) }, Modifier.testTag("autorotate-toggle"))
    Spacer(Modifier.height(10.dp))
    Label("Render quality")
    Segmented(QUALITIES, st.quality, { host.setQuality(it) }, Modifier.fillMaxWidth(), tagPrefix = "quality")
    Spacer(Modifier.height(8.dp))
}

@Composable
private fun DockPanel(app: AppState, scene: Scene) {
    val host = app.host
    val active = dockStepNumber(host.dockStep)
    val steps = dockUiSteps(scene)
    Label("Docking sequence")
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("dock-panel")) {
        steps.forEach { s ->
            val on = s.n == active
            val shape = RoundedCornerShape(14.dp)
            val bg by androidx.compose.animation.animateColorAsState(if (on) C.amberSoft else C.panel2.copy(alpha = .6f), tween(260), label = "ds")
            val bc by androidx.compose.animation.animateColorAsState(if (on) C.amber.copy(alpha = .85f) else C.line, tween(260), label = "dsb")
            Column(
                Modifier.weight(1f).heightIn(min = 92.dp).semantics { selected = on }.testTag("dock-step-${s.id}").clip(shape).background(bg).border(1.dp, bc, shape)
                    .clickable(role = Role.Button) {
                        // step 3 is "press-release & lift": a second tap lifts the laptop out
                        host.dock(if (s.n == 3 && host.dockStep == "release") "lift" else s.id)
                    }.padding(10.dp),
            ) {
                Text("${s.n}", color = if (on) C.amber else C.muted, fontSize = 20.sp, fontWeight = FontWeight.Light)
                Spacer(Modifier.height(4.dp))
                DockStepTitle(s.title, color = if (on) C.ink else C.ink.copy(alpha = .8f))
            }
        }
    }
    Spacer(Modifier.height(12.dp))
    val caption = when {
        host.dockStep == "lift" -> scene.dockSteps.firstOrNull { it.step == "lift" }?.caption ?: "Laptop free; compute stays in the base"
        active > 0 -> steps[active - 1].caption
        host.dockPlaying -> "Starting…"
        else -> "Tap a step, or play the whole sequence."
    }
    Text(caption, color = if (active > 0) C.ink else C.muted, fontSize = 13.5.sp, lineHeight = 19.sp, modifier = Modifier.testTag("dock-caption"))
    Spacer(Modifier.height(14.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        LineButton(if (host.dockPlaying) "Playing…" else "Play sequence", { if (!host.dockPlaying) { host.camera("dock"); host.dock("play") } },
            Modifier.testTag("dock-play"), filled = true, enabled = !host.dockPlaying,
            leading = { Icon(Icons.Outlined.PlayArrow, null, tint = C.amber, modifier = Modifier.size(16.dp)) })
        LineButton("Reset", { host.dock("reset") }, Modifier.testTag("dock-reset"), color = C.ink.copy(alpha = .75f))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PartsPanel(app: AppState, scene: Scene) {
    val host = app.host
    Label("Tap a part group, or tap the model")
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        scene.groups.forEach { g ->
            Chip(g.name, host.state.selected == g.id, { host.pickLocal(g.id) }, Modifier.testTag("part-${g.id}"),
                leading = { Swatch(g.materials.firstOrNull() ?: "titanium", 10.dp) })
        }
    }
}

// ------------------------------------------------------------------------------------------------
// Part sheet: shown when the viewer reports a pick (or a group is chosen in Parts).
// ------------------------------------------------------------------------------------------------

/**
 * The details scroll; the actions stay pinned at the bottom, so Isolate / Frame / Files are always in reach on short
 * screens. [handle]: the phone's bottom sheet gets a grab handle that closes it on a downward drag.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PartSheet(app: AppState, scene: Scene, g: Group, modifier: Modifier, handle: Boolean) {
    val host = app.host
    val isolated = host.state.isolate == g.id
    Column(modifier.testTag("part-sheet").padding(horizontal = 20.dp).padding(top = if (handle) 2.dp else 14.dp, bottom = 16.dp)) {
        if (handle) SheetHandle { host.closeSheet() }
        val scroll = rememberScrollState()
        Box(Modifier.weight(1f, fill = false)) {
            Column(Modifier.verticalScroll(scroll)) {
                if (handle) Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Kicker("Selected")
                        Spacer(Modifier.height(8.dp))
                        Tracked(g.name, size = 17.sp, tracking = .16f)
                    }
                    IconCircle(Icons.Outlined.Close, "Close part sheet", { host.closeSheet() }, size = 36.dp, background = C.panel2)
                }
                Spacer(Modifier.height(10.dp))
                Text(g.summary, color = C.ink.copy(alpha = .82f), fontSize = 14.sp, lineHeight = 20.sp)
                Spacer(Modifier.height(12.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    g.materials.forEach { m ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Swatch(m, 11.dp); Spacer(Modifier.width(6.dp))
                            Text(scene.materialLabel(m), color = C.muted, fontSize = 12.sp)
                        }
                    }
                }
                Spacer(Modifier.height(6.dp))
                SpecRow("Size", fmtBox(g.bboxMm))
                SpecRow("Mass", fmtMass(g.massG) + if (g.massG > 0) " (concept)" else "")
                val internal = scene.partsOf(g.id).count { it.internal }
                SpecRow("Parts", if (internal > 0) "${g.parts.size}, $internal internal" else "${g.parts.size}", last = true)
            }
            MoreBelow(scroll, C.panel)
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LineButton(if (isolated) "Show all" else "Isolate", { host.toggleIsolate(g.id) }, Modifier.weight(1f).testTag("sheet-isolate"), filled = true)
            LineButton("Frame", { host.frame(g.id) }, Modifier.weight(1f).testTag("sheet-frame"), color = C.ink.copy(alpha = .8f))
            LineButton("Files", { app.nav.go("group/${g.id}") }, Modifier.weight(1f).testTag("sheet-files"), color = C.ink.copy(alpha = .8f))
        }
    }
}

/** A grab handle for the phone's part sheet: drag it down to close the sheet (the close button does the same). */
@Composable
private fun SheetHandle(onDismiss: () -> Unit) {
    val threshold = with(LocalDensity.current) { 40.dp.toPx() }
    var drag by remember { mutableFloatStateOf(0f) }
    Box(
        Modifier.fillMaxWidth().height(22.dp).draggable(
            rememberDraggableState { drag += it }, Orientation.Vertical,
            onDragStarted = { drag = 0f }, onDragStopped = { if (drag > threshold) onDismiss() },
        ),
        contentAlignment = Alignment.Center,
    ) { Box(Modifier.width(36.dp).height(3.dp).clip(RoundedCornerShape(2.dp)).background(C.line)) }
}

/** A short fade at the bottom of a scrolling panel while there is more below. */
@Composable
fun BoxScope.MoreBelow(scroll: ScrollState, background: Color) {
    if (scroll.canScrollForward) Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(24.dp).background(Brush.verticalGradient(listOf(Color.Transparent, background))))
}

/**
 * A docking-step title ("Press-release & lift"): it may break after the hyphen, but never inside a word.
 * (Android's line breaker doesn't break at a hyphen unless hyphenation is on, so a zero-width space marks the spot.)
 */
@Composable
fun DockStepTitle(title: String, color: Color = C.ink, modifier: Modifier = Modifier) =
    Tracked(title.replace("-", "-\u200B"), modifier, size = Type.Micro, color = color, weight = FontWeight.Normal, tracking = .1f,
        lineBreak = androidx.compose.ui.text.style.LineBreak.Heading)
