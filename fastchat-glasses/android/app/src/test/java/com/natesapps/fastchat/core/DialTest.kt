package com.natesapps.fastchat.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DialTest {

    /** Feeds one drag made of these changes in x and returns the steps each one produced. */
    private fun drag(dial: Dial, vararg moves: Float): List<Int> {
        dial.start()
        return moves.map(dial::move)
    }

    @Test
    fun `every full step of travel to the right turns one step clockwise`() {
        val dial = Dial(stepSize = 0.08f)
        // Travel so far: 0.03, 0.06, 0.09, 0.15, 0.25 -> 0, 0, 1, 1, 3 steps in total.
        assertEquals(listOf(0, 0, 1, 0, 2), drag(dial, 0.03f, 0.03f, 0.03f, 0.06f, 0.10f))
        assertTrue(dial.turned)
    }

    @Test
    fun `one full wrist turn as the band reports it can reach all four replies`() {
        // Measured on a real band: x tops out at about 0.2, arriving in small samples.
        val dial = Dial()
        val steps = drag(dial, *FloatArray(20) { 0.01f }).sum()
        assertEquals(4, steps)
    }

    @Test
    fun `travel to the left turns the other way`() {
        val dial = Dial(stepSize = 0.08f)
        assertEquals(listOf(-1, -1), drag(dial, -0.09f, -0.08f))
    }

    @Test
    fun `the wrist has to come a whole step back before the highlight moves back`() {
        val dial = Dial(stepSize = 0.08f)
        // Out to 0.09 (one step), wobble around the boundary, then right back to the start.
        assertEquals(listOf(1, 0, 0, 0, -1), drag(dial, 0.09f, -0.02f, 0.02f, -0.03f, -0.07f))
    }

    @Test
    fun `a small wobble turns nothing`() {
        val dial = Dial(stepSize = 0.08f)
        assertEquals(listOf(0, 0, 0), drag(dial, 0.02f, -0.015f, 0.01f))
        assertFalse(dial.turned)
    }

    @Test
    fun `each new pinch starts from nothing`() {
        val dial = Dial(stepSize = 0.08f)
        drag(dial, 0.06f)
        assertEquals(listOf(0), drag(dial, 0.06f))
        assertFalse(dial.turned)
    }
}
