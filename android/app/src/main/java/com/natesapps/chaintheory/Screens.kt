package com.natesapps.chaintheory

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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.sqrt

// ---------- shared scaffolding ----------
@Composable
fun TopBar(title: String, nav: Nav, subtitle: String? = null, actions: @Composable RowScope.() -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().background(C.bg).statusBarsPadding().padding(horizontal = 4.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
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

// ---------- HOME ----------
@Composable
fun HomeScreen(store: Store, content: Content, nav: Nav) {
    val lit = store.earned.size
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item {
            Box(
                Modifier.fillMaxWidth().background(Brush.verticalGradient(listOf(Color(0xFF3A2312), C.bg))).statusBarsPadding()
                    .padding(horizontal = 20.dp, vertical = 18.dp)
            ) {
                Column {
                    Text("OFFLINE FIELD GUIDE", color = C.accent, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 2.sp)
                    Spacer(Modifier.height(6.dp))
                    Text("Chain Theory", fontSize = 40.sp, fontWeight = FontWeight.Black, color = C.ink, lineHeight = 44.sp)
                    Text("Alex Wissner-Gross's attempt to rebuild physics from entangled qudits, from 60 seconds to all 754 pages.",
                        fontFamily = Serif, fontSize = 17.sp, lineHeight = 25.sp, color = C.ink.copy(alpha = .85f), modifier = Modifier.padding(top = 6.dp))
                    ChainHero(Modifier.fillMaxWidth().height(86.dp).padding(top = 14.dp), lit = lit, total = LINKS.size)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val pct by animateFloatAsState(lit / LINKS.size.toFloat(), tween(800), label = "pct")
                        Text("$lit / ${LINKS.size} links forged", color = C.accent2, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Spacer(Modifier.width(12.dp))
                        LinearProgressIndicator(progress = { pct }, modifier = Modifier.weight(1f).height(6.dp).clip(CircleShape), color = C.accent, trackColor = C.line, drawStopIndicator = {})
                    }
                    val next = LINKS.firstOrNull { !store.earned.containsKey(it.id) }
                    if (next != null) TextButton(onClick = { nav.link(next.target) }, contentPadding = PaddingValues(0.dp)) {
                        Text("Next link: ${next.label} →", color = C.muted, fontSize = 14.sp)
                    } else Text("🏆 Chain complete!", color = C.thm, modifier = Modifier.padding(top = 8.dp))
                }
            }
        }
        val last = store.lastDoc.value
        if (last != null) item {
            Appear(0) {
                PressCard({ nav.go("reader/$last/${store.lastPage.value}") }, Modifier.padding(horizontal = 16.dp, vertical = 6.dp), border = C.accent.copy(alpha = .5f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Bookmark, null, tint = C.accent)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text("PICK UP WHERE YOU LEFT OFF", color = C.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                            Text("${DOC_SHORT[last]} · page ${store.lastPage.value}", fontWeight = FontWeight.SemiBold, color = C.ink)
                        }
                        Icon(Icons.AutoMirrored.Rounded.ArrowForward, null, tint = C.muted)
                    }
                }
            }
        }
        item { Box(Modifier.padding(horizontal = 20.dp)) { SectionLabel("Choose your depth") } }
        itemsIndexed(LEVELS) { i, lv ->
            Appear(i + 1) { LevelCard(lv, store, nav, Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) }
        }
        item { Box(Modifier.padding(horizontal = 20.dp)) { SectionLabel("Tools") } }
        item {
            Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                ToolTile("Quiz", "🎮", Modifier.weight(1f)) { nav.tab("play") }
                ToolTile("α calc", "🧮", Modifier.weight(1f)) { nav.go("calc") }
                ToolTile("Glossary", "📖", Modifier.weight(1f)) { nav.go("glossary") }
            }
        }
        item {
            Text("Chain Theory is days old (released Oct 23, 2026). The compendium is a \"working draft\" and the physics community hasn't evaluated it yet. This guide separates AWG's claims from established physics.",
                fontSize = 13.sp, color = C.muted, lineHeight = 19.sp, modifier = Modifier.padding(20.dp))
        }
    }
}

