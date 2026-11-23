# QuickTalk Glasses for iPhone

A port of the Android app in [`../android`](../android) to iPhone. The conversation logic, prompt, gestures and reply engine are the same; the platform pieces are being rewritten in Swift.

**Status: in progress.** The parts that don't need a Mac are written and tested. The app itself has not been built in Xcode yet.

| Piece | Status |
|---|---|
| Conversation state machine, dial, glasses screen, partner turn (`QuickTalkCore`) | ✅ Ported test for test from Android, all passing |
| Reply prompt, grammar and parser | ✅ Ported; prompt strings match Android's byte for byte |
| Reply writer (streaming, repeats dropped, retries, persona check) | ✅ Ported and tested against a scripted model |
| Effect runner (`ConversationRunner`, from `FastChat.kt`) | ✅ Ported and tested with fake ears, voice, writer and glasses |
| Language model bridge (`llm_c_api` + `LlamaEngine.swift`) | ✅ Same `llm_engine.cpp` as Android. Run from Swift against the real LFM3 model on Linux; the iOS build script has not been run yet |
| Xcode project (`project.yml`), Info.plist, entitlements | ⏳ Written from Meta's docs, not generated or built yet |
| Model download (`ModelStore`) | ⏳ To do |
| Hearing (Silero VAD + Parakeet) and voice (Supertonic 3) via sherpa-onnx | ⏳ To do, needs the sherpa-onnx iOS xcframework |
| Glasses link: registration, session, display, Neural Band inputs, simulated glasses | ⏳ To do, needs Xcode and the toolkit |
| Glasses renderer (transparent bitmaps → `Image(image: UIImage)`) and tick sound | ⏳ To do |
| Phone screens and Settings (SwiftUI) | ⏳ To do |

## Layout

```
ios/
  QuickTalkCore/      Swift package: everything without UIKit or the toolkit. `swift test` runs on macOS or Linux.
  QuickTalk/          The app target (SwiftUI). So far: LLM/LlamaEngine.swift.
  scripts/build-llm.sh  Builds llama.cpp + the engine as Frameworks/QuickTalkLLMC.xcframework.
  project.yml         XcodeGen spec for QuickTalk.xcodeproj.
```

The engine's C++ stays in `android/app/src/main/cpp/` so both apps build the same file; `llm_c_api.{h,cpp}` there is the plain C interface Swift imports.

## Test the core

```bash
cd fastchat-glasses/ios/QuickTalkCore
swift test
```

## Build the app (on a Mac)

Requires Xcode 26.4 or later (the toolkit asks for iOS 17.2+ and Swift 6), CMake and XcodeGen.

```bash
brew install cmake xcodegen
```

```bash
cd fastchat-glasses/ios
scripts/build-llm.sh
xcodegen
open QuickTalk.xcodeproj
```

## Differences from Android to know about

- **Memory.** The three models need about 1.9 GB. The app asks for Apple's increased memory limit; an iPhone 15 Pro or newer (8 GB) is the target.
- **Model thread.** Model calls run on one thread with an 8 MB stack. A dispatch queue's 512 KB stack overflows inside llama.cpp.
- **CPU, like Android.** llama.cpp is built for the CPU (ARMv8.2 with dot-product), matching how the prompt was tuned and measured. Metal is worth trying later.
- **Analytics.** The toolkit's analytics are switched off (`MWDAT > Analytics > OptOut`), in keeping with nothing from a conversation leaving the phone. The Android app sets the same (`ANALYTICS_OPT_OUT` and `CRASH_REPORTING_OPT_OUT` in its manifest).
- **Distribution.** Meta's docs say apps using the toolkit cannot go on the App Store yet, and the Inputs (d-pad) capability is experimental. Install it from Xcode.
