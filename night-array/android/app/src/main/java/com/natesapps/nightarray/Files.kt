package com.natesapps.nightarray

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.provider.DocumentsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material.icons.outlined.OpenInFull
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.ViewInAr
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileNotFoundException

// =====================================================================================================
// Export: Share (cache copy + FileProvider) and Save (Storage Access Framework)
// =====================================================================================================

object Exporter {
    const val AUTHORITY_SUFFIX = ".files"

    fun fileName(f: CadFile): String {
        val base = f.path.substringAfterLast('/')
        return if (base.startsWith("night-array")) base else "night-array-$base"
    }

    /** Copies the asset to cacheDir/share/ (the only directory the FileProvider exposes). */
    fun copyForShare(ctx: Context, f: CadFile): File {
        val dir = File(ctx.cacheDir, "share").apply { mkdirs() }
        // Copies only need to outlive the share sheet; drop ones from earlier days so the cache doesn't keep ~20 MB of CAD.
        val stale = System.currentTimeMillis() - 24L * 3600 * 1000
        dir.listFiles()?.forEach { if (it.lastModified() < stale) it.delete() }
        val out = File(dir, fileName(f))
        ctx.assets.open(f.path).use { input -> out.outputStream().use { input.copyTo(it, 64 * 1024) } }
        return out
    }

