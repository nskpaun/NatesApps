/// Turns the Neural Band's continuous pinch-and-drag stream into steps of a dial: hold a pinch and
/// turn the wrist, and every `stepSize` of travel moves the highlight one reply round.
///
/// What the band sends was measured on a real one (see the Android `core/Dial.kt` for the full
/// notes): the position starts at 0 when the pinch goes down and x tops out at about 0.2 however
/// far the wrist turns one way, so at 0.047 a full turn is four steps. Travel to the right is
/// clockwise.
///
/// The dial has detents: after a step, the wrist has to come a whole step back before the
/// highlight moves back, so a hand resting near a boundary cannot flicker between two replies.
public struct Dial: Sendable {
    /// A quarter of the band's full range one way, so a single turn can reach every reply.
    public static let defaultStep: Float = 0.047

    public let stepSize: Float
    private var travel: Float = 0
    /// Where the last step was taken: the next one is a full `stepSize` from here, either way.
    private var detent: Float = 0

    /// True if the drag in progress (or just ended) turned the dial at least one step.
    public private(set) var turned = false

    public init(stepSize: Float = Dial.defaultStep) {
        self.stepSize = stepSize
    }

    /// The pinch went down: a new drag starts.
    public mutating func start() {
        travel = 0
        detent = 0
        turned = false
    }

    /// One sample of movement, `dx` being the change in x since the last one. Returns how many
    /// steps to take now: positive clockwise, negative the other way, usually 0.
    public mutating func move(_ dx: Float) -> Int {
        travel += dx
        var steps = 0
        while travel - detent >= stepSize {
            detent += stepSize
            steps += 1
        }
        while detent - travel >= stepSize {
            detent -= stepSize
            steps -= 1
        }
        if steps != 0 { turned = true }
        return steps
    }
}
