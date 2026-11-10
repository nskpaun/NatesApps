# FastChat Glasses

An AAC (augmentative and alternative communication) app for people who cannot speak, built for **Meta Ray-Ban Display** glasses and the **Meta Neural Band**.

1. The person you are talking with holds your phone and speaks to it.
2. The phone transcribes what they said and a local language model writes four possible replies.
3. The replies appear on your glasses, one per d-pad direction, each with an emoji so it can be read at a glance.
4. You swipe up, right, down or left on the Neural Band, and the phone says that reply aloud.

Everything in a conversation happens on the phone: speech recognition, the language model and the voice. Nothing that is said or written leaves it. The internet is used only to download the models once and to register with the Meta AI app.

| Piece | What runs |
|---|---|
| Hearing | Silero VAD finds the utterance, NVIDIA Parakeet TDT 0.6b v2 transcribes it (via [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)) |
| Replies | [Ternary Bonsai 2 9B](https://huggingface.co/prism-ml/Ternary-Bonsai-2-9B-gguf) (`Q2_0`) on [llama.cpp](https://github.com/ggml-org/llama.cpp) v0.9.0, with a grammar that forces exactly four short lines |
| Glasses | Meta Wearables Device Access Toolkit 1.0.1: Display capability for the screen, Inputs capability for the Neural Band d-pad |
| Voice | Supertonic 3 text-to-speech (via sherpa-onnx), played from the phone's loudspeaker at the volume set in the app |

## Gestures

| Gesture | While listening | While choosing | While speaking |
|---|---|---|---|
| Swipe up / right / down / left | | Say that reply (as soon as it is on screen) | |
| Pinch | Quick phrases: Yes, No, Thank you, Please give me a moment | Four different replies | |
| Back | | Drop the replies and listen again | Stop talking |

The temple touchpad on the glasses does the same things as the band.

## Status

Working on a Galaxy Z Fold with the toolkit's **simulated** Meta Ray-Ban Display, which goes through the same session, display and input code as a real pair: hearing real speech, writing replies, picking one with a d-pad swipe, and speaking it.

On **real** Meta Ray-Ban Display glasses (Developer Mode): registration through Meta AI, the session, and drawing on the display all work, and the Inputs capability reports active with the Neural Band. A full turn picked with the band has not been confirmed yet.

Two things to know:

- **The d-pad is an experimental capability.** Inputs works in Developer Mode, but it has to be enabled for the app in the [Wearables Developer Center](https://wearables.developer.meta.com) for a registered app, and apps using it cannot be published to production channels yet. Without it the app still works: replies are drawn as cards you move focus between and tap ("tap to pick" in the status chip).
- **Replies are slow on the phone's CPU.** See [Speed](#speed).

If the status chip says "No glasses in range", open **Settings → Glasses**: it lists each pair Meta AI has shared with the app and what is missing (not connected, not worn, needs an update).

## Install and set up

1. Build and install (below), or install `app-debug.apk`.
2. Open the app and download the models (3.4 GB, once, over Wi-Fi).
3. In **Settings**, enter your name and a few lines about yourself. The replies are written to sound like you. Pick a voice.
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
$A --es gesture down                            # up | right | down | left | pinch | back
adb logcat -s FastChat                          # timings for hearing, replies and voice
```

`llm_cli` runs the same engine against the model from a shell, on a computer or on the phone:

```bash
cmake -S android/app/src/main/cpp -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llm_cli
build/llm_cli model.gguf prefix.txt suffix.txt grammar.gbnf 3 6    # 3 runs, 6 threads
```

## Speed

Measured on a Galaxy Z Fold (Snapdragon 8 Elite Gen 5, 12 GB), CPU only:

| Step | Time |
|---|---|
| Loading the models when the app opens | 4 to 12 s |
| Transcribing a 3.7 s sentence | 0.5 s |
| Reading the conversation (about 40 new tokens) | about 5 s |
| Writing four replies (40 to 60 tokens, about 4 tokens per second) | 11 to 16 s |
| Synthesising a reply (1.4 to 2 s of speech) | 0.4 to 0.8 s |

So the first reply reaches the glasses roughly 8 to 9 seconds after the partner stops talking, and all four after roughly 17 to 22 seconds. That is too slow for comfortable conversation, and it is the main thing to fix. Six threads was the fastest setting (four: 2.9 tokens per second; eight: 3.4). The phone also reports "severe" thermal status after a few turns back to back while charging.

The persona part of the prompt is evaluated once and restored from a snapshot, so each turn only pays for the conversation itself, and each reply is shown and can be picked the moment its line is finished.

Things that should make it faster, not yet tried:

- **The phone's GPU.** llama.cpp v0.9.0 has an OpenCL path for `Q2_0` tuned for Adreno. The build here is CPU only.
- **Bonsai's `PQ2_0` file with its MTP draft head**, which needs the [PrismML fork](https://github.com/PrismML-Eng/llama.cpp) of llama.cpp. The fork's API matches, so it is a two-line change in `cpp/CMakeLists.txt` plus the file name in `models/ModelStore.kt`.
- **A smaller Bonsai** (2B or 4B) for the first replies.

## Volume

The voice has its own volume slider (on the talk screen and in Settings), because the phone's volume keys move the glasses' volume while they are connected and cannot reach the loudspeaker. To make that work the voice plays on Android's alarm channel: the app turns that channel up for the length of each sentence and puts it back afterwards, and silent mode does not mute it.

## Limits

- English only (Parakeet v2 and the prompt are English).
- The phone has to be awake with the app in front. There is no background service yet.
- One utterance at a time: the microphone closes while you choose and while the phone speaks.
- The voice names are just "Voice 1" to "Voice 10"; pick by ear.

## Licences of what it downloads

Bonsai 2 9B: Apache-2.0. Parakeet TDT 0.6b v2: CC-BY-4.0 (NVIDIA). Silero VAD: MIT. Supertonic 3: BigScience OpenRAIL-M, which has use-based restrictions worth reading before distributing the app. sherpa-onnx and llama.cpp: Apache-2.0 and MIT.
