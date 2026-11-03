# NatesApps

A collection of small, self-contained apps. Each app lives in its own top-level directory with its own README, source, and build instructions.

## Apps

### [Chain Theory Explorer](chain-theory/)

An offline guide to Alex Wissner-Gross's **Chain Theory** (October 2026), his attempt to rebuild fundamental physics from networks of entangled qudits. It covers everything from a 60-second summary to the full 754-page compendium.

![Chain Theory Explorer on Android: home, quiz, refresher and reader screens](chain-theory/docs/screenshots.png)

- **Native Android app** (Kotlin + Jetpack Compose), fully offline: layered explainers, a kets & cross products refresher, quizzes and flashcards, an α calculator, and a swipeable reader with native PDF rendering and full-text search.
- **Single-file web version**: the same content in one HTML file that works offline in any browser.
- **Install:** download [`chain-theory/ChainTheory.apk`](chain-theory/ChainTheory.apk) on an Android phone and open it. Allow installs from unknown sources when prompted.

## Repository layout

```
<app-name>/          one directory per app
  README.md          what it is, how to install, how to build
  ...                source, assets, prebuilt artifacts
```

To add an app, create a new top-level directory with its own README, then add an entry under **Apps** above.
