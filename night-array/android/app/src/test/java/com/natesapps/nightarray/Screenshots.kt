package com.natesapps.nightarray

import android.graphics.Bitmap
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.core.app.ApplicationProvider
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/** Renders key screens to PNGs for the README: gradle testDebugUnitTest --tests '*Screenshots*' → build/screenshots */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w393dp-h852dp-xhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class Screenshots {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
    private val out = File("build/screenshots").apply { mkdirs() }
    private lateinit var app: AppState

    @Before fun setup() { Img.synchronous = true; Repo.reset() }

    private fun tick(ms: Long = 1500) {
        repeat((ms / 250).toInt()) { rule.mainClock.advanceTimeBy(250); shadowOf(Looper.getMainLooper()).idle(); rule.waitForIdle() }
    }

    private fun shoot(name: String, route: String, prep: (AppState) -> Unit = {}, extra: () -> Unit = {}) {
        app = AppState(ApplicationProvider.getApplicationContext())
        if (route in listOf("studio", "files", "specs")) app.nav.tab(route) else if (route != "explore") app.nav.go(route)
        prep(app)
        rule.mainClock.autoAdvance = false
        rule.setContent { AppTheme { App(app) } }
        tick(3000)
        extra()
        tick(2500)
        app.toast = null; tick(1000)
        var shot: Bitmap? = null
        rule.activityRule.scenario.onActivity { a ->
            val v = a.window.decorView
            shot = Bitmap.createBitmap(v.width, v.height, Bitmap.Config.ARGB_8888).also { v.draw(android.graphics.Canvas(it)) }
        }
        File(out, "$name.png").outputStream().use { shot!!.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun scrollTo(tag: String, index: Int) { rule.onNodeWithTag(tag).performScrollToIndex(index); tick(800) }

    @Test fun home() = shoot("01-home", "explore")
    @Test fun homeModes() = shoot("02-home-modes", "explore", extra = { scrollTo("explore", 2) })
    @Test fun homeDock() = shoot("03-home-docking", "explore", extra = { scrollTo("explore", 11) })
    @Test fun story() = shoot("04-story-dual", "story/dual")
    @Test fun storyDiagram() = shoot("05-story-dual-diagram", "story/dual", extra = { scrollTo("story", 2) })
    @Test fun studio() = shoot("06-studio", "studio")
    @Test fun studioControls() = shoot("07-studio-controls", "studio", prep = { it.studioPanel = "tools"; it.host.setExplode(.4f); it.host.setSection(true) })
    @Test fun studioDock() = shoot("08-studio-dock", "studio", prep = { it.studioPanel = "dock" }, extra = {
        app.host.handle("""{"type":"dockStep","step":"lower"}""")
    })
    /** Step 3 while the sequence plays: the stage badge and the panel both say how the laptop leaves (a lift, nothing else). */
    @Test fun studioDockLift() = shoot("46-studio-dock-lift", "studio", prep = { it.studioPanel = "dock" }, extra = {
        app.host.dock("play"); app.host.handle("""{"type":"dockStep","step":"lift"}""")
    })
    @Test fun partSheet() = shoot("09-part-sheet", "studio", extra = { app.host.handle("""{"type":"pick","group":"dock"}""") })
    @Test fun files() = shoot("10-files", "files")
    @Test fun group() = shoot("11-group-detail", "group/dock")
    @Test fun groupDrawing() = shoot("12-group-drawing", "group/base", extra = { scrollTo("group", 4) })
    @Test fun specs() = shoot("13-specs", "specs")
    @Test fun bom() = shoot("14-bom", "specs", prep = { it.specsTab = "bom" })
    @Test fun deskFit() = shoot("15-desk-fit", "specs", prep = { it.specsTab = "fit"; it.deskW = 160; it.deskD = 80 })
    @Test fun deskFitNo() = shoot("16-desk-fit-stow-only", "specs", prep = { it.specsTab = "fit"; it.deskW = 150; it.deskD = 60 })
    @Test fun board() = shoot("17-board", "board")
    @Test fun buy() = shoot("47-buy", "specs", prep = { it.specsTab = "buy" })
    @Test fun buySwaps() = shoot("48-buy-swaps", "specs", prep = { it.specsTab = "buy" }, extra = {
        rule.onNodeWithTag("buy-swaps").performClick(); tick(500); rule.onNodeWithTag("buy").performScrollToKey("i-monitor"); tick(800)
    })
    @Test fun night() = shoot("18-night-shift", "explore", extra = { app.startNight() })

    @Config(qualifiers = "w1280dp-h800dp-mdpi")
    @Test fun tabletHome() = shoot("19-tablet-home", "explore")

    @Config(qualifiers = "w1280dp-h800dp-mdpi")
    @Test fun tabletStudio() = shoot("20-tablet-studio", "studio", prep = { it.studioPanel = "finish" })

    @Config(qualifiers = "w891dp-h411dp-xxhdpi")
    @Test fun landscapeStudioSheet() = shoot("21-landscape-part-sheet", "studio", extra = { app.host.handle("""{"type":"pick","group":"display"}""") })

    @Config(qualifiers = "w891dp-h411dp-xxhdpi")
    @Test fun landscapeHome() = shoot("22-landscape-home", "explore")

    @Config(qualifiers = "w891dp-h411dp-xxhdpi")
    @Test fun landscapeSpecs() = shoot("23-landscape-specs", "specs")

    @Config(qualifiers = "w1280dp-h800dp-mdpi")
    @Test fun tabletStory() = shoot("24-tablet-story-dock", "story/dock")

    @Config(qualifiers = "w1280dp-h800dp-mdpi")
    @Test fun tabletGroup() = shoot("25-tablet-group-display", "group/display")

    @Config(qualifiers = "w1280dp-h800dp-mdpi")
    @Test fun tabletDeskFit() = shoot("26-tablet-desk-fit", "specs", prep = { it.specsTab = "fit"; it.deskW = 140; it.deskD = 70 })

    @Test fun storyCharge() = shoot("27-story-charge-specs", "story/charge", extra = { scrollTo("story", 6) })
    @Test fun filesGroups() = shoot("28-files-groups", "files", extra = { scrollTo("files", 3) })
    @Test fun studioParts() = shoot("29-studio-parts", "studio", prep = { it.studioPanel = "parts" })

    @Config(qualifiers = "w360dp-h640dp-xhdpi")
    @Test fun smallPhoneStudio() = shoot("30-small-phone-studio-tools", "studio", prep = { it.studioPanel = "tools" })

    @Config(qualifiers = "w360dp-h640dp-xhdpi")
    @Test fun smallPhoneSheet() = shoot("31-small-phone-part-sheet", "studio", extra = { app.host.handle("""{"type":"pick","group":"internals"}""") })

    @Test fun nightCard() = shoot("32-home-night-card", "explore", extra = { rule.onNodeWithTag("explore").performScrollToKey("night"); tick(800) })

    @Config(qualifiers = "w1280dp-h800dp-mdpi")
    @Test fun tabletNightCard() = shoot("33-tablet-night-card", "explore", extra = { rule.onNodeWithTag("explore").performScrollToKey("night"); tick(800) })

    @Test fun storyDockCard() = shoot("34-story-dock-strip", "story/dock", extra = { rule.onNodeWithTag("story").performScrollToKey("seq"); tick(800) })

    @Test fun groupInternals() = shoot("35-group-internals-parts", "group/internals", extra = { rule.onNodeWithTag("group").performScrollToKey("parts"); tick(800) })

    @Test fun bomInternals() = shoot("36-bom-internals", "specs", prep = { it.specsTab = "bom" }, extra = { rule.onNodeWithTag("bom").performScrollToKey("g-internals"); tick(800) })

    // ---------- large font scales (Settings › Display › Font size) ----------
    @Config(fontScale = 2f)
    @Test fun font2Home() = shoot("40-font2-home", "explore")

    @Config(fontScale = 2f)
    @Test fun font2StudioDock() = shoot("41-font2-studio-dock", "studio", prep = { it.studioPanel = "dock" })

    @Config(fontScale = 2f)
    @Test fun font2DeskFit() = shoot("42-font2-desk-fit", "specs", prep = { it.specsTab = "fit" })

    @Config(fontScale = 2f)
    @Test fun font2Bom() = shoot("43-font2-bom", "specs", prep = { it.specsTab = "bom" })

    @Config(fontScale = 2f)
    @Test fun font2Dock() = shoot("44-font2-home-docking", "explore", extra = { rule.onNodeWithTag("explore").performScrollToKey("dock"); tick(800) })

    @Config(fontScale = 1.3f)
    @Test fun font13StudioDock() = shoot("45-font13-studio-dock", "studio", prep = { it.studioPanel = "dock" })

    /** The adaptive launcher icon (circle mask) next to its themed (monochrome) version. */
    @Test fun launcherIcon() {
        val ctx = ApplicationProvider.getApplicationContext<android.content.Context>()
        val size = 432; val gap = 48
        val bmp = Bitmap.createBitmap(size * 3 + gap * 4, size + gap * 2, Bitmap.Config.ARGB_8888)
        val c = android.graphics.Canvas(bmp)
        c.drawColor(0xFF6B6560.toInt())
        val icon = ctx.getDrawable(R.mipmap.ic_launcher) as android.graphics.drawable.AdaptiveIconDrawable
        fun drawMasked(d: android.graphics.drawable.AdaptiveIconDrawable, x: Int) {
            c.save(); c.translate(x.toFloat(), gap.toFloat())
            val clip = android.graphics.Path().apply { addCircle(size / 2f, size / 2f, size / 2f, android.graphics.Path.Direction.CW) }
            c.clipPath(clip); d.setBounds(0, 0, size, size); d.draw(c); c.restore()
        }
        drawMasked(icon, gap)
        // the full 108 dp foreground canvas with the 66 dp safe zone, to check nothing important sits outside it
        c.save(); c.translate((size + gap * 2).toFloat(), gap.toFloat())
        val fg = icon.foreground.constantState!!.newDrawable().mutate()
        c.drawRect(0f, 0f, size.toFloat(), size.toFloat(), android.graphics.Paint().apply { color = 0xFF0C0A09.toInt() })
        fg.setBounds(0, 0, size, size); fg.draw(c)
        c.drawCircle(size / 2f, size / 2f, size * 33f / 108f, android.graphics.Paint().apply { style = android.graphics.Paint.Style.STROKE; color = 0x88F2A04A.toInt(); strokeWidth = 2f })
        c.restore()
        val mono = icon.monochrome!!.constantState!!.newDrawable().mutate().apply { setTint(0xFF2B3A55.toInt()) }
        drawMasked(android.graphics.drawable.AdaptiveIconDrawable(android.graphics.drawable.ColorDrawable(0xFFD6E2FF.toInt()), mono), size * 2 + gap * 3)
        File(out, "00-launcher-icon.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
