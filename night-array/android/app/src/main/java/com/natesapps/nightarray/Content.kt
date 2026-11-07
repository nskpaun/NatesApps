package com.natesapps.nightarray

import java.util.Locale
import kotlin.math.cos
import kotlin.math.roundToInt

/** All words in the app live here: concrete numbers from the SPEC envelope (or scene.json), no filler. */

data class ModeInfo(val id: String, val title: String, val sub: String, val body: String, val still: String, val camera: String)

val MODES = listOf(
    ModeInfo("work", "Work", "Active, open desk",
        "Keyboard and mouse come forward onto a felt mat, 15 cm clear of the base. The deck behind them stays empty and both panels sit at arm's length.",
        "hero-work.jpg", "hero"),
    ModeInfo("stow", "Stow & Charge", "Put away, power up",
        "Slide both into their pockets and they start charging. Two amber marks on the pocket lips say so, and fade out when the batteries are full.",
        "hero-stow.jpg", "trays"),
    ModeInfo("standalone", "Standalone", "Compute stays in the base",
        "Lift the laptop out and leave with it. The computer in the base keeps both panels running, session and all.",
        "hero-standalone.jpg", "hero"),
)

data class StoryStill(val name: String, val caption: String)
data class StorySpec(val label: String, val value: String)

data class Story(
    val id: String, val number: String, val kicker: String, val title: String, val line: String, val lede: String,
    val body: List<String>, val specs: List<StorySpec>, val stills: List<StoryStill>, val preset: Preset, val liveLabel: String = "See it live",
)

