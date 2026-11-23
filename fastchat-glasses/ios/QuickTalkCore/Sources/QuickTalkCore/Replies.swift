import Foundation

/// Who the replies are written for; set by the wearer in Settings.
public struct Persona: Equatable, Sendable {
    public var name: String
    public var about: String
    public init(name: String = "", about: String = "") {
        self.name = name
        self.about = about
    }
}

/// Longest reply the grammar allows, in characters. Keeps each one to a line on the glasses.
public let maxReplyChars = 50

public let replyCount = 4

extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}

/// Builds the model prompt and reads the replies back out of the model's answer.
///
/// The model (LFM3) is run as an ordinary chatbot playing the wearer: the other person's words are
/// the chat's "user" messages and the model answers as the wearer. Before the four replies it
/// writes one bracketed line, never shown, saying what the other person is doing and what the
/// wearer can do about it; having it state who did what first stops a small model answering as
/// the wrong person. See the Android `core/Replies.kt`, which this must match byte for byte so
/// both apps share the same tuned prompt.
public enum ReplyPrompt {
    private static let bos = "<|startoftext|>"

    /// Opens the model's turn with thinking switched off (an empty think block).
    private static let generate = "<|im_start|>assistant\n<think></think>"

    /// GBNF grammar the sampler is constrained to: the bracketed line, then exactly four numbered
    /// lines, each an emoji, a space and a short sentence.
    public static let grammar: String = {
        var out = #"root ::= "(They " [^\n\r()]{5,70} " I can " [^\n\r()]{5,110} ")\n" "#
        out += (1...replyCount).map { #""\#($0). " line"# }.joined(separator: #" "\n" "#)
        out += "\n"
        out += #"line ::= emoji " " [^\n\r<(]{2,\#(maxReplyChars)}"# + "\n"
        // One pictograph, optionally followed by the "show as emoji" variation selector.
        out += #"emoji ::= [\U0001F300-\U0001FAFF☀-➿] [️]?"# + "\n"
        return out
    }()

    public static func system(_ persona: Persona) -> String {
        let name = persona.name.trimmed
        var out = name.isEmpty ? "You are a person" : "You are \(name)"
        out += ". You are talking face to face with another person, and each message is something they say to you.\n"
        out += "First write, in brackets, what they are doing and \(replyCount) different things you can do about it. "
        out += "Then write the \(replyCount) short replies you would say to them, one for each, each starting with one emoji."
        return out
    }

    /// Worked examples, one per kind of thing people say. They are part of the cached prefix, so
    /// they cost nothing per turn.
    private static let examples: [(String, String)] = [
        ("Sorry I'm late, the traffic was terrible.",
         "(They are apologizing to me for being late. I can forgive them, be annoyed, ask what happened, or move on.)\n" +
         "1. 😊 That's okay, don't worry.\n2. 😠 I waited a long time.\n3. ❓ What happened?\n4. 🍽️ Let's go and eat."),
        ("Are you hungry?",
         "(They are asking if I am hungry. I can say yes, say no, ask what there is, or ask for a drink.)\n" +
         "1. 😋 Yes, I'm starving.\n2. 🙅 No, I just ate.\n3. ❓ What is there to eat?\n4. ☕ I'd just like a drink."),
        ("What do you want to drink?",
         "(They are asking what I want to drink. I can ask for water, coffee, or juice, or say nothing.)\n" +
         "1. 💧 Just water, please.\n2. ☕ A coffee would be great.\n3. 🧃 Some juice, if you have it.\n4. 🙅 Nothing for me, thanks."),
        ("I got the job!",
         "(They are telling me their good news. I can congratulate them, be sad they are leaving, ask when they start, or suggest a party.)\n" +
         "1. 🎉 Congratulations, that's wonderful!\n2. 😟 Oh, I'll miss you here.\n3. ❓ When do you start?\n4. 🥂 We should celebrate."),
        ("Do you want me to carry your bag?",
         "(They are offering to carry my bag. I can accept, refuse, check it is not too heavy for them, or say later.)\n" +
         "1. 🙏 Yes please, thank you.\n2. 🙅 No thanks, I've got it.\n3. ❓ Are you sure it's not too heavy?\n4. 😌 Maybe in a minute."),
        ("Thanks for helping me move yesterday.",
         "(They are thanking me for helping them move. I can say you're welcome, say it was hard, ask about their new place, or joke that they owe me.)\n" +
         "1. 😊 You're welcome, happy to help.\n2. 😩 It was hard work, honestly.\n3. ❓ How is the new place?\n4. 🍕 You owe me a pizza."),
        ("Where do you want to sit?",
         "(They are asking where I want to sit. I can pick the window, the door, or outside, or say I don't mind.)\n" +
         "1. 🪟 By the window.\n2. 🚪 Near the door.\n3. ☀️ Outside, if it's warm.\n4. 🤷 Anywhere is fine."),
        ("I love your shoes!",
         "(They are complimenting my shoes. I can thank them, be modest, say where I got them, or say they are comfortable.)\n" +
         "1. 😊 Thank you!\n2. 😅 They're really old.\n3. 🛍️ I got them in town.\n4. 👟 They're very comfortable."),
        ("I broke your mug, I'm really sorry.",
         "(They are apologizing for breaking my mug. I can forgive them, be upset, ask how it happened, or ask them to replace it.)\n" +
         "1. 😊 It's fine, it was only a mug.\n2. 😢 Oh no, I loved that mug.\n3. ❓ How did it happen?\n4. ☕ You can buy me a new one."),
    ]

    private static func them(_ text: String) -> String { "<|im_start|>user\n\(text.trimmed)<|im_end|>\n" }

    private static func me(_ text: String) -> String { "<|im_start|>assistant\n<think></think>\(text.trimmed)<|im_end|>\n" }

    /// The part of the prompt that only changes when the wearer's name does: the instructions and
    /// the worked examples. The engine evaluates it once and keeps a snapshot.
    public static func systemBlock(_ persona: Persona) -> String {
        var out = bos + "<|im_start|>system\n" + system(persona) + "<|im_end|>\n"
        for (said, answer) in examples { out += them(said) + me(answer) }
        return out
    }

    /// The part of the prompt that changes every turn: the conversation so far as real chat turns,
    /// then the model's turn. `facts` is the wearer's "about you" text, passed only when this turn
    /// needs it (see `PersonaCheck`).
    ///
    /// Lines in a row from one speaker become one turn. For the wearer they are joined. For the
    /// other person only the last is kept: an earlier line is one the wearer chose not to answer.
    public static func turnBlock(_ history: [Turn], facts: String? = nil) -> String {
        var blocks: [String] = []
        var index = 0
        while index < history.count {
            let speaker = history[index].speaker
            var run: [String] = []
            while index < history.count, history[index].speaker == speaker {
                run.append(history[index].text.replacingOccurrences(of: "\n", with: " ").trimmed)
                index += 1
            }
            blocks.append(speaker == .partner ? them(run.last!) : me(run.joined(separator: " ")))
        }
        if let facts, !facts.trimmed.isEmpty, !blocks.isEmpty {
            blocks.insert(
                "<|im_start|>system\nFacts about you, in case they help you answer: \(facts.trimmed)<|im_end|>\n",
                at: blocks.count - 1
            )
        }
        return blocks.joined() + generate
    }

    public static func build(_ persona: Persona, _ history: [Turn]) -> String {
        systemBlock(persona) + turnBlock(history)
    }
}

/// The decision step: a one-word model call, made before the replies are written, that says
/// whether answering this line needs the wearer's "about you" facts. The facts are then sent with
/// the reply prompt only when the answer is yes.
public enum PersonaCheck {
    /// The model may only answer with one of these two words.
    public static let grammar = #"root ::= "yes" | "no""# + "\n"

