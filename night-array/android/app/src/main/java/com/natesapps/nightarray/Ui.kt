package com.natesapps.nightarray

import android.content.Context
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.foundation.selection.toggleable
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineBreak
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.ui.platform.LocalDensity
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
/**
 * The few text sizes below body copy. Nothing that carries information is set smaller than [Micro].
 * Wide-tracked uppercase is for headings and short labels; captions and hints are sentence case.
 */
object Type {
    /** Tracked uppercase labels, column heads, status lines. */
    val Micro = 10.sp
    /** Sentence-case captions and instructions. */
    val Caption = 12.sp
}

/** Large font scale (accessibility settings): wide letter spacing is the first thing to give. */
@Composable
fun largeFont(): Boolean = LocalDensity.current.fontScale > 1.3f

/** Thin, wide-tracked uppercase text, like the lettering on the concept board. */
@Composable
fun Tracked(
    text: String, modifier: Modifier = Modifier, size: TextUnit = 12.sp, color: Color = C.ink,
    weight: FontWeight = FontWeight.Light, tracking: Float = 0.24f, align: TextAlign? = null, maxLines: Int = Int.MAX_VALUE,
    lineBreak: LineBreak? = null, fitToWidth: Boolean = false,
) {
    // At large font scales the tracking is tightened so labels keep to their lines instead of truncating.
    val large = largeFont()
    val tr = if (large) tracking.coerceAtMost(0.06f) else tracking
    if (fitToWidth && maxLines == 1 && large) {
        // A one-line label in a fixed-width control (a button, a segment): shrink it to fit rather than cut it off,
        // but never below the size it has at the default font scale.
        val fs = LocalDensity.current.fontScale
        BasicText(
            text.uppercase(), modifier, maxLines = 1, softWrap = false, overflow = TextOverflow.Ellipsis,
            style = LocalTextStyle.current.merge(TextStyle(color = color, fontSize = size, fontWeight = weight, letterSpacing = (size.value * tr).sp,
                textAlign = align ?: TextAlign.Unspecified, lineHeight = (size.value * 1.45f).sp)),
            autoSize = TextAutoSize.StepBased(minFontSize = (size.value / fs).sp, maxFontSize = size, stepSize = 0.5.sp),
        )
        return
    }
    Text(
        text.uppercase(), modifier, color = color, fontSize = size, fontWeight = weight,
        letterSpacing = (size.value * tr).sp, textAlign = align, maxLines = maxLines, lineHeight = (size.value * 1.45f).sp,
        overflow = if (maxLines == 1) TextOverflow.Ellipsis else TextOverflow.Clip,
        style = if (lineBreak != null) LocalTextStyle.current.copy(lineBreak = lineBreak) else LocalTextStyle.current,
    )
}

/** A short tracked uppercase label at the smallest readable size ([Type.Micro]). */
@Composable
fun MicroLabel(text: String, modifier: Modifier = Modifier, color: Color = C.muted, tracking: Float = 0.2f, align: TextAlign? = null, maxLines: Int = Int.MAX_VALUE, weight: FontWeight = FontWeight.Normal, fitToWidth: Boolean = false) =
    Tracked(text, modifier, size = Type.Micro, color = color, weight = weight, tracking = tracking, align = align, maxLines = maxLines, fitToWidth = fitToWidth)

/** Sentence-case caption or instruction ([Type.Caption]), no wide tracking. */
@Composable
fun Caption(text: String, modifier: Modifier = Modifier, color: Color = C.ink.copy(alpha = .75f), align: TextAlign? = null) =
    Text(text.nbUnits(), modifier, color = color, fontSize = Type.Caption, lineHeight = 16.sp, letterSpacing = 0.1.sp, textAlign = align)

/** Marks a part that sits inside the station (hidden in the Studio view, shown in X-ray). */
@Composable
fun InternalTag(modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(50)
    Box(
        modifier.semantics(mergeDescendants = true) { contentDescription = "Internal part" }
            .clip(shape).border(1.dp, C.amber.copy(alpha = .45f), shape).padding(horizontal = 7.dp, vertical = 1.dp),
    ) { Tracked("Internal", size = Type.Micro, color = C.amber, weight = FontWeight.Normal, tracking = .1f, maxLines = 1) }
}

@Composable
fun Tagline(text: String = "Your hardware. Your OS.", size: TextUnit = 20.sp, color: Color = C.ink.copy(alpha = .92f), modifier: Modifier = Modifier) {
    Text(text, modifier, fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = size, color = color, lineHeight = (size.value * 1.3f).sp)
}

val Body = TextStyle(fontSize = 15.5.sp, lineHeight = 25.sp, color = C.ink.copy(alpha = .86f))

