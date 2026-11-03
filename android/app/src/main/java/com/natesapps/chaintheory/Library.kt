package com.natesapps.chaintheory

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File

data class DocInfo(val key: String, val title: String, val desc: String, val emoji: String, val pages: Int)
val DOC_INFO = listOf(
    DocInfo("talk", "An Introduction to Chain Theory", "The talk slides. The best structured walk-through: motivation, axiom, the α count, Lean, the compendium.", "🎤", 71),
    DocInfo("alpha", "A Parameter-Free Candidate for the Fine-Structure Constant", "The alpha Letter plus Supplemental Material. The sharp, short claim.", "α", 24),
    DocInfo("comp", "Chain Theory: A Compendium of Preliminary Findings", "Working draft, release 0.1. Sixteen Parts, appendices, and 52 instrument chapters.", "📚", 754),
)

@Composable
fun LibraryScreen(store: Store, nav: Nav) {
    Column(Modifier.fillMaxSize()) {
        TopBar("Library", nav, subtitle = "Full text + original PDFs, all offline")
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            itemsIndexed(DOC_INFO) { i, d ->
                Appear(i) {
                    PressCard({ nav.go("reader/${d.key}/${store.pos(d.key)}") }) {
                        Row(verticalAlignment = Alignment.Top) {
                            Box(Modifier.size(54.dp, 70.dp).clip(RoundedCornerShape(8.dp)).background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(C.accent, Color(0xFF7A3A0E)))),
                                contentAlignment = Alignment.Center) { Text(d.emoji, fontSize = 24.sp, color = Color.White) }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text(d.title, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = C.ink, lineHeight = 22.sp)
                                Text(d.desc, color = C.muted, fontSize = 14.sp, lineHeight = 19.sp, modifier = Modifier.padding(top = 4.dp))
                                val p = store.pos(d.key)
                                Spacer(Modifier.height(8.dp))
                                LinearProgressIndicator(progress = { p / d.pages.toFloat() }, modifier = Modifier.fillMaxWidth().height(5.dp).clip(CircleShape), color = C.accent, trackColor = C.line, drawStopIndicator = {})
                                Text(if (p > 1) "Continue · page $p of ${d.pages}" else "${d.pages} pages", color = C.accent2, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
                            }
                        }
                    }
                }
            }
            item { SectionLabel("Bookmarks") }
            val bms = store.bookmarks.value
            if (bms.isEmpty()) item { Text("None yet. Tap the bookmark icon in the reader to save a page.", color = C.muted, fontSize = 14.sp) }
            items(bms) { b ->
                PressCard({ nav.go("reader/${b.doc}/${b.page}") }) {
                    Text("${DOC_SHORT[b.doc]} · p. ${b.page}", color = C.accent, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    if (b.label.isNotBlank()) Text(b.label, color = C.ink)
                }
            }
            item {
                Text("Sources: alexwg.org/publications, downloaded Nov 3, 2026. Copyright their author; bundled for personal offline reading.",
                    color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(top = 16.dp))
            }
        }
    }
}

// ---------- PDF rendering (native, offline) ----------
object Pdf {
    private val mutex = Mutex()
    private val renderers = HashMap<String, PdfRenderer>()
    private fun renderer(ctx: Context, key: String): PdfRenderer = renderers.getOrPut(key) {
        val f = File(ctx.cacheDir, "$key.pdf")
        if (!f.exists() || f.length() == 0L) ctx.assets.open("$key.pdf").use { i -> f.outputStream().use { i.copyTo(it) } }
        PdfRenderer(ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_ONLY))
    }
    suspend fun render(ctx: Context, key: String, page: Int, width: Int): Bitmap = withContext(Dispatchers.IO) {
        mutex.withLock {
            val r = renderer(ctx, key)
            r.openPage((page - 1).coerceIn(0, r.pageCount - 1)).use { p ->
                val h = (width * p.height.toFloat() / p.width).toInt()
                val bmp = Bitmap.createBitmap(width, h, Bitmap.Config.ARGB_8888)
                bmp.eraseColor(android.graphics.Color.WHITE)
                p.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                bmp
            }
        }
    }
}

