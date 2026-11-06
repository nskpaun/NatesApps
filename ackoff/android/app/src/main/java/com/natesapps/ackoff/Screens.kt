package com.natesapps.ackoff

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

// ---------- shared scaffolding ----------
@Composable
fun TopBar(title: String, nav: Nav, subtitle: String? = null, actions: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth().background(C.bg).statusBarsPadding().padding(horizontal = 4.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        if (nav.stack.size > 1) IconButton(onClick = { nav.back() }) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back", tint = C.ink) }
        else Spacer(Modifier.width(16.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 18.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = C.ink)
            if (subtitle != null) Text(subtitle, fontSize = 12.sp, color = C.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        actions()
    }
}

/** Staggered fade/slide-in for list items. */
@Composable
fun Appear(index: Int, content: @Composable () -> Unit) {
    var v by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { delay(40L * index.coerceAtMost(12)); v = true }
    val a by animateFloatAsState(if (v) 1f else 0f, tween(420, easing = FastOutSlowInEasing), label = "ap")
    Box(Modifier.graphicsLayer { alpha = a; translationY = (1 - a) * 40f }) { content() }
}

/** Animated network: parts of a system that light up and connect as you make progress. */
@Composable
fun SystemHero(modifier: Modifier = Modifier, lit: Int, total: Int) {
    val inf = rememberInfiniteTransition(label = "sys")
    val t by inf.animateFloat(0f, (2 * PI).toFloat(), infiniteRepeatable(tween(9000, easing = LinearEasing)), label = "t")
    val pulse by inf.animateFloat(.4f, 1f, infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "p")
    Canvas(modifier) {
        val cx = size.width / 2; val cy = size.height / 2
        val rx = size.width * .42f; val ry = size.height * .36f
        val pts = (0 until total).map { i ->
            val a = (2 * PI * i / total).toFloat() + t * .15f
            val wob = sin(t * 2 + i) * 6f
            Offset(cx + cos(a) * (rx + wob), cy + sin(a) * (ry + wob))
        }
        val hub = Offset(cx, cy)
        // interactions: edges between lit parts and to the whole
        for (i in 0 until total) {
            val on = i < lit
            drawLine(if (on) C.accent.copy(alpha = .55f) else C.line.copy(alpha = .6f), hub, pts[i], strokeWidth = if (on) 3f else 1.5f)
            val j = (i + 1) % total
            val both = i < lit && j < lit
            drawLine(if (both) C.accent2.copy(alpha = .7f) else C.line.copy(alpha = .5f), pts[i], pts[j], strokeWidth = if (both) 3f else 1.5f)
        }
        for (i in 0 until total) {
            val on = i < lit
            if (on) drawCircle(C.accent.copy(alpha = .22f * pulse), radius = 22f, center = pts[i])
            drawCircle(if (on) C.accent else C.panel2, radius = 11f, center = pts[i])
            drawCircle(if (on) C.ink else C.line, radius = 11f, center = pts[i], style = androidx.compose.ui.graphics.drawscope.Stroke(2f))
        }
        val whole = lit / total.toFloat()
        drawCircle(C.accent2.copy(alpha = .18f + .3f * whole * pulse), radius = 34f + 14f * whole, center = hub)
        drawCircle(C.accent2, radius = 18f, center = hub)
    }
}

// ---------- HOME ----------
@Composable
fun HomeScreen(store: Store, nav: Nav) {
    val lit = store.earned.size
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item {
            Box(Modifier.fillMaxWidth().background(Brush.verticalGradient(listOf(Color(0xFF0F3A36), C.bg))).statusBarsPadding().padding(horizontal = 20.dp, vertical = 18.dp)) {
                Column {
                    Text("SYSTEMS THINKING FOR THE FLIGHT", color = C.accent, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 2.sp)
                    Spacer(Modifier.height(6.dp))
                    Text("Russell Ackoff", fontSize = 38.sp, fontWeight = FontWeight.Black, color = C.ink, lineHeight = 42.sp)
                    Text("From mechanistic to systemic thinking, and why leadership is an aesthetic act.",
                        fontFamily = Serif, fontSize = 17.sp, lineHeight = 25.sp, color = C.ink.copy(alpha = .85f), modifier = Modifier.padding(top = 6.dp))
                    SystemHero(Modifier.fillMaxWidth().height(170.dp).padding(top = 8.dp), lit = lit, total = LINKS.size)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val pct by animateFloatAsState(lit / LINKS.size.toFloat(), tween(800), label = "pct")
                        Text("$lit / ${LINKS.size} parts connected", color = C.accent2, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Spacer(Modifier.width(12.dp))
                        LinearProgressIndicator(progress = { pct }, modifier = Modifier.weight(1f).height(6.dp).clip(CircleShape), color = C.accent, trackColor = C.line, drawStopIndicator = {})
                    }
                    val next = LINKS.firstOrNull { !store.earned.containsKey(it.id) }
                    if (next != null) TextButton(onClick = { nav.link(next.target) }, contentPadding = PaddingValues(0.dp)) {
                        Text("Next: ${next.label} →", color = C.muted, fontSize = 14.sp)
                    } else Text("🏆 The whole system is connected!", color = C.thm, modifier = Modifier.padding(top = 8.dp))
                }
            }
        }
        item {
            Appear(0) {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 6.dp).fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(C.accentSoft)
                    .border(1.dp, C.accent.copy(alpha = .5f), RoundedCornerShape(18.dp)).padding(16.dp)) {
                    Text("“The righter we do the wrong thing, the wronger we become.”", fontFamily = Serif, fontSize = 18.sp, lineHeight = 26.sp, color = C.ink)
                    Text("— Russell L. Ackoff", color = C.accent, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
                }
            }
        }
        item { Box(Modifier.padding(horizontal = 20.dp)) { SectionLabel("Choose your depth") } }
        itemsIndexed(LEVELS) { i, lv -> Appear(i + 1) { LevelCard(lv, store, nav, Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) } }
        item { Box(Modifier.padding(horizontal = 20.dp)) { SectionLabel("Play") } }
        item {
            Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                ToolTile("Machine or Systems?", "⚙︎ / ◉", Modifier.weight(1f)) { nav.go("sort") }
                ToolTile("Quizzes", "🎮", Modifier.weight(1f)) { nav.tab("play") }
                ToolTile("Glossary", "📖", Modifier.weight(1f)) { nav.go("glossary") }
            }
        }
        item {
            Text("Explanations are original summaries of Ackoff's talk and writings, not his words, except where quoted.",
                fontSize = 13.sp, color = C.muted, lineHeight = 19.sp, modifier = Modifier.padding(20.dp))
        }
    }
}

