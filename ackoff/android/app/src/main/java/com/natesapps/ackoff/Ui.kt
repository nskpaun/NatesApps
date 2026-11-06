package com.natesapps.ackoff

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.random.Random

// ---------- palette ----------
object C {
    val bg = Color(0xFF0D1317)
    val panel = Color(0xFF151D23)
    val panel2 = Color(0xFF1D2730)
    val ink = Color(0xFFE6EEF0)
    val muted = Color(0xFF8FA1A8)
    val line = Color(0xFF2A3640)
    val accent = Color(0xFF4FD1C0)
    val accent2 = Color(0xFFFFD27A)
    val accentSoft = Color(0xFF12332F)
    val thm = Color(0xFF7CC48A)
    val cond = Color(0xFFE2C062)
    val open = Color(0xFFE88A98)
    val violet = Color(0xFFB59CF0)
}

val Serif = FontFamily.Serif

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = C.accent, onPrimary = Color(0xFF1A120B), secondary = C.accent2,
            background = C.bg, surface = C.panel, onSurface = C.ink, onBackground = C.ink,
            surfaceVariant = C.panel2, onSurfaceVariant = C.muted, outline = C.line,
            surfaceContainer = C.panel, surfaceContainerHigh = C.panel2, surfaceContainerLow = C.panel,
        ),
        content = content,
    )
}

// ---------- rich text ----------
fun richText(spans: List<Span>, linkColor: Color = C.accent, onLink: (String) -> Unit): AnnotatedString = buildAnnotatedString {
    for (s in spans) {
        val style = SpanStyle(
            fontWeight = if ('b' in s.style) FontWeight.Bold else null,
            fontStyle = if ('i' in s.style) FontStyle.Italic else null,
            fontFamily = if ('c' in s.style) FontFamily.Monospace else null,
            background = if ('c' in s.style) C.panel2 else Color.Unspecified,
        )
        if (s.link.startsWith("#")) {
            withLink(LinkAnnotation.Clickable(s.link, TextLinkStyles(SpanStyle(color = linkColor, textDecoration = androidx.compose.ui.text.style.TextDecoration.Underline))) { onLink(s.link) }) {
                withStyle(style) { append(s.text) }
            }
        } else withStyle(style) { append(s.text) }
    }
}

