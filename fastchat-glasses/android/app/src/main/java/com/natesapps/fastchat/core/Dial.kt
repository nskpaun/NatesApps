package com.natesapps.fastchat.core

/**
 * Turns the Neural Band's continuous pinch-and-drag stream into steps of a dial: hold a pinch and
 * turn the wrist, and every [stepSize] of travel moves the highlight one reply round.
 *
 * What the band sends was measured on a real one, since the toolkit does not document it. The
 * position starts at 0 when the pinch goes down, arrives about 16 times a second, and x tops out
 * at about 0.2 however far the wrist is turned one way; y wanders by less than half that. So only
 * x is used, and a step has to be small enough that one turn of the wrist can reach any of the
 * four replies: at 0.047 a full turn is four steps. (At 0.08 it was only two, and since turning
 * back undoes them, the third and fourth replies needed a second pinch.) Travel to the right is
 * clockwise.
 *
 * The dial has detents: after a step, the wrist has to come a whole step back before the
 * highlight moves back, so a hand resting near a boundary cannot flicker between two replies.
 */
class Dial(private val stepSize: Float = DEFAULT_STEP) {

    private var travel = 0f

    /** Where the last step was taken: the next one is a full [stepSize] from here, either way. */
    private var detent = 0f

    /** True if the drag in progress (or just ended) turned the dial at least one step. */
    var turned = false
        private set

    /** The pinch went down: a new drag starts. */
    fun start() {
        travel = 0f
        detent = 0f
        turned = false
    }

    /**
     * One sample of movement, [dx] being the change in x since the last one. Returns how many
     * steps to take now: positive clockwise, negative the other way, usually 0.
     */
    fun move(dx: Float): Int {
        travel += dx
        var steps = 0
        while (travel - detent >= stepSize) {
            detent += stepSize
            steps++
        }
        while (detent - travel >= stepSize) {
            detent -= stepSize
            steps--
        }
        if (steps != 0) turned = true
        return steps
    }

    companion object {
        /** A quarter of the band's full range one way, so a single turn can reach every reply. */
        const val DEFAULT_STEP = 0.047f
    }
}