data class Level(val n: String, val title: String, val desc: String, val route: String, val emoji: String, val time: String)
val LEVELS = listOf(
    Level("1", "Ackoff in three minutes", "Who he was, and his four biggest ideas.", "article/l1", "⚡", "3 min"),
    Level("2", "The 1993 talk", "“From Mechanistic to Social Systemic Thinking,” section by section, with study questions.", "article/talk", "🎤", "25 min"),
    Level("3", "Leadership is aesthetic", "The four ideals, creation and recreation, leader vs manager, and an aesthetic audit.", "article/lead", "🎨", "15 min"),
    Level("4", "The Ackoff toolkit", "Messes, dissolving problems, idealized design, interactive planning, DIKW.", "article/tools", "🧰", "20 min"),
    Level("5", "Use it on Monday", "Five notebook exercises for your own team.", "article/apply", "✍️", "1 hour"),
)

@Composable
fun LevelCard(lv: Level, store: Store, nav: Nav, modifier: Modifier = Modifier) {
    val done = store.earned.containsKey(lv.route.removePrefix("article/"))
    PressCard({ nav.go(lv.route) }, modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(C.accentSoft), contentAlignment = Alignment.Center) { Text(lv.emoji, fontSize = 22.sp) }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text("LEVEL ${lv.n} · ${lv.time.uppercase()}", color = C.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                Text(lv.title, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = C.ink)
                Text(lv.desc, color = C.muted, fontSize = 14.sp, lineHeight = 19.sp)
            }
            if (done) Icon(Icons.Rounded.CheckCircle, "done", tint = C.thm, modifier = Modifier.padding(start = 6.dp))
        }
    }
}

@Composable
fun ToolTile(label: String, emoji: String, modifier: Modifier, onClick: () -> Unit) {
    PressCard(onClick, modifier) {
        Text(emoji, fontSize = 22.sp, color = C.accent2)
        Text(label, fontWeight = FontWeight.SemiBold, color = C.ink, fontSize = 14.sp, lineHeight = 18.sp)
    }
}

// ---------- LEARN ----------
@Composable
fun LearnScreen(store: Store, nav: Nav) {
    Column(Modifier.fillMaxSize()) {
        TopBar("Learn", nav)
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            itemsIndexed(LEVELS) { i, lv -> Appear(i) { LevelCard(lv, store, nav) } }
            item { Appear(6) { ToolTile("Glossary", "📖", Modifier.fillMaxWidth()) { nav.go("glossary") } } }
        }
    }
}

