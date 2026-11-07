package com.natesapps.nightarray

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/*
 * The station, drawn from the SPEC.md §2 envelope (mm, app axes: +Y up, +Z toward you) in a light oblique
 * projection (depth recedes up and to the right). It stands in wherever a render is missing, so every screen
 * always shows the object, and it can spotlight one group for part thumbnails.
 */

private const val KX = 0.10f
private const val KY = 0.14f

// Display geometry (SPEC.md §2): two facets hinged at the seam axis x=0, z=-62, toed in 10°.
private const val SEAM_Z = -62f
private const val TOE = 10f
private const val FACET = 612.7f        // glass, from the seam out along each facet
private const val ACT_IN = 7f           // active area starts 7 mm from the seam
private const val ACT_OUT = 603.7f      // … and ends 596.7 mm later
private const val GLASS_Y0 = 156f
private const val GLASS_Y1 = 516.7f
private const val ACT_Y0 = 172f
private const val ACT_Y1 = 507.7f
private const val SHROUD = 45f

@Composable
fun StationSketch(
    modifier: Modifier = Modifier, mode: String = "work", highlight: String? = null, glow: Float = 1f,
    animate: Boolean = true, finish: String = "titanium", background: Boolean = true, focus: String? = null, dockStep: String? = null,
) {
    val inf = rememberInfiniteTransition(label = "sk")
    val breathe by inf.animateFloat(.8f, 1f, infiniteRepeatable(tween(4200, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "br")
    val tm = rememberTextMeasurer()
    Canvas(modifier) { drawStation(mode, highlight, glow * (if (animate) breathe else 1f), finish, background, tm, focus, dockStep) }
}

/** Which part of the sketch stands in for a given still (SPEC.md §4 names). */
fun stillFocus(name: String): String? {
    val n = name.substringAfterLast('/')
    return when {
        n.startsWith("part-") -> n.removePrefix("part-").substringBeforeLast('.')
        n == "display.jpg" -> "display"
        n.startsWith("dock-") -> "dock"
        n == "trays.jpg" -> "trays"
        else -> null
    }
}

fun stillDockStep(name: String): String? = name.substringAfterLast('/').takeIf { it.startsWith("dock-") }?.removePrefix("dock-")?.substringBeforeLast('.')

private class Proj(val ox: Float, val oy: Float, val s: Float) {
    fun p(x: Float, y: Float, z: Float) = Offset(ox + (x - KX * z) * s, oy - (y - KY * z) * s)
}

private fun poly(a: Offset, b: Offset, c: Offset, d: Offset): Path = Path().apply {
    moveTo(a.x, a.y); lineTo(b.x, b.y); lineTo(c.x, c.y); lineTo(d.x, d.y); close()
}

private fun Proj.planRect(x0: Float, z0: Float, x1: Float, z1: Float, r: Float, y: Float): Path {
    val path = Path(); var first = true
    fun add(x: Float, z: Float) { val o = p(x, y, z); if (first) { path.moveTo(o.x, o.y); first = false } else path.lineTo(o.x, o.y) }
    val rr = min(r, min((x1 - x0) / 2, (z1 - z0) / 2))
    val corners = listOf(Triple(x1 - rr, z0 + rr, -90f), Triple(x1 - rr, z1 - rr, 0f), Triple(x0 + rr, z1 - rr, 90f), Triple(x0 + rr, z0 + rr, 180f))
    for ((cx, cz, a0) in corners) for (i in 0..6) {
        val a = Math.toRadians((a0 + i * 15f).toDouble())
        add(cx + rr * cos(a).toFloat(), cz + rr * sin(a).toFloat())
    }
    path.close(); return path
}

private data class Metal(val hi: Color, val mid: Color, val lo: Color)

private fun metal(finish: String) = when (finish) {
    "graphite" -> Metal(Color(0xFF6E6965), Color(0xFF46423F), Color(0xFF262422))
    "oxblood" -> Metal(Color(0xFFAE5A50), Color(0xFF7A2E2A), Color(0xFF431816))
    else -> Metal(Color(0xFFE2D9CC), Color(0xFFA99E90), Color(0xFF61594F))
}

/** Point on a display facet: side −1 = left, +1 = right; t = mm from the seam along the facet; n = mm along the facet normal (+ toward you). */
private fun facet(side: Int, t: Float, y: Float, n: Float = 0f): Triple<Float, Float, Float> {
    val c = cos(Math.toRadians(TOE.toDouble())).toFloat(); val s = sin(Math.toRadians(TOE.toDouble())).toFloat()
    // direction (side·cos, 0, sin); normal toward the user (−side·sin, 0, cos)
    val x = side * c * t - side * s * n
    val z = SEAM_Z + s * t + c * n
    return Triple(x, y, z)
}

private fun Proj.f(side: Int, t: Float, y: Float, n: Float = 0f): Offset = facet(side, t, y, n).let { (x, yy, z) -> p(x, yy, z) }

/** Canvas coordinate (u across the 5120 px canvas, v down) → point on the panels, exactly like an OS spans two displays. */
private fun Proj.uv(u: Float, v: Float): Offset {
    val y = ACT_Y1 - v * (ACT_Y1 - ACT_Y0)
    return if (u < .5f) f(-1, ACT_OUT - (u / .5f) * (ACT_OUT - ACT_IN), y, .3f)
    else f(1, ACT_IN + ((u - .5f) / .5f) * (ACT_OUT - ACT_IN), y, .3f)
}

private fun ridgeA(u: Float) = 0.60f - 0.17f * gauss(u, 0.27f, 0.17f) - 0.09f * gauss(u, 0.74f, 0.16f) + 0.03f * sin(u * 9f)
private fun ridgeB(u: Float) = 0.76f - 0.08f * gauss(u, 0.55f, 0.22f) - 0.04f * gauss(u, 0.12f, 0.1f)
private fun gauss(u: Float, m: Float, w: Float) = exp(-((u - m) / w) * ((u - m) / w))

/** Projected bounds (X0, X1, Y0, Y1) to frame for a group, or the whole station. */
private fun frameFor(focus: String?, work: Boolean, lift: Float): FloatArray = when (focus) {
    "display" -> floatArrayOf(-650f, 650f, 140f, 540f)
    "stand" -> floatArrayOf(-230f, 235f, 20f, 190f)
    "dock", "laptop" -> floatArrayOf(585f, 830f, -40f, 360f + lift)
    "keyboard" -> if (work) floatArrayOf(-345f, 95f, -72f, -5f) else floatArrayOf(-325f, 125f, -15f, 55f)
    "mouse" -> if (work) floatArrayOf(195f, 315f, -70f, 10f) else floatArrayOf(185f, 305f, -5f, 65f)
    "deskmat" -> floatArrayOf(-420f, 470f, -85f, -15f)
    "base", "internals" -> floatArrayOf(-665f, 680f, -30f, 70f)
    "trays" -> floatArrayOf(-330f, 330f, -25f, 75f)
    else -> floatArrayOf(-665f, 795f, if (work) -82f else -34f, 540f + lift)
}

fun DrawScope.drawStation(
    mode: String, highlight: String?, glow: Float, finish: String, background: Boolean, tm: TextMeasurer?,
    focus: String? = null, dockStep: String? = null,
) {
    val work = mode != "stow"
    // laptop heights of the dock_sequence steps (scene.json): align 70 mm up in the lead-in, lift 160 mm up and clear
    val lift = when (dockStep) { "align" -> 70f; "lift" -> 160f; else -> 0f }
    val fr = frameFor(focus, work, lift)
    val x0 = fr[0]; val x1 = fr[1]; val y0 = fr[2]; val y1 = fr[3]
    val s = min(size.width / (x1 - x0), size.height / (y1 - y0)) * (if (focus == null) 0.9f else 0.84f)
    val pr = Proj(size.width / 2 - (x0 + x1) / 2 * s, size.height / 2 + (y0 + y1) / 2 * s, s)
    val m = metal(finish)
    val px = max(1f, s * 1.1f)
    fun a(group: String) = if (highlight == null || highlight == group) 1f else 0.14f
    val amberA = glow.coerceIn(0f, 1.2f)

    // ---- room: warm wall wash behind the panels, desk plane ----
    if (background) {
        drawRect(Brush.verticalGradient(listOf(Color(0xFF15100D), Color(0xFF0E0B09), Color(0xFF120E0B))))
        val c = pr.p(0f, 330f, -400f)
        drawCircle(Brush.radialGradient(listOf(C.amber.copy(alpha = .085f * amberA), Color.Transparent), c, 760f * s), 760f * s, c)
        val deskBack = pr.p(0f, 0f, -330f).y
        drawRect(Brush.verticalGradient(listOf(Color(0xFF1A1411), Color(0xFF0F0C0A)), startY = deskBack, endY = size.height), Offset(0f, deskBack), androidx.compose.ui.geometry.Size(size.width, size.height - deskBack))
        drawLine(C.line.copy(alpha = .6f), Offset(0f, deskBack), Offset(size.width, deskBack), 1f)
    }
    // under-glow pooled on the desk in front of the base
    run {
        val l = pr.p(-560f, 0f, 160f); val r = pr.p(560f, 0f, 160f)
        val h = 70f * s
        drawRect(Brush.verticalGradient(listOf(C.amber.copy(alpha = .22f * amberA * a("base")), Color.Transparent), startY = l.y, endY = l.y + h), Offset(l.x, l.y), androidx.compose.ui.geometry.Size(r.x - l.x, h))
    }

    // ---- desk mat + devices in Work / Standalone ----
    if (work) {
        val am = a("deskmat")
        drawPath(pr.planRect(-350f, 235f, 470f, 535f, 14f, 3f), Brush.verticalGradient(listOf(Color(0xFF2E2926), Color(0xFF1F1B19)), startY = pr.p(0f, 3f, 235f).y, endY = pr.p(0f, 3f, 535f).y), alpha = am)
        drawPath(pr.planRect(-350f, 235f, 470f, 535f, 14f, 3f), C.titanium.copy(alpha = .12f * am), style = Stroke(1f))
        drawKeyboard(pr, -90f, 360f, 3f, a("keyboard"), px)
        drawMouse(pr, 290f, 360f, 3f, a("mouse"), amberA, px)
    }

    // ---- base slab ----
    val ab = a("base")
    val top = pr.planRect(-640f, -150f, 650f, 150f, 40f, 36f)
    val frontTopL = pr.p(-600f, 36f, 150f); val frontTopR = pr.p(610f, 36f, 150f)
    val frontBotL = pr.p(-600f, 0f, 150f); val frontBotR = pr.p(610f, 0f, 150f)
    // front face (with the rounded corners suggested by the top outline drawn over it)
    val front = Path().apply {
        val l = pr.p(-640f, 18f, 110f); val r = pr.p(650f, 18f, 110f)
        moveTo(l.x, l.y); lineTo(frontTopL.x, frontTopL.y); lineTo(frontTopR.x, frontTopR.y); lineTo(r.x, r.y)
        val rb = pr.p(650f, 0f, 110f); lineTo(rb.x, rb.y); lineTo(frontBotR.x, frontBotR.y); lineTo(frontBotL.x, frontBotL.y)
        val lb = pr.p(-640f, 0f, 110f); lineTo(lb.x, lb.y); close()
    }
    drawPath(front, Brush.verticalGradient(listOf(m.mid, m.lo, Color(0xFF1C1916)), startY = frontTopL.y, endY = frontBotL.y), alpha = ab)
    drawPath(top, Brush.linearGradient(listOf(m.hi, m.mid, m.hi.copy(alpha = .95f)), start = pr.p(-640f, 36f, -150f), end = pr.p(650f, 36f, 150f)), alpha = ab)
    // recessed inner deck inside the 16 mm rim
    val deck = pr.planRect(-624f, -134f, 634f, 134f, 26f, 30f)
    drawPath(deck, Brush.verticalGradient(listOf(m.mid, m.lo.copy(alpha = .9f)), startY = pr.p(0f, 30f, -134f).y, endY = pr.p(0f, 30f, 134f).y), alpha = ab)
    drawPath(deck, Color.Black.copy(alpha = .35f * ab), style = Stroke(px))
    // bright top edge of the front rim
    drawLine(m.hi.copy(alpha = .9f * ab), frontTopL, frontTopR, max(1f, px * .9f))
    // pockets with their graphite pads
    for ((r, cr) in listOf(floatArrayOf(-278f, -6f, 98f, 130f) to 10f, floatArrayOf(209f, -5f, 291f, 129f) to 12f)) {
        val pk = pr.planRect(r[0], r[1], r[2], r[3], cr, 30f)
        drawPath(pk, Color(0xFF151312), alpha = ab)
        val pad = pr.planRect(r[0] + 4, r[1] + 4, r[2] - 4, r[3] - 4, cr - 3, 18f)
        drawPath(pad, Brush.verticalGradient(listOf(Color(0xFF2A2725), Color(0xFF1E1C1B)), startY = pr.p(0f, 18f, r[1]).y, endY = pr.p(0f, 18f, r[3]).y), alpha = ab)
        drawPath(pk, m.hi.copy(alpha = .25f * ab), style = Stroke(1f))
    }
    // charge marks on the pocket lips (lit while devices charge in Stow)
    val charging = if (mode == "stow") 1f else .25f
    drawLine(C.amber.copy(alpha = amberA * charging * ab), pr.p(-105f, 30.5f, 131f), pr.p(-75f, 30.5f, 131f), max(1.5f, 2.2f * s))
    drawLine(C.amber.copy(alpha = amberA * charging * ab), pr.p(242f, 30.5f, 130f), pr.p(258f, 30.5f, 130f), max(1.5f, 2.2f * s))
    // under-glow strip along the front bottom edge
    run {
        val l = pr.p(-560f, 3.5f, 150f); val r = pr.p(560f, 3.5f, 150f)
        drawLine(C.amber.copy(alpha = .35f * amberA * ab), l, r, max(4f, 9f * s), cap = StrokeCap.Round)
        drawLine(Color(0xFFFFD39A).copy(alpha = .95f * amberA * ab), l, r, max(1.2f, 2.2f * s), cap = StrokeCap.Round)
    }
    if (highlight == "internals") drawInternals(pr, px)

    // ---- devices stowed in their pockets ----
    if (!work) {
        drawKeyboard(pr, -90f, 62f, 18f, a("keyboard"), px)
        drawMouse(pr, 250f, 62f, 18f, a("mouse"), amberA, px)
    }

    // ---- neck ----
    val an = a("stand")
    val nFront = poly(pr.p(-160f, 36f, -70f), pr.p(160f, 36f, -70f), pr.p(90f, 156f, -80f), pr.p(-90f, 156f, -80f))
    val nSide = poly(pr.p(160f, 36f, -70f), pr.p(160f, 36f, -140f), pr.p(90f, 156f, -150f), pr.p(90f, 156f, -80f))
    drawPath(nSide, Color(0xFF1F1D1C), alpha = an)
    drawPath(nFront, Brush.verticalGradient(listOf(Color(0xFF3E3A37), Color(0xFF2A2725)), startY = pr.p(0f, 156f, -80f).y, endY = pr.p(0f, 36f, -70f).y), alpha = an)
    drawPath(nFront, C.titanium.copy(alpha = .18f * an), style = Stroke(1f))
    if (tm != null && 9f * s >= 5.5f) {
        val lay = tm.measure("NIGHT ARRAY", TextStyle(color = C.titanium.copy(alpha = .75f * an), fontSize = (5.2f * s / density).coerceAtLeast(4f).sp, letterSpacing = (2f * s / density).sp, fontWeight = FontWeight.Light))
        val c = pr.p(0f, 92f, -75f)
        drawText(lay, topLeft = Offset(c.x - lay.size.width / 2f, c.y - lay.size.height / 2f))
    }
    run { // light bar on the neck's top-front edge
        val l = pr.p(-75f, 150f, -79f); val r = pr.p(75f, 150f, -79f)
        drawLine(C.amber.copy(alpha = .28f * amberA * an), l, r, max(4f, 12f * s), cap = StrokeCap.Round)
        drawLine(Color(0xFFFFCF8F).copy(alpha = amberA * an), l, r, max(1.5f, 3.5f * s), cap = StrokeCap.Round)
    }

    // ---- display: two toed-in 27" panels + the honest seam ----
    drawDisplay(pr, a("display"), m, amberA, px)

    // ---- dock + laptop on the right wing ----
    drawDock(pr, a("dock"), a("laptop"), mode != "standalone", m, amberA, px, lift, dockStep)
}

private fun DrawScope.drawDisplay(pr: Proj, ad: Float, m: Metal, amberA: Float, px: Float) {
    // shroud top + outer sides (graphite), visible because depth recedes up-right
    for (side in listOf(-1, 1)) {
        val topFace = poly(pr.f(side, 0f, GLASS_Y1 + 1, 0f), pr.f(side, FACET + 3, GLASS_Y1 + 1, 0f), pr.f(side, FACET - 6, GLASS_Y1 - 4, -SHROUD), pr.f(side, 0f, GLASS_Y1 - 4, -SHROUD - 4))
        drawPath(topFace, Color(0xFF2B2826), alpha = ad)
    }
    val outerSide = poly(pr.f(1, FACET + 3, GLASS_Y0, 0f), pr.f(1, FACET + 3, GLASS_Y1 + 1, 0f), pr.f(1, FACET - 6, GLASS_Y1 - 4, -SHROUD), pr.f(1, FACET - 6, GLASS_Y0 + 6, -SHROUD))
    drawPath(outerSide, Brush.horizontalGradient(listOf(Color(0xFF34302D), Color(0xFF1C1A18)), startX = pr.f(1, FACET, 0f).x, endX = pr.f(1, FACET - 6, 0f, -SHROUD).x), alpha = ad)

    for (side in listOf(-1, 1)) {
        // black glass face with the 16 mm chin and 9 mm top border
        val glass = poly(pr.f(side, 0f, GLASS_Y0), pr.f(side, FACET, GLASS_Y0), pr.f(side, FACET, GLASS_Y1), pr.f(side, 0f, GLASS_Y1))
        drawPath(glass, Color(0xFF0B0A0C), alpha = ad)
        // active area: one dune image spanning both panels (u: 0→0.5 left, 0.5→1 right)
        val u0 = if (side < 0) 0f else .5f; val u1 = if (side < 0) .5f else 1f
        val active = poly(pr.uv(u0, 0f), pr.uv(u1, 0f), pr.uv(u1, 1f), pr.uv(u0, 1f))
        clipPath(active) {
            val tl = pr.uv(u0, 0f); val bl = pr.uv(u0, 1f)
            drawPath(active, Brush.verticalGradient(listOf(Color(0xFF120E16), Color(0xFF231922), Color(0xFF3A2A2C)), startY = tl.y, endY = bl.y), alpha = ad)
            fun band(f: (Float) -> Float, colors: List<Color>) {
                val path = Path(); val n = 40
                for (i in 0..n) { val u = u0 + (u1 - u0) * i / n; val o = pr.uv(u, f(u)); if (i == 0) path.moveTo(o.x, o.y) else path.lineTo(o.x, o.y) }
                val br = pr.uv(u1, 1.02f); val bl2 = pr.uv(u0, 1.02f); path.lineTo(br.x, br.y); path.lineTo(bl2.x, bl2.y); path.close()
                drawPath(path, Brush.verticalGradient(colors, startY = pr.uv(u0, .4f).y, endY = bl.y), alpha = ad)
            }
            band(::ridgeA, listOf(Color(0xFF4A3537), Color(0xFF1A1316)))
            // glowing ridge line, hottest on the left like the board
            val ridge = Path(); val n = 40
            for (i in 0..n) { val u = u0 + (u1 - u0) * i / n; val o = pr.uv(u, ridgeA(u)); if (i == 0) ridge.moveTo(o.x, o.y) else ridge.lineTo(o.x, o.y) }
            drawPath(ridge, Brush.horizontalGradient(listOf(C.amber.copy(alpha = .15f), Color(0xFFFFC27A).copy(alpha = .95f * min(1f, amberA + .3f)), C.amber.copy(alpha = .35f), C.amber.copy(alpha = .1f)),
                startX = pr.uv(0f, .5f).x, endX = pr.uv(1f, .5f).x), style = Stroke(max(1.2f, px * 1.6f)), alpha = ad)
            band(::ridgeB, listOf(Color(0xFF2A1E21), Color(0xFF0E0A0C)))
            // a faint sheen across the glass
            drawPath(active, Brush.linearGradient(listOf(Color.White.copy(alpha = .05f), Color.Transparent), start = tl, end = pr.uv(u1, .6f)), alpha = ad)
        }
        // shroud rim: titanium, wrapping the outer edge and following the fold
        drawPath(glass, Brush.linearGradient(listOf(m.hi, m.mid, m.hi), start = pr.f(side, 0f, GLASS_Y1), end = pr.f(side, FACET, GLASS_Y0)), style = Stroke(max(1.4f, 3f * pr.s)), alpha = ad)
    }
    // the honest seam: a 4 mm titanium mullion, slightly proud, full glass height
    val sTop = pr.p(0f, GLASS_Y1 + 1, SEAM_Z + 1.5f); val sBot = pr.p(0f, GLASS_Y0, SEAM_Z + 1.5f)
    drawLine(Color.Black.copy(alpha = .5f * ad), sTop + Offset(px, 0f), sBot + Offset(px, 0f), max(2f, 7f * pr.s))
    drawLine(Brush.verticalGradient(listOf(m.hi, m.mid, m.hi), startY = sTop.y, endY = sBot.y), sTop, sBot, max(1.4f, 4f * pr.s), alpha = ad)
}

private fun DrawScope.drawKeyboard(pr: Proj, cx: Float, cz: Float, yb: Float, al: Float, px: Float) {
    val x0 = cx - 180; val x1 = cx + 180; val zb = cz - 60; val zf = cz + 60
    val topF = yb + 9; val topB = yb + 13
    val front = poly(pr.p(x0, yb, zf), pr.p(x1, yb, zf), pr.p(x1, topF, zf), pr.p(x0, topF, zf))
    val top = poly(pr.p(x0, topB, zb), pr.p(x1, topB, zb), pr.p(x1, topF, zf), pr.p(x0, topF, zf))
    drawPath(front, Color(0xFF1C1A19), alpha = al)
    drawPath(top, Color(0xFF34312F), alpha = al)
    // keycaps (unit 18.5 mm, ~75 %)
    val cols = 16; val rows = 6
    for (r in 0 until rows) for (c in 0 until cols) {
        val kx0 = x0 + 8 + c * 21.5f; val kz0 = zb + 6 + r * 18.2f
        if (kx0 + 18 > x1 - 6) continue
        val w = if (r == rows - 1 && c == 5) 21.5f * 5 - 3.5f else 18f
        if (r == rows - 1 && c in 6..9) continue
        val y = topB - (topB - topF) * ((kz0 - zb) / 120f) + 1.5f
        drawPath(poly(pr.p(kx0, y, kz0), pr.p(kx0 + w, y, kz0), pr.p(kx0 + w, y, kz0 + 15.5f), pr.p(kx0, y, kz0 + 15.5f)), Color(0xFF4A4542), alpha = al)
    }
    drawLine(Color.White.copy(alpha = .1f * al), pr.p(x0, topF, zf), pr.p(x1, topF, zf), px * .8f)
}

private fun DrawScope.drawMouse(pr: Proj, cx: Float, cz: Float, yb: Float, al: Float, amberA: Float, px: Float) {
    val c = pr.p(cx, yb + 16, cz)
    val rx = 34f * pr.s; val ry = (20f + 118f * KY / 2f) * pr.s
    val oval = Path().apply { addOval(androidx.compose.ui.geometry.Rect(c.x - rx, c.y - ry, c.x + rx, c.y + ry)) }
    drawPath(oval, Brush.radialGradient(listOf(Color(0xFF4A4542), Color(0xFF242120)), center = c + Offset(-rx * .3f, -ry * .45f), radius = ry * 1.6f), alpha = al)
    drawPath(oval, Color.White.copy(alpha = .08f * al), style = Stroke(1f))
    drawLine(Color(0xFF151413).copy(alpha = al), pr.p(cx, yb + 37, cz + 4), pr.p(cx, yb + 33, cz + 30), max(1f, 2.5f * pr.s))
    val tl = pr.p(cx - 14, yb + 22, cz - 56); val tr = pr.p(cx + 14, yb + 22, cz - 56)
    drawLine(C.amber.copy(alpha = .9f * amberA * al), tl, tr, max(1.2f, 2.4f * pr.s), cap = StrokeCap.Round)
}

private fun DrawScope.drawDock(pr: Proj, ad: Float, al: Float, laptop: Boolean, m: Metal, amberA: Float, px: Float, lift: Float = 0f, step: String? = null) {
    fun h(z: Float): Float { val t = ((130f - z) / 260f).coerceIn(0f, 1f); return 60f + 60f * t * t }
    val zs = (0..20).map { 130f - it * 13f }
    fun surface(xa: Float, xb: Float): Path = Path().apply {
        zs.forEachIndexed { i, z -> val o = pr.p(xa, h(z), z); if (i == 0) moveTo(o.x, o.y) else lineTo(o.x, o.y) }
        zs.reversed().forEach { z -> val o = pr.p(xb, h(z), z); lineTo(o.x, o.y) }
        close()
    }
    // top surface left of the slot, the slot, and right of it
    drawPath(surface(650f, 712f), Brush.linearGradient(listOf(m.hi, m.mid), start = pr.p(650f, 120f, -130f), end = pr.p(712f, 60f, 130f)), alpha = ad)
    drawPath(surface(712f, 732f), Color(0xFF0E0D0C), alpha = ad)
    // laptop standing on its side in the slot (hinge to the back)
    if (laptop) {
        val face = poly(pr.p(729.5f, (24f + lift), 106f), pr.p(729.5f, (328f + lift), 106f), pr.p(729.5f, (328f + lift), -106f), pr.p(729.5f, (24f + lift), -106f))
        drawPath(face, Brush.linearGradient(listOf(Color(0xFFD4D0CA), Color(0xFF8E8A85)), start = pr.p(729.5f, (328f + lift), 106f), end = pr.p(729.5f, (24f + lift), -106f)), alpha = al)
        val front = poly(pr.p(714.5f, (24f + lift), 106f), pr.p(729.5f, (24f + lift), 106f), pr.p(729.5f, (328f + lift), 106f), pr.p(714.5f, (328f + lift), 106f))
        drawPath(front, Color(0xFF6F6B66), alpha = al)
        val top = poly(pr.p(714.5f, (328f + lift), 106f), pr.p(729.5f, (328f + lift), 106f), pr.p(729.5f, (328f + lift), -106f), pr.p(714.5f, (328f + lift), -106f))
        drawPath(top, Color(0xFFB9B5AF), alpha = al)
        drawLine(Color.Black.copy(alpha = .35f * al), pr.p(722f, (30f + lift), 106f), pr.p(722f, (322f + lift), 106f), max(1f, px * .7f)) // lid seam
        drawLine(Color.Black.copy(alpha = .5f * al), pr.p(729.6f, (300f + lift), 106f), pr.p(729.6f, (250f + lift), 106f), max(1f, 2.5f * pr.s)) // ports
    }
    drawPath(surface(732f, 775f), Brush.linearGradient(listOf(m.hi, m.mid), start = pr.p(732f, 120f, -130f), end = pr.p(775f, 60f, 130f)), alpha = ad)
    // outer (+x) face and front face with brushed oxblood panels
    val side = Path().apply {
        val a0 = pr.p(775f, 0f, 130f); moveTo(a0.x, a0.y)
        zs.forEach { z -> val o = pr.p(775f, h(z), z); lineTo(o.x, o.y) }
        val b = pr.p(775f, 0f, -130f); lineTo(b.x, b.y); close()
    }
    drawPath(side, Brush.verticalGradient(listOf(m.mid, m.lo)), alpha = ad)
    val panel = Path().apply {
        val a0 = pr.p(775.5f, 6f, 120f); moveTo(a0.x, a0.y)
        zs.drop(1).dropLast(1).forEach { z -> val o = pr.p(775.5f, h(z) - 7f, z); lineTo(o.x, o.y) }
        val b = pr.p(775.5f, 6f, -120f); lineTo(b.x, b.y); close()
    }
    drawPath(panel, Brush.linearGradient(listOf(Color(0xFF9A433B), Color(0xFF5A201D), Color(0xFF86362F)), start = pr.p(775f, 120f, -120f), end = pr.p(775f, 0f, 120f)), alpha = ad)
    val front = poly(pr.p(650f, 0f, 130f), pr.p(775f, 0f, 130f), pr.p(775f, 60f, 130f), pr.p(650f, 60f, 130f))
    drawPath(front, Brush.verticalGradient(listOf(m.mid, m.lo), startY = pr.p(0f, 60f, 130f).y, endY = pr.p(0f, 0f, 130f).y), alpha = ad)
    // one oxblood front panel with the side panel's 7 mm titanium margins, so the two read as one wrap round the corner
    drawPath(poly(pr.p(657f, 7f, 130.5f), pr.p(756f, 7f, 130.5f), pr.p(756f, 53f, 130.5f), pr.p(657f, 53f, 130.5f)),
        Brush.verticalGradient(listOf(Color(0xFF8E3A33), Color(0xFF4E1B18)), startY = pr.p(0f, 53f, 130f).y, endY = pr.p(0f, 7f, 130f).y), alpha = ad)
    drawLine(m.hi.copy(alpha = .9f * ad), pr.p(650f, 60f, 130f), pr.p(775f, 60f, 130f), max(1f, px * .8f))
    // the seated light: a slim 30 × 2 mm amber line inlaid in the front panel on the slot axis, right under the laptop.
    // Only a light (nothing on the dock moves): on while the laptop sits on the plug, dark while it is out of the cradle.
    val seated = laptop && step != "align" && step != "lift"
    val l1 = pr.p(707f, 47f, 130.6f); val l2 = pr.p(737f, 47f, 130.6f)
    drawLine(Color(0xFF2A1A12).copy(alpha = ad), l1, l2, max(1.2f, 2.2f * pr.s), cap = StrokeCap.Butt)
    if (seated) {
        drawLine(C.amber.copy(alpha = .3f * amberA * ad), l1, l2, max(3f, 7f * pr.s), cap = StrokeCap.Round)
        drawLine(Color(0xFFFFCF8F).copy(alpha = amberA * ad), l1, l2, max(1.2f, 2.2f * pr.s), cap = StrokeCap.Round)
    }
    // motion cue for the sequence: down while lowering, up while lifting
    val arrowAt = when (step) {
        "align", "lower" -> pr.p(700f, 300f + lift, 106f) to pr.p(700f, 200f + lift, 106f)
        "lift" -> pr.p(700f, 200f + lift, 106f) to pr.p(700f, 300f + lift, 106f)
        else -> null
    }
    if (arrowAt != null && laptop) {
        val (a, b) = arrowAt
        val w = max(1.5f, 2.2f * pr.s); val h = max(6f, 14f * pr.s)
        drawLine(C.amber.copy(alpha = .95f * ad), a, b, w, cap = StrokeCap.Round)
        val dir = if (b.y > a.y) 1f else -1f
        drawLine(C.amber.copy(alpha = .95f * ad), b, b + Offset(-h * .6f, -dir * h), w, cap = StrokeCap.Round)
        drawLine(C.amber.copy(alpha = .95f * ad), b, b + Offset(h * .6f, -dir * h), w, cap = StrokeCap.Round)
    }
}

private fun DrawScope.drawInternals(pr: Proj, px: Float) {
    val dash = PathEffect.dashPathEffect(floatArrayOf(6f, 4f))
    val st = Stroke(max(1f, px), pathEffect = dash)
    drawPath(pr.planRect(-600f, -120f, -300f, 110f, 6f, 31f), C.amber.copy(alpha = .9f), style = st)          // mainboard
    drawPath(pr.planRect(-560f, -90f, -380f, 60f, 4f, 31f), Color(0xFFB8B8B8).copy(alpha = .8f), style = st)   // vapor chamber
    drawPath(pr.planRect(330f, -120f, 470f, 110f, 6f, 31f), C.amber.copy(alpha = .7f), style = st)            // PSU
    for (cx in listOf(-170f, -10f, 250f)) {
        val c = pr.p(cx, 31f, 62f)
        drawOval(Color(0xFFE0A070).copy(alpha = .95f), topLeft = c - Offset(30f * pr.s, 30f * pr.s * .35f), size = androidx.compose.ui.geometry.Size(60f * pr.s, 60f * pr.s * .35f), style = Stroke(max(1.2f, px * 1.4f)))
    }
}