@Composable
fun BlockView(b: Block, scale: Float, onLink: (String) -> Unit) {
    val body = 17.sp * scale
    when (b) {
        is Block.Text -> {
            val t = richText(b.spans, onLink = onLink)
            when (b.kind) {
                "kicker" -> Text(t.text.uppercase(), color = C.accent, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 1.5.sp, modifier = Modifier.padding(top = 8.dp))
                "h1" -> Text(t, fontSize = 30.sp * scale, fontWeight = FontWeight.Bold, lineHeight = 36.sp * scale, color = C.ink, modifier = Modifier.padding(vertical = 6.dp))
                "h2" -> Column(Modifier.padding(top = 26.dp, bottom = 6.dp)) {
                    Box(Modifier.width(36.dp).height(3.dp).clip(RoundedCornerShape(2.dp)).background(C.accent))
                    Spacer(Modifier.height(10.dp))
                    Text(t, fontSize = 23.sp * scale, fontWeight = FontWeight.Bold, lineHeight = 29.sp * scale, color = C.ink)
                }
                "h3" -> Text(t, fontSize = 19.sp * scale, fontWeight = FontWeight.SemiBold, color = C.accent2, modifier = Modifier.padding(top = 14.dp, bottom = 2.dp))
                "li" -> Row(Modifier.padding(vertical = 3.dp)) {
                    Text(if (b.number != null) "${b.number}." else "•", color = C.accent, fontSize = body, fontWeight = FontWeight.Bold, modifier = Modifier.width(24.dp))
                    Text(t, fontFamily = Serif, fontSize = body, lineHeight = body * 1.5f, color = C.ink)
                }
                "axiom" -> Box(
                    Modifier.fillMaxWidth().padding(vertical = 12.dp).clip(RoundedCornerShape(14.dp))
                        .background(Brush_accentSoft()).border(1.dp, C.accent.copy(alpha = .5f), RoundedCornerShape(14.dp)).padding(18.dp)
                ) { Text(t, fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 19.sp * scale, lineHeight = 28.sp * scale, color = C.ink) }
                "number" -> Box(
                    Modifier.fillMaxWidth().padding(top = 10.dp).clip(RoundedCornerShape(14.dp)).background(C.panel)
                        .border(1.dp, C.line, RoundedCornerShape(14.dp)).padding(16.dp), contentAlignment = Alignment.Center
                ) { Text(t, fontSize = 19.sp * scale, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, color = C.accent2) }
                "numsmall" -> Text(t, fontSize = 13.sp, color = C.muted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 10.dp))
                else -> Text(t, fontFamily = Serif, fontSize = body, lineHeight = body * 1.55f, color = C.ink, modifier = Modifier.padding(vertical = 6.dp))
            }
        }
        is Block.Container -> {
            val color = when (b.variant) { "warn" -> C.open; "good" -> C.thm; else -> C.cond }
            val isCallout = b.kind == "callout"
            Column(
                Modifier.fillMaxWidth().padding(vertical = 10.dp).clip(RoundedCornerShape(14.dp)).background(C.panel)
                    .border(1.dp, if (isCallout) color.copy(alpha = .6f) else C.line, RoundedCornerShape(14.dp))
                    .padding(horizontal = 16.dp, vertical = 10.dp)
            ) {
                if (isCallout) Text(if (b.variant == "warn") "⚠  CAUTION" else "◆  NOTE", color = color, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp)
                b.blocks.forEach { BlockView(it, scale, onLink) }
            }
        }
        is Block.Table -> TableView(b, scale, onLink)
    }
}

@Composable
private fun Brush_accentSoft() = androidx.compose.ui.graphics.Brush.linearGradient(listOf(C.accentSoft, C.panel))

@Composable
fun TableView(t: Block.Table, scale: Float, onLink: (String) -> Unit) {
    val cols = t.rows.maxOf { it.size }
    Column(
        Modifier.fillMaxWidth().padding(vertical = 10.dp).clip(RoundedCornerShape(12.dp)).border(1.dp, C.line, RoundedCornerShape(12.dp))
            .horizontalScroll(rememberScrollState())
    ) {
        val w = if (cols <= 2) 170.dp else if (cols == 3) 130.dp else 110.dp
        t.rows.forEachIndexed { ri, row ->
            val header = row.all { it.first }
            Row(Modifier.background(if (header) C.panel2 else if (ri % 2 == 0) C.panel else C.bg)) {
                row.forEachIndexed { ci, (h, sp) ->
                    Text(
                        richText(sp, onLink = onLink), fontSize = (if (h) 12.sp else 14.sp) * scale, lineHeight = 19.sp * scale,
                        fontWeight = if (h) FontWeight.Bold else null, color = if (h) C.muted else C.ink,
                        modifier = Modifier.width(if (ci == 0 && cols >= 3) w + 40.dp else w).padding(horizontal = 10.dp, vertical = 8.dp)
                    )
                }
            }
        }
    }
}

