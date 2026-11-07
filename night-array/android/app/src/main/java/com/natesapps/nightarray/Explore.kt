package com.natesapps.nightarray

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.*
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.DarkMode
import androidx.compose.material.icons.outlined.ViewInAr
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.delay
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

// =====================================================================================================
// Explore
// =====================================================================================================

@Composable
fun ExploreScreen(app: AppState, scene: Scene) {
    BoxWithConstraints(Modifier.fillMaxSize().background(C.bg)) {
        val wide = maxWidth >= 600.dp
        val pad = if (wide) 40.dp else 22.dp
        LazyColumn(Modifier.fillMaxSize().testTag("explore"), state = app.exploreList, contentPadding = PaddingValues(bottom = 40.dp)) {
            item(key = "hero") { Hero(app, wide) }
            item(key = "intro") { Intro(scene, pad) }
            item(key = "modes") { ModesSection(app, wide, pad) }
            item(key = "stories-h") { SectionHeader("Stories", "Eight ways into the station", Modifier.readable().padding(start = pad, end = pad, top = 44.dp, bottom = 18.dp)) }
            val rows = if (wide) STORIES.chunked(2) else STORIES.map { listOf(it) }
            items(rows, key = { r -> "s-" + r.joinToString { it.id } }) { row ->
                Row(Modifier.readable(980.dp).padding(horizontal = pad - 4.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { s -> StoryRow(s, Modifier.weight(1f).padding(vertical = 5.dp)) { app.nav.go("story/${s.id}") } }
                    if (row.size == 1 && wide) Spacer(Modifier.weight(1f))
                }
            }
            item(key = "dock") { DockingSection(app, scene, pad) }
            item(key = "materials") { MaterialsSection(app, pad) }
            item(key = "principles") { PrinciplesSection(wide, pad) }
            item(key = "board") { BoardCard(app, pad) }
            item(key = "night") { NightCard(app, pad) }
            item(key = "footer") { Footer(pad) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Hero(app: AppState, wide: Boolean) {
    // Window height in dp (the configuration value only until the window has been measured).
    val win = androidx.compose.ui.platform.LocalWindowInfo.current.containerSize
    val density = androidx.compose.ui.platform.LocalDensity.current
    val screenH = if (win.height > 0) with(density) { win.height.toDp().value.toInt() } else LocalConfiguration.current.screenHeightDp
    BoxWithConstraints(Modifier.fillMaxWidth().testTag("hero")) {
        val w = maxWidth
        // Tall wide screens (tablets): full-bleed render with the title over its lower part.
        // Phones and short landscape screens: the render on top, the title tucked under its fade.
        val overlay = wide && screenH >= 560
        val oneLine = w >= 600.dp
        val imgH = when {
            overlay -> (w * 9f / 16f).coerceIn(420.dp, (screenH * .92f).dp)
            wide -> (w * 9f / 16f).coerceAtMost((screenH * .8f).dp)
            else -> (w * .82f).coerceAtMost((screenH * .5f).dp.coerceAtLeast(300.dp))
        }
        val titleSize = if (overlay) 38f else 31f
        Box(Modifier.fillMaxWidth()) {
            Box(Modifier.fillMaxWidth().height(imgH)) {
                // At least 90 % of the render's width stays visible (the dock sits at its right edge); any band of night
                // this leaves goes to the bottom, under the fade.
                Still(listOf("hero-work.jpg", "hero-stow.jpg"), Modifier.fillMaxSize(), contentScale = CoverWidth(.9f),
                    alignment = Alignment.TopCenter, kenBurns = true,
                    description = "Night Array in Work mode at night", sketchMode = "work",
                    // keep the fallback drawing clear of the title block that sits over the lower part of a tablet hero
                    sketchPadding = if (overlay) PaddingValues(top = 24.dp, bottom = imgH * .34f) else PaddingValues(0.dp))
                Box(Modifier.fillMaxWidth().height(110.dp).background(Brush.verticalGradient(listOf(C.bg.copy(alpha = .75f), Color.Transparent))))
                Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().fillMaxHeight(if (overlay) .62f else .42f)
                    .background(Brush.verticalGradient(listOf(Color.Transparent, C.bg.copy(alpha = if (overlay) .82f else .9f), C.bg))))
            }
            AmberGlow(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(imgH * .6f))
            Column(
                Modifier.align(Alignment.BottomStart).fillMaxWidth()
                    .padding(top = if (overlay) 0.dp else imgH - if (oneLine) 34.dp else 58.dp)
                    .padding(horizontal = if (wide) 48.dp else 24.dp).padding(bottom = if (overlay) 44.dp else 8.dp),
            ) {
                Text(
                    buildAnnotatedString {
                        append("NIGHT ARRAY")
                        if (oneLine) append("  ") else append("\n")
                        withStyle(SpanStyle(color = C.amber, fontStyle = FontStyle.Italic)) { append("/ WORK & STOW") }
                    },
                    color = C.ink, fontSize = titleSize.sp, fontWeight = FontWeight.Light,
                    letterSpacing = (titleSize * if (overlay) .2f else .17f).sp, lineHeight = (titleSize * 1.28f).sp,
                )
                Spacer(Modifier.height(18.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    AmberDash(26.dp)
                    Spacer(Modifier.width(12.dp))
                    Tracked("Integrated superwide workstation", size = 10.sp, color = C.ink.copy(alpha = .8f), tracking = .34f)
                }
                Spacer(Modifier.height(16.dp))
                Tagline(size = if (overlay) 26.sp else 23.sp)
                Spacer(Modifier.height(26.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    LineButton("Open the Studio", { app.openStudio(Preset(mode = "work", camera = "hero")) }, Modifier.testTag("cta-studio"), filled = true,
                        leading = { Icon(Icons.Outlined.ViewInAr, null, tint = C.amber, modifier = Modifier.size(16.dp)) })
                    LineButton("Night shift", { app.startNight() }, Modifier.testTag("cta-night"), color = C.ink.copy(alpha = .8f),
                        leading = { Icon(Icons.Outlined.DarkMode, null, tint = C.ink.copy(alpha = .8f), modifier = Modifier.size(15.dp)) })
                }
            }
        }
    }
}

/** A low, slowly breathing amber glow, like light pooling under the base. */
@Composable
fun AmberGlow(modifier: Modifier = Modifier, strength: Float = 1f) {
    val inf = rememberInfiniteTransition(label = "glow")
    val b by inf.animateFloat(.7f, 1f, infiniteRepeatable(tween(5200, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "g")
    Canvas(modifier) {
        val c = Offset(size.width * .5f, size.height * 1.05f)
        drawCircle(Brush.radialGradient(listOf(C.amber.copy(alpha = .13f * b * strength), Color.Transparent), c, size.width * .75f), size.width * .75f, c)
    }
}

@Composable
private fun Intro(scene: Scene, pad: androidx.compose.ui.unit.Dp) {
    val sc = scene.screen
    Column(Modifier.readable().padding(horizontal = pad).padding(top = 18.dp)) {
        Text(
            "A double-wide display on a long titanium base, a vertical laptop dock on the right wing, and pockets in the deck that charge your keyboard and mouse while they're put away.",
            color = C.ink.copy(alpha = .9f), fontSize = 18.sp, lineHeight = 28.sp, fontWeight = FontWeight.Light,
        )
        Spacer(Modifier.height(26.dp))
        val stats = listOf(
            "${sc.canvasW} × ${sc.canvasH}" to "One canvas",
            "${sc.panels} × ${fmtNum(sc.panelInch)}″" to "Mainstream QHD",
            "${fmtNum(sc.seamMm)} mm" to "The honest seam",
            "1" to "Cable on the desk",
        )
        Hairline()
        stats.chunked(2).forEach { row ->
            Row(Modifier.fillMaxWidth()) {
                row.forEachIndexed { i, (v, l) ->
                    Column(Modifier.weight(1f).padding(vertical = 16.dp).padding(start = if (i == 1) 18.dp else 0.dp)) {
                        Text(v, color = C.ink, fontSize = 23.sp, fontWeight = FontWeight.Light, letterSpacing = 1.sp)
                        Spacer(Modifier.height(5.dp))
                        Tracked(l, size = 9.sp, color = C.muted, tracking = .28f)
                    }
                    if (i == 0) Box(Modifier.width(1.dp).height(74.dp).background(C.line))
                }
            }
            Hairline()
        }
    }
}

@Composable
private fun ModesSection(app: AppState, wide: Boolean, pad: androidx.compose.ui.unit.Dp) {
    Column(Modifier.fillMaxWidth().padding(top = 46.dp)) {
        SectionHeader("Three modes", "One footprint, three states", Modifier.readable().padding(horizontal = pad))
        Spacer(Modifier.height(18.dp))
        if (wide) {
            Row(Modifier.readable(1100.dp).padding(horizontal = pad), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                MODES.forEach { ModeCard(app, it, Modifier.weight(1f)) }
            }
        } else {
            LazyRow(Modifier.testTag("modes-row"), contentPadding = PaddingValues(horizontal = pad), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                items(MODES, key = { it.id }) { ModeCard(app, it, Modifier.width(292.dp)) }
            }
        }
    }
}

@Composable
private fun ModeCard(app: AppState, m: ModeInfo, modifier: Modifier) {
    PressCard({ app.openStudio(Preset(mode = m.id, style = "studio", camera = m.camera, explode = 0f)) }, modifier.testTag("mode-${m.id}")) {
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 10f)) {
            Still(listOf(m.still), Modifier.fillMaxSize(), sketchMode = m.id, animateSketch = false, maxDim = 900)
            Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, C.panel.copy(alpha = .85f)), startY = 140f)))
        }
        Column(Modifier.padding(18.dp)) {
            SectionHeader(m.title, m.sub, size = 15.sp)
            Spacer(Modifier.height(12.dp))
            Text(m.body.nbUnits(), color = C.ink.copy(alpha = .78f), fontSize = 14.sp, lineHeight = 21.sp, minLines = 4)
            Spacer(Modifier.height(14.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Kicker("Open in Studio")
                Spacer(Modifier.width(8.dp))
                Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, tint = C.amber, modifier = Modifier.size(14.dp))
            }
        }
    }
}

@Composable
private fun StoryRow(s: Story, modifier: Modifier, onClick: () -> Unit) {
    PressCard(onClick, modifier.testTag("story-${s.id}"), shape = RoundedCornerShape(18.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.padding(10.dp).size(width = 112.dp, height = 84.dp).clip(RoundedCornerShape(12.dp))) {
                Still(s.stills.map { it.name }, Modifier.fillMaxSize(), maxDim = 480, animateSketch = false, sketchMode = s.preset.mode ?: "work")
            }
            Column(Modifier.weight(1f).padding(start = 6.dp, end = 12.dp, top = 10.dp, bottom = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(s.number, color = C.amber, fontSize = 12.sp, fontWeight = FontWeight.Light, letterSpacing = 1.sp)
                    Spacer(Modifier.width(10.dp))
                    Tracked(s.kicker, size = 9.sp, color = C.muted, tracking = .3f)
                }
                Spacer(Modifier.height(6.dp))
                Text(s.title, color = C.ink, fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.Light)
                Spacer(Modifier.height(3.dp))
                Text(s.line, color = C.muted, fontSize = 12.5.sp, lineHeight = 17.sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            }
            Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, tint = C.muted, modifier = Modifier.padding(end = 16.dp).size(16.dp))
        }
    }
}

@Composable
fun DockSequenceStrip(scene: Scene, modifier: Modifier = Modifier, active: Int = 0, onStep: ((DockUiStep) -> Unit)? = null) {
    // Equal-height cards, however the captions wrap.
    Row(modifier.height(IntrinsicSize.Max), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        dockUiSteps(scene).forEach { st ->
            val on = st.n == active
            val shape = RoundedCornerShape(14.dp)
            Column(
                Modifier.weight(1f).fillMaxHeight().clip(shape).border(1.dp, if (on) C.amber.copy(alpha = .8f) else C.line, shape).background(C.panel)
                    .then(if (onStep != null) Modifier.clickable { onStep(st) } else Modifier).testTag("dock-strip-${st.id}"),
            ) {
                Box(Modifier.fillMaxWidth().aspectRatio(.82f)) {
                    Still(listOf(st.still), Modifier.fillMaxSize(), maxDim = 700, sketchMode = "stow", sketchFocus = "dock", sketchDockStep = st.id, animateSketch = false,
                        description = "Docking step ${st.n}: ${st.title}")
                }
                Column(Modifier.fillMaxWidth().padding(horizontal = 10.dp).padding(top = 10.dp, bottom = 12.dp)) {
                    Text("${st.n}", color = C.amber, fontSize = 18.sp, fontWeight = FontWeight.Light)
                    Spacer(Modifier.height(4.dp))
                    Tracked(st.title, size = 9.sp, color = C.ink, weight = FontWeight.Normal, tracking = .1f)
                    Spacer(Modifier.height(6.dp))
                    Tracked(st.caption, size = 7.5.sp, color = C.muted, tracking = .16f)
                }
            }
        }
    }
}

@Composable
private fun DockingSection(app: AppState, scene: Scene, pad: androidx.compose.ui.unit.Dp) {
    Column(Modifier.readable().padding(horizontal = pad).padding(top = 46.dp)) {
        SectionHeader("Docking sequence", "At the right outer wing")
        Spacer(Modifier.height(18.dp))
        DockSequenceStrip(scene, Modifier.fillMaxWidth().testTag("dock-strip")) { app.openStudio(Preset(mode = "stow", camera = "dock", dock = it.id)) }
        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            LineButton("Play it live", { app.openStudio(story("dock")!!.preset) }, filled = true)
            LineButton("The dock story", { app.nav.go("story/dock") }, color = C.ink.copy(alpha = .8f))
        }
    }
}

