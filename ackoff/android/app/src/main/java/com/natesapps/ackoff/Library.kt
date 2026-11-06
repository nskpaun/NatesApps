package com.natesapps.ackoff

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
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
import androidx.compose.ui.geometry.Offset
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
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.net.URLDecoder
import java.net.URLEncoder

// ---------- LIBRARY: the reading guide + PDFs the user imports ----------
@Composable
fun LibraryScreen(store: Store, content: Content, nav: Nav) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var importing by remember { mutableStateOf(false) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) scope.launch {
            importing = true
            val result = withContext(Dispatchers.IO) { importPdf(ctx, uri, store.pdfDir) }
            importing = false
            store.refreshPdfs()
            store.toast.value = if (result != null) "📄 Saved for offline reading: ${result.nameWithoutExtension}" else "That file doesn't look like a PDF."
        }
    }
    var confirmDelete by remember { mutableStateOf<File?>(null) }
    val guide = content.articles["library"]!!.filter { !(it is Block.Text && it.kind == "kicker") }
    Column(Modifier.fillMaxSize()) {
        TopBar("Library", nav, subtitle = "Your PDFs, readable offline")
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Button(onClick = { picker.launch(arrayOf("application/pdf")) }, modifier = Modifier.fillMaxWidth().height(56.dp), shape = RoundedCornerShape(16.dp), enabled = !importing) {
                    Icon(Icons.Rounded.UploadFile, null); Spacer(Modifier.width(8.dp))
                    Text(if (importing) "Importing…" else "Import PDF", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
            }
            val pdfs = store.pdfs.value
            if (pdfs.isNotEmpty()) item { SectionLabel("Your documents") }
            items(pdfs, key = { it.name }) { f ->
                Appear(0) {
                    PressCard({ nav.go("pdf/" + URLEncoder.encode(f.name, "UTF-8")) }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(44.dp, 56.dp).clip(RoundedCornerShape(6.dp)).background(C.accentSoft), contentAlignment = Alignment.Center) { Text("PDF", color = C.accent, fontWeight = FontWeight.Bold, fontSize = 12.sp) }
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(f.nameWithoutExtension, fontWeight = FontWeight.SemiBold, color = C.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                Text("${f.length() / 1024} KB · offline", color = C.muted, fontSize = 12.sp)
                            }
                            IconButton(onClick = { confirmDelete = f }) { Icon(Icons.Rounded.DeleteOutline, "Remove", tint = C.muted) }
                        }
                    }
                }
            }
            items(guide.size) { BlockView(guide[it], store.fontScale.value) { l -> nav.link(l) } }
        }
    }
    confirmDelete?.let { f ->
        AlertDialog(onDismissRequest = { confirmDelete = null }, containerColor = C.panel,
            title = { Text("Remove this PDF?") }, text = { Text(f.nameWithoutExtension) },
            confirmButton = { TextButton(onClick = { f.delete(); store.refreshPdfs(); confirmDelete = null }) { Text("Remove") } },
            dismissButton = { TextButton(onClick = { confirmDelete = null }) { Text("Cancel") } })
    }
}

/** Copies a picked document into app storage. Returns the saved file, or null if it isn't a PDF. */
fun importPdf(ctx: Context, uri: Uri, dir: File): File? {
    var name = "Document"
    ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
        if (c.moveToFirst()) c.getString(0)?.let { name = it }
    }
    name = name.removeSuffix(".pdf").removeSuffix(".PDF").replace(Regex("[\\\\/:*?\"<>|]"), "_").take(80).ifBlank { "Document" }
    val tmp = File(dir, ".import.tmp")
    ctx.contentResolver.openInputStream(uri)?.use { i -> tmp.outputStream().use { i.copyTo(it) } } ?: return null
    val head = tmp.inputStream().use { s -> ByteArray(5).also { s.read(it) } }
    if (String(head) != "%PDF-") { tmp.delete(); return null }
    var out = File(dir, "$name.pdf"); var n = 2
    while (out.exists()) { out = File(dir, "$name ($n).pdf"); n++ }
    tmp.renameTo(out)
    return out
}

// ---------- PDF viewer (native PdfRenderer, offline) ----------
class PdfDoc(file: File) {
    private val fd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    private val renderer = PdfRenderer(fd)
    private val mutex = Mutex()
    val pageCount = renderer.pageCount
    suspend fun render(index: Int, width: Int): Bitmap = withContext(Dispatchers.IO) {
        mutex.withLock {
            renderer.openPage(index).use { p ->
                val h = (width * p.height.toFloat() / p.width).toInt()
                Bitmap.createBitmap(width, h, Bitmap.Config.ARGB_8888).also {
                    it.eraseColor(android.graphics.Color.WHITE)
                    p.render(it, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                }
            }
        }
    }
    fun close() { runCatching { renderer.close(); fd.close() } }
}

@Composable
fun PdfScreen(store: Store, nav: Nav, encodedName: String) {
    val ctx = LocalContext.current
    val file = remember(encodedName) { File(store.pdfDir, URLDecoder.decode(encodedName, "UTF-8")) }
    val doc = remember(file) { runCatching { PdfDoc(file) }.getOrNull() }
    DisposableEffect(doc) { onDispose { doc?.close() } }
    val state = rememberLazyListState()
    val width = (ctx.resources.displayMetrics.widthPixels * 1.5f).toInt().coerceAtMost(2000)
    var zoomPage by remember { mutableStateOf<Int?>(null) }
    Column(Modifier.fillMaxSize().background(C.bg)) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { nav.back() }) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back", tint = C.ink) }
            Column(Modifier.weight(1f)) {
                Text(file.nameWithoutExtension, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = C.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (doc != null) Text("page ${state.firstVisibleItemIndex + 1} of ${doc.pageCount} · tap a page to zoom", fontSize = 12.sp, color = C.muted)
            }
        }
        if (doc == null) {
            Text("This PDF couldn't be opened.", color = C.muted, modifier = Modifier.padding(24.dp)); return@Column
        }
        LazyColumn(state = state, modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(doc.pageCount) { i ->
                var bmp by remember(i) { mutableStateOf<Bitmap?>(null) }
                LaunchedEffect(i) { bmp = doc.render(i, width) }
                val b = bmp
                if (b == null) Box(Modifier.fillMaxWidth().aspectRatio(0.77f).clip(RoundedCornerShape(6.dp)).background(C.panel), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = C.accent) }
                else Image(b.asImageBitmap(), "Page ${i + 1}", contentScale = ContentScale.FillWidth,
                    modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)).clickable { zoomPage = i })
            }
        }
    }
    zoomPage?.let { i -> if (doc != null) ZoomDialog(doc, i, (width * 1.4f).toInt()) { zoomPage = null } }
}