@Composable
fun PdfPageView(key: String, page: Int) {
    val ctx = LocalContext.current
    var bmp by remember(key, page) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(key, page) { bmp = Pdf.render(ctx, key, page, (ctx.resources.displayMetrics.widthPixels * 2).coerceAtMost(2400)) }
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(androidx.compose.ui.geometry.Offset.Zero) }
    val tState = rememberTransformableState { z, pan, _ ->
        scale = (scale * z).coerceIn(1f, 5f)
        offset = if (scale == 1f) androidx.compose.ui.geometry.Offset.Zero else offset + pan
    }
    Box(Modifier.fillMaxSize().background(Color(0xFF0E0D0A)).clip(RoundedCornerShape(0.dp)), contentAlignment = Alignment.TopCenter) {
        val b = bmp
        if (b == null) CircularProgressIndicator(Modifier.padding(40.dp), color = C.accent)
        else Image(
            b.asImageBitmap(), "PDF page $page",
            modifier = Modifier.fillMaxWidth().padding(8.dp).transformable(tState)
                .graphicsLayer { scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y },
            contentScale = ContentScale.FillWidth
        )
        if (b != null && scale == 1f) Text("pinch to zoom", color = C.muted, fontSize = 11.sp, modifier = Modifier.align(Alignment.BottomCenter).padding(10.dp))
    }
}