    fun shareIntent(ctx: Context, f: CadFile, file: File): Intent {
        val uri = FileProvider.getUriForFile(ctx, ctx.packageName + AUTHORITY_SUFFIX, file)
        val mime = mimeOf(f.format, f.path)
        val send = Intent(Intent.ACTION_SEND).apply {
            type = mime
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_SUBJECT, "Night Array · ${f.label.ifBlank { "CAD" }} (${f.format})")
            clipData = ClipData.newRawUri(file.name, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        return Intent.createChooser(send, "Share ${f.format}").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }

    fun copyTo(ctx: Context, f: CadFile, uri: android.net.Uri) {
        val out = ctx.contentResolver.openOutputStream(uri) ?: error("Couldn't open the destination")
        out.use { o -> ctx.assets.open(f.path).use { it.copyTo(o, 64 * 1024) } }
    }

    /**
     * Save: copies into the document the user just created, and deletes that document again if the copy fails, so no
     * empty or truncated "night-array-…" file is left behind. Blocking; call it off the main thread. True on success.
     */
    fun save(ctx: Context, f: CadFile, uri: android.net.Uri): Boolean {
        val r = runCatching { copyTo(ctx, f, uri) }
        r.exceptionOrNull()?.let { e ->
            android.util.Log.w(ViewerHost.TAG, "Save failed: ${f.path}", e)
            runCatching { DocumentsContract.deleteDocument(ctx.contentResolver, uri) }
        }
        return r.isSuccess
    }
}

/** CreateDocument whose MIME type is chosen per launch (each CAD format has its own). */
class CreateCadDocument : ActivityResultContracts.CreateDocument("application/octet-stream") {
    var mime: String = "application/octet-stream"
    override fun createIntent(context: Context, input: String): Intent = super.createIntent(context, input).setType(mime)
}

class FileActions(val share: (CadFile) -> Unit, val save: (CadFile) -> Unit)

@Composable
fun rememberFileActions(app: AppState, scene: Scene): FileActions {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val contract = remember { CreateCadDocument() }
    var pendingPath by rememberSaveable { mutableStateOf<String?>(null) }
    val launcher = rememberLauncherForActivityResult(contract) { uri ->
        val f = scene.files.firstOrNull { it.path == pendingPath }
        pendingPath = null
        // The app's scope, not the screen's: leaving the screen mid-copy must not turn a finished save into "Couldn't save".
        if (uri != null && f != null) app.scope.launch {
            val ok = withContext(Dispatchers.IO) { Exporter.save(ctx.applicationContext, f, uri) }
            app.toast = if (ok) "Saved ${Exporter.fileName(f)}" else "Couldn't save ${Exporter.fileName(f)}"
        }
    }
    return remember(scene) {
        FileActions(
            share = { f ->
                scope.launch {
                    // runCatching inside withContext: leaving the screen cancels the share quietly instead of reporting an error
                    val copy = withContext(Dispatchers.IO) { runCatching { Exporter.copyForShare(ctx.applicationContext, f) } }
                    val file = copy.getOrElse { e ->
                        app.toast = if (e is FileNotFoundException) "${f.format} isn't in this build" else "Couldn't prepare the ${f.format} file"
                        return@launch
                    }
                    runCatching { ctx.startActivity(Exporter.shareIntent(ctx, f, file).addFlags(if (ctx is android.app.Activity) 0 else Intent.FLAG_ACTIVITY_NEW_TASK)) }
                        .onFailure { app.toast = "No app can receive a ${f.format} file" }
                }
            },
            save = { f ->
                contract.mime = mimeOf(f.format, f.path)
                pendingPath = f.path
                runCatching { launcher.launch(Exporter.fileName(f)) }.onFailure { app.toast = "No file manager available"; pendingPath = null }
            },
        )
    }
}

/** Size of a file in bytes, measured off the main thread when scene.json doesn't say; -1 when missing. */
@Composable
fun rememberFileSize(f: CadFile): Long {
    val ctx = LocalContext.current
    val size by produceState(if (f.bytes > 0) f.bytes else -2L, f.path) {
        if (value == -2L) value = withContext(Dispatchers.IO) { if (AssetIndex.exists(ctx, f.path)) AssetSize.of(ctx, f) else -1L }
    }
    return size
}

// =====================================================================================================
// Files: the CAD library
// =====================================================================================================

@Composable
fun FilesScreen(app: AppState, scene: Scene) {
    val actions = rememberFileActions(app, scene)
    BoxWithConstraints(Modifier.fillMaxSize().background(C.bg)) {
        val pad = if (maxWidth >= 600.dp) 40.dp else 20.dp
        LazyColumn(Modifier.fillMaxSize().testTag("files"), state = app.filesList, contentPadding = PaddingValues(bottom = 40.dp)) {
            item(key = "head") {
                ScreenTitle(
                    "CAD library", "Files",
                    sub = "Every part of the station as STEP, STL, drawing sheets and DXF outlines, all generated from one parametric model.",
                    modifier = Modifier.readable().statusBarsPadding().padding(horizontal = pad).padding(top = 22.dp, bottom = 22.dp),
                )
            }
            item(key = "assembly") { AssemblyCard(app, scene, actions, Modifier.readable().padding(horizontal = pad)) }
            item(key = "groups-h") {
                SectionHeader("Part groups", "${scene.groups.size} groups · ${scene.parts.size} parts", Modifier.readable().padding(horizontal = pad).padding(top = 36.dp, bottom = 14.dp))
            }
            items(scene.groups, key = { it.id }) { g ->
                GroupRow(scene, g, Modifier.readable().padding(horizontal = pad).padding(vertical = 5.dp)) { app.nav.go("group/${g.id}") }
            }
            item(key = "formats") { FormatsLegend(Modifier.readable().padding(horizontal = pad).padding(top = 30.dp)) }
        }
    }
}

@Composable
private fun AssemblyCard(app: AppState, scene: Scene, actions: FileActions, modifier: Modifier) {
    val o = scene.overallMm
    Panel(modifier.testTag("assembly-card"), padding = 0.dp) {
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f)) {
            Still(listOf("exploded.jpg", "hero-stow.jpg", "cad.jpg"), Modifier.fillMaxSize(), maxDim = 1200, sketchMode = "stow", animateSketch = false)
            Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0f to Color.Transparent, .6f to Color.Transparent, 1f to C.panel)))
        }
        Column(Modifier.padding(horizontal = 18.dp).padding(bottom = 10.dp)) {
            Kicker("Full assembly")
            Spacer(Modifier.height(8.dp))
            Tracked(scene.name.substringBefore(" —").ifBlank { "Night Array" }, size = 18.sp, tracking = .2f)
            Spacer(Modifier.height(6.dp))
            Text("Stow pose · ${fmtBox(o)} · ${scene.groups.size} groups, ${scene.parts.size} parts.".nbUnits(), color = C.muted, fontSize = 13.sp, lineHeight = 19.sp)
            Spacer(Modifier.height(8.dp))
            val files = scene.filesOf(null)
            files.forEachIndexed { i, f -> FileRow(f, actions, last = i == files.lastIndex) }
            if (files.isEmpty()) Text("No assembly files in this build.", color = C.muted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 12.dp))
        }
        Hairline()
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.End) {
            LineButton("Open in Studio", { app.openStudio(Preset(mode = "stow", style = "cad", camera = "hero", explode = .6f)) }, color = C.ink.copy(alpha = .8f),
                leading = { Icon(Icons.Outlined.ViewInAr, null, tint = C.ink.copy(alpha = .8f), modifier = Modifier.size(15.dp)) })
        }
    }
}

