package com.natesapps.ackoff

import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.core.app.ApplicationProvider
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
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

    private fun shoot(name: String, route: String, extra: () -> Unit = {}) {
        val store = Store(ApplicationProvider.getApplicationContext())
        listOf("l1", "talk", "q0", "q1", "sort", "search", "lead").forEach { store.earned[it] = 1L }
        val nav = Nav("home").apply { if (route != "home") go(route) }
        rule.mainClock.autoAdvance = false
        rule.setContent { AppTheme { App(store, nav) } }
        repeat(12) { rule.mainClock.advanceTimeBy(250); rule.waitForIdle() }
        extra()
        repeat(8) { rule.mainClock.advanceTimeBy(250); rule.waitForIdle() }
        store.toast.value = null; repeat(4) { rule.mainClock.advanceTimeBy(500); rule.waitForIdle() }
        var shot: Bitmap? = null
        rule.activityRule.scenario.onActivity { a ->
            val v = a.window.decorView
            shot = Bitmap.createBitmap(v.width, v.height, Bitmap.Config.ARGB_8888).also { v.draw(android.graphics.Canvas(it)) }
        }
        File(out, "$name.png").outputStream().use { shot!!.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun home() = shoot("home", "home")
    @Test fun talk() = shoot("talk", "article/talk")
    @Test fun lead() = shoot("lead", "article/lead")
    @Test fun sort() = shoot("sort", "sort")
    @Test fun quiz() = shoot("quiz", "quiz/2") { rule.onAllNodes(hasClickAction())[2].performClick() }
}
