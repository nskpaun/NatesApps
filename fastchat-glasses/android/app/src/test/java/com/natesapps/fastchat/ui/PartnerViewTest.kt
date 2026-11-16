package com.natesapps.fastchat.ui

import android.app.Application
import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.natesapps.fastchat.core.PartnerTurn
import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w393dp-h852dp-xhdpi", application = Application::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class PartnerViewTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

    private fun show(turn: PartnerTurn, name: String = "Sam") {
        rule.mainClock.autoAdvance = false
        rule.setContent { FastChatTheme { Box(Modifier.fillMaxSize().background(Cream)) { PartnerView(turn, name) } } }
        rule.mainClock.advanceTimeBy(600)
        rule.waitForIdle()
    }

    private fun capture(name: String): Bitmap {
        lateinit var result: Bitmap
        rule.activityRule.scenario.onActivity { activity ->
            val view = activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            val folder = File("build/screenshots/phone").apply { mkdirs() }
            File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            result = bitmap
        }
        return result
    }

    @Test
    fun `the partner only sees the current turn and it changes when listening resumes`() {
        val turn = mutableStateOf(PartnerTurn.WEARERS_TURN)
        rule.mainClock.autoAdvance = false
        rule.setContent { FastChatTheme { Box(Modifier.fillMaxSize().background(Cream)) { PartnerView(turn.value, "Sam") } } }
        rule.mainClock.advanceTimeBy(600)
        rule.onNodeWithText("Sam’s turn").assertIsDisplayed()
        rule.onAllNodes(hasClickAction()).assertCountEquals(0)
        val resting = capture("sams-turn")
        rule.mainClock.advanceTimeBy(450)
        val moving = capture("sams-turn-motion")
        assertFalse("The upward cue must actually animate", resting.sameAs(moving))
        rule.runOnIdle { turn.value = PartnerTurn.YOUR_TURN }
        rule.mainClock.advanceTimeBy(250)
        rule.onNodeWithText("Your turn").assertIsDisplayed()
        rule.onNodeWithText("Sam’s turn").assertDoesNotExist()
        capture("your-turn")
    }

    @Test
    fun `an unset wearer name still gives an unambiguous wait cue`() {
        show(PartnerTurn.WEARERS_TURN, "")
        rule.onNodeWithText("Please wait").assertIsDisplayed()
        rule.onNodeWithText("My turn").assertDoesNotExist()
    }

    @Test
    fun reconnecting() {
        show(PartnerTurn.RECONNECTING)
        rule.onNodeWithText("One moment").assertIsDisplayed()
        rule.onNodeWithText("Your turn").assertDoesNotExist()
        capture("reconnecting")
    }

    @Test
    @Config(qualifiers = "w320dp-h568dp-xhdpi", fontScale = 2f)
    fun `a small phone and large text keep the turn cue readable`() {
        show(PartnerTurn.WEARERS_TURN, "Alexandra")
        val node = rule.onNodeWithText("Alexandra’s turn").assertIsDisplayed().fetchSemanticsNode()
        assertTrue(node.boundsInRoot.top >= 0f)
        capture("large-text")
    }

    @Test
    @Config(qualifiers = "w640dp-h320dp-xhdpi")
    fun landscape() {
        show(PartnerTurn.YOUR_TURN)
        rule.onNodeWithText("Your turn").assertIsDisplayed()
        capture("landscape")
    }
}
