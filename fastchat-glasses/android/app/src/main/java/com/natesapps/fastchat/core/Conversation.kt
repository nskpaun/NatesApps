package com.natesapps.fastchat.core

/**
 * The conversation as a pure state machine: [reduce] takes the current [State] and an [Event] and
 * returns the next state plus the [Effect]s to run. Nothing here touches Android, audio, the model
 * or the glasses, so the whole flow is unit-tested on the JVM.
 *
 * One turn: Listening → (partner speaks) → Choosing (replies arrive one by one) → (d-pad pick)
 * → Speaking → Listening.
 */

/** The four d-pad directions, in the order replies are assigned to them. */
enum class Dpad { UP, RIGHT, DOWN, LEFT }

/** What the wearer can do from the glasses. */
sealed interface GlassesInput {
    /** A d-pad swipe: say the reply in that slot. */
    data class Pick(val direction: Dpad) : GlassesInput

    /** A pinch: other replies while choosing, quick phrases while listening. */
    data object More : GlassesInput

    /** Back: drop the current replies (or stop speaking) and listen again. */
    data object Back : GlassesInput
}

enum class Speaker { PARTNER, ME }

data class Turn(val speaker: Speaker, val text: String)

sealed interface Phase {
    /** Conversation not running. */
    data object Off : Phase

    /** Microphone open, waiting for the partner to say something. */
    data object Listening : Phase

    /**
     * Replies on the glasses. [heard] is what the partner said, or null for quick phrases.
     * [replies] fills up while the model writes; [done] turns true when it has finished.
     */
    data class Choosing(
        val heard: String?,
        val replies: List<String>,
        val done: Boolean,
        val round: Int = 0,
    ) : Phase {
        val isQuickPhrases: Boolean get() = heard == null
    }

    /** The picked reply is being spoken from the phone. */
    data class Speaking(val text: String) : Phase
}

data class State(
    val phase: Phase = Phase.Off,
    val history: List<Turn> = emptyList(),
    /** Id of the current reply request; updates carrying an older id are dropped. */
    val generation: Int = 0,
    /** Replies already offered for the current partner turn, so "more" does not repeat them. */
    val offered: List<String> = emptyList(),
    /** Last problem worth showing on the phone, cleared when the next turn starts. */
    val problem: String? = null,
)

sealed interface Event {
    data object Start : Event
    data object Stop : Event
    data class Heard(val text: String) : Event
    data class Replies(val generation: Int, val replies: List<String>, val done: Boolean) : Event
    data class GenerationFailed(val generation: Int, val message: String) : Event
    data class Input(val input: GlassesInput) : Event
    data object SpeechFinished : Event
    data class Problem(val message: String) : Event
}

sealed interface Effect {
    data object StartListening : Effect
    data object StopListening : Effect
    data class Generate(val generation: Int, val history: List<Turn>, val avoid: List<String>) : Effect
    data object CancelGeneration : Effect
    data class Speak(val text: String) : Effect
    data object StopSpeaking : Effect
}

data class Step(val state: State, val effects: List<Effect> = emptyList())

/** How many turns of the conversation the model is shown. */
const val HISTORY_TURNS = 8

/** Fixed replies offered on a pinch while listening; no model needed, so they are instant. */
val QUICK_PHRASES = listOf("Yes", "No", "Thank you", "Please give me a moment")

fun reduce(state: State, event: Event): Step {
    val phase = state.phase
    return when (event) {
        Event.Start ->
            if (phase == Phase.Off) listen(state.copy(problem = null)) else Step(state)

        Event.Stop ->
            Step(
                state.copy(phase = Phase.Off, offered = emptyList()),
                listOf(Effect.StopListening, Effect.CancelGeneration, Effect.StopSpeaking),
            )

        is Event.Heard -> {
            val text = event.text.trim()
            if (phase != Phase.Listening || text.isEmpty()) return Step(state)
            val history = (state.history + Turn(Speaker.PARTNER, text)).takeLast(HISTORY_TURNS)
            val generation = state.generation + 1
            Step(
                state.copy(
                    phase = Phase.Choosing(heard = text, replies = emptyList(), done = false),
                    history = history,
                    generation = generation,
                    offered = emptyList(),
                    problem = null,
                ),
                listOf(Effect.Generate(generation, history, avoid = emptyList())),
            )
        }

        is Event.Replies -> {
            if (phase !is Phase.Choosing || phase.isQuickPhrases || event.generation != state.generation) {
                return Step(state)
            }
            Step(state.copy(phase = phase.copy(replies = event.replies.take(Dpad.entries.size), done = event.done)))
        }

        is Event.GenerationFailed -> {
            if (phase !is Phase.Choosing || event.generation != state.generation) return Step(state)
            // The wearer must never be left with nothing to say: fall back to the fixed phrases.
            Step(
                state.copy(
                    phase = Phase.Choosing(heard = null, replies = QUICK_PHRASES, done = true),
                    problem = event.message,
                ),
            )
        }

        is Event.Input -> onInput(state, event.input)

        Event.SpeechFinished ->
            if (phase is Phase.Speaking) listen(state) else Step(state)

        is Event.Problem -> Step(state.copy(problem = event.message))
    }
}

private fun listen(state: State): Step =
    Step(state.copy(phase = Phase.Listening, offered = emptyList()), listOf(Effect.StartListening))

private fun onInput(state: State, input: GlassesInput): Step {
    return when (val phase = state.phase) {
        Phase.Off -> Step(state)

        Phase.Listening -> when (input) {
            GlassesInput.More ->
                Step(
                    state.copy(phase = Phase.Choosing(heard = null, replies = QUICK_PHRASES, done = true)),
                    listOf(Effect.StopListening),
                )
            else -> Step(state)
        }

        is Phase.Choosing -> when (input) {
            is GlassesInput.Pick -> {
                // A reply can be picked as soon as it is on screen, without waiting for the rest.
                val text = phase.replies.getOrNull(input.direction.ordinal) ?: return Step(state)
                Step(
                    state.copy(
                        phase = Phase.Speaking(text),
                        history = (state.history + Turn(Speaker.ME, text)).takeLast(HISTORY_TURNS),
                        offered = emptyList(),
                    ),
                    listOf(Effect.CancelGeneration, Effect.Speak(text)),
                )
            }

            GlassesInput.More -> {
                if (phase.isQuickPhrases) return listen(state)
                val offered = (state.offered + phase.replies).distinct()
                val generation = state.generation + 1
                Step(
                    state.copy(
                        phase = phase.copy(replies = emptyList(), done = false, round = phase.round + 1),
                        generation = generation,
                        offered = offered,
                    ),
                    listOf(Effect.CancelGeneration, Effect.Generate(generation, state.history, avoid = offered)),
                )
            }

            GlassesInput.Back -> {
                val step = listen(state)
                step.copy(effects = listOf(Effect.CancelGeneration) + step.effects)
            }
        }

        is Phase.Speaking -> when (input) {
            GlassesInput.Back -> {
                val step = listen(state)
                step.copy(effects = listOf(Effect.StopSpeaking) + step.effects)
            }
            else -> Step(state)
        }
    }
}
