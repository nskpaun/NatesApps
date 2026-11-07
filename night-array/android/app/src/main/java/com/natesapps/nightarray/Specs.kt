package com.natesapps.nightarray

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sin

private val SPEC_TABS = listOf("sheet" to "Sheet", "bom" to "BOM", "fit" to "Desk fit")

@Composable
fun SpecsScreen(app: AppState, scene: Scene, section: String?) {
    LaunchedEffect(section) { if (section != null && SPEC_TABS.any { it.first == section }) app.specsTab = section }
    BoxWithConstraints(Modifier.fillMaxSize().background(C.bg)) {
        val pad = if (maxWidth >= 600.dp) 40.dp else 20.dp
        // On short screens (a phone in landscape) title and tabs share one row, leaving the height to the content.
        val short = maxHeight < 520.dp && maxWidth >= 560.dp
        // Tablets: one wider measure for header and every tab, so their edges line up.
        val maxW = if (maxWidth >= 840.dp) 1120.dp else 760.dp
        Column(Modifier.fillMaxSize().testTag("specs")) {
            if (short) {
                Row(Modifier.readable(maxW).statusBarsPadding().padding(horizontal = pad).padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) { AmberDash(22.dp); Spacer(Modifier.width(10.dp)); Kicker("Specifications") }
                        Spacer(Modifier.height(8.dp))
                        Tracked("Specs", size = 20.sp, tracking = .2f)
                    }
                    Segmented(SPEC_TABS, app.specsTab, { app.specsTab = it }, Modifier.width(340.dp), tagPrefix = "specs")
                }
            } else Column(Modifier.readable(maxW).statusBarsPadding().padding(horizontal = pad).padding(top = 22.dp)) {
                ScreenTitle("Specifications", "Specs")
                Spacer(Modifier.height(20.dp))
                Segmented(SPEC_TABS, app.specsTab, { app.specsTab = it }, Modifier.widthIn(max = 560.dp).fillMaxWidth(), tagPrefix = "specs")
            }
            AnimatedContent(app.specsTab, Modifier.weight(1f), transitionSpec = { fadeIn(tween(260, delayMillis = 40)) togetherWith fadeOut(tween(160)) }, label = "specs") { t ->
                when (t) {
                    "bom" -> BomList(scene, pad, maxW)
                    "fit" -> DeskFit(app, scene, pad, maxW)
                    else -> SpecSheet(scene, pad, maxW)
                }
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------
// Spec sheet
// ------------------------------------------------------------------------------------------------

data class SpecSection(val title: String, val sub: String, val rows: List<StorySpec>)

private fun mm2(v: List<Double>?, fallback: String): String = v?.takeIf { it.size >= 2 }?.let { "${fmtNum(it[0])} × ${fmtNum(it[1])} mm" } ?: fallback
private fun mm(v: Double?, fallback: String): String = v?.let { "${fmtNum(it)} mm" } ?: fallback

fun specSheet(scene: Scene): List<SpecSection> {
    val sc = scene.screen
    val fp = footprint(scene)
    val base = scene.bbox("base")
    val dock = scene.bbox("dock")
    val o = scene.overallMm
    fun box(b: List<Double>?, fallback: String) = b?.let { fmtBox(it) } ?: fallback
    val board = listOf(scene.span("internals.board.x"), scene.span("internals.board.z")).takeIf { it.all { v -> v != null } }?.map { it!! }
    val coilsKb = scene.nums("internals.qi_coils_kb_x")
    val slotW = scene.span("dock.slot.x"); val slotL = scene.span("dock.slot.z")
    return listOf(
        SpecSection("Display", "Two mainstream panels, one shroud", listOf(
            StorySpec("Panels", "${sc.panels} × ${fmtNum(sc.panelInch)}″ QHD IPS, off the shelf"),
            StorySpec("Canvas", "${sc.canvasW} × ${sc.canvasH}, as ${sc.panels} displays of ${sc.resEach[0]} × ${sc.resEach[1]}"),
            StorySpec("Active area", "${sc.panels} × ${fmtNum(sc.activeMm[0])} × ${fmtNum(sc.activeMm[1])} mm"),
            StorySpec("Density", "${sc.ppi.roundToInt()} ppi"),
            StorySpec("Toe-in", "${fmtNum(sc.toeInDeg)}° per panel, about the seam"),
            StorySpec("Seam", "${fmtNum(sc.seamMm)} mm between active areas; ${mm(scene.num("display.mullion_w"), "4 mm")} titanium mullion"),
            StorySpec("Width", "≈ ${fmtMm(scene.displayWidthMm)} mm across both panels"),
            StorySpec("Screen height", scene.nums("display.active_y")?.let { "Active area ${fmtNum(it[0])}–${fmtNum(it[1])} mm above the desk" } ?: "Active area 172–508 mm above the desk"),
            StorySpec("Mount", "VESA 100 per panel on a steel spine; ${mm(scene.num("display.shroud_depth"), "45 mm")} shroud; own scaler boards kept"),
        )),
        SpecSection("Dock", "Right outer wing", listOf(
            StorySpec("Cradle", box(dock, "125 × 120 × 260 mm") + ", titanium + brushed oxblood"),
            StorySpec("Slot", "${fmtNum(slotW ?: 20.0)} × ${fmtNum(slotL ?: 224.0)} mm, ${mm(scene.num("dock.slot.lead_in"), "4 mm")} chamfered lead-ins"),
            StorySpec("Connector", "Sprung USB-C on the slot floor"),
            StorySpec("Release", "Press latch on the front face, ${mm(scene.num("dock.latch.travel") ?: scene.num("poses_mm.latch_travel"), "3 mm")} travel"),
            StorySpec("Laptops", "Up to ${mm(slotW?.minus(LAPTOP_CLEARANCE_MM), "18 mm")} thick and ${mm(slotL, "224 mm")} deep, standing closed on edge; " +
                "USB-C port about ${mm(portFromHingeMm(scene), "46 mm")} from the hinge end"),
        )),
        SpecSection("Charging", "Qi2, in place", listOf(
            StorySpec("Keyboard pocket", mm2(scene.nums("base.kb_pocket.size"), "376 × 136 mm") + ", ${coilsKb?.size ?: 2} Qi2 coils"),
            StorySpec("Mouse pocket", mm2(scene.nums("base.mouse_pocket.size"), "82 × 134 mm") + ", 1 Qi2 coil"),
            StorySpec("Coils", coilsKb?.takeIf { it.size >= 2 }?.let { "Two under the keyboard, ${fmtNum(it.max() - it.min())} mm apart; one under the mouse" }
                ?: "Two under the keyboard, one under the mouse"),
            StorySpec("Shielding", "Ferrite plate under every coil"),
            StorySpec("Pads", "${mm(scene.num("base.pad_t"), "2 mm")} soft-touch graphite"),
            StorySpec("Indicators", "Amber marks on the pocket lips"),
        )),
        SpecSection("Compute", "Stays in the base", listOf(
            StorySpec("Mainboard", (board?.let { "${fmtNum(it[0])} × ${fmtNum(it[1])} mm" } ?: "300 × 230 mm") + ", under the left deck"),
            StorySpec("Cooling", "Vapor chamber, fin stack, slim blower"),
            StorySpec("Power", "Internal PSU beside the mouse pocket, one mains cable"),
            StorySpec("Displays", "One link per panel"),
            StorySpec("I/O", "Rear face, left side"),
        )),
        SpecSection("Peripherals", "Wireless, charged where they live", listOf(
            StorySpec("Keyboard", (scene.text("keyboard.layout") ?: "75 %") + ", " + mm2(scene.nums("keyboard.size"), "360 × 120 mm")),
            StorySpec("Keyboard height", "${mm(scene.num("keyboard.h_front"), "9 mm")} front, ${mm(scene.num("keyboard.h_back"), "13 mm")} back"),
            StorySpec("Mouse", scene.nums("mouse.size")?.takeIf { it.size == 3 }?.let { "${fmtNum(it[0])} × ${fmtNum(it[1])} × ${fmtNum(it[2])} mm, ambidextrous" } ?: "66 × 118 × 38 mm, ambidextrous"),
            StorySpec("Desk mat", "Wool felt, " + mm2(scene.nums("deskmat.size")?.let { listOf(it[0], it.last()) }, "820 × 300 mm")),
        )),
        SpecSection("Lighting", "Amber #F2A04A, dims to off", listOf(
            StorySpec("Under-glow", "1120 mm strip along the front edge"),
            StorySpec("Neck bar", "${mm(scene.num("neck.light.w"), "150 mm")}, panels awake"),
            StorySpec("Pocket marks", "30 mm and 16 mm, charging"),
            StorySpec("Latch strip", "26 mm, laptop locked in"),
            StorySpec("Mouse", "Tail light"),
        )),
        SpecSection("Materials", "Three finishes for the metal", buildList {
            listOf("titanium", "graphite", "oxblood", "glass_black", "felt").forEach { k ->
                add(StorySpec(scene.materialLabel(k), scene.materialSpecs[k]?.replaceFirstChar { it.uppercase() } ?: when (k) {
                    "titanium" -> "Grade 5 titanium, 4.43 g/cm³"; "graphite" -> "Charcoal graphite finish"; "oxblood" -> "Brushed oxblood finish"
                    "glass_black" -> "Black cover glass"; else -> "Pressed wool felt"
                }))
            }
            add(StorySpec("Finish choice", FINISHES.joinToString(" · ") { it.second }))
        }),
        SpecSection("Dimensions", "Stow pose, millimetres", listOf(
            StorySpec("Overall", "${fmtMm(fp.widthMm)} × ${fmtMm(o[1])} × ${fmtMm(fp.baseDepthMm)} mm (W × H × D)"),
            StorySpec("Base slab", box(base, "1 290 × 36 × 300 mm")),
            StorySpec("Display top", "${fmtMm(o[1])} mm above the desk"),
            StorySpec("Work zone", "${fmtMm(fp.workGapMm)} mm clear in front of the base"),
            StorySpec("Desk needed", "${cm(fp.widthMm)} × ${cm(fp.workDepthMm)} cm to work, ${cm(fp.widthMm)} × ${cm(fp.baseDepthMm)} cm stowed"),
            StorySpec("Mass", if (scene.stationMassG > 0) "${fmtMass(scene.stationMassG)} without laptop and mat (concept estimate)" else "—"),
        )),
    )
}

@Composable
private fun SpecSheet(scene: Scene, pad: androidx.compose.ui.unit.Dp, maxW: androidx.compose.ui.unit.Dp) {
    val sections = remember(scene) { specSheet(scene) }
    @Composable fun SectionBlock(sec: SpecSection, modifier: Modifier) {
        Column(modifier.padding(bottom = 26.dp)) {
            SectionHeader(sec.title, sec.sub, size = 14.sp)
            Spacer(Modifier.height(8.dp))
            sec.rows.forEachIndexed { i, r -> SpecRow(r.label, r.value, last = i == sec.rows.lastIndex) }
        }
    }
    LazyColumn(Modifier.fillMaxSize().testTag("spec-sheet"), contentPadding = PaddingValues(top = 22.dp, bottom = 40.dp)) {
        if (maxW > 900.dp) {
            // two balanced columns, in reading order down the left then the right
            item(key = "columns") {
                val total = sections.sumOf { it.rows.size + 3 }
                var acc = 0
                val split = sections.indexOfFirst { acc += it.rows.size + 3; acc * 2 >= total } + 1
                Row(Modifier.readable(maxW).padding(horizontal = pad), horizontalArrangement = Arrangement.spacedBy(48.dp)) {
                    Column(Modifier.weight(1f)) { sections.take(split).forEach { SectionBlock(it, Modifier) } }
                    Column(Modifier.weight(1f)) { sections.drop(split).forEach { SectionBlock(it, Modifier) } }
                }
            }
        } else items(sections, key = { it.title }) { sec -> SectionBlock(sec, Modifier.readable().padding(horizontal = pad)) }
        item {
            Text(
                if (scene.fromFile) "Numbers come from the CAD export (model/scene.json). " + scene.massNote.ifBlank { "Masses are concept estimates from the CAD volumes and real densities." }
                else "The CAD export isn't bundled in this build; numbers are the design envelope from the spec.",
                color = C.muted, fontSize = 12.sp, lineHeight = 18.sp, modifier = Modifier.readable(maxW).padding(horizontal = pad),
            )
        }
    }
}

// ------------------------------------------------------------------------------------------------
// Bill of materials
// ------------------------------------------------------------------------------------------------

@Composable
private fun BomList(scene: Scene, pad: androidx.compose.ui.unit.Dp, maxW: androidx.compose.ui.unit.Dp) {
    val matW = if (maxW > 900.dp) 280.dp else 118.dp
    // the mass column grows with the font size, so "301 g" and the header never wrap
    val massW = (if (maxW > 900.dp) 90.dp else 62.dp) * LocalDensity.current.fontScale.coerceIn(1f, 1.6f)
    LazyColumn(Modifier.fillMaxSize().testTag("bom"), contentPadding = PaddingValues(top = 22.dp, bottom = 40.dp)) {
        item {
            Column(Modifier.readable(maxW).padding(horizontal = pad)) {
                Row(verticalAlignment = Alignment.Bottom) {
                    Column(Modifier.weight(1f)) {
                        Kicker("Bill of materials")
                        Spacer(Modifier.height(6.dp))
                        Text("${scene.parts.size} parts in ${scene.groups.size} groups", color = C.ink, fontSize = 16.sp, fontWeight = FontWeight.Light)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(fmtMass(scene.stationMassG).nbUnits(), color = C.amber, fontSize = 20.sp, fontWeight = FontWeight.Light)
                        MicroLabel("Station", color = C.muted, tracking = .24f, weight = FontWeight.Light)
                    }
                }
                Spacer(Modifier.height(16.dp))
                Row(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                    MicroLabel("Part", Modifier.weight(1f), color = C.muted, tracking = .22f, weight = FontWeight.Light)
                    MicroLabel("Material", Modifier.width(matW), color = C.muted, tracking = .22f, weight = FontWeight.Light, maxLines = 1)
                    MicroLabel("Mass", Modifier.width(massW), color = C.muted, tracking = .22f, align = TextAlign.End, weight = FontWeight.Light, maxLines = 1)
                }
                Hairline()
            }
        }
        scene.groups.forEach { g ->
            item(key = "g-${g.id}") {
                Row(Modifier.readable(maxW).padding(horizontal = pad).padding(top = 18.dp, bottom = 6.dp).testTag("bom-${g.id}"), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.width(2.dp).height(13.dp).background(C.amber))
                    Spacer(Modifier.width(10.dp))
                    Tracked(g.name, Modifier.weight(1f), size = 10.5.sp, color = C.ink, weight = FontWeight.Normal, tracking = .16f)
                    Text(fmtMass(g.massG).nbUnits(), color = C.ink, fontSize = 12.5.sp, maxLines = 1)
                }
            }
            val parts = scene.partsOf(g.id)
            items(parts, key = { "p-${it.id}" }) { p ->
                Column(Modifier.readable(maxW).padding(horizontal = pad)) {
                    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f).padding(start = 12.dp, end = 8.dp)) {
                            Text(p.name, color = if (p.internal) C.ink.copy(alpha = .7f) else C.ink.copy(alpha = .9f), fontSize = 13.sp, lineHeight = 17.sp)
                            if (p.internal) InternalTag(Modifier.padding(top = 4.dp))
                        }
                        Row(Modifier.width(matW), verticalAlignment = Alignment.CenterVertically) {
                            Swatch(p.material, 9.dp); Spacer(Modifier.width(6.dp))
                            Text(scene.materialLabel(p.material), color = C.muted, fontSize = 11.5.sp, lineHeight = 15.sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                        }
                        Text(fmtMass(p.massG).nbUnits(), Modifier.width(massW), color = C.ink.copy(alpha = .8f), fontSize = 12.sp, textAlign = TextAlign.End, maxLines = 1)
                    }
                    Hairline(color = C.line.copy(alpha = .45f))
                }
            }
        }
        item {
            Text(
                (scene.massNote.ifBlank { "Masses use real densities (titanium 4.43, steel 7.85, copper 8.96, glass 2.5 g/cm³…) and assume solid parts unless the model is hollow." }) +
                    " “Station” excludes the laptop and the desk mat.",
                color = C.muted, fontSize = 12.sp, lineHeight = 18.sp, modifier = Modifier.readable(maxW).padding(horizontal = pad).padding(top = 22.dp),
            )
        }
    }
}