val STORIES = listOf(
    Story(
        "dual", "01", "Display", "Two panels, one horizon", "Two mainstream QHD panels in one titanium shroud",
        "Inside the shroud sit two ordinary 27-inch QHD monitors with their plastic housings taken off. Side by side they draw 5120 × 1440: the pixels of a 49-inch super-ultrawide, for the price of two good mainstream screens.",
        listOf(
            "Each panel is a 2560 × 1440 IPS module, the size and resolution the industry builds by the million, which is exactly why it is cheap and why it is good. Together they give almost 1.2 m of active width at 109 pixels per inch: crisp text at arm's length.",
            "Each panel is toed in 10° about the seam, which brings its outer edge about 106 mm toward you. Both halves face you squarely, so you turn your eyes, not your head.",
            "Between the two active areas runs a 14 mm seam. We don't disguise it. A 4 mm titanium mullion covers the joint and becomes the station's centre line, and most work splits there anyway: code on the left, preview on the right; the call on one side, your notes on the other.",
            "Your OS already knows how to drive two displays. Snap a window to each half, or span one across both. And if a panel gives out in year five, the replacement is a standard 27-inch module on four VESA screws, not a service ticket.",
        ),
        emptyList(), // built from scene.json's screen block, see storySpecs()
        listOf(StoryStill("display.jpg", "The honest seam: a 4 mm titanium mullion over the 14 mm joint."), StoryStill("hero-work.jpg", "One 5120 × 1440 canvas, split exactly where your OS splits it.")),
        Preset(mode = "work", style = "studio", camera = "display", explode = 0f),
        liveLabel = "See the panels live",
    ),
    Story(
        "work-stow", "02", "Modes", "Work & Stow", "Two states, one footprint",
        "Pull the keyboard and mouse forward to work. Push them back into the base when you're done, and the desk is clear.",
        listOf(
            "In Work, the keyboard sits on a felt mat 15 cm in front of the base: close enough that the panels stay at arm's length, far enough that your wrists rest on the desk instead of the titanium.",
            "In Stow, both drop into pockets cut into the deck. The keyboard pocket is 376 × 136 mm and the mouse pocket 82 × 134 mm, with a few millimetres of play all round, so they go in without looking and come out with two fingers.",
            "There is no drawer and no cable to put away. Tidying up is the same motion as plugging in.",
        ),
        listOf(
            StorySpec("Work offset", "150 mm in front of the base"), StorySpec("Keyboard pocket", "376 × 136 mm"), StorySpec("Mouse pocket", "82 × 134 mm"),
            StorySpec("Pocket depth", "14 mm below the deck"), StorySpec("Desk mat", "820 × 300 mm felt"),
        ),
        listOf(StoryStill("hero-work.jpg", "Work: active, open desk."), StoryStill("hero-stow.jpg", "Stow & Charge: put away, power up.")),
        Preset(mode = "stow", style = "studio", camera = "hero", explode = 0f),
        liveLabel = "Switch modes live",
    ),
    Story(
        "dock", "03", "Dock", "The dock", "A vertical cradle on the right wing",
        "Your laptop stands on its edge in the right wing, lid closed, connected by its own weight.",
        listOf(
            "The cradle is a titanium wing with a 20 mm slot and chamfered lead-ins. Lower the laptop and its USB-C port meets a sprung connector on the slot floor. The chamfers do the aiming, not your eyes.",
            "To leave, press the latch on the cradle's front face. It travels 3 mm, the amber strip on top goes dark, the connector lets go, and the laptop lifts straight out.",
            "The outer faces wear brushed oxblood: the station's one deep colour, on the side your hand reaches for.",
        ),
        listOf(
            StorySpec("Position", "Right outer wing"), StorySpec("Slot", "20 × 224 mm, 4 mm lead-in chamfers"), StorySpec("Connector", "Sprung USB-C on the slot floor"),
            StorySpec("Release", "Press latch, 3 mm travel"), StorySpec("Laptop", "Any slim laptop up to 20 mm thick, on its edge"), StorySpec("Footprint", "125 × 260 mm"),
        ),
        listOf(StoryStill("dock-align.jpg", "1 · Align: guide into the open cradle."), StoryStill("dock-lower.jpg", "2 · Lower: seat the laptop onto the connector."), StoryStill("dock-release.jpg", "3 · Press-release & lift.")),
        Preset(mode = "stow", style = "studio", camera = "dock", explode = 0f, dock = "play"), liveLabel = "Play the sequence live",
    ),
    Story(
        "charge", "04", "Charging", "Charge in place", "Qi2 coils under the pads",
        "Set it down where it lives and it charges. No cable, no puck, nothing to line up.",
        listOf(
            "Under each soft-touch pad is a flat Qi2 coil on a ferrite shield: two under the keyboard, one under the mouse. The pocket walls place each device within a few millimetres of its coil, which is all inductive charging asks for.",
            "Titanium would block the field, so the pocket floors are cut with round non-metallic windows over every coil. A faint ring debossed in each pad marks the spot, though the walls already put you there.",
            "The receiver coils sit in the floors of the keyboard and mouse, directly over the transmitters when stowed, with 2 mm of pad between them.",
            "A thin amber mark on each pocket's front lip glows while charging and fades out when the battery is full.",
        ),
        listOf(
            StorySpec("Standard", "Qi2"), StorySpec("Keyboard", "2 coils, at x = −170 and −10 mm"), StorySpec("Mouse", "1 coil"),
            StorySpec("Shielding", "Ferrite plate under every coil"), StorySpec("Pad", "2 mm soft-touch graphite"), StorySpec("Indicators", "30 mm and 16 mm amber marks"),
        ),
        listOf(StoryStill("trays.jpg", "Both pockets, devices stowed."), StoryStill("xray.jpg", "X-ray: coils and ferrite under the pads.")),
        Preset(mode = "stow", style = "xray", camera = "trays", explode = 0f),
    ),
    Story(
        "compute", "05", "Compute", "Compute stays in the base", "A computer, not a monitor waiting for one",
        "The Array runs on its own. Dock a laptop and it's a guest; lift it out and the base keeps working.",
        listOf(
            "A full mainboard with a vapor-chamber cooler and a slim blower lives under the left half of the 36 mm base. The power supply sits on the right, beside the mouse pocket. One mains cable feeds everything.",
            "Each 27-inch panel keeps its own scaler board, mounted on the steel spine behind it. To the computer they are simply two monitors on two standard display links: no custom display electronics, nothing proprietary to fail.",
            "Air comes in under the front edge and leaves through the rear cut-outs on the left, away from your hands.",
        ),
        listOf(
            StorySpec("Mainboard", "300 × 230 mm, base left"), StorySpec("Cooling", "Vapor chamber + slim blower"), StorySpec("Display links", "2, one per panel"),
            StorySpec("Power", "Internal PSU, one cable"), StorySpec("I/O", "Rear face, left side"), StorySpec("Base height", "36 mm"),
        ),
        listOf(StoryStill("hero-standalone.jpg", "Standalone: laptop gone, both panels still running."), StoryStill("section.jpg", "Section through the base."), StoryStill("exploded.jpg", "Exploded: every part, every layer.")),
        Preset(mode = "standalone", style = "xray", camera = "hero", explode = 0.35f),
    ),
    Story(
        "amber", "06", "Light", "Light that informs", "Amber only where it means something",
        "Five lights, five jobs. None of them blinks, none of them changes colour.",
        listOf(
            "The under-glow along the front edge finds the desk in a dark room. The bar on the neck says the panels are awake. The marks on the pocket lips say charging. The strip on the dock latch says the laptop is locked in. The tail light on the mouse tells you where you left it.",
            "One slider sets all five, from off to a low warm glow. The amber sits well below the screens' white, so it never competes with what you're reading.",
        ),
        listOf(
            StorySpec("Under-glow", "1120 mm strip, front edge"), StorySpec("Neck bar", "150 mm, panels awake"), StorySpec("Pocket marks", "Charging; fade when full"),
            StorySpec("Latch strip", "Laptop locked in"), StorySpec("Mouse", "Tail light"), StorySpec("Colour", "Amber #F2A04A, dims to off"),
        ),
        listOf(StoryStill("hero-work.jpg", "Amber at 70 %."), StoryStill("amber-off.jpg", "Amber off.")),
        Preset(mode = "stow", style = "studio", amber = 1f, camera = "trays"), liveLabel = "Set the light live",
    ),
    Story(
        "materials", "07", "Materials", "Materials & finishes", "Titanium, graphite, oxblood",
        "Three materials, chosen to look better at night than in a showroom.",
        listOf(
            "The base, cradle, shroud rim, seam mullion and neck lettering are titanium: stiff enough that a 1.3 m slab doesn't flex under your palms, warm enough in tone to sit beside wood.",
            "The surfaces you touch or look past most are charcoal graphite: the pads, the neck, the back of the shroud. The dock's outer panels are brushed oxblood.",
            "Pick the metal: Neutral Titanium, Charcoal Graphite or Brushed Oxblood. The rest of the palette holds still.",
        ),
        listOf(
            StorySpec("Primary metal", "Titanium, 4.43 g/cm³"), StorySpec("Soft surfaces", "Charcoal graphite"), StorySpec("Accent", "Brushed oxblood panels"),
            StorySpec("Panel faces", "Black glass"), StorySpec("Finishes", "Titanium · Graphite · Oxblood"),
        ),
        listOf(StoryStill("finish-titanium.jpg", "Neutral Titanium."), StoryStill("finish-graphite.jpg", "Charcoal Graphite."), StoryStill("finish-oxblood.jpg", "Brushed Oxblood.")),
        Preset(mode = "stow", style = "studio", finish = "graphite", camera = "hero"), liveLabel = "Try the finishes live",
    ),
    Story(
        "cablefree", "08", "Desk", "A cable-free desk", "One cable leaves the back",
        "From your chair, nothing on the desk is plugged into anything.",
        listOf(
            "Mains power enters at the rear and is shared inside the base by the two panels, the computer, the dock and both chargers. The ports are cut into the back face on the left, out of sight.",
            "The keyboard and mouse are wireless and charge in their pockets. The laptop connects through the floor of the cradle. The only cable you'll ever see runs from the back of the base to the wall.",
        ),
        listOf(
            StorySpec("Cables on the desk", "1, power, at the rear"), StorySpec("Ports", "Rear face, left side"), StorySpec("Peripherals", "Wireless, charged in place"),
            StorySpec("Laptop", "Docks without a cable"),
        ),
        listOf(StoryStill("blueprint.jpg", "Blueprint: every edge, nothing else."), StoryStill("cad.jpg", "CAD view of the assembly.")),
        Preset(mode = "stow", style = "blueprint", camera = "back"),
    ),
)

