# QuickTalk Glasses for iPhone

QuickTalk helps someone who cannot speak choose a reply with Meta Ray-Ban Display glasses and a Meta Neural Band. A conversation partner speaks to the iPhone. Silero and Parakeet transcribe the utterance, LFM3 suggests replies, and Supertonic speaks the selected reply through the iPhone speaker. Inference runs on the phone. The first setup downloads 1.9 GB of model files. Registration with the glasses uses Meta AI.

## Build and install

Use Xcode 26.4 or later, CMake, and XcodeGen on a Mac. The native build scripts create arm64 slices for iPhone and Apple Silicon Simulator.

```bash
cd fastchat-glasses/ios
scripts/build-llm.sh
scripts/build-speech.sh
xcodegen generate
open QuickTalk.xcodeproj
```

Select your Apple Developer team for the QuickTalk target and run it on an iPhone. The models target 8 GB devices such as iPhone 15 Pro or iPhone 16. The app uses the increased-memory-limit entitlement.

1. Download the models in QuickTalk. Verified files are reused if you pause the download or retry.
2. Pair and update the glasses in Meta AI. Enable Developer Mode in Meta AI for local builds, then choose **Connect through Meta AI** in QuickTalk. For a registered integration, supply `META_APP_ID`, `CLIENT_TOKEN`, and the matching Apple signing team when building.
3. Optionally set your name, personal details, and voice under **Settings**.
4. Wear the glasses, start a conversation, and speak a question into the phone. Swipe to highlight a reply and pinch to speak it. If Inputs is unavailable, move focus to a reply card and tap it.
5. Tap **Pause** to release the display and microphone, or to adjust the voice volume. QuickTalk also pauses when it goes to the background.

Debug builds offer **Simulated glasses** in Settings. This uses Meta’s Mock Device Kit to exercise the same display and input paths and shows their preview and controls on the phone.

## Test

```bash
cd fastchat-glasses/ios/QuickTalkCore
swift test
```

After downloading the models on an iPhone, run the **QuickTalk** scheme’s `OfflineTurnTests` on the same phone. The test uses a synthetic sample to exercise Supertonic, Silero, Parakeet, the real LFM3 model, the reply state machine, and the glasses renderer. A second test connects the Meta mock display and checks swipe, pinch, and pinch-and-turn events. For the accessory check, use the paired glasses and Neural Band to confirm that a spoken question produces reply choices, that swipe and pinch select and speak the intended reply, and that Pause releases the display.

## Distribution

Use Meta’s Wearables Developer Center to confirm production publishing eligibility and which capabilities the release channel permits. The app includes a focus-and-tap control path for channels where Neural Band Inputs is unavailable. [Meta publishing and discovery](https://developers.meta.com/wearables/faq/)

The model sources, external libraries, and licenses are listed in the [QuickTalk project README](../README.md).

### Private beta

Configure the iOS integration in the Wearables Developer Center with bundle ID `com.natesapps.quicktalk`, the Apple signing team, and a full HTTPS Universal Link. Use the same URL in the integration version and the app build.

Create `QuickTalkBeta.local.xcconfig` next to `project.yml` with the values for that integration. Xcode includes this ignored file only in Release builds.

```xcconfig
META_APP_ID = <Wearables Developer Center app ID>
CLIENT_TOKEN = <Wearables Developer Center client token>
QUICKTALK_CALLBACK_HOST = <your HTTPS hostname>
MWDAT_CALLBACK_URL = https:/$()/$(QUICKTALK_CALLBACK_HOST)/quicktalk/connect
CODE_SIGN_ENTITLEMENTS = QuickTalk/QuickTalkBeta.entitlements
```

Serve `/.well-known/apple-app-site-association` on that hostname over HTTPS, without a redirect, with `Content-Type: application/json`. Match the application identifier from your signed build.

```json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["<Application Identifier Prefix>.com.natesapps.quicktalk"],
        "components": [{ "/": "/quicktalk/connect" }]
      }
    ]
  }
}
```

Regenerate the project, archive it as Release using the same Apple team, and upload it to TestFlight. Enable Display and Inputs in the Wearables Developer Center, assign an integration version to a private Beta channel, and invite the tester's Meta account. Verify the invite has been accepted and test registration and one full conversation with Developer Mode off.