@Composable
private fun MaterialsSection(app: AppState, pad: androidx.compose.ui.unit.Dp) {
    Column(Modifier.readable().padding(horizontal = pad).padding(top = 46.dp)) {
        SectionHeader("Materials", "Three metals, one amber")
        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            listOf("graphite" to "Charcoal Graphite", "oxblood" to "Brushed Oxblood", "titanium" to "Neutral Titanium").forEach { (k, label) ->
                Column(Modifier.weight(1f).testTag("swatch-$k").clip(RoundedCornerShape(12.dp)).clickable {
                    app.openStudio(Preset(mode = "stow", style = "studio", finish = k, camera = "hero"))
                }) {
                    BrushedSwatch(k, Modifier.fillMaxWidth().aspectRatio(1.5f))
                    Spacer(Modifier.height(10.dp))
                    Tracked(label, size = 8.5.sp, color = C.ink.copy(alpha = .8f), tracking = .26f, align = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                }
            }
        }
        Spacer(Modifier.height(24.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clip(RoundedCornerShape(12.dp)).clickable { app.nav.go("story/amber") }.padding(vertical = 6.dp)) {
            Box(Modifier.width(1.dp).height(44.dp).background(C.line))
            Spacer(Modifier.width(18.dp))
            Column {
                AmberLine(Modifier.width(120.dp).height(18.dp))
                Spacer(Modifier.height(6.dp))
                Tracked("Subtle amber lighting", size = 9.sp, color = C.ink.copy(alpha = .8f), tracking = .3f)
            }
        }
        Spacer(Modifier.height(14.dp))
        Text("Tap a finish to see it on the station.", color = C.muted, fontSize = 13.sp)
    }
}

/** A brushed-metal tile: the finish gradient plus fine horizontal grain. */
@Composable
fun BrushedSwatch(material: String, modifier: Modifier = Modifier) {
    val cols = swatchColors(material)
    Canvas(modifier.clip(RoundedCornerShape(10.dp))) {
        drawRect(Brush.linearGradient(cols + cols.first(), start = Offset.Zero, end = Offset(size.width, size.height)))
        var y = 0f; var i = 0
        while (y < size.height) {
            drawLine(Color.White.copy(alpha = if (i % 3 == 0) .05f else .025f), Offset(0f, y), Offset(size.width, y + (i % 5) * .4f), 1f)
            y += 2.2f; i++
        }
        drawRect(Brush.linearGradient(listOf(Color.White.copy(alpha = .12f), Color.Transparent, Color.Black.copy(alpha = .18f)), start = Offset(0f, 0f), end = Offset(size.width * .8f, size.height)))
    }
}

@Composable
fun AmberLine(modifier: Modifier = Modifier, alpha: Float = 1f) {
    Canvas(modifier) {
        val y = size.height / 2
        for (k in 5 downTo 1) drawLine(C.amber.copy(alpha = .06f * k * alpha), Offset(size.width * .05f, y), Offset(size.width * .95f, y), k * 2.4f, StrokeCap.Round)
        drawLine(Brush.horizontalGradient(listOf(Color.Transparent, Color(0xFFFFD39A).copy(alpha = alpha), C.amber.copy(alpha = alpha), Color.Transparent)), Offset(0f, y), Offset(size.width, y), 2f, StrokeCap.Round)
    }
}

@Composable
private fun PrinciplesSection(wide: Boolean, pad: androidx.compose.ui.unit.Dp) {
    Column(Modifier.readable(if (wide) 980.dp else 760.dp).padding(horizontal = pad).padding(top = 50.dp)) {
        SectionHeader("Design principles", "What we kept every time we had to choose")
        Spacer(Modifier.height(10.dp))
        val rows = if (wide) PRINCIPLES.withIndex().chunked(2) else PRINCIPLES.withIndex().map { listOf(it) }
        rows.forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
                row.forEach { (i, p) ->
                    Column(Modifier.weight(1f).padding(vertical = 14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("%02d".format(i + 1), color = C.amber, fontSize = 12.sp, fontWeight = FontWeight.Light, letterSpacing = 1.sp)
                            Spacer(Modifier.width(12.dp))
                            Tracked(p.title, size = 12.sp, color = C.ink, weight = FontWeight.Normal, tracking = .2f)
                        }
                        Spacer(Modifier.height(8.dp))
                        Text(p.body, color = C.muted, fontSize = 14.sp, lineHeight = 21.sp, modifier = Modifier.padding(start = 30.dp))
                    }
                }
                if (row.size == 1 && wide) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun BoardCard(app: AppState, pad: androidx.compose.ui.unit.Dp) {
    Column(Modifier.readable().padding(horizontal = pad).padding(top = 40.dp)) {
        SectionHeader("Where it started", "The original concept board")
        Spacer(Modifier.height(18.dp))
        PressCard({ app.nav.go("board") }, Modifier.fillMaxWidth().testTag("board-card")) {
            Box(Modifier.fillMaxWidth().aspectRatio(1536f / 1024f)) {
                Still(listOf("concept/board.jpg"), Modifier.fillMaxSize(), maxDim = 1200, description = "The original Night Array concept board")
            }
            Column(Modifier.padding(18.dp)) {
                Text(BOARD_NOTE, color = C.ink.copy(alpha = .8f), fontSize = 14.sp, lineHeight = 22.sp)
                Spacer(Modifier.height(14.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Kicker("Open the board")
                    Spacer(Modifier.width(8.dp))
                    Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, tint = C.amber, modifier = Modifier.size(14.dp))
                }
            }
        }
    }
}

@Composable
private fun NightCard(app: AppState, pad: androidx.compose.ui.unit.Dp) {
    Column(Modifier.readable().padding(horizontal = pad).padding(top = 40.dp)) {
        SectionHeader("Night shift", "Ambient mode")
        Spacer(Modifier.height(18.dp))
        PressCard({ app.startNight() }, Modifier.fillMaxWidth().testTag("night-card"), background = C.bg) {
            Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f)) {
                Still(listOf("night.jpg", "hero-stow.jpg"), Modifier.fillMaxSize(), maxDim = 1200, sketchMode = "stow")
                Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, C.bg.copy(alpha = .9f)), startY = 200f)))
                Column(Modifier.align(Alignment.BottomStart).padding(20.dp)) {
                    Tagline("Leave it running at the end of the day.", size = 19.sp)
                    Spacer(Modifier.height(8.dp))
                    Text("A slow orbit around the station in the dark, lit only by its own amber. Tap Back to leave.", color = C.ink.copy(alpha = .72f), fontSize = 13.5.sp, lineHeight = 20.sp)
                    Spacer(Modifier.height(14.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.DarkMode, null, tint = C.amber, modifier = Modifier.size(15.dp))
                        Spacer(Modifier.width(8.dp))
                        Kicker("Start Night shift")
                    }
                }
            }
        }
    }
}