@Composable
fun BodyText(text: String, modifier: Modifier = Modifier, color: Color = C.ink.copy(alpha = .84f)) {
    Text(text.nbUnits(), modifier, style = Body.copy(color = color))
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
            .padding(horizontal = 16.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center,
    ) {
        if (leading != null) { leading(); Spacer(Modifier.width(8.dp)) }
        Tracked(text, size = 11.sp, color = if (enabled) color else color.copy(alpha = .4f), weight = FontWeight.Normal, tracking = 0.17f, maxLines = 1, fitToWidth = true)
    }
}

@Composable
fun Chip(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, leading: (@Composable () -> Unit)? = null, compact: Boolean = false) {
    val shape = RoundedCornerShape(50)
    val bgc by animateColorAsState(if (selected) C.amberSoft else C.panel.copy(alpha = .7f), tween(220), label = "chip")
    val bc by animateColorAsState(if (selected) C.amber.copy(alpha = .8f) else C.line, tween(220), label = "chipb")
    Row(
        modifier.semantics { this.selected = selected }.clip(shape).background(bgc).border(1.dp, bc, shape)
            .clickable(role = Role.Tab, onClick = onClick).padding(horizontal = if (compact) 11.dp else 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (leading != null) { leading(); Spacer(Modifier.width(7.dp)) }
        Tracked(label, size = 10.5.sp, color = if (selected) C.amber else C.ink.copy(alpha = .85f), weight = FontWeight.Normal, tracking = if (compact) 0.05f else 0.16f, maxLines = 1)
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
                Tracked(label, size = 10.5.sp, color = if (on) C.ink else C.muted, weight = if (on) FontWeight.Normal else FontWeight.Light, tracking = 0.2f, maxLines = 1, fitToWidth = true)
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
private val UNIT_GAP = Regex("""(\d) (mm|cm|kg|g|ppi|%|cm³|m|°)(?!\p{L})""")

/**
 * Keeps a number with its unit ("54 mm", "29.00 kg") and with "×", so a measurement never breaks across lines; and an
 * em dash with the word before it, so no line starts with one ("Lift straight up — nothing to unlock").
 */
fun String.nbUnits(): String = UNIT_GAP.replace(this) { "${it.groupValues[1]}\u00A0${it.groupValues[2]}" }.replace(" × ", "\u00A0×\u00A0").replace(" — ", "\u00A0— ")

@Composable
fun SpecRow(label: String, value: String, modifier: Modifier = Modifier, last: Boolean = false) {
    Column(modifier) {
        Row(Modifier.fillMaxWidth().padding(vertical = 11.dp), verticalAlignment = Alignment.Top) {
            Tracked(label, Modifier.weight(0.42f).padding(top = 2.dp, end = 12.dp), size = Type.Micro, color = C.muted, tracking = 0.2f)
            Text(value.nbUnits(), Modifier.weight(0.58f), color = C.ink, fontSize = 14.sp, lineHeight = 20.sp)
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
        // produceState keeps its value across key changes: start from this path's own bitmap, never the previous one's
        value = initial
        if (path != null && initial == null && !Img.knownMissing(path)) value = withContext(Dispatchers.IO) { Img.load(ctx.applicationContext, path, maxDim) }
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
    sketchMode: String = "work", sketchHighlight: String? = null, sketchFinish: String = "titanium", animateSketch: Boolean = true,
    sketchFocus: String? = null, sketchDockStep: String? = null, sketchPadding: PaddingValues = PaddingValues(0.dp),
) {
    val ctx = LocalContext.current
    val path = remember(names) { firstExisting(ctx, names.map { if (it.contains('/')) it else "renders/$it" }) }
    val img by rememberAssetImage(path, maxDim)
    Box(modifier.background(C.bg).clipToBounds()) {
        val bmp = img
        if (bmp != null) {
            val drift = if (kenBurns) kenBurnsDrift() else null
            val fade = remember(bmp) { Animatable(if (Img.synchronous) 1f else 0f) }
            LaunchedEffect(bmp) { fade.animateTo(1f, tween(480)) }
            Image(
                bmp, description, contentScale = contentScale, alignment = alignment,
                modifier = Modifier.fillMaxSize().graphicsLayer {
                    alpha = fade.value
                    if (drift != null) { scaleX = drift.scale; scaleY = drift.scale; translationX = drift.dx * size.width; translationY = drift.dy * size.height }
                },
            )
        } else if (path == null || Img.knownMissing(path)) {
            val first = names.firstOrNull().orEmpty()
            StationSketch(Modifier.fillMaxSize().padding(sketchPadding), mode = sketchMode, highlight = sketchHighlight, finish = sketchFinish, animate = animateSketch,
                focus = sketchFocus ?: stillFocus(first), dockStep = sketchDockStep ?: stillDockStep(first))
        }
    }
}

/**
 * Like [ContentScale.Crop], but never zooms in so far that less than [minWidth] of the image's width stays visible.
 * The renders are 16:9 with the station spanning the frame; in a tall box plain Crop would cut off the dock and the
 * left panel, so tall boxes get a band of night above and below instead. `CoverWidth(1f)` keeps the whole width.
 */
class CoverWidth(private val minWidth: Float) : ContentScale {
    override fun computeScaleFactor(srcSize: Size, dstSize: Size): androidx.compose.ui.layout.ScaleFactor {
        if (srcSize.width <= 0f || srcSize.height <= 0f) return androidx.compose.ui.layout.ScaleFactor(1f, 1f)
        val fill = max(dstSize.width / srcSize.width, dstSize.height / srcSize.height)
        val cap = dstSize.width / (srcSize.width * minWidth.coerceIn(.1f, 1f))
        val s = kotlin.math.min(fill, cap)
        return androidx.compose.ui.layout.ScaleFactor(s, s)
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


// ---------- chrome ----------
@Composable
fun IconCircle(
    icon: ImageVector, description: String, onClick: () -> Unit, modifier: Modifier = Modifier, tint: Color = C.ink,
    size: Dp = 42.dp, background: Color = C.bg.copy(alpha = .6f), border: Color = C.ink.copy(alpha = .14f),
) {
    Box(
        modifier.size(size).clip(CircleShape).background(background).border(1.dp, border, CircleShape)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, description, tint = tint, modifier = Modifier.size(size * 0.46f)) }
}

@Composable
fun BackButton(onClick: () -> Unit, modifier: Modifier = Modifier) =
    IconCircle(Icons.AutoMirrored.Outlined.ArrowBack, "Back", onClick, modifier)

/** True once a list has scrolled [past] its first item's top by more than [threshold]. */
@Composable
fun rememberScrolledPast(list: LazyListState, threshold: Dp): State<Boolean> {
    val px = with(LocalDensity.current) { threshold.toPx() }
    return remember(list, px) { derivedStateOf { list.firstVisibleItemIndex > 0 || list.firstVisibleItemScrollOffset > px } }
}

/**
 * Top chrome for scrolling detail screens: a floating back button over the hero image; once the page scrolls
 * under it, a night-dark scrim and the screen title fade in so nothing reads through the button.
 */
@Composable
fun DetailChrome(title: String, scrolled: Boolean, onBack: () -> Unit, modifier: Modifier = Modifier, actions: @Composable RowScope.() -> Unit = {}) {
    val a by animateFloatAsState(if (scrolled) 1f else 0f, tween(280), label = "chrome")
    Box(modifier.fillMaxWidth()) {
        Box(Modifier.matchParentSize().graphicsLayer { alpha = a }
            .background(Brush.verticalGradient(0f to C.bg, .8f to C.bg, 1f to Color.Transparent)))
        Row(
            Modifier.fillMaxWidth().statusBarsPadding().padding(start = 14.dp, end = 14.dp, top = 8.dp, bottom = 20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BackButton(onBack)
            Spacer(Modifier.width(14.dp))
            Tracked(title, Modifier.weight(1f).graphicsLayer { alpha = a }.testTag("chrome-title"), size = 11.sp, tracking = .26f, maxLines = 1)
            actions()
        }
    }
}

/** Title block for tab roots: amber dash + kicker, thin wide-tracked title, optional muted line. */
@Composable
fun ScreenTitle(kicker: String, title: String, modifier: Modifier = Modifier, sub: String? = null) {
    Column(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) { AmberDash(22.dp); Spacer(Modifier.width(10.dp)); Kicker(kicker) }
        Spacer(Modifier.height(14.dp))
        Tracked(title, size = 25.sp, tracking = .2f)
        if (sub != null) { Spacer(Modifier.height(10.dp)); Text(sub, color = C.muted, fontSize = 14.5.sp, lineHeight = 22.sp) }
    }
}

@Composable
fun Hairline(modifier: Modifier = Modifier, color: Color = C.line) = Box(modifier.fillMaxWidth().height(1.dp).background(color))

/** Thin on/off switch: a line track with an amber knob. */
@Composable
fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit, modifier: Modifier = Modifier, sub: String? = null) {
    val t by animateFloatAsState(if (checked) 1f else 0f, tween(220), label = "tg")
    Row(
        modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).toggleable(checked, role = Role.Switch, onValueChange = onChange)
            .padding(vertical = 9.dp, horizontal = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Tracked(label, size = 10.5.sp, color = C.ink.copy(alpha = .9f), weight = FontWeight.Normal, tracking = .18f)
            if (sub != null) Text(sub, color = C.muted, fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 3.dp))
        }
        Box(
            Modifier.size(40.dp, 22.dp).clip(RoundedCornerShape(50)).background(lerp(C.panel2, C.amberSoft, t))
                .border(1.dp, lerp(C.line, C.amber.copy(alpha = .7f), t), RoundedCornerShape(50)).padding(3.dp),
        ) { Box(Modifier.offset { androidx.compose.ui.unit.IntOffset((18.dp.toPx() * t).toInt(), 0) }.size(16.dp).clip(CircleShape).background(lerp(C.muted, C.amber, t))) }
    }
}

/** Slider with a hairline track and an amber knob. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NaSlider(value: Float, onChange: (Float) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, range: ClosedFloatingPointRange<Float> = 0f..1f) {
    val src = remember { MutableInteractionSource() }
    Slider(
        value = value, onValueChange = onChange, modifier = modifier.height(34.dp), enabled = enabled, valueRange = range, interactionSource = src,
        thumb = {
            Box(Modifier.size(18.dp).clip(CircleShape).background(if (enabled) C.amber else C.muted.copy(alpha = .5f)).border(4.dp, C.bg.copy(alpha = .35f), CircleShape))
        },
        track = { st ->
            val f = ((st.value - st.valueRange.start) / (st.valueRange.endInclusive - st.valueRange.start)).coerceIn(0f, 1f)
            Canvas(Modifier.fillMaxWidth().height(18.dp)) {
                val y = size.height / 2
                drawLine(C.line, Offset(0f, y), Offset(size.width, y), 2.dp.toPx(), StrokeCap.Round)
                drawLine(if (enabled) C.amber else C.muted.copy(alpha = .4f), Offset(0f, y), Offset(size.width * f, y), 2.dp.toPx(), StrokeCap.Round)
            }
        },
    )
}

@Composable
fun LabeledSlider(label: String, value: Float, onChange: (Float) -> Unit, valueText: String, modifier: Modifier = Modifier, enabled: Boolean = true, sliderTag: String? = null) {
    Column(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Tracked(label, Modifier.weight(1f), size = 10.5.sp, color = if (enabled) C.ink.copy(alpha = .9f) else C.muted, weight = FontWeight.Normal, tracking = .18f)
            Text(valueText, color = if (enabled) C.amber else C.muted, fontSize = 12.5.sp)
        }
        NaSlider(value, onChange, Modifier.fillMaxWidth().then(if (sliderTag != null) Modifier.testTag(sliderTag) else Modifier), enabled)
    }
}

@Composable
fun PageDots(count: Int, current: Int, modifier: Modifier = Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
        repeat(count) { i ->
            val w by animateDpAsState(if (i == current) 18.dp else 6.dp, tween(260), label = "dot")
            Box(Modifier.width(w).height(2.dp).clip(RoundedCornerShape(1.dp)).background(if (i == current) C.amber else C.ink.copy(alpha = .3f)))
        }
    }
}

@Composable
fun FormatBadge(format: String, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(6.dp)
    Box(modifier.widthIn(min = 46.dp).clip(shape).background(C.panel2).border(1.dp, C.line, shape).padding(horizontal = 8.dp, vertical = 5.dp), contentAlignment = Alignment.Center) {
        Tracked(format, size = 10.sp, color = C.titanium, weight = FontWeight.Normal, tracking = .16f, maxLines = 1)
    }
}

/** A small rounded notice: dot + text (+ optional action). */
@Composable
fun Notice(text: String, modifier: Modifier = Modifier, dot: Color = C.amber, action: String? = null, small: Boolean = false, onAction: () -> Unit = {}) {
    val shape = RoundedCornerShape(50)
    Row(
        modifier.clip(shape).background(C.bg.copy(alpha = .8f)).border(1.dp, C.line, shape)
            .padding(start = 12.dp, end = if (action != null) 4.dp else 14.dp, top = if (small) 2.dp else 4.dp, bottom = if (small) 2.dp else 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(dot))
        Spacer(Modifier.width(9.dp))
        Text(text, color = C.ink.copy(alpha = .84f), fontSize = if (small) 11.sp else 12.sp, lineHeight = 15.sp, maxLines = 2,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false).padding(vertical = 5.dp))
        if (action != null) {
            Spacer(Modifier.width(8.dp))
            Box(Modifier.clip(shape).clickable(role = Role.Button, onClick = onAction).padding(horizontal = 12.dp, vertical = 6.dp)) {
                Tracked(action, size = 10.sp, color = C.amber, weight = FontWeight.Normal, tracking = .2f)
            }
        }
    }
}

/** Centres content and caps its width for tablets / landscape. */
fun Modifier.readable(max: Dp = 760.dp): Modifier = this.fillMaxWidth().wrapContentWidth(Alignment.CenterHorizontally).widthIn(max = max).fillMaxWidth()