@Composable
private fun GroupRow(scene: Scene, g: Group, modifier: Modifier, onClick: () -> Unit) {
    PressCard(onClick, modifier.testTag("group-${g.id}"), shape = RoundedCornerShape(18.dp)) {
        Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            PartThumb(g.id, Modifier.size(92.dp).clip(RoundedCornerShape(12.dp)))
            Column(Modifier.weight(1f).padding(start = 14.dp, end = 6.dp)) {
                Tracked(g.name, size = 12.5.sp, color = C.ink, weight = FontWeight.Normal, tracking = .14f, maxLines = 2)
                Spacer(Modifier.height(5.dp))
                Text(g.summary, color = C.muted, fontSize = 12.5.sp, lineHeight = 17.sp, maxLines = 3, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                Spacer(Modifier.height(8.dp))
                Text(listOf(fmtBox(g.bboxMm), fmtMass(g.massG)).filter { it != "—" }.joinToString("  ·  ").ifBlank { "${g.parts.size} parts" },
                    color = C.ink.copy(alpha = .75f), fontSize = 11.5.sp)
                Spacer(Modifier.height(6.dp))
                FormatsLine(scene.filesOf(g.id))
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FormatsLine(files: List<CadFile>) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        files.forEach { f ->
            val size = rememberFileSize(f)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(f.format, color = if (size >= 0) C.titanium else C.muted.copy(alpha = .5f), fontSize = 10.sp, letterSpacing = 1.sp, fontWeight = FontWeight.Medium)
                if (size > 0) { Spacer(Modifier.width(4.dp)); Text(fmtBytes(size), color = C.muted, fontSize = 10.sp) }
            }
        }
    }
}

/** Render of an isolated group; the station sketch with that group spotlit when the render is missing. */
@Composable
fun PartThumb(groupId: String, modifier: Modifier, maxDim: Int = 400) {
    Box(modifier.background(C.panel2)) {
        Still(listOf("part-$groupId.jpg"), Modifier.fillMaxSize(), maxDim = maxDim, sketchMode = if (groupId == "deskmat" || groupId == "keyboard" || groupId == "mouse") "work" else "stow",
            sketchHighlight = groupId, animateSketch = false, description = "Render of the $groupId group")
    }
}

@Composable
private fun FormatsLegend(modifier: Modifier) {
    Column(modifier) {
        Kicker("Formats", color = C.muted)
        Spacer(Modifier.height(10.dp))
        FORMAT_NOTES.forEach { (k, v) ->
            Row(Modifier.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                FormatBadge(k); Spacer(Modifier.width(12.dp)); Text(v, color = C.muted, fontSize = 13.sp)
            }
        }
        Spacer(Modifier.height(10.dp))
        Text("STEP and STL are in millimetres, Z up, so they open upright in CAD tools and slicers. SVG and DXF are in millimetres; GLB is in metres, Y up.", color = C.muted.copy(alpha = .8f), fontSize = 12.sp)
    }
}

@Composable
fun FileRow(f: CadFile, actions: FileActions, last: Boolean = false) {
    val size = rememberFileSize(f)
    val present = size >= 0 || size == -2L
    Column {
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp).testTag("file-${f.id}"), verticalAlignment = Alignment.CenterVertically) {
            FormatBadge(f.format)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(FORMAT_NOTES[f.format] ?: f.label, color = C.ink.copy(alpha = .9f), fontSize = 13.5.sp, lineHeight = 18.sp)
                // The size never truncates, and a long name loses its middle, not its extension.
                if (size == -1L) Text("Not in this build", color = C.muted, fontSize = 11.5.sp, maxLines = 1)
                else Row {
                    if (size > 0) Text("${fmtBytes(size)} · ".nbUnits(), color = C.muted, fontSize = 11.5.sp, maxLines = 1, softWrap = false)
                    Text(Exporter.fileName(f), Modifier.weight(1f, fill = false), color = C.muted, fontSize = 11.5.sp, maxLines = 1, softWrap = false,
                        overflow = androidx.compose.ui.text.style.TextOverflow.MiddleEllipsis)
                }
            }
            IconCircle(Icons.Outlined.Share, "Share ${f.format}", { if (present) actions.share(f) }, Modifier.graphicsLayer { alpha = if (present) 1f else .35f }.testTag("share-${f.id}"),
                size = 38.dp, background = C.panel2)
            Spacer(Modifier.width(8.dp))
            IconCircle(Icons.Outlined.Download, "Save ${f.format}", { if (present) actions.save(f) }, Modifier.graphicsLayer { alpha = if (present) 1f else .35f }.testTag("save-${f.id}"),
                size = 38.dp, background = C.panel2)
        }
        if (!last) Hairline(color = C.line.copy(alpha = .7f))
    }
}