@Composable
private fun Footer(pad: androidx.compose.ui.unit.Dp) {
    Column(Modifier.readable().padding(horizontal = pad).padding(top = 56.dp, bottom = 16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        AmberDash(28.dp)
        Spacer(Modifier.height(18.dp))
        Tagline(size = 22.sp)
        Spacer(Modifier.height(12.dp))
        Tracked("Night Array · Work & Stow", size = 9.sp, color = C.muted, tracking = .34f)
        Spacer(Modifier.height(8.dp))
        Text("Every number in this app comes from the parametric CAD model.", color = C.muted.copy(alpha = .8f), fontSize = 12.sp, textAlign = TextAlign.Center)
    }
}

// =====================================================================================================
// Story
// =====================================================================================================

@Composable
fun StoryScreen(app: AppState, scene: Scene, id: String) {
    val s = story(id) ?: STORIES.first()
    val list = rememberLazyListState()
    val scrolled by rememberScrolledPast(list, 180.dp)
    BoxWithConstraints(Modifier.fillMaxSize().background(C.bg)) {
        val wide = maxWidth >= 600.dp
        val pad = if (wide) 40.dp else 22.dp
        LazyColumn(Modifier.fillMaxSize().testTag("story"), state = list, contentPadding = PaddingValues(bottom = 48.dp)) {
            item(key = "gallery") { StoryGallery(s, wide, maxHeight) }
            item(key = "head") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 22.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(s.number, color = C.amber, fontSize = 13.sp, fontWeight = FontWeight.Light, letterSpacing = 1.sp)
                        Spacer(Modifier.width(10.dp)); AmberDash(18.dp); Spacer(Modifier.width(10.dp))
                        Kicker(s.kicker, color = C.muted)
                    }
                    Spacer(Modifier.height(14.dp))
                    Tracked(s.title, size = if (wide) 30.sp else 25.sp, tracking = .16f)
                    Spacer(Modifier.height(10.dp))
                    Tagline(s.line, size = 18.sp, color = C.titanium)
                    Spacer(Modifier.height(22.dp))
                    Text(s.lede.nbUnits(), color = C.ink, fontSize = 18.sp, lineHeight = 28.sp, fontWeight = FontWeight.Light)
                }
            }
            if (s.id == "dual") item(key = "diagram") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 26.dp)) {
                    DualCanvasDiagram(scene, Modifier.fillMaxWidth().testTag("dual-diagram"))
                }
            }
            if (s.id == "dock") item(key = "seq") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 26.dp)) {
                    DockSequenceStrip(scene, Modifier.fillMaxWidth()) { app.openStudio(Preset(mode = "stow", camera = "dock", dock = it.id)) }
                }
            }
            items(s.body.size, key = { "p$it" }) { i ->
                Text(s.body[i].nbUnits(), Modifier.readable().padding(horizontal = pad).padding(top = 18.dp), style = Body)
            }
            item(key = "specs") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 30.dp)) {
                    Panel(Modifier.fillMaxWidth().testTag("story-specs"), padding = 18.dp) {
                        Kicker("In numbers")
                        Spacer(Modifier.height(6.dp))
                        val specs = storySpecs(s, scene)
                        specs.forEachIndexed { i, sp -> SpecRow(sp.label, sp.value, last = i == specs.lastIndex) }
                    }
                    Spacer(Modifier.height(24.dp))
                    LineButton(s.liveLabel, { app.openStudio(s.preset) }, Modifier.fillMaxWidth().testTag("see-live"), filled = true,
                        leading = { Icon(Icons.Outlined.ViewInAr, null, tint = C.amber, modifier = Modifier.size(16.dp)) })
                }
            }
            item(key = "next") {
                val next = STORIES[(STORIES.indexOf(s) + 1) % STORIES.size]
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 36.dp)) {
                    Hairline()
                    Row(
                        Modifier.fillMaxWidth().clickable { app.nav.go("story/${next.id}") }.padding(vertical = 20.dp).testTag("next-story"),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Kicker("Next · ${next.number}", color = C.muted)
                            Spacer(Modifier.height(6.dp))
                            Text(next.title, color = C.ink, fontSize = 18.sp, fontWeight = FontWeight.Light)
                        }
                        Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, tint = C.amber, modifier = Modifier.size(18.dp))
                    }
                    Hairline()
                }
            }
        }
        DetailChrome("${s.number} · ${s.title}", scrolled, { app.nav.back() })
    }
}