    private static let examples: [(String, String)] = [
        ("How old are you?", "yes"),
        ("Sorry I'm late.", "no"),
        ("Do you have any pets?", "yes"),
        ("What do you want to drink?", "no"),
        ("What do you do for work?", "yes"),
        ("Can I borrow your pen?", "no"),
        ("Who do you live with?", "yes"),
        ("Nice weather today.", "no"),
        ("What do you do for fun?", "yes"),
        ("Thanks for your help!", "no"),
        ("Do you want to go for a walk?", "no"),
        ("Where did you two meet?", "yes"),
        ("I love your scarf.", "no"),
        ("Goodbye, see you soon!", "no"),
    ]

    /// The fixed part: the facts, the rule and the examples. Changes only with the persona.
    public static func systemBlock(_ persona: Persona) -> String {
        let trimmedName = persona.name.trimmed
        let name = trimmedName.isEmpty ? "this person" : trimmedName
        var out = "<|startoftext|><|im_start|>system\n"
        out += "Facts about \(name): \(persona.about.trimmed)\n\n"
        out += "Each message is something another person says to \(name). Answer yes only if it is a question about "
        out += "\(name)'s own life (age, work, home, family, pets, likes) or names someone or something from the facts. "
        out += "Greetings, thanks, compliments, offers, invitations and news are no."
        out += "<|im_end|>\n"
        for (said, answer) in examples {
            out += "<|im_start|>user\n\(said)<|im_end|>\n<|im_start|>assistant\n<think></think>\(answer)<|im_end|>\n"
        }
        return out
    }

