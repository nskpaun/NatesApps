package com.natesapps.nightarray

/** All words in the app live here: concrete numbers from the SPEC envelope, no filler. */

data class ModeInfo(val id: String, val title: String, val sub: String, val body: String, val still: String, val camera: String)

val MODES = listOf(
    ModeInfo("work", "Work", "Active, open desk",
        "Keyboard and mouse sit 15 cm in front of the base on a felt mat. The deck behind them stays empty; the display floats above it.",
        "hero-work.jpg", "hero"),
    ModeInfo("stow", "Stow & Charge", "Put away, power up",
        "Push both into their pockets and they start charging. Two amber marks on the pocket lips say so, then fade when they're full.",
        "hero-stow.jpg", "trays"),
    ModeInfo("standalone", "Standalone", "Compute stays in the base",
        "Lift the laptop out and leave. The mainboard in the base keeps driving the display, with your session still open.",
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
        "superwide", "01", "Display", "A horizon, not a monitor", "Superwide 4:1 panel on an 1800R curve",
        "One continuous 4:1 panel, curved on an 1800 mm radius, so the ends wrap toward you instead of falling away.",
        listOf(
            "The active area is 1400 × 350 mm: wider than two 27-inch screens side by side, with no seam down the middle and no second stand. At 7680 × 1920 pixels that is about 139 pixels per inch, sharp enough for small type at a normal sitting distance.",
            "1800R means the glass follows a circle 1.8 m in radius. Straight on it reads almost flat; at the far ends it has turned about 14 cm toward you, which keeps the corners at a readable angle without moving your head.",
            "Three full-height documents fit side by side. So does a timeline that never needs to scroll.",
        ),
        listOf(
            StorySpec("Class", "57-inch, 4:1"), StorySpec("Resolution", "7680 × 1920"), StorySpec("Curvature", "1800R"),
            StorySpec("Active area", "1400 × 350 mm"), StorySpec("Density", "≈ 139 ppi"), StorySpec("Edge wrap", "≈ 14 cm toward you"),
        ),
        listOf(StoryStill("display.jpg", "Cover glass runs edge to edge; the titanium rim is 3 mm."), StoryStill("hero-work.jpg", "Work mode, amber at 70 %.")),
        Preset(mode = "work", style = "studio", camera = "display", explode = 0f),
    ),
    Story(
        "work-stow", "02", "Modes", "Work & Stow", "Two states, one footprint",
        "Pull the keyboard and mouse forward to work. Push them back into the base and the desk is empty.",
        listOf(
            "In Work, the keyboard sits on a felt mat 15 cm in front of the base: close enough that the display is at arm's length, far enough that your wrists rest on the desk instead of the slab.",
            "In Stow, both slide into pockets cut into the titanium deck. The keyboard pocket is 376 × 136 mm, the mouse pocket 82 × 134 mm; each leaves 8 mm of play all round, so you can drop things in without looking, and lift them out with two fingers.",
            "Nothing needs a cable and nothing needs a drawer. Tidying up is the same motion as plugging in.",
        ),
        listOf(
            StorySpec("Work offset", "150 mm in front of the base"), StorySpec("Keyboard pocket", "376 × 136 mm"), StorySpec("Mouse pocket", "82 × 134 mm"),
            StorySpec("Pocket floor", "14 mm below the deck"), StorySpec("Desk mat", "820 × 300 mm felt"),
        ),
        listOf(StoryStill("hero-work.jpg", "Work: active, open desk."), StoryStill("hero-stow.jpg", "Stow & Charge: put away, power up.")),
        Preset(mode = "stow", style = "studio", camera = "hero", explode = 0f),
    ),
    Story(
        "dock", "03", "Dock", "The dock", "A vertical cradle on the right wing",
        "Your laptop stands on its edge in the right wing, lid closed, plugged in by its own weight.",
        listOf(
            "The cradle is a titanium wing with a 20 mm slot and chamfered lead-ins. Lower the laptop and its USB-C port meets a sprung connector on the slot floor; the chamfers do the aiming, not you.",
            "To take it with you, press the latch on the cradle's front face. It travels 3 mm, the amber strip on top goes dark, the connector lets go, and the laptop lifts straight out.",
            "The outer face wears brushed oxblood panels: the one deep colour on the station, on the side your hand goes to.",
        ),
        listOf(
            StorySpec("Position", "Right outer wing"), StorySpec("Slot", "20 × 224 mm, chamfered"), StorySpec("Connector", "Sprung USB-C on the slot floor"),
            StorySpec("Release", "Press latch, 3 mm travel"), StorySpec("Footprint", "125 × 260 mm"),
        ),
        listOf(StoryStill("dock-align.jpg", "1 · Align: guide into the open cradle."), StoryStill("dock-lower.jpg", "2 · Lower: seat the laptop onto the connector."), StoryStill("dock-release.jpg", "3 · Press-release & lift.")),
        Preset(mode = "stow", style = "studio", camera = "dock", explode = 0f, dock = "play"), liveLabel = "Play the sequence live",
    ),
    Story(
        "charge", "04", "Charging", "Charge in place", "Qi2 coils under the pads",
        "Set it down where it lives and it charges. No cable, no puck, no lining anything up.",
        listOf(
            "Under each soft-touch pad sits a flat Qi2 coil on a ferrite shield: two under the keyboard, one under the mouse. The pocket walls place each device within a few millimetres of its coil, which is all inductive charging asks for.",
            "The receiver coils live inside the keyboard and mouse floors, directly above the transmitters when stowed. The pad between them is 2 mm thick.",
            "A thin amber mark on each pocket's front lip glows while charging and fades out when the battery is full.",
        ),
        listOf(
            StorySpec("Keyboard", "2 Qi2 coils at x = −170 / −10 mm"), StorySpec("Mouse", "1 Qi2 coil"), StorySpec("Shielding", "Ferrite plate under each coil"),
            StorySpec("Pad", "2 mm soft-touch graphite"), StorySpec("Indicators", "30 mm and 16 mm amber marks"),
        ),
        listOf(StoryStill("trays.jpg", "Both pockets, devices stowed."), StoryStill("xray.jpg", "X-ray: coils and ferrite under the pads.")),
        Preset(mode = "stow", style = "xray", camera = "trays", explode = 0f),
    ),
    Story(
        "compute", "05", "Compute", "Compute stays in the base", "A computer, not a monitor waiting for one",
        "The Array runs on its own. Dock a laptop and it becomes a guest; lift it out and the base keeps working.",
        listOf(
            "A full mainboard with a vapor-chamber cooler and a slim blower lives under the left half of the 36 mm base. The power supply sits on the right, beside the mouse pocket. One mains cable feeds everything.",
            "With the laptop docked you can drive the display from either machine. Without it, the base keeps your session, your files and your OS on screen.",
            "Air comes in under the front edge and leaves through the rear I/O cut-outs on the left, away from your hands.",
        ),
        listOf(
            StorySpec("Mainboard", "300 × 230 mm, base left"), StorySpec("Cooling", "Vapor chamber + slim blower"), StorySpec("Power", "Internal PSU, one cable"),
            StorySpec("I/O", "Rear face, left side"), StorySpec("Base height", "36 mm"),
        ),
        listOf(StoryStill("hero-standalone.jpg", "Standalone: laptop gone, display still running."), StoryStill("section.jpg", "Section through the base."), StoryStill("exploded.jpg", "Exploded: every part, every layer.")),
        Preset(mode = "standalone", style = "xray", camera = "hero", explode = 0.35f),
    ),
    Story(
        "amber", "06", "Light", "Light that informs", "Amber only where it means something",
        "Five lights, five jobs. None of them blink, none of them change colour.",
        listOf(
            "The under-glow along the front edge marks the edge of the desk in a dark room. The bar on the neck says the display is awake. The marks on the pocket lips say charging. The strip on the dock latch says the laptop is locked in. The tail light on the mouse tells you where it is.",
            "One slider sets all of them, from off to a low warm glow. The colour is a single amber that sits below the screen's white, so it never competes with what you're reading.",
        ),
        listOf(
            StorySpec("Under-glow", "1120 mm strip, front edge"), StorySpec("Neck bar", "150 mm, display awake"), StorySpec("Pocket marks", "Charging state"),
            StorySpec("Latch strip", "Laptop locked"), StorySpec("Colour", "Amber #F2A04A, dimmable"),
        ),
        listOf(StoryStill("hero-work.jpg", "Amber at 70 %."), StoryStill("amber-off.jpg", "Amber off.")),
        Preset(mode = "stow", style = "studio", amber = 1f, camera = "trays"),
    ),
    Story(
        "materials", "07", "Materials", "Materials & finishes", "Titanium, graphite, oxblood",
        "Three materials, chosen to look better at night than in a showroom.",
        listOf(
            "The base, cradle, display rim and neck lettering are titanium: stiff enough that a 1.3 m slab doesn't flex under your palms, warm enough in tone to sit next to wood.",
            "The surfaces you touch most are charcoal graphite: the pads, the neck, the back of the display. The dock's side panels are brushed oxblood.",
            "Choose the metal: Neutral Titanium, Charcoal Graphite or Brushed Oxblood. The rest of the palette stays put.",
        ),
        listOf(
            StorySpec("Primary metal", "Titanium, 4.43 g/cm³"), StorySpec("Soft surfaces", "Charcoal graphite"), StorySpec("Accent", "Brushed oxblood panels"),
            StorySpec("Glass", "Black cover glass"), StorySpec("Finishes", "Titanium · Graphite · Oxblood"),
        ),
        listOf(StoryStill("finish-titanium.jpg", "Neutral Titanium."), StoryStill("finish-graphite.jpg", "Charcoal Graphite."), StoryStill("finish-oxblood.jpg", "Brushed Oxblood.")),
        Preset(mode = "stow", style = "studio", finish = "graphite", camera = "hero"), liveLabel = "Try the finishes live",
    ),
    Story(
        "cablefree", "08", "Desk", "A cable-free desk", "One cable leaves the back",
        "From your chair, nothing on the desk is plugged into anything.",
        listOf(
            "Mains power enters at the rear and is shared inside the base by the display, the computer, the dock and both chargers. Ports are cut into the back face on the left, out of sight.",
            "The keyboard and mouse are wireless and charge in their pockets. The laptop connects through the floor of the cradle. The only cable you'll ever see runs from the back of the base to the wall.",
        ),
        listOf(
            StorySpec("Cables on the desk", "1 (power, at the rear)"), StorySpec("Ports", "Rear face, left side"), StorySpec("Peripherals", "Wireless, charged in place"),
            StorySpec("Laptop", "Docks without a cable"),
        ),
        listOf(StoryStill("blueprint.jpg", "Blueprint: every edge, nothing else."), StoryStill("cad.jpg", "CAD view of the assembly.")),
        Preset(mode = "stow", style = "blueprint", camera = "back"),
    ),
)