@Composable
private fun StoryGallery(s: Story, wide: Boolean, screenH: androidx.compose.ui.unit.Dp) {
    val pager = rememberPagerState { s.stills.size }
    Column(Modifier.fillMaxWidth()) {
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val h = (maxWidth * 9f / 16f).coerceAtMost(if (wide) screenH * .72f else 600.dp) + if (wide) 0.dp else 40.dp
            Box(Modifier.fillMaxWidth().height(h)) {
                HorizontalPager(pager, Modifier.fillMaxSize().testTag("gallery")) { i ->
                    Still(listOf(s.stills[i].name) + s.stills.map { it.name }, Modifier.fillMaxSize(), contentScale = CoverWidth(.85f), sketchMode = s.preset.mode ?: "work",
                        sketchHighlight = storyHighlight(s.id), description = s.stills[i].caption,
                        sketchFinish = s.stills[i].name.takeIf { it.startsWith("finish-") }?.removePrefix("finish-")?.substringBefore('.') ?: "titanium")
                }
                Box(Modifier.fillMaxWidth().height(110.dp).background(Brush.verticalGradient(listOf(C.bg.copy(alpha = .7f), Color.Transparent))))
                Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(70.dp).background(Brush.verticalGradient(listOf(Color.Transparent, C.bg))))
            }
        }
        Row(Modifier.readable().padding(horizontal = if (wide) 40.dp else 22.dp).padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            AnimatedContent(pager.currentPage, transitionSpec = { fadeIn(tween(260)) togetherWith fadeOut(tween(160)) }, modifier = Modifier.weight(1f), label = "cap") { p ->
                Text(s.stills[p].caption, color = C.muted, fontSize = 12.5.sp, lineHeight = 18.sp)
            }
            if (s.stills.size > 1) { Spacer(Modifier.width(14.dp)); PageDots(s.stills.size, pager.currentPage) }
        }
    }
}

