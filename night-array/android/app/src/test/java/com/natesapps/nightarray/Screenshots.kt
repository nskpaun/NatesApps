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
    @Test fun partSheet() = shoot("09-part-sheet", "studio", extra = { app.host.handle("""{"type":"pick","group":"dock"}""") })
    @Test fun files() = shoot("10-files", "files")
    @Test fun group() = shoot("11-group-detail", "group/dock")
    @Test fun groupDrawing() = shoot("12-group-drawing", "group/base", extra = { scrollTo("group", 4) })
    @Test fun specs() = shoot("13-specs", "specs")
    @Test fun bom() = shoot("14-bom", "specs", prep = { it.specsTab = "bom" })
    @Test fun deskFit() = shoot("15-desk-fit", "specs", prep = { it.specsTab = "fit"; it.deskW = 160; it.deskD = 80 })
    @Test fun deskFitNo() = shoot("16-desk-fit-stow-only", "specs", prep = { it.specsTab = "fit"; it.deskW = 150; it.deskD = 60 })
    @Test fun board() = shoot("17-board", "board")
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
}