data class Principle(val title: String, val body: String)

val PRINCIPLES = listOf(
    Principle("One object", "Display, dock, chargers and computer are one piece of furniture, not a cluster of gadgets sharing a desk."),
    Principle("Put it away, power it up", "The tidy motion and the charging motion are the same motion."),
    Principle("Light means something", "Amber appears only where it reports a state. It never blinks."),
    Principle("The slot does the aiming", "Chamfers, pockets and stops guide every move, so you don't have to look."),
    Principle("Your hardware. Your OS.", "USB-C, Qi2 and standard display links. Bring the laptop and the operating system you already use."),
    Principle("Quiet at night", "Matte surfaces, warm light, no glare, and a blower you have to listen for."),
)

val FINISHES = listOf("titanium" to "Neutral Titanium", "graphite" to "Charcoal Graphite", "oxblood" to "Brushed Oxblood")
val STYLES = listOf("studio" to "Studio", "cad" to "CAD", "xray" to "X-ray", "blueprint" to "Blueprint")
val MODE_TABS = listOf("work" to "Work", "stow" to "Stow", "standalone" to "Standalone")
val CAMERAS = listOf("hero" to "Hero", "front" to "Front", "top" to "Top", "side" to "Side", "back" to "Back", "dock" to "Dock", "trays" to "Trays", "display" to "Display")

val NIGHT_LINES = listOf(
    "Compute stays in the base.",
    "Put it away. It powers up.",
    "One cable leaves the back.",
    "1800R · 7680 × 1920.",
    "Light only where it means something.",
    "Your hardware. Your OS.",
)

/** Dock UI steps: release and lift are both part of step 3. */
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