private fun storyHighlight(id: String): String? = when (id) {
    "dual" -> "display"; "dock" -> "dock"; "charge" -> "internals"; "compute" -> "internals"; else -> null
}

/**
 * The dual display explained in one drawing: a plan view of the two panels toed in about the seam, and the
 * 5120 × 1440 canvas split into two 2560 × 1440 displays exactly where the mullion is.
 */
@Composable
fun DualCanvasDiagram(scene: Scene, modifier: Modifier = Modifier) {
    val sc = scene.screen
    val tm = rememberTextMeasurer()
    val label = TextStyle(color = C.muted, fontSize = 9.5.sp, letterSpacing = 1.4.sp)
    val strong = TextStyle(color = C.ink, fontSize = 10.sp, letterSpacing = 1.6.sp)
    val amberT = TextStyle(color = C.amber, fontSize = 10.sp, letterSpacing = 1.4.sp)
    val shape = RoundedCornerShape(20.dp)
    Column(modifier.clip(shape).background(C.panel).border(1.dp, C.line, shape).padding(18.dp)) {
        Kicker("Two displays, one canvas")
        Spacer(Modifier.height(14.dp))
        Canvas(Modifier.fillMaxWidth().aspectRatio(1.55f)) {
            grid(18.dp.toPx(), C.line.copy(alpha = .35f))
            val toe = Math.toRadians(sc.toeInDeg)
            val facet = sc.seamMm / 2 + sc.activeMm[0] + 9.0
            val ox = facet * cos(toe); val fwd = facet * sin(toe)
            val k = (size.width * .76f / (2 * ox)).toFloat()
            val cx = size.width / 2; val seamY = size.height * .24f
            fun P(x: Double, z: Double) = Offset(cx + (x * k).toFloat(), seamY + (z * k).toFloat()) // +z toward you = down
            val l = P(-ox, fwd); val r = P(ox, fwd); val s0 = P(0.0, 0.0)
            // rear shroud, then the two glass facets
            val back = 45.0
            val nl = Offset((sin(toe) * back * k).toFloat(), (-cos(toe) * back * k).toFloat())
            val shroud = Path().apply { moveTo(l.x, l.y); lineTo(s0.x, s0.y); lineTo(r.x, r.y); lineTo(r.x + nl.x, r.y + nl.y); lineTo(s0.x, s0.y - back.toFloat() * k * 1.02f); lineTo(l.x - nl.x, l.y + nl.y); close() }
            drawPath(shroud, C.graphite.copy(alpha = .7f))
            drawLine(C.ink.copy(alpha = .9f), l, s0, 3.dp.toPx(), StrokeCap.Round)
            drawLine(C.ink.copy(alpha = .9f), s0, r, 3.dp.toPx(), StrokeCap.Round)
            drawCircle(C.titanium, 3.2.dp.toPx(), s0)
            // sight lines from the viewer
            val eye = P(0.0, 600.0)
            val dash = PathEffect.dashPathEffect(floatArrayOf(5f, 6f))
            if (eye.y < size.height - 6.dp.toPx()) {
                listOf(l, r, s0).forEach { drawLine(C.amber.copy(alpha = .28f), eye, it, 1f, pathEffect = dash) }
                drawCircle(C.amber, 3.dp.toPx(), eye)
            }
            // forward offset of the outer edges
            val dimX = r.x + 10.dp.toPx()
            drawLine(C.muted, Offset(dimX, s0.y), Offset(dimX, r.y), 1f)
            drawLine(C.muted, Offset(dimX - 4.dp.toPx(), s0.y), Offset(dimX + 4.dp.toPx(), s0.y), 1f)
            drawLine(C.muted, Offset(dimX - 4.dp.toPx(), r.y), Offset(dimX + 4.dp.toPx(), r.y), 1f)
            drawLine(C.line, Offset(s0.x, s0.y), Offset(dimX, s0.y), 1f, pathEffect = dash)
            val fwdT = tm.measure("${fwd.roundToInt()} MM", label)
            drawText(fwdT, topLeft = Offset(dimX - fwdT.size.width / 2f, r.y + 6.dp.toPx()))
            // toe-in angle arc at the left facet end
            val arcR = 64.dp.toPx()
            drawLine(C.muted.copy(alpha = .6f), l, Offset(l.x + arcR * 1.25f, l.y), 1f, pathEffect = dash)
            drawArc(C.amber, startAngle = -sc.toeInDeg.toFloat(), sweepAngle = sc.toeInDeg.toFloat(), useCenter = false,
                topLeft = Offset(l.x - arcR, l.y - arcR), size = Size(arcR * 2, arcR * 2), style = Stroke(1.5.dp.toPx()))
            val tT = tm.measure("${fmtNum(sc.toeInDeg)}° TOE-IN", amberT)
            drawText(tT, topLeft = Offset(l.x + arcR * .35f, l.y + 4.dp.toPx()))
            val seamT = tm.measure("${fmtNum(sc.seamMm)} MM SEAM", strong)
            drawText(seamT, topLeft = Offset(s0.x - seamT.size.width / 2f, s0.y - seamT.size.height - 14.dp.toPx()))
            val youT = tm.measure("YOU · ≈ 60 CM", amberT)
            if (eye.y < size.height - 6.dp.toPx()) drawText(youT, topLeft = Offset(eye.x + 8.dp.toPx(), eye.y - youT.size.height / 2f))
            // overall width
            val yW = l.y + 30.dp.toPx()
            drawLine(C.muted.copy(alpha = .7f), Offset(l.x, yW), Offset(r.x, yW), 1f)
            drawLine(C.muted.copy(alpha = .7f), Offset(l.x, yW - 4.dp.toPx()), Offset(l.x, yW + 4.dp.toPx()), 1f)
            drawLine(C.muted.copy(alpha = .7f), Offset(r.x, yW - 4.dp.toPx()), Offset(r.x, yW + 4.dp.toPx()), 1f)
            val wT = tm.measure("≈ ${fmtMm(scene.displayWidthMm)} MM", label)
            drawRect(C.panel, Offset(cx - wT.size.width / 2f - 6.dp.toPx(), yW - wT.size.height / 2f), Size(wT.size.width + 12.dp.toPx().toFloat(), wT.size.height.toFloat()))
            drawText(wT, topLeft = Offset(cx - wT.size.width / 2f, yW - wT.size.height / 2f))
        }
        Spacer(Modifier.height(18.dp))
        // the canvas: two displays, one seam
        Canvas(Modifier.fillMaxWidth().aspectRatio(sc.canvasW.toFloat() / sc.canvasH * .92f)) {
            val gap = 5.dp.toPx()
            val w = (size.width - gap) / 2; val h = size.height
            listOf(0f, w + gap).forEachIndexed { i, x ->
                drawRect(Brush.verticalGradient(listOf(Color(0xFF1A1418), Color(0xFF2A1E21))), Offset(x, 0f), Size(w, h))
                // a window snapped to each half
                val m = 8.dp.toPx()
                drawRoundRect(C.ink.copy(alpha = .08f), Offset(x + m, m), Size(w - 2 * m, h - 2 * m), androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()))
                drawRoundRect(C.ink.copy(alpha = .16f), Offset(x + m, m), Size(w - 2 * m, h - 2 * m), androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()), style = Stroke(1f))
                for (j in 0..4) drawLine(C.ink.copy(alpha = .1f), Offset(x + m * 2, m * 3.2f + j * 9.dp.toPx()), Offset(x + w * (.55f + .08f * ((j * 7 + i * 3) % 5)) - m, m * 3.2f + j * 9.dp.toPx()), 2.dp.toPx(), StrokeCap.Round)
                val t = tm.measure("DISPLAY ${i + 1}", strong)
                drawText(t, topLeft = Offset(x + w / 2 - t.size.width / 2f, h - t.size.height * 2.4f))
                val r = tm.measure("${sc.resEach[0]} × ${sc.resEach[1]}", label)
                drawText(r, topLeft = Offset(x + w / 2 - r.size.width / 2f, h - r.size.height * 1.3f))
            }
            drawRect(Brush.verticalGradient(listOf(C.titanium, Color(0xFF8E8478), C.titanium)), Offset(w, 0f), Size(gap, h))
        }
        Spacer(Modifier.height(14.dp))
        Text(
            "Your OS sees two ordinary ${fmtNum(sc.panelInch)}-inch displays. Together they make one ${sc.canvasW} × ${sc.canvasH} desktop, split at the mullion: snap a window to each half, or span one across both.",
            color = C.muted, fontSize = 13.sp, lineHeight = 20.sp,
        )
    }
}