// ------------------------------------------------------------------------------------------------
// Desk fit
// ------------------------------------------------------------------------------------------------

/** Plan footprint in mm (x right, z toward you), derived from scene.json where it can be. */
data class Footprint(
    val xMin: Double, val xMax: Double, val baseDepthMm: Double, val workGapMm: Double, val matCz: Double, val matW: Double, val matD: Double, val matCx: Double,
) {
    val widthMm get() = xMax - xMin
    val baseFront get() = baseDepthMm / 2
    /** Work needs room up to the front edge of the desk mat. */
    val workDepthMm get() = baseDepthMm / 2 + matCz + matD / 2
}

fun footprint(scene: Scene): Footprint {
    var x0 = scene.boundsMin[0] * 1000; var x1 = scene.boundsMax[0] * 1000
    if (x1 - x0 < 500) { x0 = -640.0; x1 = 775.0 }
    val baseD = scene.bbox("base")?.get(2)?.takeIf { it in 150.0..600.0 } ?: 300.0
    val mat = scene.bbox("deskmat")
    val matD = mat?.get(2)?.takeIf { it in 100.0..800.0 } ?: 300.0
    val matW = mat?.get(0)?.takeIf { it in 200.0..2000.0 } ?: 820.0
    val pv = scene.group("deskmat")?.pivot
    val mc = scene.nums("deskmat.c")?.takeIf { it.size == 2 && it[1] > baseD / 2 }
    val matCz = mc?.get(1) ?: pv?.getOrNull(2)?.times(1000)?.takeIf { it > baseD / 2 } ?: 385.0
    val matCx = mc?.get(0) ?: pv?.getOrNull(0)?.times(1000)?.takeIf { pv[2] * 1000 > baseD / 2 } ?: 60.0
    // work zone: from the base's front edge to the keyboard's back edge in the Work pose
    val kbZ = scene.nums("keyboard.stow_c")?.getOrNull(1) ?: 62.0
    val kbD = scene.nums("keyboard.size")?.getOrNull(1) ?: 120.0
    val workT = scene.poseT("work", "keyboard")[2] * 1000
    val gap = (kbZ + workT - kbD / 2 - baseD / 2).takeIf { workT > 0 && it in 50.0..400.0 } ?: 150.0
    return Footprint(x0, x1, baseD, gap, matCz, matW, matD, matCx)
}