data class Level(val n: String, val title: String, val desc: String, val route: String, val emoji: String, val time: String)
val LEVELS = listOf(
    Level("1", "The 60-second version", "What it says, why it matters, and whether it's settled. No physics needed.", "article/l1", "⚡", "2 min"),
    Level("2", "The big picture", "The 50-year drought, three clues, one axiom, chains vs strings, six kinds of link, proved vs conjectured.", "article/l2", "🔭", "20 min"),
    Level("3", "The math of α", "Qudits, the read cap at d₁d₂ ≤ 6, the gauge group, and the 172-record count step by step.", "article/l3", "∑", "45 min"),
    Level("4", "Compendium map", "All sixteen Parts: what each claims and how its results are graded.", "map", "🗺", "browse"),
    Level("5", "The primary sources", "The talk, the alpha Letter, and the full 754-page compendium, plus the original PDFs.", "library", "📚", "the flight"),
)

@Composable
fun LevelCard(lv: Level, store: Store, nav: Nav, modifier: Modifier = Modifier) {
    val done = when (lv.route) { "article/l1" -> "l1"; "article/l2" -> "l2"; "article/l3" -> "l3"; "map" -> "l4"; else -> "comp" }.let { store.earned.containsKey(it) }
    PressCard({ if (lv.route == "library") nav.tab("library") else nav.go(lv.route) }, modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(C.accentSoft), contentAlignment = Alignment.Center) {
                Text(lv.emoji, fontSize = 22.sp, color = C.accent2)
            }
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
        Text(emoji, fontSize = 26.sp)
        Text(label, fontWeight = FontWeight.SemiBold, color = C.ink, fontSize = 15.sp)
    }
}

// ---------- LEARN hub ----------
@Composable
fun LearnScreen(store: Store, nav: Nav) {
    Column(Modifier.fillMaxSize()) {
        TopBar("Learn", nav)
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            itemsIndexed(LEVELS) { i, lv -> Appear(i) { LevelCard(lv, store, nav) } }
            item {
                Appear(6) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        ToolTile("α calculator", "🧮", Modifier.weight(1f)) { nav.go("calc") }
                        ToolTile("Glossary", "📖", Modifier.weight(1f)) { nav.go("glossary") }
                    }
                }
            }
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
    // section jump list
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
                        modifier = Modifier.fillMaxWidth().clickable {
                            showToc = false
                            scope.launch { state.animateScrollToItem(s.index) }
                        }.padding(horizontal = 24.dp, vertical = 14.dp))
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
    val (label, route) = when (key) {
        "l1" -> "Level 2 · The big picture" to "article/l2"
        "l2" -> "Level 3 · The math" to "article/l3"
        "l3" -> "Test yourself: the Math quiz" to "quiz/2"
        else -> "The full compendium" to "reader/comp/2"
    }
    Spacer(Modifier.height(24.dp))
    PressCard({ nav.go(route) }, border = C.accent.copy(alpha = .6f)) {
        Text("UP NEXT", color = C.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = C.ink, modifier = Modifier.weight(1f))
            Icon(Icons.AutoMirrored.Rounded.ArrowForward, null, tint = C.accent)
        }
    }
    if (key in listOf("l1", "l2")) {
        Spacer(Modifier.height(10.dp))
        PressCard({ nav.go("quiz/${if (key == "l1") 0 else 1}") }) {
            Text("🎮  Quiz yourself on this level", fontWeight = FontWeight.SemiBold, color = C.ink)
        }
    }
}

// ---------- MAP ----------
@Composable
fun MapScreen(store: Store, content: Content, nav: Nav) {
    LaunchedEffect(Unit) { delay(2500); store.earn("l4") }
    val intro = content.articles["l4"]!!.filter { it !is Block.Text || it.kind !in listOf("kicker") }
    Column(Modifier.fillMaxSize()) {
        TopBar("Compendium map", nav)
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(intro.size) { BlockView(intro[it], store.fontScale.value) { l -> nav.link(l) } }
            itemsIndexed(content.parts) { i, p ->
                Appear(i) { PartCard(p) { pg -> nav.go("reader/comp/$pg") } }
            }
        }
    }
}

