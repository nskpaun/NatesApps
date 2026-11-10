package com.natesapps.fastchat.core

/** What the glasses should be showing, derived from the conversation [State]. */
sealed interface GlassesScreen {
    /** A status line. [offersQuickPhrases] is true while a pinch would open the quick phrases. */
    data class Status(
        val title: String,
        val detail: String? = null,
        val offersQuickPhrases: Boolean = false,
    ) : GlassesScreen

    /**
     * Four reply slots, one per d-pad direction in [Dpad] order. A null slot is still being
     * written. [heard] is what the partner said, null for the quick phrases ([quick]).
     * [done] is false while the model is still writing.
     */
    data class Choices(
        val heard: String?,
        val replies: List<String?>,
        val done: Boolean,
        val quick: Boolean,
    ) : GlassesScreen
}

/** Longest stretch of the partner's words echoed above the replies. */
private const val HEARD_PREVIEW_CHARS = 70

fun screenFor(state: State): GlassesScreen = when (val phase = state.phase) {
    Phase.Off -> GlassesScreen.Status("FastChat", "Paused")

    Phase.Listening -> GlassesScreen.Status("Listening…", offersQuickPhrases = true)

    is Phase.Choosing -> GlassesScreen.Choices(
        heard = phase.heard?.let(::preview),
        replies = Dpad.entries.map { phase.replies.getOrNull(it.ordinal) },
        done = phase.done,
        quick = phase.isQuickPhrases,
    )

    is Phase.Speaking -> GlassesScreen.Status("Saying", phase.text)
}

/** The end of a long utterance matters most: it is usually the question. */
private fun preview(heard: String): String =
    if (heard.length <= HEARD_PREVIEW_CHARS) heard else "…" + heard.takeLast(HEARD_PREVIEW_CHARS - 1).trimStart()