// ---------- animated chain hero ----------
@Composable
fun ChainHero(modifier: Modifier = Modifier, lit: Int = 12, total: Int = 12, pop: String? = null) {
    val inf = rememberInfiniteTransition(label = "chain")
    val t by inf.animateFloat(0f, (2 * PI).toFloat(), infiniteRepeatable(tween(5200, easing = LinearEasing)), label = "t")
    val glow by inf.animateFloat(.35f, 1f, infiniteRepeatable(tween(1400), RepeatMode.Reverse), label = "g")
    Canvas(modifier) {
        val n = total
        val linkW = size.width / (n * 0.62f + 0.6f)
        val linkH = linkW * 0.58f
        val stroke = linkW * 0.13f
        for (i in 0 until n) {
            val cx = linkW * 0.55f + i * linkW * 0.62f
            val wave = sin(t + i * 0.55f)
            val cy = size.height / 2 + wave * size.height * 0.16f
            val on = i < lit
            val col = if (on) C.accent else C.line
            val angle = cos(t + i * 0.55f) * 10f
            val horizontal = i % 2 == 0
            val w = if (horizontal) linkW else linkW * 0.82f
            val h = if (horizontal) linkH else linkH * 0.62f
            rotate(angle, Offset(cx, cy)) {
                if (on) drawRoundRect(C.accent.copy(alpha = 0.18f * glow), Offset(cx - w / 2 - stroke, cy - h / 2 - stroke), Size(w + 2 * stroke, h + 2 * stroke), CornerRadius(h), style = Stroke(stroke * 2.2f))
                drawRoundRect(col, Offset(cx - w / 2, cy - h / 2), Size(w, h), CornerRadius(h / 2), style = Stroke(stroke))
            }
        }
    }
}

// ---------- confetti ----------
private class Bit(var x: Float, var y: Float, val vx: Float, var vy: Float, val c: Color, val s: Float, var r: Float, val vr: Float)

@Composable
fun ConfettiLayer(trigger: Int) {
    val bits = remember { mutableStateListOf<Bit>() }
    var frame by remember { mutableLongStateOf(0L) }
    LaunchedEffect(trigger) {
        if (trigger == 0) return@LaunchedEffect
        val cols = listOf(C.accent, C.accent2, C.thm, C.cond, C.open, C.violet)
        repeat(110) {
            bits += Bit(Random.nextFloat(), -0.05f - Random.nextFloat() * .3f, (Random.nextFloat() - .5f) * .004f, .004f + Random.nextFloat() * .006f,
                cols[it % cols.size], 6f + Random.nextFloat() * 8f, Random.nextFloat() * 360, (Random.nextFloat() - .5f) * 14)
        }
        while (bits.isNotEmpty()) {
            withFrameNanos { frame = it }
            bits.forEach { it.x += it.vx; it.y += it.vy; it.vy += 0.00012f; it.r += it.vr }
            bits.removeAll { it.y > 1.1f }
        }
    }
    if (bits.isNotEmpty()) Canvas(Modifier.fillMaxSize()) {
        frame.let { }
        bits.forEach { b ->
            rotate(b.r, Offset(b.x * size.width, b.y * size.height)) {
                drawRect(b.c, Offset(b.x * size.width, b.y * size.height), Size(b.s * density / 2, b.s * density))
            }
        }
    }
}

// ---------- small components ----------
@Composable
fun Pill(text: String, color: Color) {
    Text(text, color = color, fontSize = 12.sp, fontWeight = FontWeight.Bold,
        modifier = Modifier.clip(RoundedCornerShape(50)).border(1.dp, color, RoundedCornerShape(50)).padding(horizontal = 9.dp, vertical = 2.dp))
}

@Composable
fun SectionLabel(text: String) {
    Text(text.uppercase(), color = C.accent, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 1.5.sp, modifier = Modifier.padding(top = 18.dp, bottom = 8.dp))
}

@Composable
fun PressCard(onClick: () -> Unit, modifier: Modifier = Modifier, border: Color = C.line, content: @Composable ColumnScope.() -> Unit) {
    val src = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val sc by animateFloatAsState(if (pressed) 0.97f else 1f, spring(dampingRatio = .5f, stiffness = 600f), label = "press")
    Column(
        modifier.fillMaxWidth().graphicsScale(sc).clip(RoundedCornerShape(18.dp)).background(C.panel).border(1.dp, border, RoundedCornerShape(18.dp))
            .clickable(interactionSource = src, indication = androidx.compose.material3.ripple(), onClick = onClick).padding(16.dp),
        content = content
    )
}

fun Modifier.graphicsScale(s: Float) = this.graphicsLayer { scaleX = s; scaleY = s }