@Composable
fun PartCard(p: Part, open: (Int) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val rot by animateFloatAsState(if (expanded) 180f else 0f, label = "rot")
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(C.panel).border(1.dp, C.line, RoundedCornerShape(16.dp))
            .clickable { expanded = !expanded }.animateContentSize(spring(stiffness = Spring.StiffnessMediumLow)).padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(p.title, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = C.ink, modifier = Modifier.weight(1f))
            Icon(Icons.Rounded.ExpandMore, null, tint = C.muted, modifier = Modifier.graphicsLayer { rotationZ = rot })
        }
        if (p.counts != null) {
            Spacer(Modifier.height(8.dp))
            GradeBar(p.counts)
        }
        if (expanded) {
            Text(p.desc, fontFamily = Serif, fontSize = 16.sp, lineHeight = 24.sp, color = C.ink, modifier = Modifier.padding(top = 10.dp))
            if (p.page != null) Button(onClick = { open(p.page) }, modifier = Modifier.padding(top = 10.dp)) { Text("Read from p. ${p.page}") }
        }
    }
}

@Composable
fun GradeBar(c: List<Int>) {
    val total = c.sum().coerceAtLeast(1)
    var go by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { go = true }
    val f by animateFloatAsState(if (go) 1f else 0f, tween(900, easing = FastOutSlowInEasing), label = "gb")
    Column {
        Row(Modifier.fillMaxWidth().height(8.dp).clip(CircleShape).background(C.line)) {
            listOf(C.thm to c[0], C.cond to c[1], C.open to c[2]).forEach { (col, n) ->
                if (n > 0) Box(Modifier.weight(n.toFloat() / total).fillMaxHeight().graphicsLayer { scaleX = f; transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f) }.background(col))
            }
        }
        Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill("${c[0]} thm", C.thm); Pill("${c[1]} cond", C.cond); Pill("${c[2]} open", C.open)
        }
    }
}

