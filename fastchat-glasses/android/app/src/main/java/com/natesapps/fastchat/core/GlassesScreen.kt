package com.natesapps.fastchat.core

/** What the glasses should be showing, derived from the conversation [State]. */
sealed interface GlassesScreen {
    /** A status line. [offersQuickPhrases] is true while a pinch would open the quick phrases. */
    data class Status(
        val title: String,
        val detail: String? = null,
        val offersQuickPhrases: Boolean = false,
        val activity: GlassesCue = GlassesCue.QUIET,
    ) : GlassesScreen

    /**
     * Four reply slots, one per position in [Dpad] order. A null slot is still being written.
     * [heard] is what the partner said, null for the quick phrases ([quick]). [done] is false
     * while the model is still writing. [focus] is the highlighted slot, if any.
     */
    data class Choices(
        val heard: String?,
        val replies: List<Reply?>,
        val done: Boolean,
        val quick: Boolean,
        val focus: Dpad? = null,
    ) : GlassesScreen
}

/** Longest stretch of the partner's words echoed above the replies. */
private const val HEARD_PREVIEW_CHARS = 70

fun screenFor(state: State, hearingSpeech: Boolean = false): GlassesScreen = when (val phase = state.phase) {
    Phase.Off -> GlassesScreen.Status("Paused")

    Phase.Listening -> GlassesScreen.Status(
        "Listening",
        offersQuickPhrases = true,
        activity = if (hearingSpeech) GlassesCue.HEARING else GlassesCue.LISTENING,
    )

    is Phase.Choosing -> GlassesScreen.Choices(
        heard = phase.heard?.let(::preview),
        replies = Dpad.entries.map { phase.replies.getOrNull(it.ordinal) },
        done = phase.done,
        quick = phase.isQuickPhrases,
        focus = phase.focus,
    )

    is Phase.Speaking -> GlassesScreen.Status("Speaking", phase.text, activity = GlassesCue.SPEAKING)
}

enum class GlassesCue { QUIET, LISTENING, HEARING, GENERATING, SWIPE_THUMB, PINCH, SPEAKING }

/** The first completed reply is enough to start choosing; the other slots can still be empty. */
val GlassesScreen.cue: GlassesCue
    get() = when (this) {
        is GlassesScreen.Status -> activity
        is GlassesScreen.Choices -> when {
            focus != null -> GlassesCue.PINCH
            replies.any { it != null } -> GlassesCue.SWIPE_THUMB
            else -> GlassesCue.GENERATING
        }
    }

/** The end of a long utterance matters most: it is usually the question. */
private fun preview(heard: String): String =
    if (heard.length <= HEARD_PREVIEW_CHARS) heard else "…" + heard.takeLast(HEARD_PREVIEW_CHARS - 1).trimStart()
