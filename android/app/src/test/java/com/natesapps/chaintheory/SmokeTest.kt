package com.natesapps.chaintheory

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.core.app.ApplicationProvider
import android.content.Context
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Renders every screen of the app and exercises its main interactions. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class SmokeTest {
    @get:Rule val rule = createComposeRule()
    private val ctx: Context get() = ApplicationProvider.getApplicationContext()

    private fun show(route: String, extra: (Store) -> Unit = {}) {
        val store = Store(ctx)
        val nav = Nav("home").apply { if (route != "home") go(route) }
        rule.mainClock.autoAdvance = false
        rule.setContent { AppTheme { App(store, nav) } }
        repeat(6) { rule.mainClock.advanceTimeBy(500); rule.waitForIdle() }
        extra(store)
    }
    private fun tick(ms: Long = 1500) { repeat((ms / 250).toInt()) { rule.mainClock.advanceTimeBy(250); rule.waitForIdle() } }
    private fun scrollTo(t: String) { rule.onAllNodes(hasScrollToNodeAction())[0].performScrollToNode(hasText(t, substring = true)); tick() }
    private fun click(t: String) { rule.onAllNodesWithText(t, substring = true)[0].performClick(); tick() }

    @Test fun home() = show("home") { rule.onAllNodesWithText("links forged", substring = true)[0].assertExists() }
    @Test fun learn() = show("learn") { click("Compendium map"); scrollTo("Part VII"); click("Part VII"); click("Read from p.") }
    @Test fun l1() = show("article/l1") { rule.onAllNodesWithText("Chain Theory in a minute")[0].assertExists() }
    @Test fun l2() = show("article/l2") { rule.onNodeWithContentDescription("Sections").performClick(); tick() }
    @Test fun l3() = show("article/l3") { rule.onAllNodesWithText("How the count works")[0].assertExists() }
    @Test fun map() = show("map") { scrollTo("Part IX"); click("Part IX"); click("Read from p."); Thread.sleep(2000); tick(2000) }
    @Test fun calc() = show("calc") { rule.onAllNodesWithContentDescription("plus")[0].performClick(); tick(); click("k not √k"); click("Reset") }
    @Test fun glossary() = show("glossary") { click("Bound entanglement") }
    @Test fun play() = show("play") { click("Basics") }
    @Test fun quiz() = show("quiz/0") {
        repeat(8) {
            rule.onAllNodes(hasClickAction())[1].performClick(); tick()
            if (rule.onAllNodesWithText("See results").fetchSemanticsNodes().isNotEmpty()) click("See results") else click("Next")
        }
        tick(3000)
        rule.onAllNodesWithText("Play again")[0].assertExists()
    }
    @Test fun flash() = show("flash") { click("tap to flip"); click("Knew it"); click("Again") }
    @Test fun library() = show("library") { scrollTo("Bookmarks"); click("A Parameter-Free"); Thread.sleep(1500); tick(2000) }
    @Test fun reader() = show("reader/comp/46") {
        Thread.sleep(2500); tick(3000); Thread.sleep(500); tick()
        rule.onAllNodesWithText("Compendium · p. 46", substring = true)[0].assertExists()
        rule.onNodeWithContentDescription("Bookmark").performClick(); tick()
        rule.onNodeWithContentDescription("Next").performClick(); tick()
        rule.onAllNodesWithText("Compendium · p. 47", substring = true)[0].assertExists()
        rule.onNodeWithContentDescription("Contents").performClick(); tick()
    }
    @Test fun readerTalk() = show("reader/alpha/1") { Thread.sleep(1500); tick(3000); rule.onAllNodesWithText("Letter · p. 1", substring = true)[0].assertExists() }
    @Test fun search() = show("search") {
        rule.onAllNodes(hasSetTextAction())[0].performTextInput("Higgs quartic")
        tick(1000); Thread.sleep(4000); tick(1000); Thread.sleep(1000); tick(1000)
        rule.onAllNodesWithText("matches", substring = true)[0].assertExists()
    }
}
