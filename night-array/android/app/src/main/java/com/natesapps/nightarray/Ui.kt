package com.natesapps.nightarray

import android.content.Context
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlin.math.max

// ---------- palette (SPEC.md §5) ----------
object C {
    val bg = Color(0xFF0C0A09)
    val panel = Color(0xFF15110F)
    val panel2 = Color(0xFF1E1915)
    val line = Color(0xFF2E2621)
    val ink = Color(0xFFF2EAE1)
    val muted = Color(0xFFA39A90)
    val amber = Color(0xFFF2A04A)
    val amberSoft = Color(0xFF3A2614)
    val titanium = Color(0xFFBDB2A4)
    val oxblood = Color(0xFF7A2E2A)
    val graphite = Color(0xFF3A3735)
    /** Oxblood lifted for legibility as a "does not fit" signal on near-black. */
    val warn = Color(0xFFD9796B)
    val faint = Color(0x14F2EAE1)
    val scrim = Color(0xCC0C0A09)
}

val Serif = FontFamily.Serif

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = C.amber, onPrimary = C.bg, secondary = C.titanium, onSecondary = C.bg,
            background = C.bg, onBackground = C.ink, surface = C.panel, onSurface = C.ink,
            surfaceVariant = C.panel2, onSurfaceVariant = C.muted, outline = C.line, outlineVariant = C.line,
            surfaceContainer = C.panel, surfaceContainerHigh = C.panel2, surfaceContainerHighest = C.panel2,
            surfaceContainerLow = C.panel, surfaceContainerLowest = C.bg, error = C.warn,
        ),
        content = content,
    )
}

// ---------- type ----------
/** Thin, wide-tracked uppercase text, like the lettering on the concept board. */
@Composable
fun Tracked(
    text: String, modifier: Modifier = Modifier, size: TextUnit = 12.sp, color: Color = C.ink,
    weight: FontWeight = FontWeight.Light, tracking: Float = 0.24f, align: TextAlign? = null, maxLines: Int = Int.MAX_VALUE,
) {
    Text(
        text.uppercase(), modifier, color = color, fontSize = size, fontWeight = weight,
        letterSpacing = (size.value * tracking).sp, textAlign = align, maxLines = maxLines, lineHeight = (size.value * 1.45f).sp,
    )
}

@Composable
fun Tagline(text: String = "Your hardware. Your OS.", size: TextUnit = 20.sp, color: Color = C.ink.copy(alpha = .92f), modifier: Modifier = Modifier) {
    Text(text, modifier, fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = size, color = color, lineHeight = (size.value * 1.3f).sp)
}

val Body = TextStyle(fontSize = 15.5.sp, lineHeight = 25.sp, color = C.ink.copy(alpha = .86f))

@Composable
fun BodyText(text: String, modifier: Modifier = Modifier, color: Color = C.ink.copy(alpha = .84f)) {
    Text(text, modifier, style = Body.copy(color = color))
}

/** "| WORK" — amber tick + thin tracked title + optional tracked subtitle. */
@Composable
fun SectionHeader(title: String, sub: String? = null, modifier: Modifier = Modifier, size: TextUnit = 15.sp) {
    Row(modifier.padding(top = 8.dp), verticalAlignment = Alignment.Top) {
        Box(Modifier.padding(top = 3.dp).width(2.dp).height((size.value * 1.15f).dp).background(C.amber))
        Spacer(Modifier.width(14.dp))
        Column {
            Tracked(title, size = size, tracking = 0.28f)
            if (sub != null) Tracked(sub, size = 10.sp, color = C.muted, tracking = 0.3f, modifier = Modifier.padding(top = 5.dp))
        }
    }
}

@Composable
fun Kicker(text: String, color: Color = C.amber, modifier: Modifier = Modifier) =
    Tracked(text, modifier, size = 10.sp, color = color, weight = FontWeight.Normal, tracking = 0.32f)

/** A thin amber dash, the board's signature mark. */
@Composable
fun AmberDash(width: Dp = 28.dp, modifier: Modifier = Modifier) {
    Box(modifier.width(width).height(1.5.dp).background(Brush.horizontalGradient(listOf(C.amber, C.amber.copy(alpha = .35f)))))
}