fun story(id: String): Story? = STORIES.firstOrNull { it.id == id }

/**
 * Spec rows for a story. Where scene.json carries the number (screen block, params.py), the row is built from it so
 * the story always matches the CAD; otherwise the SPEC envelope values written above stand.
 */
fun storySpecs(s: Story, scene: Scene): List<StorySpec> = when (s.id) {
    "dual" -> dualSpecs(scene)
    "dock" -> {
        val slotW = scene.span("dock.slot.x"); val slotL = scene.span("dock.slot.z")
        val lead = scene.num("dock.slot.lead_in"); val travel = scene.num("dock.latch.travel")
        val w = scene.span("dock.x"); val d = scene.span("dock.z")
        s.specs.map { r ->
            when (r.label) {
                "Slot" -> if (slotW != null && slotL != null) r.copy(value = "${fmtNum(slotW)} × ${fmtNum(slotL)} mm, ${fmtNum(lead ?: 4.0)} mm lead-in chamfers") else r
                "Release" -> if (travel != null) r.copy(value = "Press latch, ${fmtNum(travel)} mm travel") else r
                "Laptop" -> if (slotW != null) r.copy(value = "Any slim laptop up to ${fmtNum(slotW)} mm thick, on its edge") else r
                "Footprint" -> if (w != null && d != null) r.copy(value = "${fmtNum(w)} × ${fmtNum(d)} mm") else r
                else -> r
            }
        }
    }
    "work-stow" -> {
        val kb = scene.nums("base.kb_pocket.size"); val ms = scene.nums("base.mouse_pocket.size")
        val deck = scene.num("base.deck_y"); val floor = scene.num("base.kb_pocket.floor_y"); val mat = scene.nums("deskmat.size")
        val gap = footprint(scene).workGapMm
        s.specs.map { r ->
            when (r.label) {
                "Work offset" -> r.copy(value = "${fmtNum(gap)} mm in front of the base")
                "Keyboard pocket" -> kb?.takeIf { it.size >= 2 }?.let { r.copy(value = "${fmtNum(it[0])} × ${fmtNum(it[1])} mm") } ?: r
                "Mouse pocket" -> ms?.takeIf { it.size >= 2 }?.let { r.copy(value = "${fmtNum(it[0])} × ${fmtNum(it[1])} mm") } ?: r
                "Pocket depth" -> if (deck != null && floor != null) r.copy(value = "${fmtNum(deck - floor)} mm below the deck") else r
                "Desk mat" -> mat?.takeIf { it.size >= 3 }?.let { r.copy(value = "${fmtNum(it[0])} × ${fmtNum(it[2])} mm felt") } ?: r
                else -> r
            }
        }
    }
    "charge" -> {
        val kbx = scene.nums("internals.qi_coils_kb_x"); val win = scene.num("base.coil_window_d"); val pad = scene.num("base.pad_t")
        s.specs.map { r ->
            when (r.label) {
                "Keyboard" -> kbx?.let { r.copy(value = "${it.size} coils, at x = ${it.joinToString(" and ") { v -> fmtNum(v).replace("-", "−") }} mm") } ?: r
                "Shielding" -> if (win != null) r.copy(value = "Ferrite under every coil; ${fmtNum(win)} mm windows in the titanium") else r
                "Pad" -> if (pad != null) r.copy(value = "${fmtNum(pad)} mm soft-touch graphite") else r
                else -> r
            }
        }
    }
    else -> s.specs
}