/** Room left beside a laptop in the slot: the 20 mm slot takes laptops up to 18 mm thick. */
const val LAPTOP_CLEARANCE_MM = 2.0

/** Where the dock's USB-C plug sits, measured from the hinge end of a docked laptop (mm), from params. */
fun portFromHingeMm(scene: Scene): Double? {
    val plug = scene.num("dock.connector.z") ?: scene.num("laptop.port_z") ?: return null
    val hingeEnd = scene.nums("laptop.z")?.firstOrNull() ?: return null
    return (plug - hingeEnd).takeIf { it in 5.0..200.0 }
}

private fun cm(mm: Double): String { val c = mm / 10.0; return if (c == Math.floor(c)) c.toInt().toString() else String.format(Locale.US, "%.1f", c) }

enum class Fit { Fits, StowOnly, No }

fun fitOf(fp: Footprint, deskWcm: Int, deskDcm: Int): Fit {
    val w = deskWcm * 10.0; val d = deskDcm * 10.0
    return when {
        w + 0.5 < fp.widthMm || d + 0.5 < fp.baseDepthMm -> Fit.No
        d + 0.5 < fp.workDepthMm -> Fit.StowOnly
        else -> Fit.Fits
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DeskFit(app: AppState, scene: Scene, pad: androidx.compose.ui.unit.Dp, maxW: androidx.compose.ui.unit.Dp) {
    val fp = remember(scene) { footprint(scene) }
    val fit = fitOf(fp, app.deskW, app.deskD)
    var planMode by rememberSaveable { mutableStateOf("work") }
    val inputs: @Composable ColumnScope.() -> Unit = {
        Text("Enter your desk and see the station on it, from above, with the ${cm(fp.workGapMm)} cm work zone.", color = C.muted, fontSize = 14.sp, lineHeight = 21.sp)
        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            CmField("Desk width", app.deskW, { app.deskW = it }, Modifier.weight(1f), "desk-width")
            CmField("Desk depth", app.deskD, { app.deskD = it }, Modifier.weight(1f), "desk-depth")
        }
        Spacer(Modifier.height(12.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(120 to 60, 140 to 70, 160 to 80, 180 to 90).forEach { (w, d) ->
                Chip("$w × $d", app.deskW == w && app.deskD == d, { app.deskW = w; app.deskD = d }, Modifier.testTag("desk-$w"), compact = true)
            }
        }
        Spacer(Modifier.height(20.dp))
        Verdict(fp, fit, app.deskW, app.deskD)
    }
    val plan: @Composable ColumnScope.() -> Unit = {
        Row(verticalAlignment = Alignment.CenterVertically) {
            MicroLabel("Plan view", Modifier.weight(1f), color = C.muted, tracking = .26f, weight = FontWeight.Light)
            Segmented(listOf("work" to "Work", "stow" to "Stow"), planMode, { planMode = it }, Modifier.width(190.dp), tagPrefix = "plan")
        }
        Spacer(Modifier.height(12.dp))
        DeskPlan(fp, app.deskW, app.deskD, planMode, Modifier.fillMaxWidth().testTag("desk-plan"))
        Spacer(Modifier.height(14.dp))
        Legend()
    }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val twoColumns = maxW > 900.dp && maxWidth >= 840.dp
        LazyColumn(Modifier.fillMaxSize().testTag("desk-fit"), contentPadding = PaddingValues(top = 22.dp, bottom = 40.dp)) {
            item {
                if (twoColumns) {
                    Row(Modifier.readable(maxW).padding(horizontal = pad), horizontalArrangement = Arrangement.spacedBy(36.dp)) {
                        Column(Modifier.weight(.42f), content = inputs)
                        Column(Modifier.weight(.58f), content = plan)
                    }
                } else {
                    Column(Modifier.readable().padding(horizontal = pad)) { inputs(); Spacer(Modifier.height(18.dp)); plan() }
                }
            }
        }
    }
}

@Composable
private fun Verdict(fp: Footprint, fit: Fit, wcm: Int, dcm: Int) {
    val (title, color) = when (fit) {
        Fit.Fits -> "It fits" to C.amber
        Fit.StowOnly -> "Fits stowed only" to C.titanium
        Fit.No -> "Doesn't fit" to C.warn
    }
    val spareW = (wcm * 10 - fp.widthMm) / 10.0
    val text = when (fit) {
        Fit.Fits -> {
            val side = spareW / 2
            val front = (dcm * 10 - fp.workDepthMm) / 10.0
            "${fmt1(side)} cm spare at each side and ${fmt1(front)} cm in front of the mat in Work. Stowed, the station needs only ${cm(fp.baseDepthMm)} cm of depth."
        }
        Fit.StowOnly -> "Stowed, it fits with ${fmt1(dcm - fp.baseDepthMm / 10)} cm to spare. Working needs ${cm(fp.workDepthMm)} cm: the base, the ${cm(fp.workGapMm)} cm work zone and the mat. You're ${fmt1(fp.workDepthMm / 10 - dcm)} cm short."
        Fit.No -> buildList {
            if (wcm * 10 < fp.widthMm) add("The station is ${cm(fp.widthMm)} cm wide including the dock; your desk is $wcm cm, ${fmt1(fp.widthMm / 10 - wcm)} cm short.")
            if (dcm * 10 < fp.baseDepthMm) add("The base alone is ${cm(fp.baseDepthMm)} cm deep; your desk is $dcm cm.")
        }.joinToString(" ")
    }
    val shape = RoundedCornerShape(18.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(color.copy(alpha = .08f)).border(1.dp, color.copy(alpha = .5f), shape).padding(18.dp).testTag("fit-verdict")) {
        Tracked(title, size = 16.sp, color = color, tracking = .26f, weight = FontWeight.Normal)
        Spacer(Modifier.height(8.dp))
        Text(text.nbUnits(), color = C.ink.copy(alpha = .86f), fontSize = 14.sp, lineHeight = 21.sp)
    }
}

private fun fmt1(d: Double): String = if (d == Math.floor(d)) d.toInt().toString() else String.format(Locale.US, "%.1f", d)

@Composable
private fun CmField(label: String, value: Int, onValue: (Int) -> Unit, modifier: Modifier, tag: String) {
    var text by remember(value) { mutableStateOf(value.toString()) }
    val shape = RoundedCornerShape(16.dp)
    // The number grows with the font size up to 1.3×, then holds, so three digits always fit between the buttons.
    val fs = LocalDensity.current.fontScale
    val valueSize = (21f * minOf(fs, 1.3f) / fs).sp
    BoxWithConstraints(modifier) {
        val roomy = maxWidth >= 150.dp // on a narrow field the unit moves up into the label
        Column(Modifier.fillMaxWidth()) {
            MicroLabel(if (roomy) label else "$label (cm)", Modifier.padding(bottom = 8.dp), color = C.muted, tracking = .24f, weight = FontWeight.Light)
            Row(Modifier.fillMaxWidth().clip(shape).background(C.panel).border(1.dp, C.line, shape).padding(5.dp), verticalAlignment = Alignment.CenterVertically) {
                IconCircle(Icons.Outlined.Remove, "Decrease $label", { onValue((value - 5).coerceAtLeast(30)) }, size = 34.dp, background = C.panel2)
                BasicTextField(
                    text, { t -> val d = t.filter(Char::isDigit).take(3); text = d; d.toIntOrNull()?.takeIf { it in 1..999 }?.let(onValue) },
                    Modifier.weight(1f).testTag(tag), singleLine = true,
                    textStyle = TextStyle(color = C.ink, fontSize = valueSize, fontWeight = FontWeight.Light, textAlign = TextAlign.Center),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                    cursorBrush = SolidColor(C.amber),
                )
                if (roomy) Text("cm", color = C.muted, fontSize = 12.sp, maxLines = 1, modifier = Modifier.padding(end = 6.dp))
                IconCircle(Icons.Outlined.Add, "Increase $label", { onValue((value + 5).coerceAtMost(400)) }, size = 34.dp, background = C.panel2)
            }
        }
    }
}

@Composable
private fun Legend() {
    Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
        @Composable fun item(c: Color, t: String) = Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).clip(RoundedCornerShape(2.dp)).background(c)); Spacer(Modifier.width(6.dp)); Text(t, color = C.muted, fontSize = 11.5.sp)
        }
        item(C.titanium.copy(alpha = .7f), "Station")
        item(C.amber.copy(alpha = .55f), "Work zone")
        item(Color(0xFF4A4541), "Mat & devices")
    }
}