// ---------- READER ----------
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReaderScreen(store: Store, nav: Nav, key: String, startPage: Int, highlight: String?) {
    val ctx = LocalContext.current
    var doc by remember { mutableStateOf<Doc?>(null) }
    LaunchedEffect(key) { doc = Repo.doc(ctx, key) }
    val d = doc
    if (d == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                ChainHero(Modifier.size(220.dp, 70.dp), lit = 6, total = 6)
                Text("Opening ${DOC_SHORT[key]}…", color = C.muted)
            }
        }
        return
    }
    val pager = rememberPagerState(initialPage = (startPage - 1).coerceIn(0, d.pages.size - 1)) { d.pages.size }
    val page = pager.currentPage + 1
    LaunchedEffect(page) { store.read(key, page) }
    var showPdf by remember { mutableStateOf(key == "talk") }
    var showToc by remember { mutableStateOf(false) }
    var showJump by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val section = d.sectionFor(page)
    val marked = store.bookmarks.value.any { it.doc == key && it.page == page }
    val scale = store.fontScale.value

    Column(Modifier.fillMaxSize().background(C.bg)) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { nav.back() }) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back", tint = C.ink) }
            Column(Modifier.weight(1f).clickable { showJump = true }) {
                Text(d.short + " · p. $page / ${d.pages.size}", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = C.ink)
                Text(section?.title ?: d.title, fontSize = 12.sp, color = C.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            IconButton(onClick = { showPdf = !showPdf }) {
                Icon(if (showPdf) Icons.Rounded.Notes else Icons.Rounded.PictureAsPdf, "Toggle original page", tint = if (showPdf) C.accent else C.ink)
            }
            if (d.outline.isNotEmpty()) IconButton(onClick = { showToc = true }) { Icon(Icons.Rounded.Toc, "Contents", tint = C.ink) }
            IconButton(onClick = { store.toggleBookmark(key, page, section?.title ?: "") }) {
                AnimatedContent(marked, transitionSpec = { scaleIn(spring(dampingRatio = .4f)) togetherWith scaleOut() }, label = "bm") {
                    Icon(if (it) Icons.Rounded.Bookmark else Icons.Rounded.BookmarkBorder, "Bookmark", tint = if (it) C.accent else C.ink)
                }
            }
        }
        val prog by animateFloatAsState(page / d.pages.size.toFloat(), label = "rp")
        LinearProgressIndicator(progress = { prog }, modifier = Modifier.fillMaxWidth().height(3.dp), color = C.accent, trackColor = C.line, drawStopIndicator = {})
        HorizontalPager(state = pager, modifier = Modifier.weight(1f), beyondViewportPageCount = 1) { i ->
            val p = i + 1
            Box(Modifier.graphicsLayer {
                val off = (pager.currentPage - i + pager.currentPageOffsetFraction)
                alpha = 1f - kotlin.math.abs(off).coerceIn(0f, 1f) * .5f
                val s = 1f - kotlin.math.abs(off).coerceIn(0f, 1f) * .06f
                scaleX = s; scaleY = s
            }) {
                if (showPdf) PdfPageView(key, p)
                else PageText(d.pages[i], p, d, scale, highlight)
            }
        }
        Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { scope.launch { pager.animateScrollToPage((pager.currentPage - 1).coerceAtLeast(0)) } }) { Icon(Icons.Rounded.ChevronLeft, "Previous", tint = C.ink) }
            Text("swipe ‹ › for pages", color = C.muted, fontSize = 12.sp, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            FontButton(store)
            IconButton(onClick = { scope.launch { pager.animateScrollToPage((pager.currentPage + 1).coerceAtMost(d.pages.size - 1)) } }) { Icon(Icons.Rounded.ChevronRight, "Next", tint = C.ink) }
        }
    }

    if (showToc) ModalBottomSheet(onDismissRequest = { showToc = false }, containerColor = C.panel) {
        var q by remember { mutableStateOf("") }
        OutlinedTextField(q, { q = it }, Modifier.fillMaxWidth().padding(horizontal = 16.dp), placeholder = { Text("Filter sections…") }, singleLine = true, shape = RoundedCornerShape(12.dp))
        val front = if (key == "comp" && q.isBlank()) listOf(OutlineItem("Preface", 1, 2), OutlineItem("Contents", 1, 6), OutlineItem("Abstract & Introduction", 1, 20), OutlineItem("Rosetta glossary", 1, 22), OutlineItem("Register matrix", 1, 36)) else emptyList()
        val items = front + d.outline.filter { q.isBlank() || it.title.contains(q, true) }
        val curIdx = items.indexOfLast { it.page <= page }.coerceAtLeast(0)
        val ls = androidx.compose.foundation.lazy.rememberLazyListState(initialFirstVisibleItemIndex = (curIdx - 3).coerceAtLeast(0))
        LazyColumn(state = ls, contentPadding = PaddingValues(bottom = 40.dp)) {
            itemsIndexed(items) { idx, o ->
                Row(Modifier.fillMaxWidth().background(if (idx == curIdx && q.isBlank()) C.accentSoft else Color.Transparent).clickable {
                    showToc = false; scope.launch { pager.scrollToPage(o.page - 1) }
                }.padding(start = (16 + 14 * o.depth.coerceAtMost(2)).dp, end = 16.dp, top = 11.dp, bottom = 11.dp)) {
                    Text(o.title, modifier = Modifier.weight(1f), color = if (o.depth == 0) C.accent else C.ink,
                        fontWeight = if (o.depth == 0) FontWeight.Bold else null, fontSize = if (o.depth >= 2) 14.sp else 15.sp)
                    Text("${o.page}", color = C.muted, fontSize = 12.sp)
                }
            }
        }
    }
    if (showJump) {
        var v by remember { mutableFloatStateOf(page.toFloat()) }
        AlertDialog(onDismissRequest = { showJump = false }, containerColor = C.panel,
            title = { Text("Go to page ${v.toInt()}") },
            text = {
                Column {
                    Slider(v, { v = it }, valueRange = 1f..d.pages.size.toFloat())
                    Text(d.sectionFor(v.toInt())?.title ?: "", color = C.muted, fontSize = 13.sp)
                }
            },
            confirmButton = { TextButton(onClick = { showJump = false; scope.launch { pager.scrollToPage(v.toInt() - 1) } }) { Text("Go") } },
            dismissButton = { TextButton(onClick = { showJump = false }) { Text("Cancel") } })
    }
}

