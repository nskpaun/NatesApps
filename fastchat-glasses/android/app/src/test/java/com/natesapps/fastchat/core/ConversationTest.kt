package com.natesapps.fastchat.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ConversationTest {

    private val four = listOf(
        Reply("👍", "Yes, I'd love to."),
        Reply("🙅", "No, not today."),
        Reply("❓", "Where would we go?"),
        Reply("🤷", "Maybe later."),
    )

    /** Feeds [events] through the reducer, returning the final state and every effect in order. */
    private fun run(vararg events: Event, from: State = State()): Pair<State, List<Effect>> {
        var state = from
        val effects = mutableListOf<Effect>()
        for (event in events) {
            val step = reduce(state, event)
            state = step.state
            effects += step.effects
        }
        return state to effects
    }

    private fun input(input: GlassesInput) = Event.Input(input)

    private fun highlight(direction: Dpad) = input(GlassesInput.Highlight(direction))

    private val tap = input(GlassesInput.Confirm)
    private val back = input(GlassesInput.Back)

    private fun turn(clockwise: Boolean) = input(GlassesInput.Turn(clockwise))

    private fun choosing(): State = run(
        Event.Start,
        Event.Heard("Do you want to get lunch?"),
        Event.Replies(generation = 1, replies = four, done = true),
    ).first

    private fun focusOf(state: State): Dpad? = (state.phase as Phase.Choosing).focus

    @Test
    fun `a full turn listens, offers replies, speaks the tapped one and listens again`() {
        val (state, effects) = run(
            Event.Start,
            Event.Heard("Do you want to get lunch?"),
            Event.Replies(1, four.take(2), done = false),
            Event.Replies(1, four, done = true),
            highlight(Dpad.DOWN),
            tap,
            Event.SpeechFinished,
        )

        assertEquals(Phase.Listening, state.phase)
        assertEquals(
            listOf(
                Turn(Speaker.PARTNER, "Do you want to get lunch?"),
                Turn(Speaker.ME, "Where would we go?"),
            ),
            state.history,
        )
        assertEquals(
            listOf(
                Effect.StartListening,
                Effect.Generate(1, listOf(Turn(Speaker.PARTNER, "Do you want to get lunch?")), emptyList()),
                Effect.CancelGeneration,
                Effect.Speak("Where would we go?"),
                Effect.StartListening,
            ),
            effects,
        )
    }

    @Test
    fun `a swipe only highlights, nothing is said until the tap`() {
        val (state, effects) = run(highlight(Dpad.RIGHT), from = choosing())
        assertEquals(Dpad.RIGHT, focusOf(state))
        assertTrue(effects.isEmpty())

        // Changing your mind is just another swipe.
        val (changed, _) = run(highlight(Dpad.LEFT), from = state)
        assertEquals(Dpad.LEFT, focusOf(changed))
    }

    @Test
    fun `each direction holds the reply in its slot`() {
        val expected = mapOf(Dpad.UP to four[0], Dpad.RIGHT to four[1], Dpad.DOWN to four[2], Dpad.LEFT to four[3])
        for ((direction, reply) in expected) {
            val (state, _) = run(highlight(direction), tap, from = choosing())
            assertEquals(Phase.Speaking(reply.text), state.phase)
        }
    }

    @Test
    fun `the emoji is shown on the glasses but never spoken or sent back to the model`() {
        val (state, effects) = run(highlight(Dpad.UP), tap, from = choosing())
        assertEquals(Effect.Speak("Yes, I'd love to."), effects.last())
        assertEquals(Turn(Speaker.ME, "Yes, I'd love to."), state.history.last())
        assertEquals(four[0], (screenFor(choosing()) as GlassesScreen.Choices).replies[0])
    }

    @Test
    fun `turning the dial moves the highlight round the replies, both ways`() {
        val start = choosing()
        // Clockwise from nothing: top, right, bottom, left, and round to the top again.
        var state = start
        val clockwise = (1..5).map { state = run(turn(true), from = state).first; focusOf(state) }
        assertEquals(listOf(Dpad.UP, Dpad.RIGHT, Dpad.DOWN, Dpad.LEFT, Dpad.UP), clockwise)

        // The other way from nothing starts at the left.
        state = start
        val anticlockwise = (1..3).map { state = run(turn(false), from = state).first; focusOf(state) }
        assertEquals(listOf(Dpad.LEFT, Dpad.DOWN, Dpad.RIGHT), anticlockwise)

        // And a tap says whatever the dial stopped on.
        assertEquals(Phase.Speaking(four[1].text), run(tap, from = state).first.phase)
    }

    @Test
    fun `the dial skips slots whose reply has not been written yet`() {
        val partial = run(Event.Start, Event.Heard("Coffee?"), Event.Replies(1, four.take(2), done = false)).first
        var state = partial
        val seen = (1..4).map { state = run(turn(true), from = state).first; focusOf(state) }
        assertEquals(listOf(Dpad.UP, Dpad.RIGHT, Dpad.UP, Dpad.RIGHT), seen)

        val empty = run(Event.Start, Event.Heard("Coffee?")).first
        assertNull(focusOf(run(turn(true), from = empty).first))
    }

    @Test
    fun `a reply can be highlighted and said while the others are still being written`() {
        val (state, effects) = run(
            Event.Start,
            Event.Heard("Coffee?"),
            Event.Replies(1, four.take(1), done = false),
            highlight(Dpad.UP),
            Event.Replies(1, four.take(3), done = false), // the highlight survives new replies arriving
            tap,
        )
        assertEquals(Phase.Speaking(four[0].text), state.phase)
        assertTrue(Effect.CancelGeneration in effects)
    }

    @Test
    fun `swiping towards a slot that has no reply yet does nothing`() {
        val before = run(Event.Start, Event.Heard("Coffee?"), Event.Replies(1, four.take(1), done = false)).first
        val (after, effects) = run(highlight(Dpad.LEFT), from = before)
        assertEquals(before, after)
        assertTrue(effects.isEmpty())
    }

    @Test
    fun `a tap with nothing highlighted asks for new replies and remembers the old ones`() {
        val (state, effects) = run(tap, from = choosing())

        val phase = state.phase as Phase.Choosing
        assertTrue(phase.replies.isEmpty())
        assertEquals(1, phase.round)
        assertEquals(Effect.Generate(2, state.history, avoid = four.map { it.text }), effects.last())

        // A second "more" avoids both earlier sets, and starts with nothing highlighted.
        val second = listOf("Sure.", "I can't.", "What time?", "Let me think.").map { Reply("🙂", it) }
        val (again, againEffects) = run(Event.Replies(2, second, done = true), tap, from = state)
        assertEquals((four + second).map { it.text }, (againEffects.last() as Effect.Generate).avoid)
        assertNull(focusOf(again))
    }

    @Test
    fun `replies from a superseded request are ignored`() {
        val afterMore = run(tap, from = choosing()).first
        val (state, _) = run(Event.Replies(generation = 1, replies = four, done = true), from = afterMore)
        assertTrue((state.phase as Phase.Choosing).replies.isEmpty())
    }

    @Test
    fun `back first clears the highlight, then drops the replies and listens again`() {
        val highlighted = run(highlight(Dpad.UP), from = choosing()).first

        val (cleared, noEffects) = run(back, from = highlighted)
        assertNull(focusOf(cleared))
        assertTrue(noEffects.isEmpty())

        val (state, effects) = run(back, from = cleared)
        assertEquals(Phase.Listening, state.phase)
        assertEquals(listOf(Effect.CancelGeneration, Effect.StartListening), effects)
        assertEquals(1, state.history.size) // what the partner said is kept
    }

    @Test
    fun `a tap while listening offers quick phrases, and a second tap goes back`() {
        val (quick, effects) = run(Event.Start, tap)
        val phase = quick.phase as Phase.Choosing
        assertTrue(phase.isQuickPhrases)
        assertEquals(QUICK_PHRASES, phase.replies)
        assertEquals(Effect.StopListening, effects.last())

        val (said, _) = run(highlight(Dpad.UP), tap, from = quick)
        assertEquals(Phase.Speaking("Yes"), said.phase)

        val (listening, backEffects) = run(tap, from = quick)
        assertEquals(Phase.Listening, listening.phase)
        assertEquals(listOf<Effect>(Effect.StartListening), backEffects)
    }

    @Test
    fun `swipes and turns while listening do nothing`() {
        val listening = run(Event.Start).first
        assertEquals(listening, run(highlight(Dpad.UP), turn(true), from = listening).first)
    }

    @Test
    fun `speech heard while replies are showing does not replace them`() {
        val before = choosing()
        val (after, effects) = run(Event.Heard("Hello? Are you there?"), from = before)
        assertEquals(before, after)
        assertTrue(effects.isEmpty())
    }

    @Test
    fun `if the model fails the wearer still gets quick phrases`() {
        val (state, _) = run(Event.Start, Event.Heard("Hi"), Event.GenerationFailed(1, "out of memory"))
        assertEquals(QUICK_PHRASES, (state.phase as Phase.Choosing).replies)
        assertEquals("out of memory", state.problem)
    }

    @Test
    fun `back while speaking stops the voice`() {
        val speaking = run(highlight(Dpad.UP), tap, from = choosing()).first
        val (state, effects) = run(back, from = speaking)
        assertEquals(Phase.Listening, state.phase)
        assertEquals(listOf(Effect.StopSpeaking, Effect.StartListening), effects)
    }

    @Test
    fun `stop shuts everything down from any phase`() {
        val (state, effects) = run(Event.Stop, from = choosing())
        assertEquals(Phase.Off, state.phase)
        assertEquals(listOf(Effect.StopListening, Effect.CancelGeneration, Effect.StopSpeaking), effects)
    }

    @Test
    fun `blank speech is ignored and history is capped`() {
        val (blank, _) = run(Event.Start, Event.Heard("   "))
        assertEquals(Phase.Listening, blank.phase)

        var state = run(Event.Start).first
        repeat(HISTORY_TURNS) { i ->
            state = run(
                Event.Heard("question $i"),
                Event.Replies(state.generation + 1, four, done = true),
                highlight(Dpad.UP),
                tap,
                Event.SpeechFinished,
                from = state,
            ).first
        }
        assertEquals(HISTORY_TURNS, state.history.size)
        assertEquals(Turn(Speaker.ME, four[0].text), state.history.last())
    }

    @Test
    fun `the glasses screen follows the phase and carries the highlight`() {
        assertEquals(
            GlassesScreen.Status("Listening…", offersQuickPhrases = true),
            screenFor(run(Event.Start).first),
        )

        val partial = run(Event.Start, Event.Heard("Lunch?"), Event.Replies(1, four.take(2), done = false)).first
        assertEquals(
            GlassesScreen.Choices("Lunch?", listOf(four[0], four[1], null, null), done = false, quick = false),
            screenFor(partial),
        )

        val highlighted = run(highlight(Dpad.RIGHT), from = choosing()).first
        assertEquals(Dpad.RIGHT, (screenFor(highlighted) as GlassesScreen.Choices).focus)

        val speaking = run(tap, from = highlighted).first
        assertEquals(GlassesScreen.Status("Saying", four[1].text), screenFor(speaking))
    }

    @Test
    fun `a long utterance is previewed by its ending`() {
        val long = "So I was thinking about the weekend and all the things we could do. " +
            "Would you rather go to the beach or stay home and watch a film?"
        val screen = screenFor(run(Event.Start, Event.Heard(long)).first) as GlassesScreen.Choices
        assertTrue(screen.heard!!.startsWith("…"))
        assertTrue(screen.heard!!.endsWith("watch a film?"))
        assertTrue(screen.heard!!.length <= 70)
        assertNull((screenFor(run(Event.Start, tap).first) as GlassesScreen.Choices).heard)
    }
}