// ---------- buttons, chips, cards ----------
@Composable
fun LineButton(
    text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = C.amber, filled: Boolean = false,
    leading: (@Composable () -> Unit)? = null, enabled: Boolean = true,
) {
    val shape = RoundedCornerShape(50)
    Row(
        modifier.clip(shape)
            .background(if (filled) color.copy(alpha = .16f) else Color.Transparent)
            .border(1.dp, color.copy(alpha = if (enabled) .75f else .25f), shape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center,
    ) {
        if (leading != null) { leading(); Spacer(Modifier.width(8.dp)) }
        Tracked(text, size = 11.sp, color = if (enabled) color else color.copy(alpha = .4f), weight = FontWeight.Normal, tracking = 0.22f, maxLines = 1)
    }
}

@Composable
fun Chip(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, leading: (@Composable () -> Unit)? = null) {
    val shape = RoundedCornerShape(50)
    val bgc by animateColorAsState(if (selected) C.amberSoft else C.panel.copy(alpha = .7f), tween(220), label = "chip")
    val bc by animateColorAsState(if (selected) C.amber.copy(alpha = .8f) else C.line, tween(220), label = "chipb")
    Row(
        modifier.semantics { this.selected = selected }.clip(shape).background(bgc).border(1.dp, bc, shape)
            .clickable(role = Role.Tab, onClick = onClick).padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (leading != null) { leading(); Spacer(Modifier.width(7.dp)) }
        Tracked(label, size = 10.5.sp, color = if (selected) C.amber else C.ink.copy(alpha = .85f), weight = FontWeight.Normal, tracking = 0.16f, maxLines = 1)
    }
}

/** Segmented control with a sliding amber underline. */
@Composable
fun Segmented(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit, modifier: Modifier = Modifier, tagPrefix: String = "seg") {
    val shape = RoundedCornerShape(14.dp)
    Row(modifier.clip(shape).background(C.panel.copy(alpha = .82f)).border(1.dp, C.line, shape).padding(4.dp)) {
        options.forEach { (id, label) ->
            val on = id == selected
            val bgc by animateColorAsState(if (on) C.panel2 else Color.Transparent, tween(240), label = "seg")
            Column(
                Modifier.weight(1f).semantics { this.selected = on }.testTag("$tagPrefix-$id").clip(RoundedCornerShape(11.dp)).background(bgc)
                    .clickable(role = Role.Tab) { onSelect(id) }.padding(vertical = 10.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Tracked(label, size = 10.5.sp, color = if (on) C.ink else C.muted, weight = if (on) FontWeight.Normal else FontWeight.Light, tracking = 0.2f, maxLines = 1)
                Spacer(Modifier.height(5.dp))
                val w by animateDpAsState(if (on) 18.dp else 0.dp, tween(260), label = "segw")
                Box(Modifier.width(w).height(1.5.dp).background(C.amber))
            }
        }
    }
}

@Composable
fun PressCard(onClick: () -> Unit, modifier: Modifier = Modifier, shape: RoundedCornerShape = RoundedCornerShape(20.dp), border: Color = C.line, background: Color = C.panel, padding: Dp = 0.dp, content: @Composable ColumnScope.() -> Unit) {
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val sc by animateFloatAsState(if (pressed) 0.975f else 1f, spring(dampingRatio = .6f, stiffness = 700f), label = "press")
    Column(
        modifier.graphicsLayer { scaleX = sc; scaleY = sc }.clip(shape).background(background).border(1.dp, border, shape)
            .clickable(interactionSource = src, indication = ripple(color = C.amber), onClick = onClick).padding(padding),
        content = content,
    )
}

@Composable
fun Panel(modifier: Modifier = Modifier, padding: Dp = 18.dp, content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(20.dp)
    Column(modifier.clip(shape).background(C.panel).border(1.dp, C.line, shape).padding(padding), content = content)
}

/** label ......... value row used in spec lists. */
@Composable
fun SpecRow(label: String, value: String, modifier: Modifier = Modifier, last: Boolean = false) {
    Column(modifier) {
        Row(Modifier.fillMaxWidth().padding(vertical = 11.dp), verticalAlignment = Alignment.Top) {
            Tracked(label, Modifier.weight(0.42f).padding(top = 2.dp, end = 12.dp), size = 9.5.sp, color = C.muted, tracking = 0.2f)
            Text(value, Modifier.weight(0.58f), color = C.ink, fontSize = 14.sp, lineHeight = 20.sp)
        }
        if (!last) Box(Modifier.fillMaxWidth().height(1.dp).background(C.line.copy(alpha = .7f)))
    }
}

@Composable
fun Swatch(material: String, size: Dp = 14.dp, modifier: Modifier = Modifier) {
    Box(modifier.size(size).clip(CircleShape).background(Brush.linearGradient(swatchColors(material))).border(1.dp, C.ink.copy(alpha = .18f), CircleShape))
}

fun swatchColors(material: String): List<Color> = when (material) {
    "titanium" -> listOf(Color(0xFFD9D0C4), Color(0xFFA89D90), Color(0xFFCBC1B4))
    "graphite" -> listOf(Color(0xFF55514E), Color(0xFF2E2C2A), Color(0xFF45413E))
    "oxblood" -> listOf(Color(0xFF97423C), Color(0xFF5E211E), Color(0xFF86362F))
    "glass_black" -> listOf(Color(0xFF2A2A2E), Color(0xFF0A0A0C))
    "screen" -> listOf(Color(0xFF3B2D3A), Color(0xFF14101A))
    "keycap" -> listOf(Color(0xFF3A3836), Color(0xFF242220))
    "rubber" -> listOf(Color(0xFF2A2828), Color(0xFF161515))
    "amber_led" -> listOf(Color(0xFFFFC27A), Color(0xFFF2A04A))
    "copper" -> listOf(Color(0xFFE0A070), Color(0xFF9A5A30))
    "pcb" -> listOf(Color(0xFF2F6B4E), Color(0xFF173828))
    "ferrite" -> listOf(Color(0xFF5A5856), Color(0xFF353331))
    "laptop_alu" -> listOf(Color(0xFFC9C6C2), Color(0xFF8F8C88))
    "felt" -> listOf(Color(0xFF4A4541), Color(0xFF2C2825))
    "steel" -> listOf(Color(0xFFB8B8B8), Color(0xFF6E6E6E))
    else -> listOf(C.muted, C.line)
}

// ---------- assets & images ----------
/** Decodes JPEG/PNG assets off the main thread, downsampled, with a small LRU cache. */
object Img {
    /** Tests flip this so images decode inline and screenshots are deterministic. */
    @Volatile var synchronous = false
    private val cache = object : LruCache<String, ImageBitmap>(48 * 1024 * 1024) {
        override fun sizeOf(key: String, value: ImageBitmap) = value.width * value.height * 4
    }
    private val missing = java.util.Collections.synchronizedSet(HashSet<String>())

    fun key(path: String, maxDim: Int) = "$path@$maxDim"
    fun cached(path: String, maxDim: Int): ImageBitmap? = cache.get(key(path, maxDim))
    fun knownMissing(path: String) = path in missing

    fun load(ctx: Context, path: String, maxDim: Int): ImageBitmap? {
        cached(path, maxDim)?.let { return it }
        if (path in missing) return null
        return try {
            val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            ctx.assets.open(path).use { BitmapFactory.decodeStream(it, null, opts) }
            if (opts.outWidth <= 0) { missing += path; return null }
            var sample = 1
            while (max(opts.outWidth, opts.outHeight) / (sample * 2) >= maxDim) sample *= 2
            val bmp = ctx.assets.open(path).use { BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample }) }
            bmp?.asImageBitmap()?.also { cache.put(key(path, maxDim), it) } ?: run { missing += path; null }
        } catch (_: Exception) { missing += path; null } catch (_: OutOfMemoryError) { null }
    }
}