@Composable
fun PageText(text: String, page: Int, d: Doc, scale: Float, highlight: String?) {
    val paras = remember(text) { text.split("\n\n").filter { it.isNotBlank() } }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 30.dp)) {
        if (paras.isEmpty()) item { Text("(This page is mostly a figure or table. Tap the PDF icon above to see the original.)", color = C.muted) }
        items(paras.size) { i ->
            val p = paras[i]
            val isHeading = p.length < 90 && !p.endsWith(".") && (p.firstOrNull()?.isUpperCase() == true || p.firstOrNull()?.isDigit() == true)
            Text(
                hl(p, highlight),
                fontFamily = if (d.key == "talk" || isHeading) null else Serif,
                fontSize = (if (isHeading) 18.sp else 17.sp) * scale,
                lineHeight = (if (isHeading) 24.sp else 26.sp) * scale,
                fontWeight = if (isHeading) FontWeight.Bold else null,
                color = if (isHeading) C.accent2 else C.ink,
                modifier = Modifier.padding(vertical = if (d.key == "talk") 4.dp else 7.dp)
            )
        }
    }
}

fun hl(text: String, q: String?): AnnotatedString {
    if (q.isNullOrBlank()) return AnnotatedString(text)
    return buildAnnotatedString {
        var i = 0; val lower = text.lowercase(); val ql = q.lowercase()
        while (true) {
            val j = lower.indexOf(ql, i)
            if (j < 0) { append(text.substring(i)); break }
            append(text.substring(i, j))
            withStyle(SpanStyle(background = Color(0xFFFFE08A), color = Color.Black)) { append(text.substring(j, j + q.length)) }
            i = j + q.length
        }
    }
}

// ---------- SEARCH ----------
data class Hit(val where: String, val snippet: AnnotatedString, val route: String)

