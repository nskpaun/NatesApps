# NatesApps

A collection of small, self-contained apps. Each app lives in its own top-level directory with its own README, source, and build instructions.

## Apps

### [Chain Theory Explorer](chain-theory/)

An offline guide to Alex Wissner-Gross's **Chain Theory** (October 2026), his attempt to rebuild fundamental physics from networks of entangled qudits. It covers everything from a 60-second summary to the full 754-page compendium.

![Chain Theory Explorer on Android: home, quiz, refresher and reader screens](chain-theory/docs/screenshots.png)

- **Native Android app** (Kotlin + Jetpack Compose), fully offline: layered explainers, a kets & cross products refresher, quizzes and flashcards, an α calculator, and a swipeable reader with native PDF rendering and full-text search.
- **Single-file web version**: the same content in one HTML file that works offline in any browser.
- **Install:** download [`chain-theory/ChainTheory.apk`](chain-theory/ChainTheory.apk) on an Android phone and open it. Allow installs from unknown sources when prompted.

### [Ackoff: Systems Thinking for the Flight](ackoff/)

A guide to **Russell Ackoff**: his 1993 talk *From Mechanistic to Social Systemic Thinking*, and his claim that leadership is an aesthetic act.

![Ackoff app on Android: home, talk guide, leadership, swipe game and quiz](ackoff/docs/screenshots.png)

- **Native Android app**, fully offline: five levels (from a 3-minute intro to hands-on exercises), a section-by-section study guide to the talk, quizzes, flashcards, a "Machine or Systems?" swipe game, search, and a library that imports PDFs for offline reading.
- **Install:** download [`ackoff/Ackoff.apk`](ackoff/Ackoff.apk) on an Android phone and open it.

## Repository layout

```
<app-name>/          one directory per app
  README.md          what it is, how to install, how to build
  ...                source, assets, prebuilt artifacts
```

To add an app, create a new top-level directory with its own README, then add an entry under **Apps** above.