@Composable
fun rememberAssetImage(path: String?, maxDim: Int = 1600): State<ImageBitmap?> {
    val ctx = LocalContext.current
    val initial = remember(path, maxDim) { if (path == null) null else if (Img.synchronous) Img.load(ctx, path, maxDim) else Img.cached(path, maxDim) }
    return produceState(initial, path, maxDim) {
        if (path != null && value == null && !Img.knownMissing(path)) value = withContext(Dispatchers.IO) { Img.load(ctx.applicationContext, path, maxDim) }
    }
}

/** First existing path among candidates (cheap: uses the asset index). */
fun firstExisting(ctx: Context, candidates: List<String>): String? = candidates.firstOrNull { AssetIndex.exists(ctx, it) }

/**
 * Shows a render from assets/renders. Candidates are tried in order; when none exists the station
 * sketch is drawn instead, so every screen still looks intentional before the stills are rendered.
 */
@Composable
fun Still(
    names: List<String>, modifier: Modifier = Modifier, contentScale: ContentScale = ContentScale.Crop,
    alignment: Alignment = Alignment.Center, maxDim: Int = 1600, kenBurns: Boolean = false, description: String? = null,
    sketchMode: String = "work",
) {
    val ctx = LocalContext.current
    val path = remember(names) { firstExisting(ctx, names.map { if (it.contains('/')) it else "renders/$it" }) }
    val img by rememberAssetImage(path, maxDim)
    Box(modifier.background(C.bg).clipToBounds()) {
        val bmp = img
        if (bmp != null) {
            val drift = if (kenBurns) kenBurnsDrift() else null
            val fade by animateFloatAsState(1f, tween(500), label = "imgfade")
            Image(
                bmp, description, contentScale = contentScale, alignment = alignment,
                modifier = Modifier.fillMaxSize().graphicsLayer {
                    alpha = fade
                    if (drift != null) { scaleX = drift.scale; scaleY = drift.scale; translationX = drift.dx * size.width; translationY = drift.dy * size.height }
                },
            )
        } else if (path == null || Img.knownMissing(path)) {
            StationSketch(Modifier.fillMaxSize(), mode = sketchMode)
        }
    }
}

