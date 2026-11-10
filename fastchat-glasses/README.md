# FastChat Glasses

An AAC (augmentative and alternative communication) app for people who cannot speak, built for **Meta Ray-Ban Display** glasses and the **Meta Neural Band**.

1. The person you are talking with holds your phone and speaks to it.
2. The phone transcribes what they said and a local language model writes four possible replies.
3. The replies appear on your glasses, laid out up, right, down and left, each with an emoji so it can be read at a glance.
4. You swipe towards one on the Neural Band to highlight it and tap to confirm, and the phone says it aloud.

Everything in a conversation happens on the phone: speech recognition, the language model and the voice. Nothing that is said or written leaves it. The internet is used only to download the models once and to register with the Meta AI app.

| Piece | What runs |
|---|---|
| Hearing | Silero VAD finds the utterance, NVIDIA Parakeet TDT 0.6b v2 transcribes it (via [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)) |
| Replies | [LFM3-1.7B](https://huggingface.co/LiquidAI/LFM3-1.7B) (4-bit `QAD-Q4_0`) on [llama.cpp](https://github.com/ggml-org/llama.cpp) v0.9.0, with a grammar that forces exactly four short lines |
| Glasses | Meta Wearables Device Access Toolkit 1.0.1: Display capability for the screen, Inputs capability for the Neural Band d-pad |
| Voice | Supertonic 3 text-to-speech (via sherpa-onnx), played from the phone's loudspeaker at the volume set in the app |

## Gestures

The four replies sit where their swipe points: up, right, down and left. Nothing is said until you tap.

| Gesture | While listening | While choosing | While speaking |
|---|---|---|---|
| Swipe up / right / down / left | | Highlight that reply | |
| Pinch and turn | | Move the highlight round to the next reply | |
| Tap | Quick phrases: Yes, No, Thank you, Please give me a moment | Say the highlighted reply. With nothing highlighted: four different replies | |
| Back | | Clear the highlight. With nothing highlighted: drop the replies and listen again | Stop talking |

The temple touchpad on the glasses does the same things as the band.

**How the pinch-and-turn works.** The toolkit has no "turn" event. It reports a pinch-and-drag stream, and the dial is built on that. Measured on a real band, the position starts at 0 when the pinch goes down and x tops out at about 0.2 however far the wrist turns one way, so the dial steps every 0.047: one full turn is four steps, enough to reach any reply without letting go. After a step the wrist has to come a whole step back before the highlight moves back, so it cannot flicker between two replies. Debug builds log every drag sample (`adb logcat -s FastChatGlasses`) for further tuning.

**Feedback when the highlight moves.** The toolkit gives apps no way to vibrate the band or the glasses, so each move of the highlight plays a soft click in the glasses' own speakers instead, heard only by the wearer. It follows the glasses' media volume and can be switched off in Settings. If the glasses are not connected as a Bluetooth speaker, nothing is played.

## Status

Working on a Galaxy Z Fold with the toolkit's **simulated** Meta Ray-Ban Display, which goes through the same session, display and input code as a real pair: hearing real speech, writing replies, picking one with a d-pad swipe, and speaking it.

On **real** Meta Ray-Ban Display glasses (Developer Mode): registration through Meta AI, the session, and drawing on the display all work, and the Inputs capability reports active with the Neural Band. A full turn picked with the band has not been confirmed yet.

One thing to know:

- **The d-pad is an experimental capability.** Inputs works in Developer Mode, but it has to be enabled for the app in the [Wearables Developer Center](https://wearables.developer.meta.com) for a registered app, and apps using it cannot be published to production channels yet. Without it the app still works: replies are drawn as cards you move focus between and tap ("tap to pick" in the status chip).

If the status chip says "No glasses in range", open **Settings → Glasses**: it lists each pair Meta AI has shared with the app and what is missing (not connected, not worn, needs an update).

## Install and set up

1. Build and install (below), or install `app-debug.apk`.
2. Open the app and download the models (1.9 GB, once, over Wi-Fi).
3. In **Settings**, enter your name and a few lines about yourself (age, work, family, pets, what you like), and pick a voice.
4. In **Settings → Glasses**, choose **Connect through Meta AI**. This needs the Meta AI app, with Developer Mode on (Meta AI → Settings → App Info → tap the version five times) and the Device Access Toolkit installed on the glasses from there.
5. Press **Start conversation** and hand the phone over.

No glasses? Turn on **Settings → Simulated glasses**: the glasses display and a d-pad appear on the phone.

## Build

Requires JDK 21, the Android SDK (platform 36, build-tools 36, NDK 28.2, CMake 3.31) and `git`. Put the SDK path in `android/local.properties` (`sdk.dir=...`).

```bash
cd fastchat-glasses/android
./gradlew testDebugUnitTest   # the conversation state machine, prompt, parser and downloader
./gradlew assembleDebug       # → app/build/outputs/apk/debug/app-debug.apk
```

The first build clones llama.cpp v0.9.0 into `android/third_party/` and compiles it for arm64.

For a build that registers outside Developer Mode, add your Wearables Developer Center credentials to `android/local.properties`:

```
mwdat_application_id=...
mwdat_client_token=...
```

## Layout

```
fastchat-glasses/android/app/src/main/
  java/com/natesapps/fastchat/
    core/       the conversation as a pure state machine, the prompt and the reply parser (no Android)
    glasses/    GlassesLink: registration, session, display layout, d-pad input, simulated glasses
    llm/        LlamaEngine (JNI) and ReplyWriter (streams replies as each line is finished)
    speech/     Ears (microphone → VAD → transcript) and Voice (text → speech → loudspeaker)
    models/     the model catalogue and the resumable, checksummed downloader
    ui/         the partner-facing talk screen, setup and settings
    FastChat.kt runs the state machine's effects and owns the loaded models
  cpp/          llm_engine (llama.cpp wrapper), its JNI bridge, and a command-line test tool
```

## Testing without anyone talking

Debug builds accept commands from a computer:

```bash
A="adb shell am start -n com.natesapps.fastchat/.MainActivity"
$A --ez start true                              # press Start
$A --es heard "Do you want to get lunch?"       # as if the partner had said this
$A --es gesture down                            # up | right | down | left | cw | ccw | tap | back
$A --ez simulated true                          # switch the simulated glasses on or off
$A --ez reset true                              # forget the conversation so far
$A --es name Sam --es about "I have a dog."      # set the wearer's details
adb logcat -s FastChat                          # timings for hearing, replies and voice
```

`llm_cli` runs the same engine against the model from a shell, on a computer or on the phone:

```bash
cmake -S android/app/src/main/cpp -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llm_cli
build/llm_cli model.gguf prefix.txt suffix.txt grammar.gbnf 3 6    # 3 runs, 6 threads
```

## How the replies are written

The model is run as an ordinary chatbot playing the wearer: the other person's words are the chat's "user" messages and the model answers as the wearer. Before the four replies it writes one bracketed line, never shown, saying what the other person is doing and what the wearer can do about it:

```
Them: I'm going to the store, do you want anything?
(They are going to the store and asking if I want anything. I can say no, or ask for a snack or a coffee.)
1. 🙅 No, I don't need anything.
2. ☕ Maybe some cookies?
3. 🥤 A cold drink would be nice.
4. 🍎 An apple?
```

A model this small, asked straight for "four replies", often answers as the wrong person ("I'm sorry I scratched your car"). Having it state who did what first fixes most of that, and nine worked examples in the prompt teach the format, the length and the perspective. On a deliberately hard test set roughly one reply in ten is still wrong; apologies for damaging the wearer's things are the worst case.

### About you, only when it is needed

The "about you" text is not part of every prompt: a small model that always sees "loves strong coffee" brings coffee into everything. Instead a decision step runs first, a one-word (yes/no) call to the same model asking whether the line just heard is about the wearer's own life or names something from their facts. Only on a yes are the facts added to the reply prompt, right before the line being answered.

| Heard | Decision | A reply offered |
|---|---|---|
| Do you have any pets? | needed | 🐕 My dog is named Biscuit. |
| What do you do for work? | needed | 🎨 I work as a graphic designer. |
| Is this seat taken? | not needed | ❌ No, it's free. |
| What do you want to eat? | not needed | 🍕 Pizza sounds good. |

On the Fold the decision takes about 0.1 s every turn, and a turn that does use the facts spends about 0.15 s more reading them. On a 30-sentence test it decided correctly 25 times; its mistakes lean towards yes for lines that merely touch a fact ("Do you want to get some coffee?"). Without the facts the model invents answers to personal questions ("I work as a barista").

The engine keeps a snapshot for each prompt's fixed part, so the decision prompt and the reply prompt take turns without either being re-read.

"More replies" does not tell the model what to avoid, which does not work at this size. The app asks again with looser sampling and drops anything already offered.

## Speed

Measured on a Galaxy Z Fold (Snapdragon 8 Elite Gen 5, 12 GB), CPU only, six threads:

| Step | Time |
|---|---|
| Loading the models when the app opens | about 4 s |
| Transcribing a 2 to 4 s sentence | 0.1 to 0.5 s |
| Deciding whether "about you" is needed | 0.1 s |
| Reading the new turn (15 to 40 tokens; about 60 with the facts) | 0.1 to 0.3 s |
| Writing the hidden line and four replies (55 to 90 tokens at 45 to 50 tokens per second) | 1.1 to 1.8 s |
| Synthesising a reply (1.4 to 2 s of speech) | 0.4 to 0.8 s |

So all four replies are on the glasses about 1.3 to 2.2 seconds after the sentence is transcribed. The first version used Ternary Bonsai 2 9B, which wrote better replies but took 13 to 17 seconds for the same turn.

Three things make it fast:

- **A small model.** LFM3-1.7B at 4 bits is about 1 GB and runs at 45 to 50 tokens per second on this phone's CPU, against 4 to 5 for the 9B.
- **A lazy grammar check.** Testing every token in the vocabulary against the grammar cost more than running the model for a token. The engine now tests only the model's own pick and falls back to the full check when that pick breaks the format.
- **A cached prefix.** The instructions and worked examples are evaluated once and restored from a snapshot, so each turn only pays for the new sentence.

The phone warms up under continuous use and drops towards 35 tokens per second.

## Volume

The voice has its own volume slider (on the talk screen and in Settings), because the phone's volume keys move the glasses' volume while they are connected and cannot reach the loudspeaker. To make that work the voice plays on Android's alarm channel: the app turns that channel up for the length of each sentence and puts it back afterwards, and silent mode does not mute it.

## When FastChat is on the glasses

Only while a conversation is running. Pressing **Start** opens it on the glasses and **Pause** takes it off again, so a paused or backgrounded app never pushes itself in front of whatever else the wearer is doing. If FastChat is closed on the glasses themselves while a conversation is running, the phone pauses the conversation rather than reopening it. If the Bluetooth link drops mid-conversation, it comes back on its own when the glasses return.

## Limits

- English only (Parakeet v2 and the prompt are English).
- The phone has to be awake with the app in front. There is no background service yet.
- One utterance at a time: the microphone closes while you choose and while the phone speaks.
- The voice names are just "Voice 1" to "Voice 10"; pick by ear.

## Licences of what it downloads

LFM3-1.7B: LFM Open License v1.0, which allows commercial use only below $10M annual revenue. Parakeet TDT 0.6b v2: CC-BY-4.0 (NVIDIA). Silero VAD: MIT. Supertonic 3: BigScience OpenRAIL-M, which has use-based restrictions worth reading before distributing the app. sherpa-onnx and llama.cpp: Apache-2.0 and MIT.
