package com.natesapps.nightarray

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import kotlin.math.roundToInt

// ---------- scene.json model (SPEC.md §3) ----------
data class Group(
    val id: String, val name: String, val summary: String, val description: String, val parts: List<String>,
    val pivot: List<Double>, val bboxMm: List<Double>, val massG: Double, val volumeCm3: Double, val materials: List<String>,
)

data class Part(
    val id: String, val group: String, val name: String, val material: String, val internal: Boolean,
    val bboxMm: List<Double>, val volumeCm3: Double, val massG: Double,
)

data class CadFile(val id: String, val group: String?, val format: String, val label: String, val path: String, val bytes: Long)
data class DockStep(val step: String, val title: String, val caption: String)
data class Dim(val id: String, val label: String, val pose: String?)
/** scene.json `screen` block: the dual 27" layout (SPEC.md §2/§3). */
data class ScreenInfo(
    val layout: String, val panels: Int, val panelInch: Double, val activeMm: List<Double>, val resEach: List<Int>,
    val seamMm: Double, val toeInDeg: Double,
) {
    val canvasW: Int get() = resEach[0] * panels
    val canvasH: Int get() = resEach[1]
    /** Pixels per inch of one panel. */
    val ppi: Double get() = resEach[0] / (activeMm[0] / 25.4)
    /** Active width of all panels together (mm). */
    val activeTotalMm: Double get() = activeMm[0] * panels

    companion object {
        val DEFAULT = ScreenInfo("dual", 2, 27.0, listOf(596.7, 335.7), listOf(2560, 1440), 14.0, 10.0)
    }
}

class Scene(
    val name: String,
    val params: JSONObject,
    val boundsMin: List<Double>, val boundsMax: List<Double>,
    val materialLabels: Map<String, String>,
    val groups: List<Group>,
    val parts: List<Part>,
    val files: List<CadFile>,
    val drawings: Map<String, String>,
    val dims: List<Dim>,
    val screen: ScreenInfo,
    val dockSteps: List<DockStep>,
    val poses: JSONObject,
    /** True when parsed from the real model/scene.json, false when using the built-in fallback. */
    val fromFile: Boolean,
    /** Material key → one-line spec ("Grade 5 titanium, bead-blasted and brushed"), when scene.json has it. */
    val materialSpecs: Map<String, String> = emptyMap(),
    val massNote: String = "",
) {
    /** Any value in params by dot path, e.g. "base.kb_pocket.size". */
    fun param(path: String): Any? {
        var cur: Any? = params
        for (k in path.split('.')) cur = (cur as? JSONObject)?.opt(k) ?: return null
        return cur
    }
    fun num(path: String): Double? = (param(path) as? Number)?.toDouble()?.takeIf { !it.isNaN() }
    fun nums(path: String): List<Double>? = (param(path) as? JSONArray)?.let { a -> (0 until a.length()).map { a.optDouble(it) } }?.takeIf { l -> l.isNotEmpty() && l.none { it.isNaN() } }
    fun text(path: String): String? = (param(path) as? String)?.takeIf { it.isNotBlank() }
    /** Span of a [lo, hi] param range, e.g. dock.slot.x → 20. */
    fun span(path: String): Double? = nums(path)?.takeIf { it.size == 2 }?.let { it[1] - it[0] }

    fun group(id: String?): Group? = groups.firstOrNull { it.id == id }
    fun partsOf(groupId: String): List<Part> = parts.filter { it.group == groupId }
    fun filesOf(groupId: String?): List<CadFile> = files.filter { it.group == groupId }
    fun materialLabel(key: String): String = materialLabels[key] ?: MATERIAL_LABELS[key] ?: key.replace('_', ' ').replaceFirstChar { it.uppercase() }

    /** Numeric param from params.py (mm), trying several plausible key spellings. */
    fun p(vararg keys: String): Double? {
        for (k in keys) {
            val v = findNumber(params, k)
            if (v != null) return v
        }
        return null
    }

    /** Stow-pose overall size in mm (W, H, D). */
    val overallMm: List<Double> get() = listOf(0, 1, 2).map { (boundsMax[it] - boundsMin[it]) * 1000 }

    /** World-space translation of a group in a pose (metres), or zero. */
    fun poseT(pose: String, group: String): List<Double> {
        val g = poses.optJSONObject(pose)?.optJSONObject(group) ?: return listOf(0.0, 0.0, 0.0)
        val t = g.optJSONArray("t") ?: return listOf(0.0, 0.0, 0.0)
        return doubles(t, 3)
    }

    fun hiddenIn(pose: String, group: String): Boolean = poses.optJSONObject(pose)?.optJSONObject(group)?.optBoolean("hidden", false) == true

    val stationMassG: Double get() = groups.filter { it.id !in setOf("laptop", "deskmat") }.sumOf { it.massG }

    /** Display width across both facets (mm): the display group's bbox, else derived from the screen block. */
    val displayWidthMm: Double get() = group("display")?.bboxMm?.getOrNull(0)?.takeIf { it > 100 } ?: chordFromScreen(screen)

    /** Group bbox [w, h, d] in mm or null when unknown. */
    fun bbox(groupId: String): List<Double>? = group(groupId)?.bboxMm?.takeIf { it.size == 3 && it.all { v -> v > 0 } }
}