/** Top-down plan of the desk with the station pushed to the back edge, centred left to right. */
@Composable
private fun DeskPlan(fp: Footprint, wcm: Int, dcm: Int, mode: String, modifier: Modifier) {
    val tm = rememberTextMeasurer()
    val dimStyle = TextStyle(color = C.ink.copy(alpha = .85f), fontSize = 10.sp, letterSpacing = 1.2.sp)
    val small = TextStyle(color = C.muted, fontSize = 9.sp, letterSpacing = 1.2.sp)
    val amberT = TextStyle(color = C.amber, fontSize = 9.5.sp, letterSpacing = 1.2.sp)
    val deskW = wcm * 10.0; val deskD = dcm * 10.0
    val work = mode == "work"
    val needD = if (work) fp.workDepthMm else fp.baseDepthMm
    // world extents (mm): desk from 0..W, 0..D; station centred on the desk, base back on the desk's back edge
    val ext = Size(max(deskW, fp.widthMm).toFloat(), max(deskD, needD).toFloat())
    val aspect = ((ext.width + 260f) / (ext.height + 240f)).coerceIn(1.1f, 3.2f)
    Canvas(modifier.aspectRatio(aspect).clip(RoundedCornerShape(18.dp)).background(C.panel).border(1.dp, C.line, RoundedCornerShape(18.dp))) {
        val padL = 18.dp.toPx(); val padR = 52.dp.toPx(); val padT = 40.dp.toPx(); val padB = 36.dp.toPx()
        val s = minOf((size.width - padL - padR) / ext.width, (size.height - padT - padB) / ext.height)
        val ox = padL + ((size.width - padL - padR) - ext.width * s) / 2
        val oy = padT
        val deskLeft = (ext.width - deskW.toFloat()) / 2
        val stationShift = (ext.width / 2) - ((fp.xMin + fp.xMax) / 2).toFloat()
        // station mm (x, z) → px
        fun P(x: Double, z: Double) = Offset(ox + (x.toFloat() + stationShift) * s, oy + (z + fp.baseDepthMm / 2).toFloat() * s)
        fun D(x: Float, z: Float) = Offset(ox + (deskLeft + x) * s, oy + z * s)
        fun rect(x0: Double, z0: Double, x1: Double, z1: Double): Pair<Offset, Size> { val a = P(x0, z0); val b = P(x1, z1); return a to Size(b.x - a.x, b.y - a.y) }

        val fits = fitOf(fp, wcm, dcm)
        val bad = fits == Fit.No || (work && fits == Fit.StowOnly)
        // desk
        val d0 = D(0f, 0f)
        drawRoundRect(Color(0xFF231C17), d0, Size(deskW.toFloat() * s, deskD.toFloat() * s), CornerRadius(4.dp.toPx()))
        clipRect(d0.x, d0.y, d0.x + deskW.toFloat() * s, d0.y + deskD.toFloat() * s) { grid(100f * s, C.line.copy(alpha = .55f), major = 5) }
        drawRoundRect(if (bad) C.warn else C.titanium.copy(alpha = .45f), d0, Size(deskW.toFloat() * s, deskD.toFloat() * s), CornerRadius(4.dp.toPx()), style = Stroke(1.5.dp.toPx()))

        // work zone + mat + devices
        if (work) {
            val (wz, wzs) = rect(fp.xMin + 40, fp.baseFront, fp.xMax - 140, fp.baseFront + fp.workGapMm)
            drawRect(C.amber.copy(alpha = .12f), wz, wzs)
            val hatch = 14f * s.coerceAtLeast(.4f) * 3
            clipRect(wz.x, wz.y, wz.x + wzs.width, wz.y + wzs.height) {
                var x = wz.x - wzs.height; while (x < wz.x + wzs.width) { drawLine(C.amber.copy(alpha = .22f), Offset(x, wz.y + wzs.height), Offset(x + wzs.height, wz.y), 1f); x += hatch }
            }
            val (m0, ms) = rect(fp.matCx - fp.matW / 2, fp.matCz - fp.matD / 2, fp.matCx + fp.matW / 2, fp.matCz + fp.matD / 2)
            drawRoundRect(Color(0xFF3A3532), m0, ms, CornerRadius(6f * s))
            val (k0, ks) = rect(-270.0, 300.0, 90.0, 420.0); drawRoundRect(Color(0xFF55504C), k0, ks, CornerRadius(8f * s))
            val (mo0, mos) = rect(257.0, 301.0, 323.0, 419.0); drawRoundRect(Color(0xFF55504C), mo0, mos, CornerRadius(30f * s))
            // 15 cm dimension
            val a = P(-470.0, fp.baseFront); val b = P(-470.0, fp.baseFront + fp.workGapMm)
            drawLine(C.amber, a, b, 1.5f); drawLine(C.amber, a - Offset(5f, 0f), a + Offset(5f, 0f), 1.5f); drawLine(C.amber, b - Offset(5f, 0f), b + Offset(5f, 0f), 1.5f)
            val t = tm.measure("${cm(fp.workGapMm)} CM", amberT)
            drawText(t, topLeft = Offset(a.x + 6.dp.toPx(), (a.y + b.y) / 2 - t.size.height / 2f))
        }
        // base slab with pockets
        val (b0, bs) = rect(-640.0, -fp.baseDepthMm / 2, 650.0, fp.baseDepthMm / 2)
        drawRoundRect(C.titanium.copy(alpha = .62f), b0, bs, CornerRadius(40f * s))
        drawRoundRect(C.titanium, b0, bs, CornerRadius(40f * s), style = Stroke(1.dp.toPx()))
        val (kp, kps) = rect(-278.0, -6.0, 98.0, 130.0); drawRoundRect(Color(0xFF26231F), kp, kps, CornerRadius(8f * s))
        val (mp, mps) = rect(209.0, -5.0, 291.0, 129.0); drawRoundRect(Color(0xFF26231F), mp, mps, CornerRadius(10f * s))
        if (!work) {
            val (k0, ks) = rect(-270.0, 2.0, 90.0, 122.0); drawRoundRect(Color(0xFF55504C), k0, ks, CornerRadius(8f * s))
            val (mo0, mos) = rect(217.0, 3.0, 283.0, 121.0); drawRoundRect(Color(0xFF55504C), mo0, mos, CornerRadius(30f * s))
        }
        // neck + display facets (plan), seam mullion
        val (n0, ns) = rect(-160.0, -140.0, 160.0, -70.0); drawRect(Color(0xFF3A3735), n0, ns)
        val toe = Math.toRadians(10.0); val f = 612.7
        val seam = P(0.0, -62.0); val l = P(-f * cos(toe), -62 + f * sin(toe)); val r = P(f * cos(toe), -62 + f * sin(toe))
        val shroud = Path().apply {
            val lb = P(-f * cos(toe) - 45 * sin(toe), -62 + f * sin(toe) - 45 * cos(toe)); val rb = P(f * cos(toe) + 45 * sin(toe), -62 + f * sin(toe) - 45 * cos(toe))
            val sb = P(0.0, -62.0 - 47); moveTo(l.x, l.y); lineTo(seam.x, seam.y); lineTo(r.x, r.y); lineTo(rb.x, rb.y); lineTo(sb.x, sb.y); lineTo(lb.x, lb.y); close()
        }
        drawPath(shroud, Color(0xFF2B2826))
        drawLine(Color(0xFF0B0A0C), l, seam, 4f * s.coerceAtLeast(.6f) * 2, StrokeCap.Round)
        drawLine(Color(0xFF0B0A0C), seam, r, 4f * s.coerceAtLeast(.6f) * 2, StrokeCap.Round)
        drawCircle(C.titanium, 2.5.dp.toPx(), seam)
        // dock wing + laptop slot
        val (dk, dks) = rect(650.0, -130.0, 775.0, 130.0)
        drawRoundRect(C.titanium.copy(alpha = .62f), dk, dks, CornerRadius(14f * s))
        drawRoundRect(C.oxblood, dk + Offset(dks.width - 3.dp.toPx(), 0f), Size(3.dp.toPx(), dks.height), CornerRadius(2f))
        val (ls, lss) = rect(714.5, -106.0, 729.5, 106.0); drawRect(Color(0xFFB9B5AF), ls, lss)

        // overflow beyond the desk
        if (bad) {
            val dash = PathEffect.dashPathEffect(floatArrayOf(6f, 5f))
            val stL = P(fp.xMin, 0.0).x; val stR = P(fp.xMax, 0.0).x
            val dl = d0.x; val dr = d0.x + deskW.toFloat() * s; val db = d0.y + deskD.toFloat() * s
            val needB = P(0.0, needD - fp.baseDepthMm / 2).y
            if (stL < dl) drawRect(C.warn.copy(alpha = .22f), Offset(stL, b0.y), Size(dl - stL, needB - b0.y))
            if (stR > dr) drawRect(C.warn.copy(alpha = .22f), Offset(dr, b0.y), Size(stR - dr, needB - b0.y))
            if (needB > db) drawRect(C.warn.copy(alpha = .22f), Offset(max(stL, dl), db), Size(minOf(stR, dr) - max(stL, dl), needB - db))
            // the needed depth is a problem only when it runs past the desk; otherwise it stays a quiet reference line
            drawLine(if (needB > db) C.warn else C.muted.copy(alpha = .5f), Offset(stL, needB), Offset(stR, needB), 1.2f, pathEffect = dash)
        }

        // dimensions: station width above, needed depth on the right
        val yDim = oy - 16.dp.toPx()
        val xa = P(fp.xMin, 0.0).x; val xb = P(fp.xMax, 0.0).x
        drawLine(C.muted, Offset(xa, yDim), Offset(xb, yDim), 1f)
        drawLine(C.muted, Offset(xa, yDim - 5f), Offset(xa, yDim + 5f), 1f); drawLine(C.muted, Offset(xb, yDim - 5f), Offset(xb, yDim + 5f), 1f)
        val wt = tm.measure("${cm(fp.widthMm)} CM", dimStyle)
        drawRect(C.panel, Offset((xa + xb) / 2 - wt.size.width / 2f - 6f, yDim - wt.size.height / 2f), Size(wt.size.width + 12f, wt.size.height.toFloat()))
        drawText(wt, topLeft = Offset((xa + xb) / 2 - wt.size.width / 2f, yDim - wt.size.height / 2f))
        val xDim = ox + ext.width * s + 16.dp.toPx()
        val za = oy; val zb = P(0.0, needD - fp.baseDepthMm / 2).y
        drawLine(C.muted, Offset(xDim, za), Offset(xDim, zb), 1f)
        drawLine(C.muted, Offset(xDim - 5f, za), Offset(xDim + 5f, za), 1f); drawLine(C.muted, Offset(xDim - 5f, zb), Offset(xDim + 5f, zb), 1f)
        val dt = tm.measure("${cm(needD)}", dimStyle)
        drawText(dt, topLeft = Offset(xDim + 6f, (za + zb) / 2 - dt.size.height / 2f))
        val dl = tm.measure("CM", small)
        drawText(dl, topLeft = Offset(xDim + 6f, (za + zb) / 2 + dt.size.height / 2f))
        // desk label
        val lab = tm.measure("YOUR DESK · $wcm × $dcm CM", small)
        val below = max(d0.y + deskD.toFloat() * s, P(0.0, needD - fp.baseDepthMm / 2).y)
        drawText(lab, topLeft = Offset(d0.x, below + 8.dp.toPx()))
    }
}
