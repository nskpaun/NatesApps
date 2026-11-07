# Web ports

Each directory here is one app’s website, built and deployed on its own. The Android projects stay where they are. A new port is a new folder next to `chain-theory/`, with its own `package.json`, and is published by pointing a Vercel project at that folder.

| Site | Vercel root directory |
| --- | --- |
| [Chain Theory Explorer](chain-theory/) | `web/chain-theory` |

The single-file offline page at `chain-theory/web/` is unchanged. It is still the source the Android app is generated from.
