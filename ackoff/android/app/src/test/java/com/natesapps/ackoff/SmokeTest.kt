package com.natesapps.ackoff

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
import java.io.File

/** Renders every screen of the app and exercises its main interactions. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class SmokeTest {
    @get:Rule val rule = createComposeRule()
    private val ctx: Context get() = ApplicationProvider.getApplicationContext()

    private fun show(route: String, prep: (Store) -> Unit = {}, extra: (Store) -> Unit = {}) {
        val store = Store(ctx); prep(store)
        val nav = Nav("home").apply { if (route != "home") go(route) }
        rule.mainClock.autoAdvance = false
        rule.setContent { AppTheme { App(store, nav) } }
        tick(3000)
        extra(store)
    }
    private fun tick(ms: Long = 1500) { repeat((ms / 250).toInt()) { rule.mainClock.advanceTimeBy(250); rule.waitForIdle() } }
    private fun click(t: String) { rule.onAllNodesWithText(t, substring = true)[0].performClick(); tick() }

    @Test fun home() = show("home") { rule.onAllNodesWithText("parts connected", substring = true)[0].assertExists() }
    @Test fun learn() = show("learn") { click("The 1993 talk"); rule.onAllNodesWithText("From Mechanistic to Social Systemic Thinking")[0].assertExists() }
    @Test fun article_l1() = show("article/l1") { rule.onAllNodes(hasScrollToIndexAction())[0].performScrollToIndex(5); tick() }
    @Test fun article_talk() = show("article/talk") { rule.onAllNodes(hasScrollToIndexAction())[0].performScrollToIndex(5); tick() }
    @Test fun article_lead() = show("article/lead") { rule.onAllNodes(hasScrollToIndexAction())[0].performScrollToIndex(5); tick() }
    @Test fun article_tools() = show("article/tools") { rule.onAllNodes(hasScrollToIndexAction())[0].performScrollToIndex(5); tick() }
    @Test fun article_apply() = show("article/apply") { rule.onAllNodes(hasScrollToIndexAction())[0].performScrollToIndex(5); tick() }
    @Test fun talkSections() = show("article/talk") { rule.onNodeWithContentDescription("Sections").performClick(); tick() }
    @Test fun lead() = show("article/lead") { rule.onAllNodesWithText("Leadership as an aesthetic act")[0].assertExists() }
    @Test fun glossary() = show("glossary") { click("Synthesis") }
    @Test fun play() = show("play") { click("Machine or Systems?") }
    private fun runQuiz(d: Int) = show("quiz/$d") {
        val n = Repo.content(ctx).decks[d].questions.size
        repeat(n) {
            rule.onAllNodes(hasClickAction())[1].performClick(); tick()
            if (rule.onAllNodesWithText("See results").fetchSemanticsNodes().isNotEmpty()) click("See results") else click("Next")
        }
        tick(3000)
        rule.onAllNodesWithText("Play again")[0].assertExists()
    }
    @Test fun quiz0() = runQuiz(0)
    @Test fun quiz1() = runQuiz(1)
    @Test fun quiz2() = runQuiz(2)
    @Test fun quiz3() = runQuiz(3)
    @Test fun sortGame() = show("sort") { st ->
        val n = Repo.content(ctx).sort.size
        repeat(n) { rule.onAllNodesWithText("Systems  ◉")[0].performClick(); tick(1000) }
        tick(2000)
        rule.onAllNodesWithText("Play again")[0].assertExists()
        assert(st.sortBest.value in 1 until n)
    }
    @Test fun flash() = show("flash") { click("tap to flip"); click("Knew it"); click("Again") }
    @Test fun libraryEmpty() = show("library") { rule.onAllNodesWithText("Import PDF")[0].assertExists() }
    @Test fun libraryWithPdf() = show("library", prep = { s ->
        File(s.pdfDir, "Test Article.pdf").writeText("%PDF-1.4\n%fake\n"); s.refreshPdfs()
    }) { click("Test Article"); tick(1000) }
    @Test fun search() = show("search") {
        rule.onAllNodes(hasSetTextAction())[0].performTextInput("acorn"); tick(1000)
        rule.onAllNodesWithText("matches", substring = true)[0].assertExists()
        rule.onAllNodesWithText("The 1993 talk", substring = true)[0].performClick(); tick()
    }
}
