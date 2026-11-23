import QuickTalkCore
import UIKit

@MainActor
enum GlassesRenderer {
    private static let ink = UIColor(red: 1, green: 0.91, blue: 0.76, alpha: 1)

    static func render(_ screen: GlassesScreen, frame: Int) -> UIImage {
        let size = CGSize(width: 600, height: 400)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            switch screen {
            case .status(let status):
                let symbol = status.activity == .speaking ? ["speaker.wave.2", "speaker.wave.3"][frame % 2] :
                    ["mic", "waveform"][status.activity == .hearing ? frame % 2 : 0]
                icon(symbol, at: CGRect(x: 274, y: 107, width: 52, height: 52))
                text(status.title, in: CGRect(x: 30, y: 174, width: 540, height: 50), size: 36)
                if let detail = status.detail {
                    text(detail, in: CGRect(x: 50, y: 232, width: 500, height: 90), size: 30)
                } else if status.offersQuickPhrases {
                    text("Pinch for quick phrases", in: CGRect(x: 80, y: 240, width: 440, height: 42), size: 24)
                }
            case .choices(let choices):
                let slots = [
                    CGRect(x: 150, y: 75, width: 300, height: 74),
                    CGRect(x: 361, y: 154, width: 218, height: 85),
                    CGRect(x: 150, y: 251, width: 300, height: 74),
                    CGRect(x: 21, y: 154, width: 218, height: 85)
                ]
                if let heading = choices.quick ? "Quick phrases" : choices.heard {
                    text(heading, in: CGRect(x: 38, y: 15, width: 524, height: 53), size: 22)
                }
                for position in Dpad.allCases {
                    guard let reply = choices.replies[position.rawValue] else { continue }
                    let slot = slots[position.rawValue]
                    text(reply.emoji + " " + reply.text, in: slot, size: 25)
                    if position == choices.focus {
                        ink.setFill()
                        UIBezierPath(roundedRect: CGRect(x: slot.midX - 42, y: slot.maxY - 2, width: 84, height: 3),
                                     cornerRadius: 1.5).fill()
                    }
                }
                if screen.cue == .generating {
                    text("Finding replies" + String(repeating: ".", count: frame % 3 + 1),
                         in: CGRect(x: 125, y: 172, width: 350, height: 55), size: 29)
                } else {
                    let pinching = choices.focus != nil
                    let hand = pinching ? "hand.pinch" : "hand.point.up.left"
                    let shift = frame % 2 == 0 ? CGFloat(0) : 4
                    icon(hand, at: CGRect(x: 199 + shift, y: 334, width: 35, height: 35))
                    text(pinching ? "Pinch to say" : "Swipe thumb",
                         in: CGRect(x: 226, y: 339, width: 167, height: 42), size: 23)
                }
            }
        }
    }

    private static func icon(_ name: String, at rect: CGRect) {
        UIImage(systemName: name)?.withTintColor(ink, renderingMode: .alwaysOriginal).draw(in: rect)
    }

    private static func text(_ value: String, in rect: CGRect, size: CGFloat) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .center
        paragraph.lineBreakMode = .byTruncatingTail
        (value as NSString).draw(
            with: rect, options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine],
            attributes: [.font: UIFont.systemFont(ofSize: size, weight: .semibold),
                         .foregroundColor: ink, .paragraphStyle: paragraph], context: nil
        )
    }
}