class Drift(val scale: Float, val dx: Float, val dy: Float)

@Composable
fun kenBurnsDrift(): Drift {
    val inf = rememberInfiniteTransition(label = "kb")
    val t by inf.animateFloat(0f, 1f, infiniteRepeatable(tween(26000, easing = LinearEasing), RepeatMode.Reverse), label = "kbt")
    val e = FastOutSlowInEasing.transform(t)
    return Drift(1.05f + 0.07f * e, -0.022f + 0.044f * e, 0.012f - 0.02f * e)
}

/** Pinch / double-tap zoom container. Pans only when zoomed, so it plays well inside scrolling pages. */
@Composable
fun Zoomable(modifier: Modifier = Modifier, maxScale: Float = 6f, content: @Composable BoxScope.() -> Unit) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    var boxSize by remember { mutableStateOf(Size.Zero) }
    fun clamp(o: Offset, s: Float): Offset {
        val mx = boxSize.width * (s - 1) / 2; val my = boxSize.height * (s - 1) / 2
        return Offset(o.x.coerceIn(-mx, mx), o.y.coerceIn(-my, my))
    }
    val ts = rememberTransformableState { z, pan, _ ->
        scale = (scale * z).coerceIn(1f, maxScale); offset = clamp(offset + pan * scale, scale)
    }
    Box(
        modifier.clipToBounds()
            .drawBehind { boxSize = size }
            .pointerInput(Unit) {
                detectTapGestures(onDoubleTap = { p ->
                    if (scale > 1.05f) { scale = 1f; offset = Offset.Zero } else {
                        scale = 2.6f; offset = clamp(Offset((size.width / 2f - p.x) * 1.6f, (size.height / 2f - p.y) * 1.6f), scale)
                    }
                })
            }
            .transformable(ts, canPan = { scale > 1.01f })
    ) {
        Box(Modifier.fillMaxSize().graphicsLayer { scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y }, content = content)
    }
}

/** Staggered fade/rise for list items. */
@Composable
fun Appear(index: Int = 0, content: @Composable () -> Unit) {
    var v by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { delay(45L * index.coerceAtMost(10)); v = true }
    val a by animateFloatAsState(if (v) 1f else 0f, tween(520, easing = FastOutSlowInEasing), label = "ap")
    Box(Modifier.graphicsLayer { alpha = a; translationY = (1 - a) * 36f }) { content() }
}

/** A faint drafting grid, used behind drawings and the desk-fit plan. */
fun DrawScope.grid(step: Float, color: Color = C.line.copy(alpha = .45f), major: Int = 5) {
    var i = 0; var x = 0f
    while (x <= size.width) { drawLine(if (i % major == 0) color else color.copy(alpha = color.alpha * .45f), Offset(x, 0f), Offset(x, size.height), 1f); x += step; i++ }
    i = 0; var y = 0f
    while (y <= size.height) { drawLine(if (i % major == 0) color else color.copy(alpha = color.alpha * .45f), Offset(0f, y), Offset(size.width, y), 1f); y += step; i++ }
}

