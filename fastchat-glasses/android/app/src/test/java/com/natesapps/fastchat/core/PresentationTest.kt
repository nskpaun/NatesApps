package com.natesapps.fastchat.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PresentationTest {
    private val replies = listOf(
        Reply("🙂", "Yes, please."), Reply("☕", "Coffee instead."),
        Reply("🤫", "Somewhere quiet."), Reply("✋", "Not now."),
    )

    @Test
    fun `the first reply changes the cue from generating to thumb swipe before generation is done`() {
        var state = reduce(reduce(State(), Event.Start).state, Event.Heard("Lunch?")).state
        assertEquals(GlassesCue.GENERATING, screenFor(state).cue)
        for (count in 1..4) {
            state = reduce(state, Event.Replies(state.generation, replies.take(count), done = count == 4)).state
            val screen = screenFor(state) as GlassesScreen.Choices
            assertEquals(GlassesCue.SWIPE_THUMB, screen.cue)
            for (position in Dpad.entries) {
                assertEquals(replies.take(count).getOrNull(position.ordinal), screen.replies[position.ordinal])
            }
        }
    }

    @Test
    fun `pinch cue and exact selected words survive later replies arriving`() {
        var state = reduce(reduce(State(), Event.Start).state, Event.Heard("Lunch?")).state
        state = reduce(state, Event.Replies(state.generation, replies.take(1), done = false)).state
        state = reduce(state, Event.Input(GlassesInput.Highlight(Dpad.UP))).state
        assertEquals(GlassesCue.PINCH, screenFor(state).cue)
        state = reduce(state, Event.Replies(state.generation, replies.take(3), done = false)).state
        assertEquals(GlassesCue.PINCH, screenFor(state).cue)
        assertEquals(Dpad.UP, (screenFor(state) as GlassesScreen.Choices).focus)
        state = reduce(state, Event.Input(GlassesInput.Confirm)).state
        assertEquals(Phase.Speaking(replies[0].text), state.phase)
        assertEquals(GlassesCue.SPEAKING, screenFor(state).cue)
    }

    @Test
    fun `the partner sees one stable wearer turn throughout generating choosing and speaking`() {
        assertEquals(PartnerTurn.YOUR_TURN, partnerTurn(Phase.Listening, glassesReady = true))
        listOf(
            Phase.Choosing("Lunch?", emptyList(), done = false),
            Phase.Choosing("Lunch?", replies.take(1), done = false),
            Phase.Choosing("Lunch?", replies, done = true, focus = Dpad.RIGHT),
            Phase.Choosing(null, QUICK_PHRASES, done = true),
            Phase.Speaking("Coffee instead."),
        ).forEach { phase ->
            assertEquals(PartnerTurn.WEARERS_TURN, partnerTurn(phase, glassesReady = true))
            assertEquals(PartnerTurn.RECONNECTING, partnerTurn(phase, glassesReady = false))
        }
        assertEquals(PartnerTurn.RECONNECTING, partnerTurn(Phase.Listening, glassesReady = false))
        assertEquals(PartnerTurn.PAUSED, partnerTurn(Phase.Off, glassesReady = false))
    }

    @Test
    fun `hearing activity and returning to listening clear the selection cue`() {
        val listening = State(phase = Phase.Listening)
        assertEquals(GlassesCue.LISTENING, screenFor(listening).cue)
        assertEquals(GlassesCue.HEARING, screenFor(listening, hearingSpeech = true).cue)
        assertEquals(GlassesCue.QUIET, screenFor(State()).cue)
        val cleared = reduce(State(phase = Phase.Choosing("Lunch?", replies, true, focus = Dpad.UP)), Event.Input(GlassesInput.Back)).state
        assertNull((cleared.phase as Phase.Choosing).focus)
        assertEquals(GlassesCue.SWIPE_THUMB, screenFor(cleared).cue)
    }
}