val MATERIAL_LABELS = mapOf(
    "titanium" to "Neutral Titanium", "graphite" to "Charcoal Graphite", "oxblood" to "Brushed Oxblood",
    "glass_black" to "Black cover glass", "screen" to "Display panel", "keycap" to "PBT keycaps", "rubber" to "Rubber",
    "amber_led" to "Amber LED", "copper" to "Copper", "pcb" to "Circuit board", "ferrite" to "Ferrite",
    "laptop_alu" to "Laptop aluminium", "felt" to "Wool felt", "steel" to "Steel",
)

val GROUP_ORDER = listOf("display", "stand", "base", "dock", "laptop", "keyboard", "mouse", "deskmat", "internals")

private fun findNumber(o: JSONObject, key: String): Double? {
    if (o.has(key)) {
        val v = o.opt(key)
        if (v is Number) return v.toDouble()
        if (v is String) v.toDoubleOrNull()?.let { return it }
    }
    // nested dicts (e.g. params.display.radius)
    if ('.' in key) {
        val head = key.substringBefore('.'); val rest = key.substringAfter('.')
        o.optJSONObject(head)?.let { return findNumber(it, rest) }
    }
    return null
}

private fun doubles(a: JSONArray?, n: Int = -1): List<Double> {
    if (a == null) return if (n > 0) List(n) { 0.0 } else emptyList()
    val l = (0 until a.length()).map { a.optDouble(it, 0.0).let { d -> if (d.isNaN()) 0.0 else d } }
    return if (n > 0) (l + List(n) { 0.0 }).take(n) else l
}