// =====================================================================================================
// Group detail
// =====================================================================================================

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GroupScreen(app: AppState, scene: Scene, id: String) {
    val g = scene.group(id) ?: scene.groups.first()
    val actions = rememberFileActions(app, scene)
    val list = rememberLazyListState()
    val scrolled by rememberScrolledPast(list, 220.dp)
    BoxWithConstraints(Modifier.fillMaxSize().background(C.bg)) {
        val wide = maxWidth >= 600.dp
        val pad = if (wide) 40.dp else 20.dp
        LazyColumn(Modifier.fillMaxSize().testTag("group"), state = list, contentPadding = PaddingValues(bottom = 44.dp)) {
            item(key = "hero") {
                val h = minOf(maxWidth * (if (wide) .5f else .9f), 460.dp)
                Box(Modifier.fillMaxWidth().height(h).background(C.panel)) {
                    PartThumb(g.id, Modifier.fillMaxSize(), maxDim = 1000)
                    Box(Modifier.fillMaxWidth().height(100.dp).background(Brush.verticalGradient(listOf(C.bg.copy(alpha = .7f), Color.Transparent))))
                    Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(90.dp).background(Brush.verticalGradient(listOf(Color.Transparent, C.bg))))
                }
            }
            item(key = "title") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 8.dp)) {
                    Kicker("Part group · ${g.id}")
                    Spacer(Modifier.height(12.dp))
                    Tracked(g.name, size = if (wide) 28.sp else 23.sp, tracking = .16f)
                    Spacer(Modifier.height(10.dp))
                    Tagline(g.summary, size = 17.sp, color = C.titanium)
                    if (g.description.isNotBlank()) { Spacer(Modifier.height(16.dp)); Text(g.description.nbUnits(), style = Body) }
                }
            }
            item(key = "facts") {
                Panel(Modifier.readable().padding(horizontal = pad).padding(top = 24.dp).testTag("group-facts")) {
                    SpecRow("Size", fmtBox(g.bboxMm))
                    SpecRow("Mass", fmtMass(g.massG) + if (g.massG > 0) " (concept estimate)" else "")
                    SpecRow("Volume", if (g.volumeCm3 > 0) "${fmtMm(g.volumeCm3)} cm³" else "—")
                    SpecRow("Parts", "${g.parts.size}")
                    Column(Modifier.padding(top = 12.dp)) {
                        MicroLabel("Materials", color = C.muted, tracking = .2f, weight = FontWeight.Light)
                        Spacer(Modifier.height(10.dp))
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            g.materials.forEach { m ->
                                Row(verticalAlignment = Alignment.CenterVertically) { Swatch(m, 12.dp); Spacer(Modifier.width(7.dp)); Text(scene.materialLabel(m), color = C.ink.copy(alpha = .85f), fontSize = 13.sp) }
                            }
                        }
                    }
                }
            }
            item(key = "studio") {
                LineButton("View in Studio", {
                    app.openStudio(Preset(isolate = g.id, style = if (g.id == "internals") "xray" else "studio", explode = 0f))
                    app.host.frame(g.id)
                }, Modifier.readable().padding(horizontal = pad).padding(top = 20.dp).testTag("view-in-studio"), filled = true,
                    leading = { Icon(Icons.Outlined.ViewInAr, null, tint = C.amber, modifier = Modifier.size(16.dp)) })
            }
            item(key = "drawing") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 34.dp)) {
                    SectionHeader("Drawing sheet", "Three views, iso, title block")
                    Spacer(Modifier.height(14.dp))
                    DrawingPanel(scene, g.id, Modifier.fillMaxWidth().testTag("drawing-panel"), onExpand = { app.nav.go("drawing/${g.id}") })
                }
            }
            item(key = "parts") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 34.dp)) {
                    SectionHeader("Parts", "${g.parts.size} in this group")
                    Spacer(Modifier.height(10.dp))
                    val parts = scene.partsOf(g.id).ifEmpty { g.parts.map { Part(it, g.id, prettyId(it), "titanium", false, emptyList(), 0.0, 0.0) } }
                    Panel(Modifier.fillMaxWidth(), padding = 0.dp) {
                        parts.forEachIndexed { i, p -> PartLine(scene, p, last = i == parts.lastIndex) }
                    }
                }
            }
            item(key = "files") {
                Column(Modifier.readable().padding(horizontal = pad).padding(top = 34.dp)) {
                    SectionHeader("Files", "Share or save, in millimetres")
                    Spacer(Modifier.height(8.dp))
                    val files = scene.filesOf(g.id)
                    Panel(Modifier.fillMaxWidth().testTag("group-files"), padding = 0.dp) {
                        Column(Modifier.padding(horizontal = 16.dp)) {
                            files.forEachIndexed { i, f -> FileRow(f, actions, last = i == files.lastIndex) }
                            if (files.isEmpty()) Text("No files for this group in this build.", color = C.muted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 14.dp))
                        }
                    }
                }
            }
        }
        DetailChrome(g.name, scrolled, { app.nav.back() })
    }
}

