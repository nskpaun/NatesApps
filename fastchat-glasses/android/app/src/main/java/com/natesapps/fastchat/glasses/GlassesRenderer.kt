package com.natesapps.fastchat.glasses

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import com.natesapps.fastchat.core.Dpad
import com.natesapps.fastchat.core.GlassesCue
import com.natesapps.fastchat.core.GlassesScreen
import com.natesapps.fastchat.core.Reply
import com.natesapps.fastchat.core.cue
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * A transparent light layer, not a picture of a dark HUD. Empty slots emit nothing. The whole
 * compass has fixed geometry, so neither streaming replies nor a changing hand cue moves a choice.
 * Bitmap content also lets the real display use our warm type and custom animated hand outlines.
 */
class GlassesRenderer {
    private var cachedScreen: GlassesScreen? = null
    private val frames = mutableMapOf<Int, Bitmap>()

    /** Native focus navigation is used when the band input capability isn't available. */
    fun tapCentre(screen: GlassesScreen.Choices): Bitmap =
        Bitmap.createBitmap(200, 200, Bitmap.Config.ARGB_8888).also {
            val label = when {
                !screen.done -> "Choose a reply"
                screen.quick -> "Back"
                else -> "More replies"
            }
            words(Canvas(it), label, 100f, 80f, 170, 22f)
        }

    fun render(screen: GlassesScreen, frame: Int = 0): Bitmap {
        if (cachedScreen != screen) {
            frames.clear()
            cachedScreen = screen
        }
        return frames.getOrPut(frame) {
            Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888).also { bitmap ->
                val canvas = Canvas(bitmap)
                when (screen) {
                    is GlassesScreen.Choices -> {
                        Dpad.entries.forEach { direction ->
                            screen.replies.getOrNull(direction.ordinal)?.let { reply ->
                                val (x, top) = when (direction) {
                                    Dpad.UP -> 300f to 24f
                                    Dpad.RIGHT -> 496f to 218f
                                    Dpad.DOWN -> 300f to 412f
                                    Dpad.LEFT -> 104f to 218f
                                }
                                drawReply(canvas, reply, x, top, screen.focus == direction)
                            }
                        }
                        val cue = screen.cue
                        CueDrawing.draw(canvas, cue, RectF(258f, 238f, 342f, 322f), frame)
                        val label = when (cue) {
                            GlassesCue.SWIPE_THUMB -> "Swipe thumb"
                            GlassesCue.PINCH -> "Pinch to say"
                            else -> "Finding replies"
                        }
                        words(canvas, label, 300f, 337f, 172, 18f)
                    }
                    is GlassesScreen.Status -> {
                        val speaking = screen.activity == GlassesCue.SPEAKING
                        val x = if (speaking) 350f else 442f
                        CueDrawing.draw(canvas, screen.cue, RectF(x - 32, 365f, x + 32, 429f), frame)
                        words(canvas, screen.detail ?: screen.title, x, 451f, if (speaking) 452 else 280, 26f)
                        if (screen.offersQuickPhrases) {
                            words(canvas, "Pinch for quick phrases", x, 548f, 280, 17f)
                        }
                    }
                }
            }
        }
    }

    private fun drawReply(canvas: Canvas, reply: Reply, x: Float, top: Float, selected: Boolean) {
        val emoji = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = LIGHT
            textSize = 46f
            textAlign = Paint.Align.CENTER
        }
        canvas.drawText(reply.emoji.ifBlank { "💬" }, x, top + 46, emoji)
        var size = 25f
        var layout = layout(reply.text, 186, size)
        while (layout.height > 103 && size > 19f) {
            size -= 1f
            layout = layout(reply.text, 186, size)
        }
        canvas.save()
        canvas.translate(x - layout.width / 2f, top + 60)
        layout.draw(canvas)
        canvas.restore()
        if (selected) {
            val width = (0 until layout.lineCount).maxOf { layout.getLineWidth(it) }.coerceIn(40f, 178f)
            val y = top + 60 + layout.height + 9
            canvas.drawPath(Path().apply {
                moveTo(x - width / 2, y)
                quadTo(x, y + 3, x + width / 2, y)
            }, CueDrawing.stroke(ACCENT, 4f))
        }
    }

    private fun words(canvas: Canvas, text: String, x: Float, top: Float, width: Int, size: Float) {
        val layout = layout(text, width, size)
        canvas.save()
        canvas.translate(x - width / 2f, top)
        layout.draw(canvas)
        canvas.restore()
    }

    private fun layout(text: String, width: Int, size: Float): StaticLayout {
        val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = LIGHT
            textSize = size
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
        }
        return StaticLayout.Builder.obtain(text, 0, text.length, paint, width)
            .setAlignment(Layout.Alignment.ALIGN_CENTER)
            .setIncludePad(false)
            .setLineSpacing(3f, 1f)
            .build()
    }

    companion object {
        const val SIZE = 600
        val LIGHT: Int = Color.rgb(255, 244, 220)
        val ACCENT: Int = Color.rgb(255, 204, 145)

        /** Eight movement frames followed by a long rest, rather than perpetual instruction motion. */
        fun animationFrame(elapsedMs: Long): Int {
            val tick = (elapsedMs.coerceAtLeast(0) % 2_400L / 120L).toInt()
            return if (tick < 8) tick else 0
        }
    }
}