private fun strings(a: JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { a.optString(it, "").takeIf { s -> s.isNotEmpty() } }

private fun JSONObject.str(k: String, def: String = ""): String = if (has(k) && !isNull(k)) optString(k, def) else def

object SceneParser {
    fun parse(text: String): Scene {
        val o = JSONObject(text)
        val params = o.optJSONObject("params") ?: JSONObject()
        val b = o.optJSONObject("bounds")
        val fb = Fallback.scene
        val bmin = b?.optJSONArray("min")?.let { doubles(it, 3) } ?: fb.boundsMin
        val bmax = b?.optJSONArray("max")?.let { doubles(it, 3) } ?: fb.boundsMax

        val mats = LinkedHashMap<String, String>()
        val matSpecs = LinkedHashMap<String, String>()
        o.optJSONObject("materials")?.let { m ->
            m.keys().forEach { k ->
                mats[k] = m.optJSONObject(k)?.str("label")?.ifBlank { null } ?: MATERIAL_LABELS[k] ?: k
                m.optJSONObject(k)?.str("spec")?.takeIf { it.isNotBlank() }?.let { matSpecs[k] = it }
            }
        }

        val partsArr = o.optJSONArray("parts") ?: JSONArray()
        val parts = (0 until partsArr.length()).mapNotNull { i ->
            val p = partsArr.optJSONObject(i) ?: return@mapNotNull null
            val id = p.str("id").ifBlank { return@mapNotNull null }
            Part(id, p.str("group"), p.str("name").ifBlank { prettyId(id) }, p.str("material", "titanium"), p.optBoolean("internal", false),
                doubles(p.optJSONArray("bbox_mm"), 3), p.optDouble("volume_cm3", 0.0).orZero(), p.optDouble("mass_g", 0.0).orZero())
        }

        val groupsArr = o.optJSONArray("groups") ?: JSONArray()
        val groups = (0 until groupsArr.length()).mapNotNull { i ->
            val g = groupsArr.optJSONObject(i) ?: return@mapNotNull null
            val id = g.str("id").ifBlank { return@mapNotNull null }
            val fg = fb.group(id)
            val gp = strings(g.optJSONArray("parts")).ifEmpty { parts.filter { it.group == id }.map { it.id } }
            val gparts = parts.filter { it.id in gp }
            Group(
                id, g.str("name").ifBlank { fg?.name ?: prettyId(id) }, g.str("summary").ifBlank { fg?.summary ?: "" },
                g.str("description").ifBlank { fg?.description ?: "" }, gp, doubles(g.optJSONArray("pivot"), 3),
                doubles(g.optJSONArray("bbox_mm"), 3),
                g.optDouble("mass_g", Double.NaN).let { if (it.isNaN() || it <= 0) gparts.sumOf { p -> p.massG } else it },
                g.optDouble("volume_cm3", Double.NaN).let { if (it.isNaN() || it <= 0) gparts.sumOf { p -> p.volumeCm3 } else it },
                strings(g.optJSONArray("materials")).ifEmpty { gparts.map { it.material }.distinct() },
            )
        }.sortedBy { GROUP_ORDER.indexOf(it.id).let { i -> if (i < 0) 99 else i } }

        val filesArr = o.optJSONArray("files") ?: JSONArray()
        val files = (0 until filesArr.length()).mapNotNull { i ->
            val f = filesArr.optJSONObject(i) ?: return@mapNotNull null
            val path = f.str("path").ifBlank { return@mapNotNull null }
            CadFile(f.str("id").ifBlank { path }, f.str("group").ifBlank { null }, f.str("format").ifBlank { path.substringAfterLast('.').uppercase() }.uppercase(Locale.ROOT),
                f.str("label"), path, f.optLong("bytes", 0L).coerceAtLeast(0L))
        }

        val drawings = LinkedHashMap<String, String>()
        o.optJSONObject("drawings")?.let { d -> d.keys().forEach { k -> d.str(k).takeIf { it.isNotBlank() }?.let { drawings[k] = it } } }

        val dimsArr = o.optJSONArray("dims") ?: JSONArray()
        val dims = (0 until dimsArr.length()).mapNotNull { i ->
            val d = dimsArr.optJSONObject(i) ?: return@mapNotNull null
            Dim(d.str("id"), d.str("label"), d.str("pose").ifBlank { null })
        }

        val scr = o.optJSONObject("screen")
        val screen = if (scr == null) fb.screen else {
            val d = ScreenInfo.DEFAULT
            val active = doubles(scr.optJSONArray("panel_active_mm")).takeIf { it.size >= 2 && it[0] > 0 && it[1] > 0 } ?: d.activeMm
            val res = doubles(scr.optJSONArray("resolution_each")).map { it.roundToInt() }.takeIf { it.size >= 2 && it[0] > 0 && it[1] > 0 } ?: d.resEach
            ScreenInfo(
                scr.str("layout", d.layout).ifBlank { d.layout }, scr.optInt("panels", d.panels).takeIf { it in 1..8 } ?: d.panels,
                scr.optDouble("panel_inch", d.panelInch).orElse(d.panelInch), active.take(2), res.take(2),
                scr.optDouble("seam_mm", d.seamMm).let { if (it.isNaN() || it < 0) d.seamMm else it },
                scr.optDouble("toe_in_deg", d.toeInDeg).let { if (it.isNaN() || it < 0 || it > 45) d.toeInDeg else it },
            )
        }

        val seqArr = o.optJSONArray("dock_sequence")
        val steps = if (seqArr == null) fb.dockSteps else (0 until seqArr.length()).mapNotNull { i ->
            val s = seqArr.optJSONObject(i) ?: return@mapNotNull null
            val id = s.str("step").ifBlank { return@mapNotNull null }
            val f = fb.dockSteps.firstOrNull { it.step == id }
            DockStep(id, s.str("title").ifBlank { f?.title ?: prettyId(id) }, s.str("caption").ifBlank { f?.caption ?: "" })
        }.ifEmpty { fb.dockSteps }

        return Scene(
            o.str("name").ifBlank { fb.name }, params, bmin, bmax, mats,
            groups.ifEmpty { fb.groups }, parts.ifEmpty { fb.parts },
            files.ifEmpty { fb.files }, drawings.ifEmpty { fb.drawings }, dims, screen, steps,
            o.optJSONObject("poses") ?: fb.poses, fromFile = true,
            materialSpecs = matSpecs, massNote = o.str("mass_note"),
        )
    }

    private fun Double.orZero() = if (isNaN() || isInfinite()) 0.0 else this
    private fun Double.orElse(d: Double) = if (isNaN() || this <= 0) d else this
}

fun prettyId(id: String) = id.replace('_', ' ').replace('-', ' ').replaceFirstChar { it.uppercase() }

/** The SPEC envelope as a scene, so the app is complete even before (or without) the CAD export. */
object Fallback {
    private fun g(id: String, name: String, summary: String, description: String, parts: List<Pair<String, String>>, bbox: List<Double>, pivot: List<Double>) =
        Group(id, name, summary, description, parts.map { it.first }, pivot, bbox, 0.0, 0.0, parts.map { it.second }.distinct())

    private val groupDefs = listOf(
        g("display", "Dual 27-inch display", "Two off-the-shelf 27\u2033 QHD panels in one titanium shroud, 5120 × 1440.",
            "Two mainstream 27-inch QHD IPS monitors, stripped of their housings and mounted side by side on a steel spine, each toed in 10°. A 4 mm titanium mullion covers the 14 mm seam between them; a shared titanium rim and graphite rear shroud make them one object.",
            listOf("display_screen" to "screen", "display_glass" to "glass_black", "display_seam" to "titanium", "display_frame" to "titanium", "display_back" to "graphite", "display_spine" to "steel", "display_boards" to "pcb"),
            listOf(1213.0, 361.0, 196.0), listOf(0.0, 0.156, -0.062)),
        g("stand", "Neck", "Trapezoid graphite neck with the amber status bar.",
            "Carries the display 156 mm above the desk and leans slightly back. The light bar on its top edge shows the display is awake; the NIGHT ARRAY lettering is inlaid titanium.",
            listOf("neck" to "graphite", "neck_light" to "amber_led", "neck_badge" to "titanium"), listOf(320.0, 120.0, 70.0), listOf(0.0, 0.036, -0.105)),
        g("base", "Base & charging trays", "Titanium slab with two Qi2 charging pockets.",
            "One 1290 mm titanium slab with a raised rim and a recessed deck. Two pockets hold the keyboard and mouse on soft-touch charging pads; amber marks on the pocket lips show charge state.",
            listOf("base_shell" to "titanium", "tray_pad_kb" to "graphite", "tray_pad_mouse" to "graphite", "base_glow" to "amber_led", "kb_charge_led" to "amber_led", "mouse_charge_led" to "amber_led", "base_feet" to "rubber"),
            listOf(1290.0, 36.0, 300.0), listOf(0.005, 0.0, 0.0)),
        g("dock", "Laptop dock", "Open right-wing cradle: guide the laptop in, its own weight seats it on a sprung USB-C, lift it straight out.",
            "A titanium cradle with a 20 mm slot and chamfered lead-ins. The laptop's own weight seats it on a sprung, self-centring USB-C plug on the slot floor; to undock, lift it straight out. A slim amber light on the front face glows while it is seated.",
            listOf("dock_cradle" to "titanium", "dock_panels" to "oxblood", "dock_led" to "amber_led", "dock_connector" to "steel"),
            listOf(125.0, 120.0, 260.0), listOf(0.7125, 0.0, 0.0)),
        g("laptop", "Laptop", "Generic 14-inch laptop, docked on its side.",
            "A stand-in for your laptop: 304 × 212 × 15 mm, standing lid-closed in the cradle, hinge to the back.",
            listOf("laptop_body" to "laptop_alu"), listOf(15.0, 304.0, 212.0), listOf(0.722, 0.024, 0.0)),
        g("keyboard", "Keyboard", "Low-profile 75 % wireless keyboard.",
            "360 × 120 mm wedge, 9 mm at the front rising to 13 mm. A receiver coil inside charges it whenever it sits in its pocket.",
            listOf("keyboard_body" to "graphite", "keyboard_keys" to "keycap", "keyboard_coil" to "copper"), listOf(360.0, 20.0, 120.0), listOf(-0.09, 0.018, 0.062)),
        g("mouse", "Mouse", "Ambidextrous wireless mouse with an amber tail light.",
            "66 × 118 × 38 mm shell with a rubber wheel. Charges in its pocket through the receiver coil in its floor.",
            listOf("mouse_shell" to "graphite", "mouse_wheel" to "rubber", "mouse_glow" to "amber_led", "mouse_coil" to "copper"), listOf(66.0, 38.0, 118.0), listOf(0.25, 0.018, 0.062)),
        g("deskmat", "Desk mat", "Felt mat for the work position.",
            "820 × 300 mm felt mat that sits 15 cm in front of the base in Work mode.", listOf("deskmat" to "felt"), listOf(820.0, 3.0, 300.0), listOf(0.06, 0.0, 0.385)),
        g("internals", "Compute & charging internals", "Mainboard, cooling, PSU and Qi2 coils inside the base.",
            "The computer lives in the base: a mainboard with a vapor-chamber cooler and slim blower on the left, the power supply on the right, and flat Qi2 coils on ferrite shields under each charging pad.",
            listOf("compute_board" to "pcb", "compute_heatsink" to "steel", "compute_fan" to "graphite", "psu" to "graphite", "qi_coil_kb" to "copper", "qi_coil_mouse" to "copper", "ferrite_kb" to "ferrite", "ferrite_mouse" to "ferrite", "dock_board" to "pcb"),
            listOf(1100.0, 22.0, 240.0), listOf(-0.1, 0.004, 0.0)),
    )

    private val internalParts = setOf("display_spine", "display_boards", "compute_board", "compute_heatsink", "compute_fan", "psu", "qi_coil_kb", "qi_coil_mouse", "ferrite_kb", "ferrite_mouse", "dock_board", "keyboard_coil", "mouse_coil")

    val scene: Scene by lazy {
        val parts = groupDefs.flatMap { g -> g.parts.mapIndexed { i, pid -> Part(pid, g.id, prettyId(pid), g.materials.getOrElse(i) { g.materials.first() }, pid in internalParts, emptyList(), 0.0, 0.0) } }
        // material per part from the definition pairs
        val matOf = mapOf(
            "display_glass" to "glass_black", "display_screen" to "screen", "display_seam" to "titanium", "display_frame" to "titanium", "display_back" to "graphite",
            "display_spine" to "steel", "display_boards" to "pcb",
            "neck" to "graphite", "neck_light" to "amber_led", "neck_badge" to "titanium", "base_shell" to "titanium", "tray_pad_kb" to "graphite",
            "tray_pad_mouse" to "graphite", "base_glow" to "amber_led", "kb_charge_led" to "amber_led", "mouse_charge_led" to "amber_led", "base_feet" to "rubber",
            "dock_cradle" to "titanium", "dock_panels" to "oxblood", "dock_led" to "amber_led", "dock_connector" to "steel",
            "laptop_body" to "laptop_alu", "keyboard_body" to "graphite", "keyboard_keys" to "keycap", "keyboard_coil" to "copper", "mouse_shell" to "graphite",
            "mouse_wheel" to "rubber", "mouse_glow" to "amber_led", "mouse_coil" to "copper", "deskmat" to "felt", "compute_board" to "pcb", "compute_heatsink" to "steel",
            "compute_fan" to "graphite", "psu" to "graphite", "qi_coil_kb" to "copper", "qi_coil_mouse" to "copper", "ferrite_kb" to "ferrite", "ferrite_mouse" to "ferrite", "dock_board" to "pcb",
        )
        val fixedParts = parts.map { it.copy(material = matOf[it.id] ?: it.material) }
        val files = buildList {
            add(CadFile("assembly-step", null, "STEP", "Full assembly", "files/night-array-assembly.step", 0))
            add(CadFile("assembly-glb", null, "GLB", "Full assembly", "model/station.glb", 0))
            groupDefs.forEach { g ->
                add(CadFile("${g.id}-step", g.id, "STEP", g.name, "files/parts/${g.id}.step", 0))
                add(CadFile("${g.id}-stl", g.id, "STL", g.name, "files/parts/${g.id}.stl", 0))
                add(CadFile("${g.id}-svg", g.id, "SVG", g.name, "files/drawings/${g.id}.svg", 0))
                add(CadFile("${g.id}-dxf", g.id, "DXF", g.name, "files/drawings/${g.id}-top.dxf", 0))
            }
        }
        val poses = JSONObject("""{"stow":{"deskmat":{"hidden":true}},"work":{"keyboard":{"t":[0,-0.015,0.298]},"mouse":{"t":[0.04,-0.015,0.298]}},"standalone":{"keyboard":{"t":[0,-0.015,0.298]},"mouse":{"t":[0.04,-0.015,0.298]},"laptop":{"hidden":true}}}""")
        Scene(
            "Night Array — Work & Stow", JSONObject(), listOf(-0.640, 0.0, -0.15), listOf(0.775, 0.520, 0.15), MATERIAL_LABELS,
            groupDefs, fixedParts, files, groupDefs.associate { it.id to "drawings/${it.id}.png" }, emptyList(), ScreenInfo.DEFAULT,
            DOCK_STEPS.map { (id, title, caption) -> DockStep(id, title, caption) },
            poses, fromFile = false,
        )
    }
}

object Repo {
    @Volatile private var scene: Scene? = null
    fun scene(ctx: Context): Scene = scene ?: synchronized(this) {
        scene ?: load(ctx).also { scene = it }
    }

    fun load(ctx: Context): Scene = try {
        val text = ctx.assets.open("model/scene.json").bufferedReader().use { it.readText() }
        SceneParser.parse(text)
    } catch (e: Exception) {
        if (e !is java.io.FileNotFoundException) android.util.Log.w("NightArray", "model/scene.json unreadable; using the built-in envelope", e)
        Fallback.scene
    }

    /** For tests. */
    fun reset() { scene = null; AssetIndex.reset() }
}

/** Lists asset directories once so existence checks are cheap and never throw. */
object AssetIndex {
    private val listed = HashMap<String, Set<String>>()
    @Synchronized fun exists(ctx: Context, path: String): Boolean {
        val dir = path.substringBeforeLast('/', "")
        val name = path.substringAfterLast('/')
        val names = listed.getOrPut(dir) { runCatching { ctx.assets.list(dir)?.toSet() }.getOrNull() ?: emptySet() }
        return name in names
    }
    @Synchronized fun reset() = listed.clear()
}

/** Size of an asset in bytes: scene.json's number when present, else measured (cached). */
object AssetSize {
    private val sizes = java.util.concurrent.ConcurrentHashMap<String, Long>()
    fun of(ctx: Context, f: CadFile): Long {
        if (f.bytes > 0) return f.bytes
        sizes[f.path]?.let { return it }
        val n = runCatching { ctx.assets.openFd(f.path).use { it.length } }.getOrNull()
            ?: runCatching {
                ctx.assets.open(f.path).use { s -> var total = 0L; val buf = ByteArray(64 * 1024); while (true) { val r = s.read(buf); if (r < 0) break; total += r }; total }
            }.getOrNull() ?: -1L
        sizes[f.path] = n
        return n
    }
}

// ---------- formatting ----------
fun fmtBytes(b: Long): String = when {
    b < 0 -> "—"
    b < 1024 -> "$b B"
    b < 1024 * 1024 -> "${(b / 1024.0).roundToInt()} KB"
    else -> String.format(Locale.US, "%.1f MB", b / (1024.0 * 1024.0))
}

fun fmtMass(g: Double): String = when {
    g <= 0 -> "—"
    g < 1 -> "< 1 g"
    g < 1000 -> "${g.roundToInt()} g"
    g < 10_000 -> String.format(Locale.US, "%.2f kg", g / 1000.0)
    else -> String.format(Locale.US, "%.1f kg", g / 1000.0) // concept estimates: 0.1 kg is precision enough at this size
}

/** Thin-space grouped millimetres, e.g. 1 474. */
fun fmtMm(mm: Double): String {
    val n = mm.roundToInt()
    val s = n.toString()
    return if (n >= 1000) s.dropLast(3) + " " + s.takeLast(3) else s
}

fun fmtBox(b: List<Double>): String = if (b.size < 3 || b.all { it <= 0 }) "—" else "${fmtMm(b[0])} × ${fmtMm(b[1])} × ${fmtMm(b[2])} mm"

fun mimeOf(format: String, path: String = ""): String = when (format.uppercase(Locale.ROOT)) {
    "STEP", "STP" -> "model/step"
    "STL" -> "model/stl"
    "GLB" -> "model/gltf-binary"
    "SVG" -> "image/svg+xml"
    "DXF" -> "image/vnd.dxf"
    "PNG" -> "image/png"
    "JSON" -> "application/json"
    else -> when (path.substringAfterLast('.').lowercase(Locale.ROOT)) { "step", "stp" -> "model/step"; "stl" -> "model/stl"; "glb" -> "model/gltf-binary"; "svg" -> "image/svg+xml"; "dxf" -> "image/vnd.dxf"; else -> "application/octet-stream" }
}

val FORMAT_NOTES = mapOf(
    "STEP" to "B-rep solids for any CAD tool",
    "STL" to "Mesh in mm, ready to slice",
    "GLB" to "glTF binary, one node per part",
    "SVG" to "Drawing sheet, 3 views + iso",
    "DXF" to "2D top-view outline",
)