private fun dualSpecs(scene: Scene): List<StorySpec> {
    val sc = scene.screen
    return listOf(
        StorySpec("Panels", "${sc.panels} × ${fmtNum(sc.panelInch)}″ QHD IPS, off the shelf"),
        StorySpec("Canvas", "${sc.canvasW} × ${sc.canvasH}"),
        StorySpec("Each panel", "${sc.resEach[0]} × ${sc.resEach[1]}, ${fmtNum(sc.activeMm[0])} × ${fmtNum(sc.activeMm[1])} mm"),
        StorySpec("Density", "${sc.ppi.roundToInt()} ppi"),
        StorySpec("Toe-in", "${fmtNum(sc.toeInDeg)}° per panel"),
        StorySpec("Seam", "${fmtNum(sc.seamMm)} mm, 4 mm titanium mullion"),
        StorySpec("Width", "≈ ${fmtMm(scene.displayWidthMm)} mm across"),
        StorySpec("Mount", "VESA 100 per panel, steel spine"),
    )
}

/** 596.7 → "596.7", 27.0 → "27". */
fun fmtNum(d: Double): String = if (d == Math.floor(d)) d.toLong().toString() else String.format(Locale.US, "%.1f", d)

data class Principle(val title: String, val body: String)

val PRINCIPLES = listOf(
    Principle("One object", "Display, dock, chargers and computer are one piece of furniture, not a cluster of gadgets sharing a desk."),
    Principle("Put it away, power it up", "Tidying and charging are the same motion."),
    Principle("Honest parts", "Two off-the-shelf 27-inch panels, VESA 100, USB-C, Qi2. Anything that wears out is something you can buy."),
    Principle("Show the seam", "Where two things meet, say so. The titanium mullion is the station's centre line, not a flaw to paper over."),
    Principle("Light means something", "Amber appears only where it reports a state. It never blinks."),
    Principle("The slot does the aiming", "Chamfers, pockets and stops guide every move, so you don't have to look."),
    Principle("Your hardware. Your OS.", "Bring the laptop and the operating system you already use. Nothing here needs an app or an account."),
)