// =====================================================================================================
// The original board
// =====================================================================================================

@Composable
fun BoardScreen(app: AppState) {
    BoxWithConstraints(Modifier.fillMaxSize().background(Color(0xFF070605)).testTag("board")) {
        val wide = maxWidth > maxHeight
        Column(Modifier.fillMaxSize().statusBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                BackButton({ app.nav.back() })
                Spacer(Modifier.width(14.dp))
                Column {
                    Tracked("Where it started", size = 13.sp, tracking = .26f)
                    Tracked("Pinch or double-tap to zoom", size = 8.5.sp, color = C.muted, tracking = .26f, modifier = Modifier.padding(top = 3.dp))
                }
            }
            Zoomable(Modifier.weight(1f).fillMaxWidth().testTag("board-zoom")) {
                Still(listOf("concept/board.jpg"), Modifier.fillMaxSize(), contentScale = ContentScale.Fit, maxDim = 2048, description = "The original concept board")
            }
            if (!wide) {
                Column(Modifier.fillMaxWidth().background(C.bg).padding(horizontal = 22.dp, vertical = 18.dp)) {
                    Kicker("What changed")
                    Spacer(Modifier.height(8.dp))
                    Text(BOARD_NOTE, color = C.ink.copy(alpha = .8f), fontSize = 13.5.sp, lineHeight = 21.sp)
                }
            }
        }
    }
}