// ---------- the station, drawn (fallback art + decoration) ----------
/**
 * Front elevation of the Night Array drawn from the SPEC envelope numbers (mm). Used wherever a
 * render is missing, so the app always shows the object, not an empty box.
 */
@Composable
fun StationSketch(modifier: Modifier = Modifier, mode: String = "work", glow: Float = 1f) {
    val inf = rememberInfiniteTransition(label = "sk")
    val breathe by inf.animateFloat(.75f, 1f, infiniteRepeatable(tween(4200, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "br")
    Canvas(modifier.background(Brush.verticalGradient(listOf(Color(0xFF14100D), C.bg, Color(0xFF110D0B))))) {
        // model space: x ∈ [-720, 800] mm, y ∈ [-40, 560] mm
        val x0 = -720f; val x1 = 800f; val y0 = -60f; val y1 = 580f
        val s = minOf(size.width / (x1 - x0), size.height / (y1 - y0)) * 0.92f
        val ox = size.width / 2 - (x0 + x1) / 2 * s
        val oy = size.height / 2 + (y0 + y1) / 2 * s
        fun X(x: Float) = ox + x * s
        fun Y(y: Float) = oy - y * s
        val a = glow * breathe
        // desk + warm wash
        drawRect(Brush.verticalGradient(listOf(Color.Transparent, C.amber.copy(alpha = .05f * a)), startY = Y(300f), endY = Y(0f)), Offset(0f, Y(300f)), Size(size.width, Y(0f) - Y(300f)))
        drawLine(C.line, Offset(0f, Y(0f)), Offset(size.width, Y(0f)), 1.2f)
        // under-glow reflection on the desk
        for (k in 6 downTo 1) drawLine(C.amber.copy(alpha = .05f * a * k / 6f), Offset(X(-560f), Y(-k * 5f)), Offset(X(560f), Y(-k * 5f)), (k * 3f) * s.coerceAtLeast(.3f))
        // display (front elevation, slight bow suggests the 1800R curve)
        val top = Y(529f); val bot = Y(156f); val l = X(-692f); val r = X(692f)
        val bow = 10f * s
        val glass = Path().apply {
            moveTo(l, top - bow); quadraticTo((l + r) / 2, top + bow * .6f, r, top - bow)
            lineTo(r, bot + bow); quadraticTo((l + r) / 2, bot - bow * .6f, l, bot + bow); close()
        }
        drawPath(glass, Brush.verticalGradient(listOf(Color(0xFF17131A), Color(0xFF0B090B)), startY = top, endY = bot))
        // dunes on the screen
        clipPathCompat(glass) {
            val d1 = Path().apply {
                moveTo(l, Y(300f)); cubicTo(X(-350f), Y(380f), X(-120f), Y(250f), X(150f), Y(320f)); cubicTo(X(380f), Y(380f), X(560f), Y(300f), r, Y(330f))
                lineTo(r, bot); lineTo(l, bot); close()
            }
            drawPath(d1, Brush.verticalGradient(listOf(Color(0xFF3A2C33), Color(0xFF120E11)), startY = Y(380f), endY = bot))
            val ridge = Path().apply { moveTo(l, Y(300f)); cubicTo(X(-350f), Y(380f), X(-120f), Y(250f), X(150f), Y(320f)); cubicTo(X(380f), Y(380f), X(560f), Y(300f), r, Y(330f)) }
            drawPath(ridge, Brush.horizontalGradient(listOf(Color.Transparent, C.amber.copy(alpha = .75f * a), C.amber.copy(alpha = .15f), Color.Transparent), startX = l, endX = r), style = Stroke(1.6f * s.coerceAtLeast(.6f)))
            val d2 = Path().apply { moveTo(l, Y(240f)); cubicTo(X(-200f), Y(300f), X(200f), Y(220f), r, Y(270f)); lineTo(r, bot); lineTo(l, bot); close() }
            drawPath(d2, Brush.verticalGradient(listOf(Color(0xFF231A1E), Color(0xFF0D0A0C)), startY = Y(300f), endY = bot))
        }
        drawPath(glass, Brush.horizontalGradient(listOf(C.titanium.copy(alpha = .9f), C.titanium.copy(alpha = .45f), C.titanium.copy(alpha = .9f)), startX = l, endX = r), style = Stroke(2.2f * s.coerceAtLeast(.5f)))
        // neck
        val neck = Path().apply { moveTo(X(-160f), Y(36f)); lineTo(X(160f), Y(36f)); lineTo(X(90f), Y(156f)); lineTo(X(-90f), Y(156f)); close() }
        drawPath(neck, Brush.verticalGradient(listOf(Color(0xFF2B2826), Color(0xFF3E3A37)), startY = Y(156f), endY = Y(36f)))
        drawPath(neck, C.titanium.copy(alpha = .25f), style = Stroke(1f))
        for (k in 4 downTo 1) drawLine(C.amber.copy(alpha = .16f * a * k / 4f), Offset(X(-75f), Y(150f)), Offset(X(75f), Y(150f)), (k * 4f) * s.coerceAtLeast(.3f))
        drawLine(C.amber.copy(alpha = .95f * a), Offset(X(-75f), Y(150f)), Offset(X(75f), Y(150f)), 4f * s.coerceAtLeast(.4f))
        // base slab
        drawRoundRect(Brush.verticalGradient(listOf(Color(0xFFCFC5B8), Color(0xFF8E8478), Color(0xFF5E564D)), startY = Y(36f), endY = Y(0f)), Offset(X(-640f), Y(36f)), Size(1290f * s, 36f * s), CornerRadius(8f * s))
        drawLine(Color(0xFFEDE4D8).copy(alpha = .8f), Offset(X(-630f), Y(35f)), Offset(X(640f), Y(35f)), 1.2f)
        // pockets / devices
        if (mode != "work") {
            drawRoundRect(Color(0xFF1C1A19), Offset(X(-268f), Y(31f)), Size(356f * s, 9f * s), CornerRadius(3f * s))
            drawRoundRect(Color(0xFF1C1A19), Offset(X(217f), Y(48f)), Size(66f * s, 22f * s), CornerRadius(10f * s))
            drawLine(C.amber.copy(alpha = .9f * a), Offset(X(235f), Y(30f)), Offset(X(265f), Y(30f)), 2.5f * s.coerceAtLeast(.4f))
        }
        drawLine(C.amber.copy(alpha = .95f * a), Offset(X(-105f), Y(6f)), Offset(X(-75f), Y(6f)), 2f * s.coerceAtLeast(.4f))
        // under-glow strip
        drawLine(C.amber.copy(alpha = a), Offset(X(-560f), Y(2.5f)), Offset(X(560f), Y(2.5f)), 2f * s.coerceAtLeast(.4f))
        // dock wing + laptop
        if (mode != "standalone") drawRoundRect(Brush.horizontalGradient(listOf(Color(0xFFD7CEC2), Color(0xFF9C9286)), startX = X(714f), endX = X(730f)), Offset(X(714.5f), Y(328f)), Size(15f * s, 304f * s), CornerRadius(5f * s))
        val cradle = Path().apply { moveTo(X(650f), Y(0f)); lineTo(X(650f), Y(60f)); quadraticTo(X(700f), Y(66f), X(712f), Y(120f)); lineTo(X(775f), Y(120f)); lineTo(X(775f), Y(0f)); close() }
        drawPath(cradle, Brush.verticalGradient(listOf(Color(0xFFC9BFB2), Color(0xFF6E655B)), startY = Y(120f), endY = Y(0f)))
        drawRect(Brush.verticalGradient(listOf(Color(0xFF8E3A33), Color(0xFF4E1B18)), startY = Y(118f), endY = Y(0f)), Offset(X(745f), Y(118f)), Size(30f * s, 118f * s))
        drawRoundRect(Color(0xFF2E2B29), Offset(X(735f), Y(40f)), Size(34f * s, 22f * s), CornerRadius(3f * s))
        drawLine(C.amber.copy(alpha = a), Offset(X(739f), Y(41f)), Offset(X(765f), Y(41f)), 2f * s.coerceAtLeast(.4f))
    }
}

private inline fun DrawScope.clipPathCompat(p: Path, block: DrawScope.() -> Unit) {
    drawContext.canvas.save(); drawContext.canvas.clipPath(p); block(); drawContext.canvas.restore()
}