const val BOARD_NOTE = "The first board drew a single curved ultrawide. We kept the base, the trays, the dock, the light and the materials, " +
    "and swapped the display for two mainstream 27-inch QHD panels in one titanium shroud: the same 5120 × 1440 pixels for a fraction of the price, " +
    "and a dead panel is a cheap swap. The seam is the trade, so we made it a feature."

val FINISHES = listOf("titanium" to "Neutral Titanium", "graphite" to "Charcoal Graphite", "oxblood" to "Brushed Oxblood")
val STYLES = listOf("studio" to "Studio", "cad" to "CAD", "xray" to "X-ray", "blueprint" to "Blueprint")
val MODE_TABS = listOf("work" to "Work", "stow" to "Stow", "standalone" to "Standalone")
val CAMERAS = listOf("hero" to "Hero", "front" to "Front", "display" to "Display", "dock" to "Dock", "trays" to "Trays", "top" to "Top", "side" to "Side", "back" to "Back")
val QUALITIES = listOf("high" to "High", "balanced" to "Balanced", "battery" to "Battery")

val NIGHT_LINES = listOf(
    "Two panels. One horizon.",
    "Compute stays in the base.",
    "Put it away. It powers up.",
    "5120 × 1440 · two 27-inch QHD.",
    "The seam is part of the deal.",
    "One cable leaves the back.",
    "Light only where it means something.",
    "Your hardware. Your OS.",
)

/** Dock UI steps: release and lift are both part of step 3, as on the board. */
data class DockUiStep(val n: Int, val id: String, val title: String, val caption: String, val still: String)

fun dockUiSteps(scene: Scene): List<DockUiStep> {
    fun st(id: String) = scene.dockSteps.firstOrNull { it.step == id }
    return listOf(
        DockUiStep(1, "align", st("align")?.title ?: "Align", st("align")?.caption ?: "Guide into the open cradle", "dock-align.jpg"),
        DockUiStep(2, "lower", st("lower")?.title ?: "Lower", st("lower")?.caption ?: "Seat the laptop onto the connector", "dock-lower.jpg"),
        DockUiStep(3, "release", st("release")?.title ?: "Press-release & lift", st("release")?.caption ?: "Press to release, then lift out", "dock-release.jpg"),
    )
}

fun dockStepNumber(step: String?): Int = when (step) { "align" -> 1; "lower" -> 2; "release", "lift" -> 3; else -> 0 }

/** Chord width of the two toed-in facets, from the screen block (used when scene.json has no display bbox). */
fun chordFromScreen(sc: ScreenInfo): Double {
    val facet = sc.seamMm / 2 + sc.activeMm[0] + 9.0 + 3.0 // seam half + active + outer border + shroud rim
    return 2 * facet * cos(Math.toRadians(sc.toeInDeg))
}