/** Small, unfilled vector strokes. No hand asset carries a background into an additive display. */
internal object CueDrawing {
    fun stroke(color: Int, width: Float = 3.6f): Paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        this.color = color
        style = Paint.Style.STROKE
        strokeWidth = width
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    fun draw(canvas: Canvas, cue: GlassesCue, bounds: RectF, frame: Int) {
        val light = stroke(GlassesRenderer.LIGHT)
        val accent = stroke(GlassesRenderer.ACCENT)
        val phase = frame.coerceIn(0, 7) / 7f
        canvas.save()
        canvas.translate(bounds.left, bounds.top)
        canvas.scale(bounds.width() / 100f, bounds.height() / 100f)
        when (cue) {
            GlassesCue.SWIPE_THUMB -> fist(canvas, light, accent, phase)
            GlassesCue.PINCH -> pinch(canvas, light, accent, phase)
            GlassesCue.GENERATING -> {
                val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = GlassesRenderer.LIGHT }
                repeat(3) { i ->
                    val lift = if (frame == 0) 0f else (sin(phase * PI * 2 - i * 0.8).toFloat()).coerceAtLeast(0f) * 6
                    canvas.drawCircle(26f + i * 24, 53f - lift, 5f, fill)
                }
            }
            GlassesCue.LISTENING, GlassesCue.HEARING -> {
                canvas.drawPath(Path().apply {
                    moveTo(43f, 84f)
                    cubicTo(23f, 80f, 38f, 62f, 32f, 52f)
                    cubicTo(14f, 24f, 38f, 8f, 56f, 20f)
                    cubicTo(76f, 33f, 57f, 50f, 50f, 60f)
                    cubicTo(47f, 65f, 51f, 78f, 43f, 84f)
                    moveTo(35f, 41f)
                    cubicTo(29f, 30f, 48f, 24f, 49f, 37f)
                    cubicTo(50f, 43f, 40f, 45f, 41f, 54f)
                }, light)
                if (cue == GlassesCue.HEARING) sound(canvas, accent, phase)
            }
            GlassesCue.SPEAKING -> {
                canvas.drawPath(Path().apply {
                    moveTo(18f, 40f); lineTo(32f, 40f); lineTo(52f, 25f)
                    lineTo(52f, 75f); lineTo(32f, 60f); lineTo(18f, 60f); close()
                }, light)
                sound(canvas, accent, phase)
            }
            GlassesCue.QUIET -> Unit
        }
        canvas.restore()
    }

    private fun fist(canvas: Canvas, light: Paint, accent: Paint, phase: Float) {
        // All four fingers stay curled and stationary. Only the thumb rocks on the first index
        // joint above the base knuckle, as if using that small curved surface as a joystick.
        canvas.drawPath(Path().apply {
            moveTo(36f, 95f); lineTo(31f, 82f)
            cubicTo(17f, 79f, 11f, 69f, 15f, 61f)
            cubicTo(10f, 53f, 11f, 45f, 16f, 40f)
            cubicTo(13f, 31f, 16f, 25f, 24f, 24f)
            cubicTo(22f, 13f, 33f, 8f, 42f, 16f)
            moveTo(17f, 39f)
            cubicTo(25f, 33f, 42f, 36f, 43f, 44f)
            cubicTo(43f, 52f, 27f, 51f, 16f, 47f)
            moveTo(16f, 53f)
            cubicTo(27f, 49f, 42f, 52f, 41f, 60f)
            cubicTo(40f, 68f, 25f, 65f, 16f, 62f)
            moveTo(17f, 67f)
            cubicTo(27f, 63f, 39f, 67f, 37f, 73f)
            cubicTo(35f, 79f, 23f, 78f, 20f, 74f)
            moveTo(31f, 82f)
            cubicTo(45f, 87f, 64f, 80f, 70f, 71f)
            moveTo(72f, 64f)
            cubicTo(79f, 52f, 82f, 34f, 74f, 25f)
            moveTo(76f, 58f)
            cubicTo(78f, 72f, 84f, 82f, 90f, 90f)
        }, light)
        val dx = sin(phase * 2 * PI).toFloat() * 3f
        val dy = (1 - cos(phase * 2 * PI).toFloat()) * -2.5f
        canvas.drawPath(Path().apply {
            moveTo(67f, 57f)
            cubicTo(59f, 53f, 57f, 43f, 60f, 34f)
            cubicTo(49f, 36f, 40f + dx, 30f + dy, 38f + dx, 23f + dy)
            cubicTo(34f + dx, 15f + dy, 40f + dx, 13f + dy, 48f + dx, 16f + dy)
            cubicTo(57f, 18f, 63f, 11f, 70f, 17f)
            cubicTo(81f, 23f, 84f, 38f, 79f, 49f)
        }, accent)
    }

    private fun pinch(canvas: Canvas, light: Paint, accent: Paint, phase: Float) {
        val close = ((1 - cos(phase * 2 * PI)) / 2).toFloat()
        val gap = 11f * (1 - close)
        canvas.drawPath(Path().apply {
            moveTo(34f, 95f); lineTo(29f, 82f)
            cubicTo(11f, 70f, 10f, 56f, 21f, 50f)
            cubicTo(11f, 35f, 18f, 17f, 38f, 16f)
            cubicTo(53f, 13f, 65f, 19f, 64f, 25f)
            cubicTo(63f, 31f, 48f, 31f, 39f, 29f)
            cubicTo(31f, 34f, 32f, 45f, 38f, 50f)
            moveTo(22f, 50f)
            cubicTo(32f, 44f, 45f, 52f, 42f, 59f)
            cubicTo(39f, 66f, 27f, 62f, 20f, 58f)
            moveTo(20f, 64f)
            cubicTo(30f, 58f, 44f, 65f, 39f, 72f)
            cubicTo(35f, 77f, 27f, 73f, 23f, 70f)
            moveTo(78f, 56f)
            cubicTo(77f, 71f, 83f, 83f, 88f, 93f)
        }, light)
        canvas.drawPath(Path().apply {
            moveTo(64f, 70f)
            cubicTo(47f, 62f, 51f, 48f, 58f, 36f + gap)
            cubicTo(61f, 30f + gap, 67f, 26f + gap, 73f, 33f + gap)
            cubicTo(88f, 45f, 88f, 62f, 79f, 72f)
        }, accent)
        if (close > 0.85f) {
            canvas.drawLine(75f, 19f, 80f, 12f, accent)
            canvas.drawLine(81f, 27f, 91f, 25f, accent)
        }
    }

    private fun sound(canvas: Canvas, paint: Paint, phase: Float) {
        val lift = sin(phase * PI * 2).toFloat() * 3f
        canvas.drawArc(RectF(50f, 35f - lift, 74f, 65f + lift), -55f, 110f, false, paint)
        canvas.drawArc(RectF(50f, 24f - lift, 91f, 76f + lift), -55f, 110f, false, paint)
    }
}