    /// The part that changes: the line just heard, then the model's one-word turn.
    public static func turnBlock(_ said: String) -> String {
        "<|im_start|>user\n\(said.replacingOccurrences(of: "\n", with: " ").trimmed)<|im_end|>\n<|im_start|>assistant\n<think></think>"
    }

    public static func saysYes(_ answer: String) -> Bool {
        answer.trimmed.lowercased().hasPrefix("yes")
    }
}

public enum ReplyParser {
    /// Replies finished so far in `text`, the model's output up to now. A line counts once the
    /// newline after it has arrived, or once `finished` says the model has stopped, so a reply is
    /// never shown (or spoken) half written.
    public static func parse(_ text: String, finished: Bool) -> [Reply] {
        let lines = text.components(separatedBy: "\n")
        let complete = finished ? lines[...] : lines.dropLast()
        return Array(
            complete
                .compactMap(numberedBody)
                .map(reply)
                .filter { !$0.text.isEmpty }
                .prefix(replyCount)
        )
    }

    /// The text after "3." or "3)" at the start of a line, or nil if the line is not numbered.
    private static func numberedBody(_ line: String) -> String? {
        var rest = Substring(line).drop(while: { $0.isWhitespace })
        let digits = rest.prefix(while: { $0.isASCII && $0.isNumber })
        guard !digits.isEmpty else { return nil }
        rest = rest.dropFirst(digits.count).drop(while: { $0.isWhitespace })
        guard let mark = rest.first, mark == "." || mark == ")" else { return nil }
        return String(rest.dropFirst().drop(while: { $0.isWhitespace }))
    }

    /// Splits "👍 Yes, I would." into its emoji and its words; a line without an emoji is fine.
    private static func reply(_ line: String) -> Reply {
        let trimmed = line.trimmed
        let first = trimmed.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init) ?? ""
        if !first.isEmpty, first != trimmed, isEmoji(first) {
            return Reply(first, clean(String(trimmed.dropFirst(first.count))))
        }
        return Reply("", clean(trimmed))
    }

    /// Pictographs and symbols only: nothing a sentence would start with.
    private static func isEmoji(_ token: String) -> Bool {
        token.unicodeScalars.allSatisfy { $0.value >= 0x2190 }
    }

    /// The words only: no stray emoji, asterisks or quotation marks. What is left is spoken aloud.
    private static func clean(_ reply: String) -> String {
        var words = String.UnicodeScalarView()
        for scalar in reply.unicodeScalars where scalar.value < 0x2190 && scalar != "*" {
            words.append(scalar)
        }
        let quotes = CharacterSet(charactersIn: "\"\u{201C}\u{201D}")
        return String(words).trimmed.trimmingCharacters(in: quotes).trimmed
    }

    /// The same reply, as far as a listener could tell: used to drop repeats.
    public static func sameWords(_ reply: String) -> String {
        String(reply.lowercased().filter { $0.isLetter || $0.isNumber })
    }
}