// ---------- ARTICLE ----------
@Composable
fun ArticleScreen(store: Store, content: Content, nav: Nav, key: String) {
    val blocks = content.articles[key] ?: emptyList()
    val title = (blocks.firstOrNull { it is Block.Text && it.kind == "h1" } as? Block.Text)?.spans?.joinToString("") { it.text } ?: ""
    val state = rememberLazyListState()
    val scale = store.fontScale.value
    val progress by remember { derivedStateOf {
        val info = state.layoutInfo; val total = info.totalItemsCount
        if (total == 0) 0f else ((state.firstVisibleItemIndex + info.visibleItemsInfo.size) / total.toFloat()).coerceIn(0f, 1f)
    } }
    val animP by animateFloatAsState(progress, label = "p")
    val atEnd by remember { derivedStateOf { !state.canScrollForward && state.layoutInfo.totalItemsCount > 0 } }
    LaunchedEffect(atEnd) { if (atEnd) store.earn(key) }
    val sections = blocks.withIndex().filter { (it.value as? Block.Text)?.kind == "h2" }
    var showToc by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize()) {
        TopBar(title, nav, actions = {
            if (sections.isNotEmpty()) IconButton(onClick = { showToc = true }) { Icon(Icons.Rounded.List, "Sections", tint = C.ink) }
            FontButton(store)
        })
        LinearProgressIndicator(progress = { animP }, modifier = Modifier.fillMaxWidth().height(3.dp), color = C.accent, trackColor = C.line, drawStopIndicator = {})
        LazyColumn(state = state, contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 40.dp)) {
            items(blocks.size) { i -> BlockView(blocks[i], scale) { nav.link(it) } }
            item { NextUp(key, nav) }
        }
    }
    if (showToc) {
        @OptIn(ExperimentalMaterial3Api::class)
        ModalBottomSheet(onDismissRequest = { showToc = false }, containerColor = C.panel) {
            LazyColumn(contentPadding = PaddingValues(bottom = 30.dp)) {
                items(sections) { s ->
                    Text((s.value as Block.Text).spans.joinToString("") { it.text }, color = C.ink, fontSize = 16.sp,
                        modifier = Modifier.fillMaxWidth().clickable { showToc = false; scope.launch { state.animateScrollToItem(s.index) } }.padding(horizontal = 24.dp, vertical = 14.dp))
                }
            }
        }
    }
}

@Composable
fun FontButton(store: Store) {
    IconButton(onClick = {
        val steps = listOf(0.9f, 1f, 1.12f, 1.25f)
        val i = steps.indexOfFirst { abs(it - store.fontScale.value) < .01f }
        store.setFontScale(steps[(i + 1) % steps.size])
    }) { Icon(Icons.Rounded.FormatSize, "Text size", tint = C.ink) }
}

@Composable
fun NextUp(key: String, nav: Nav) {
    val order = listOf("l1", "talk", "lead", "tools", "apply")
    val quiz = mapOf("l1" to 0, "talk" to 1, "lead" to 2, "tools" to 3)
    val idx = order.indexOf(key)
    Spacer(Modifier.height(24.dp))
    if (idx in 0 until order.size - 1) {
        val next = LEVELS[idx + 1]
        PressCard({ nav.go(next.route) }, border = C.accent.copy(alpha = .6f)) {
            Text("UP NEXT", color = C.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(next.title, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = C.ink, modifier = Modifier.weight(1f))
                Icon(Icons.AutoMirrored.Rounded.ArrowForward, null, tint = C.accent)
            }
        }
    }
    quiz[key]?.let { q ->
        Spacer(Modifier.height(10.dp))
        PressCard({ nav.go("quiz/$q") }) { Text("🎮  Quiz yourself on this level", fontWeight = FontWeight.SemiBold, color = C.ink) }
    }
    if (key == "talk") {
        Spacer(Modifier.height(10.dp))
        PressCard({ nav.go("sort") }) { Text("⚙︎ / ◉  Play “Machine or Systems?”", fontWeight = FontWeight.SemiBold, color = C.ink) }
    }
}

// ---------- GLOSSARY ----------
@Composable
fun GlossaryScreen(content: Content, nav: Nav) {
    var q by remember { mutableStateOf("") }
    val list = content.glossary.filter { q.isBlank() || it.term.contains(q, true) || it.def.contains(q, true) }
    Column(Modifier.fillMaxSize()) {
        TopBar("Glossary", nav, subtitle = "${content.glossary.size} terms · tap to expand")
        OutlinedTextField(q, { q = it }, Modifier.fillMaxWidth().padding(horizontal = 16.dp), placeholder = { Text("Filter terms…") },
            leadingIcon = { Icon(Icons.Rounded.Search, null) }, singleLine = true, shape = RoundedCornerShape(14.dp))
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(list, key = { it.term }) { t ->
                var open by remember { mutableStateOf(q.isNotBlank()) }
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.panel).clickable { open = !open }.animateContentSize().padding(14.dp)) {
                    Text(t.term, fontWeight = FontWeight.Bold, color = if (open) C.accent else C.ink, fontSize = 16.sp)
                    if (open) Text(t.def, fontFamily = Serif, fontSize = 16.sp, lineHeight = 23.sp, color = C.ink, modifier = Modifier.padding(top = 6.dp))
                }
            }
        }
    }
}