@Composable
private fun PartLine(scene: Scene, p: Part, last: Boolean) {
    Column {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Swatch(p.material, 12.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(p.name, Modifier.weight(1f, fill = false), color = C.ink, fontSize = 14.sp)
                    if (p.internal) { Spacer(Modifier.width(8.dp)); InternalTag() }
                }
                Text(listOf(scene.materialLabel(p.material), fmtBox(p.bboxMm).takeIf { it != "—" }).filterNotNull().joinToString(" · "), color = C.muted, fontSize = 11.5.sp)
            }
            Text(fmtMass(p.massG), color = C.ink.copy(alpha = .8f), fontSize = 12.5.sp)
        }
        if (!last) Hairline(color = C.line.copy(alpha = .6f))
    }
}

/** The group's drawing sheet on a dark drafting panel; pinch or double-tap to zoom. */
@Composable
fun DrawingPanel(scene: Scene, groupId: String, modifier: Modifier, onExpand: (() -> Unit)? = null, fill: Boolean = false) {
    val ctx = LocalContext.current
    val path = remember(groupId) { (scene.drawings[groupId] ?: "drawings/$groupId.png").let { if (AssetIndex.exists(ctx, it)) it else null } }
    val img by rememberAssetImage(path, 2400)
    val bmp = img
    val aspect = if (bmp != null) bmp.width.toFloat() / bmp.height else 1.414f
    val shape = RoundedCornerShape(if (fill) 0.dp else 18.dp)
    Box(
        modifier.then(if (fill) Modifier.fillMaxSize() else Modifier.aspectRatio(aspect.coerceIn(.6f, 2.4f)))
            .clip(shape).background(Color(0xFF0F0D0C)).border(if (fill) 0.dp else 1.dp, C.line, shape),
    ) {
        Canvas(Modifier.fillMaxSize()) { grid(14.dp.toPx(), C.line.copy(alpha = .5f)) }
        if (bmp != null) {
            Zoomable(Modifier.fillMaxSize()) {
                Image(bmp, "Drawing sheet for $groupId", Modifier.fillMaxSize().padding(if (fill) 12.dp else 8.dp), contentScale = ContentScale.Fit)
            }
        } else {
            StationSketch(Modifier.fillMaxSize().padding(24.dp).graphicsLayer { alpha = .5f }, mode = "stow", highlight = groupId, animate = false, background = false)
            Text("Drawing sheet not in this build", color = C.muted, fontSize = 12.sp, modifier = Modifier.align(Alignment.BottomCenter).padding(14.dp))
        }
        if (onExpand != null && bmp != null) {
            IconCircle(Icons.Outlined.OpenInFull, "Open drawing full screen", onExpand, Modifier.align(Alignment.TopEnd).padding(10.dp).testTag("drawing-expand"), size = 36.dp)
        }
    }
}

@Composable
fun DrawingScreen(app: AppState, scene: Scene, id: String) {
    val g = scene.group(id) ?: scene.groups.first()
    val actions = rememberFileActions(app, scene)
    Column(Modifier.fillMaxSize().background(Color(0xFF0A0908)).testTag("drawing")) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            BackButton({ app.nav.back() })
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Tracked("Drawing · ${g.name}", size = 12.sp, tracking = .22f, maxLines = 1)
                MicroLabel("Pinch or double-tap to zoom", Modifier.padding(top = 3.dp), color = C.muted, tracking = .2f, weight = FontWeight.Light)
            }
            scene.filesOf(g.id).firstOrNull { it.format == "SVG" }?.let { svg ->
                IconCircle(Icons.Outlined.Share, "Share SVG", { actions.share(svg) }, size = 38.dp, background = C.panel2)
                Spacer(Modifier.width(8.dp))
                IconCircle(Icons.Outlined.Download, "Save SVG", { actions.save(svg) }, size = 38.dp, background = C.panel2)
            }
        }
        DrawingPanel(scene, g.id, Modifier.weight(1f).fillMaxWidth().navigationBarsPadding(), fill = true)
    }
}