@Composable
fun SearchScreen(store: Store, content: Content, nav: Nav) {
    val ctx = LocalContext.current
    var q by remember { mutableStateOf(store.lastQuery) }
    var filter by remember { mutableStateOf("all") }
    var hits by remember { mutableStateOf<List<Hit>>(emptyList()) }
    var total by remember { mutableIntStateOf(0) }
    var busy by remember { mutableStateOf(false) }
    LaunchedEffect(q, filter) {
        store.lastQuery = q
        if (q.trim().length < 2) { hits = emptyList(); total = 0; return@LaunchedEffect }
        kotlinx.coroutines.delay(250)
        busy = true
        val query = q.trim(); val ql = query.lowercase()
        val res = ArrayList<Hit>(); var n = 0
        withContext(Dispatchers.Default) {
            if (filter == "all" || filter == "guide") {
                for ((k, blocks) in content.articles) {
                    fun walk(bs: List<Block>) {
                        for (b in bs) when (b) {
                            is Block.Text -> { val t = b.spans.joinToString("") { it.text }; val i = t.lowercase().indexOf(ql); if (i >= 0) { n++; if (res.size < 300) res += Hit("Guide · " + guideName(k), snippet(t, i, query), if (k == "l4") "map" else if (k == "calc") "calc" else "article/$k") } }
                            is Block.Container -> walk(b.blocks)
                            is Block.Table -> b.rows.forEach { r -> r.forEach { c -> val t = c.second.joinToString("") { it.text }; val i = t.lowercase().indexOf(ql); if (i >= 0) { n++; if (res.size < 300) res += Hit("Guide · " + guideName(k), snippet(t, i, query), "article/$k") } } }
                        }
                    }
                    walk(blocks)
                }
                content.glossary.forEach { t -> val s = t.term + " — " + t.def; val i = s.lowercase().indexOf(ql); if (i >= 0) { n++; res += Hit("Glossary", snippet(s, i, query), "glossary") } }
            }
            for (key in DOC_KEYS) {
                if (filter != "all" && filter != key) continue
                val d = Repo.doc(ctx, key)
                d.lower.forEachIndexed { pi, tl ->
                    var i = tl.indexOf(ql); if (i < 0) return@forEachIndexed
                    val first = i; var c = 0
                    while (i >= 0) { c++; i = tl.indexOf(ql, i + ql.length) }
                    n += c
                    if (res.size < 300) {
                        val sec = d.sectionFor(pi + 1)?.title
                        res += Hit("${d.short} · p. ${pi + 1}" + (if (sec != null) " · $sec" else "") + (if (c > 1) " · $c hits" else ""),
                            snippet(d.pages[pi], first, query), "reader/$key/${pi + 1}?q=$query")
                    }
                }
            }
        }
        hits = res; total = n; busy = false
        if (n > 0) store.earn("search")
    }
    Column(Modifier.fillMaxSize()) {
        TopBar("Search", nav, subtitle = "Every word of the guide and all three documents")
        OutlinedTextField(q, { q = it }, Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            placeholder = { Text("e.g. Higgs, Born rule, 31104, confinement") }, leadingIcon = { Icon(Icons.Rounded.Search, null) },
            trailingIcon = { if (q.isNotEmpty()) IconButton(onClick = { q = "" }) { Icon(Icons.Rounded.Close, "Clear") } },
            singleLine = true, shape = RoundedCornerShape(14.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("all" to "All", "guide" to "Guide", "talk" to "Talk", "alpha" to "Letter", "comp" to "Compendium").forEach { (k, l) ->
                FilterChip(selected = filter == k, onClick = { filter = k }, label = { Text(l) },
                    colors = FilterChipDefaults.filterChipColors(selectedContainerColor = C.accent, selectedLabelColor = C.bg))
            }
        }
        AnimatedVisibility(busy) { LinearProgressIndicator(Modifier.fillMaxWidth(), color = C.accent, trackColor = C.line) }
        if (q.trim().length >= 2 && !busy) Text(if (total == 0) "No matches." else "$total matches" + if (hits.size >= 300) " (showing first 300)" else "",
            color = C.muted, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 20.dp))
        if (q.isBlank()) Column(Modifier.padding(20.dp)) {
            Text("Try:", color = C.muted)
            FlowChips(listOf("Higgs", "Born rule", "confinement", "dark matter", "Lorentz", "three generations", "Koide", "cosmological", "proton"), onPick = { q = it })
        }
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(hits) { h ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.panel).clickable { nav.go(h.route) }.padding(14.dp)) {
                    Text(h.where, color = C.accent, fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(h.snippet, color = C.ink, fontSize = 15.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 4.dp))
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FlowChips(items: List<String>, onPick: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        items.forEach { AssistChip(onClick = { onPick(it) }, label = { Text(it) }) }
    }
}

fun guideName(k: String) = mapOf("l1" to "Level 1", "l2" to "Level 2", "l3" to "Level 3", "l4" to "Compendium map", "calc" to "α calculator")[k] ?: k

fun snippet(t: String, i: Int, q: String): AnnotatedString {
    val s = (i - 80).coerceAtLeast(0); val e = (i + q.length + 130).coerceAtMost(t.length)
    val pre = (if (s > 0) "…" else "") + t.substring(s, i).replace(Regex("\\s+"), " ")
    val post = t.substring(i + q.length, e).replace(Regex("\\s+"), " ") + if (e < t.length) "…" else ""
    return buildAnnotatedString {
        append(pre)
        withStyle(SpanStyle(background = Color(0xFFFFE08A), color = Color.Black, fontWeight = FontWeight.Bold)) { append(t.substring(i, i + q.length)) }
        append(post)
    }
}
