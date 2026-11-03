package com.natesapps.chaintheory

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.activity.ComponentActivity
import androidx.test.core.app.ApplicationProvider
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/** Renders key screens to PNGs for the README: gradle testDebugUnitTest --tests '*Screenshots*' -Dshots=1 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w393dp-h852dp-xhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class Screenshots {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
    private val out = File(System.getProperty("shots.dir") ?: "build/screenshots").apply { mkdirs() }

    private fun shoot(name: String, route: String, waitMs: Long = 3000, extra: () -> Unit = {}) {
        val store = Store(ApplicationProvider.getApplicationContext())
        listOf("l1", "l2", "q0", "calc", "search").forEach { store.earned[it] = 1L }
        val nav = Nav("home").apply { if (route != "home") go(route) }
        rule.mainClock.autoAdvance = false
        rule.setContent { AppTheme { App(store, nav) } }
        repeat((waitMs / 250).toInt()) { rule.mainClock.advanceTimeBy(250); rule.waitForIdle() }
        extra()
        Thread.sleep(1500); repeat(8) { rule.mainClock.advanceTimeBy(250); rule.waitForIdle() }
        store.toast.value = null; repeat(4) { rule.mainClock.advanceTimeBy(500); rule.waitForIdle() }
        var shot: Bitmap? = null
        rule.activityRule.scenario.onActivity { a ->
            val v = a.window.decorView
            val b = Bitmap.createBitmap(v.width, v.height, Bitmap.Config.ARGB_8888)
            v.draw(android.graphics.Canvas(b)); shot = b
        }
        val bmp = shot!!
        File(out, "$name.png").outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun home() = shoot("home", "home")
    @Test fun quiz() = shoot("quiz", "quiz/0") { rule.onAllNodes(hasClickAction())[2].performClick() }
    @Test fun primer() = shoot("primer", "article/primer")
    @Test fun reader() = shoot("reader", "reader/comp/20", 4000)
    @Test fun map() = shoot("map", "map")
}