@Composable
fun ZoomDialog(doc: PdfDoc, index: Int, width: Int, onClose: () -> Unit) {
    var bmp by remember { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(index) { bmp = doc.render(index, width) }
    var scale by remember { mutableFloatStateOf(1.6f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val ts = rememberTransformableState { z, pan, _ -> scale = (scale * z).coerceIn(1f, 6f); offset += pan }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().background(Color(0xF0000000)).transformable(ts)) {
            bmp?.let {
                Image(it.asImageBitmap(), null, contentScale = ContentScale.FillWidth,
                    modifier = Modifier.fillMaxWidth().align(Alignment.Center).graphicsLayer { scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y })
            }
            IconButton(onClick = onClose, modifier = Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(8.dp).clip(CircleShape).background(C.panel)) {
                Icon(Icons.Rounded.Close, "Close", tint = C.ink)
            }
            Text("pinch to zoom · drag to pan", color = C.muted, fontSize = 12.sp, modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(12.dp))
        }
    }
}

// ---------- SEARCH ----------
data class Hit(val where: String, val snippet: AnnotatedString, val route: String)

val ARTICLE_NAMES = mapOf("l1" to "Ackoff in three minutes", "talk" to "The 1993 talk", "lead" to "Leadership is aesthetic", "tools" to "The toolkit", "apply" to "Use it on Monday", "library" to "Library")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SearchScreen(store: Store, content: Content, nav: Nav) {
    var q by remember { mutableStateOf(store.lastQuery) }
    val query = q.trim()
    val hits = remember(query) {
        store.lastQuery = q
        if (query.length < 2) emptyList() else buildList {
            val ql = query.lowercase()
            fun addHit(k: String, t: String) { val i = t.lowercase().indexOf(ql); if (i >= 0) this.add(Hit(ARTICLE_NAMES[k] ?: k, snippet(t, i, query), if (k == "library") "library" else "article/$k")) }
            for ((k, blocks) in content.articles) {
                fun walk(bs: List<Block>) { for (b in bs) when (b) {
                    is Block.Text -> addHit(k, b.spans.joinToString("") { it.text })
                    is Block.Container -> walk(b.blocks)
                    is Block.Table -> b.rows.forEach { r -> addHit(k, r.joinToString("  ·  ") { c -> c.second.joinToString("") { it.text } }) }
                } }
                walk(blocks)
            }
            content.glossary.forEach { t -> val s = t.term + " — " + t.def; val i = s.lowercase().indexOf(ql); if (i >= 0) this.add(Hit("Glossary", snippet(s, i, query), "glossary")) }
        }
    }
    LaunchedEffect(hits.size) { if (hits.isNotEmpty()) store.earn("search") }
    Column(Modifier.fillMaxSize()) {
        TopBar("Search", nav, subtitle = "Every word of the guide and glossary")
        OutlinedTextField(q, { q = it }, Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            placeholder = { Text("e.g. synthesis, aesthetic, acorn, mess") }, leadingIcon = { Icon(Icons.Rounded.Search, null) },
            trailingIcon = { if (q.isNotEmpty()) IconButton(onClick = { q = "" }) { Icon(Icons.Rounded.Close, "Clear") } },
            singleLine = true, shape = RoundedCornerShape(14.dp))
        if (query.length >= 2) Text(if (hits.isEmpty()) "No matches." else "${hits.size} matches", color = C.muted, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp))
        else Column(Modifier.padding(20.dp)) {
            Text("Try:", color = C.muted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("synthesis", "aesthetic", "acorn", "mess", "dissolve", "Taylor", "recreation", "idealized", "automation").forEach { AssistChip(onClick = { q = it }, label = { Text(it) }) }
            }
        }
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(hits) { h ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.panel).clickable { nav.go(h.route) }.padding(14.dp)) {
                    Text(h.where, color = C.accent, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text(h.snippet, color = C.ink, fontSize = 15.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 4.dp))
                }
            }
        }
    }
}

fun snippet(t: String, i: Int, q: String): AnnotatedString {
    val s = (i - 80).coerceAtLeast(0); val e = (i + q.length + 130).coerceAtMost(t.length)
    return buildAnnotatedString {
        append((if (s > 0) "…" else "") + t.substring(s, i))
        withStyle(SpanStyle(background = Color(0xFFFFD27A), color = Color.Black, fontWeight = FontWeight.Bold)) { append(t.substring(i, i + q.length)) }
        append(t.substring(i + q.length, e) + if (e < t.length) "…" else "")
    }
}