// =====================================================================================================
// Night shift — the shared viewer in cinematic mode, full screen
// =====================================================================================================

@Composable
fun NightShift(app: AppState, scene: Scene) {
    val host = app.host
    BackHandler(enabled = app.nightShift) { app.stopNight() } // not while fading out: a second Back should navigate
    val view = LocalView.current
    DisposableEffect(view) {
        view.keepScreenOn = true
        val window = (view.context as? Activity)?.window
        val ctl = window?.let { WindowCompat.getInsetsController(it, view) }
        ctl?.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        ctl?.hide(WindowInsetsCompat.Type.systemBars())
        onDispose { view.keepScreenOn = false; ctl?.show(WindowInsetsCompat.Type.systemBars()) }
    }
    var chrome by remember { mutableStateOf(true) }
    var poke by remember { mutableIntStateOf(0) }
    LaunchedEffect(poke) { chrome = true; delay(4000); chrome = false }
    var line by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) { while (true) { delay(7000); line = (line + 1) % NIGHT_LINES.size } }
    val ready = host.status == LiveStatus.Ready
    val stillA by animateFloatAsState(if (ready) 0f else 1f, tween(900), label = "ns")

    Box(
        Modifier.fillMaxSize().background(C.bg).testTag("night")
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { poke++ },
    ) {
        Box(Modifier.fillMaxSize().graphicsLayer { alpha = stillA }) {
            Still(listOf("night.jpg", "hero-stow.jpg", "hero-work.jpg"), Modifier.fillMaxSize(), contentScale = CoverWidth(.7f), kenBurns = true,
                sketchMode = "stow", sketchFinish = host.state.finish, description = "Night Array at night")
        }
        ViewerSlot(host, Modifier.fillMaxSize())
        // vignette + floor glow
        Box(Modifier.fillMaxSize().background(Brush.radialGradient(listOf(Color.Transparent, C.bg.copy(alpha = .55f)), radius = 1600f)))
        AmberGlow(Modifier.align(Alignment.BottomCenter).fillMaxWidth().fillMaxHeight(.35f), strength = .8f)
        Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding().padding(bottom = 46.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            AnimatedContent(line, transitionSpec = { fadeIn(tween(1400)) togetherWith fadeOut(tween(1000)) }, label = "nl") { i ->
                Tagline(NIGHT_LINES[i], size = 22.sp, color = C.ink.copy(alpha = .86f))
            }
            Spacer(Modifier.height(14.dp))
            AmberDash(24.dp)
        }
        AnimatedVisibility(chrome, enter = fadeIn(tween(300)), exit = fadeOut(tween(900)), modifier = Modifier.fillMaxWidth().statusBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Tracked("Night shift", size = 12.sp, tracking = .32f)
                    Tracked(if (ready) "Live · slow orbit" else "Still · tap back to leave", size = 8.5.sp, color = C.muted, tracking = .28f, modifier = Modifier.padding(top = 3.dp))
                }
                IconCircle(Icons.Outlined.Close, "Exit Night shift", { app.stopNight() })
            }
        }
    }
}
