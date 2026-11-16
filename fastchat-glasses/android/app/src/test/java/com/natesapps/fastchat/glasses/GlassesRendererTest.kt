package com.natesapps.fastchat.glasses

import android.app.Application
import android.graphics.Bitmap
import android.graphics.Color
import com.natesapps.fastchat.core.Dpad
import com.natesapps.fastchat.core.GlassesScreen
import com.natesapps.fastchat.core.Reply
import com.natesapps.fastchat.core.Phase
import com.natesapps.fastchat.core.State
import com.natesapps.fastchat.core.screenFor
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], application = Application::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class GlassesRendererTest {
    private val replies = listOf(
        Reply("🙂", "Yes, please."), Reply("☕", "Coffee instead."),
        Reply("🤫", "Somewhere quiet."), Reply("✋", "Not now."),
    )

    private fun screen(count: Int, focus: Dpad? = null) = GlassesScreen.Choices(
        "Lunch?", Dpad.entries.map { replies.take(count).getOrNull(it.ordinal) },
        done = count == 4, quick = false, focus = focus,
    )

    private fun region(bitmap: Bitmap, x: Int, y: Int, width: Int, height: Int) =
        Bitmap.createBitmap(bitmap, x, y, width, height)

    @Test
    fun `missing replies and corners emit no light and new replies never move the first one`() {
        val renderer = GlassesRenderer()
        val first = renderer.render(screen(1))
        assertTrue(first.hasAlpha())
        assertEquals(0, Color.alpha(first.getPixel(5, 5)))
        assertEquals(0, Color.alpha(first.getPixel(595, 595)))
        val emptyRight = region(first, 410, 218, 180, 180)
        assertTrue(emptyRight.sameAs(Bitmap.createBitmap(180, 180, Bitmap.Config.ARGB_8888)))
        val firstReply = region(first, 190, 0, 220, 200)
        assertFalse("The very first reply must be visible immediately", firstReply.sameAs(Bitmap.createBitmap(220, 200, Bitmap.Config.ARGB_8888)))
        for (count in 2..4) {
            val next = renderer.render(screen(count))
            assertTrue(firstReply.sameAs(region(next, 190, 0, 220, 200)))
        }
    }

    @Test
    fun `gesture motion does not move or dim reply text and selection only adds an underline`() {
        val renderer = GlassesRenderer()
        val resting = renderer.render(screen(4), 0)
        val moving = renderer.render(screen(4), 3)
        assertFalse(region(resting, 240, 230, 120, 100).sameAs(region(moving, 240, 230, 120, 100)))
        assertTrue(region(resting, 400, 210, 200, 190).sameAs(region(moving, 400, 210, 200, 190)))
        val selected = renderer.render(screen(4, Dpad.UP), 0)
        assertTrue(region(resting, 400, 210, 200, 190).sameAs(region(selected, 400, 210, 200, 190)))
        assertTrue(region(resting, 0, 210, 200, 190).sameAs(region(selected, 0, 210, 200, 190)))
        assertFalse(region(resting, 190, 0, 220, 200).sameAs(region(selected, 190, 0, 220, 200)))
    }

    @Test
    fun `render streaming and selected states for visual review`() {
        val folder = File("build/screenshots/glasses").apply { mkdirs() }
        val renderer = GlassesRenderer()
        for (count in 0..4) {
            File(folder, "replies-$count.png").outputStream().use { renderer.render(screen(count)).compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        File(folder, "selected.png").outputStream().use { renderer.render(screen(4, Dpad.RIGHT), 3).compress(Bitmap.CompressFormat.PNG, 100, it) }
        val statuses = mapOf(
            "listening" to screenFor(State(phase = Phase.Listening)),
            "hearing" to screenFor(State(phase = Phase.Listening), hearingSpeech = true),
            "speaking" to screenFor(State(phase = Phase.Speaking("I'd prefer a coffee."))),
        )
        statuses.forEach { (name, status) ->
            File(folder, "$name.png").outputStream().use { renderer.render(status, 3).compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
    }
}