// ---------- CALCULATOR ----------
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CalcScreen(store: Store, content: Content, nav: Nav) {
    var c1 by remember { mutableIntStateOf(79) }
    var c2 by remember { mutableIntStateOf(48) }
    var c3 by remember { mutableIntStateOf(42) }
    var c6 by remember { mutableIntStateOf(3) }
    var n by remember { mutableIntStateOf(31104) }
    var useK by remember { mutableStateOf(false) }
    var touched by remember { mutableStateOf(false) }
    LaunchedEffect(touched) { if (touched) { delay(500); store.earn("calc") } }
    val w2 = if (useK) 2.0 else sqrt(2.0); val w3 = if (useK) 3.0 else sqrt(3.0); val w6 = if (useK) 6.0 else sqrt(6.0)
    val num = c1 + c2 * w2 + c3 * w3 + c6 * w6
    val inv = n / num
    val sigma = (inv - 137.035999177) / 0.000000021
    val ok = abs(sigma) < 2
    val needle by animateFloatAsState((sigma / 6.0).coerceIn(-1.0, 1.0).toFloat(), spring(dampingRatio = .45f, stiffness = 120f), label = "needle")
    val color by animateColorAsState(if (ok) C.thm else C.open, label = "c")
    fun t() { touched = true }
    Column(Modifier.fillMaxSize()) {
        TopBar("α calculator", nav)
        LazyColumn(contentPadding = PaddingValues(16.dp)) {
            item {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(C.panel).border(2.dp, color.copy(alpha = .7f), RoundedCornerShape(20.dp)).padding(18.dp),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("1 / α  =", color = C.muted, fontSize = 14.sp)
                    AnimatedContent(String.format("%.9f", inv), transitionSpec = { (fadeIn() + scaleIn(initialScale = .9f)) togetherWith fadeOut() }, label = "v") {
                        Text(it, fontSize = 32.sp, fontWeight = FontWeight.Black, color = color)
                    }
                    Text("measured (CODATA 2022): 137.035999177 ± 21", color = C.muted, fontSize = 12.sp)
                    Spacer(Modifier.height(14.dp))
                    // sigma meter
                    Box(Modifier.fillMaxWidth().height(34.dp)) {
                        Row(Modifier.fillMaxWidth().height(10.dp).align(Alignment.Center).clip(CircleShape)) {
                            Box(Modifier.weight(2f).fillMaxHeight().background(C.open.copy(alpha = .35f)))
                            Box(Modifier.weight(1f).fillMaxHeight().background(C.thm.copy(alpha = .5f)))
                            Box(Modifier.weight(2f).fillMaxHeight().background(C.open.copy(alpha = .35f)))
                        }
                        BoxWithConstraints(Modifier.fillMaxSize()) {
                            Box(Modifier.offset(x = maxWidth / 2 + maxWidth / 2 * needle - 3.dp).width(6.dp).fillMaxHeight().clip(CircleShape).background(C.ink))
                        }
                    }
                    Text(if (abs(sigma) < 1e4) String.format("%+.2fσ from measurement", sigma) else String.format("%.1f million σ away", abs(sigma) / 1e6),
                        fontWeight = FontWeight.Bold, color = color)
                    Text(if (ok) "✓ consistent with experiment" else "✗ ruled out by experiment", color = color, fontSize = 13.sp)
                }
            }
            item { SectionLabel("Counts × weights") }
            item { Stepper("Weight 1 (antisymmetric)", c1, 1) { c1 = it; t() } }
            item { Stepper(if (useK) "Weight 2" else "Weight √2 (one slot each end)", c2, 1) { c2 = it; t() } }
            item { Stepper(if (useK) "Weight 3" else "Weight √3 (both slots one kind)", c3, 1) { c3 = it; t() } }
            item { Stepper(if (useK) "Weight 6" else "Weight √6 (commutators)", c6, 1) { c6 = it; t() } }
            item { Stepper("Denominator N", n, 24) { n = it; t() } }
            item {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 8.dp)) {
                    Switch(checked = useK, onCheckedChange = { useK = it; t() })
                    Spacer(Modifier.width(10.dp)); Text("Use weights k instead of √k", color = C.ink)
                }
            }
            item {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    AssistChip(onClick = { c1 = 79; c2 = 48; c3 = 42; c6 = 3; n = 31104; useK = false }, label = { Text("Reset to the Letter") })
                    AssistChip(onClick = { c1 = 172; c2 = 0; c3 = 0; c6 = 0; useK = false; t() }, label = { Text("No weights") })
                    AssistChip(onClick = { c1 = 79; c2 = 48; c3 = 42; c6 = 3; n = 31104; useK = true; t() }, label = { Text("k not √k") })
                }
            }
            val rest = content.articles["calc"]!!.dropWhile { !(it is Block.Text && it.kind == "h3") }
            items(rest.size) { BlockView(rest[it], store.fontScale.value) { l -> nav.link(l) } }
        }
    }
}


@Composable
fun Stepper(label: String, value: Int, step: Int, onChange: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp).clip(RoundedCornerShape(14.dp)).background(C.panel).padding(horizontal = 14.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = C.ink, fontSize = 14.sp, modifier = Modifier.weight(1f))
        IconButton(onClick = { onChange((value - step).coerceAtLeast(0)) }) { Icon(Icons.Rounded.Remove, "minus", tint = C.accent) }
        AnimatedContent(value, transitionSpec = {
            if (targetState > initialState) (slideInVertically { -it } + fadeIn()) togetherWith (slideOutVertically { it } + fadeOut())
            else (slideInVertically { it } + fadeIn()) togetherWith (slideOutVertically { -it } + fadeOut())
        }, label = "st") { Text("$it", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = C.ink, textAlign = TextAlign.Center, modifier = Modifier.widthIn(min = 56.dp)) }
        IconButton(onClick = { onChange(value + step) }) { Icon(Icons.Rounded.Add, "plus", tint = C.accent) }
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
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.panel).clickable { open = !open }
                    .animateContentSize().padding(14.dp)) {
                    Text(t.term, fontWeight = FontWeight.Bold, color = if (open) C.accent else C.ink, fontSize = 16.sp)
                    if (open) Text(t.def, fontFamily = Serif, fontSize = 16.sp, lineHeight = 23.sp, color = C.ink, modifier = Modifier.padding(top = 6.dp))
                }
            }
            item {
                TextButton(onClick = { nav.go("reader/comp/22") }) { Text("AWG's own ~200-term Rosetta table → compendium p. 22") }
            }
        }
    }
}
