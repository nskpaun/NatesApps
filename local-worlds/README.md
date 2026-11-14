# Nate's Worlds

Turn photos of a room, or a sentence describing one, into a 3D world you can look around, drop balls in and relight. Everything runs on this Mac with local models: no cloud services are called once the models are downloaded.

![The office, reconstructed from 20 phone photos](docs/office-splat.jpg)

| | |
|---|---|
| ![A wizard study built from a prompt in 14.5 minutes](docs/wizard-study.jpg) | ![A cabin invented from one sentence](docs/cabin.jpg) |
| A wizard study built from a prompt in 14.5 minutes | A cabin invented from one sentence |
| ![Night mode with a draggable lamp](docs/office-night.jpg) | ![The reconstructed mesh with balls resting on the desk](docs/office-mesh-balls.jpg) |
| Night mode with a draggable lamp | The mesh, with balls resting on the desk |
| ![A bedroom built from a prompt in the app](docs/bedroom.jpg) | ![The New world dialog](docs/new-world.jpg) |
| A bedroom built from a prompt in the app | The New world dialog |
| ![Three rooms arranged from above in the stitch editor](docs/stitch-editor.jpg) | ![Looking through a doorway from one room into the next](docs/stitch-doorway.jpg) |
| Stitching three rooms into one world | Looking through a doorway into the next room |

## What it does

| Tool | Input | Output |
|---|---|---|
| Photos to world | 20 to 60 overlapping photos of a room (JPG, PNG, HEIC) | A Gaussian splat you can orbit |
| Splat to mesh | Any world | A GLB mesh and a collider; balls bounce on it |
| Relight | Any world | Night mode with a draggable lamp and shadows |
| Prompt to world | A layout sentence and a style sentence | A blocked-out room, painted and turned into a splat |
| Stitch worlds | Two or more worlds | One bigger world, with doorways between rooms |

In the app, choose **New world…**, then **From your photos** or **From a prompt**. One world is built at a time, and a panel in the corner shows progress.

## Stitching worlds together

Choose **Stitch worlds…** to see your worlds from above with their ceilings hidden.

1. Tick the worlds to include.
2. Click a world to select it, then drag the arrows to move it. Switch to **Rotate** to turn it. **Snap** moves in 25 cm steps and turns in 15° steps.
3. Drop a room near another and it slides so the two walls meet. A green block shows where a doorway will be cut.
4. Name it and choose **Save as one world**.

The stitched world keeps a list of its rooms and where each one sits, so it loads the original worlds side by side. Doorways (1 m wide, 2.1 m tall) are cut through the splats, the mesh and the collider wherever two invented rooms have facing walls that touch, so balls roll from room to room. Chain rooms this way to lay out a dungeon.

## Requirements

- An Apple Silicon Mac. Developed on an M4 Pro with 64 GB; the pipelines are kept under about 32 GB by running one model at a time.
- macOS 14 or later, Xcode command line tools (`xcode-select --install`), and [Homebrew](https://brew.sh).
- Tens of GB of free disk for model weights, which download on first use.

## Build

From the `local-worlds` folder:

```bash
brew install uv colmap ollama libusb node
```

```bash
ollama pull qwen3.5:9b
```

```bash
uv venv --python 3.12 thread/.venv && uv pip install --python thread/.venv/bin/python -r thread/requirements.txt
```

```bash
uv venv --python 3.12 spike/.venv && uv pip install --python spike/.venv/bin/python -r spike/requirements.txt
```

```bash
npm install --prefix thread/viewer
```

```bash
app/build.sh
```

That produces `app/Nate's Worlds.app`. Drag it to the Desktop or Applications and open it.

The app is a thin window around this folder: it starts `thread/server.py` and shows the page. It stores the folder's path when built, so rebuild it if the folder moves. It is signed ad hoc, for this Mac only.

To run without the app:

```bash
thread/.venv/bin/python thread/server.py 8765
```

Then open `http://127.0.0.1:8765/viewer/index.html`.

To redraw the icon, run `thread/.venv/bin/python make_icon.py` inside `app/`, then rebuild.

## How it works

**Photos to world** (`pipeline.py photos`, a few minutes)

1. COLMAP solves where each photo was taken.
2. msplat trains a Gaussian splat on the Mac's GPU.
3. Depth Pro estimates depth for each photo. Each depth map is scaled to match COLMAP's 3D points, and all of them are fused into one mesh, coloured from the photos.

**Prompt to world** (`pipeline.py prompt`, about 10 to 32 minutes depending on detail; a 12-view world measured 14.5 minutes)

1. Qwen3.5 9B reads the layout sentence and writes a rough plan: the room's size, plus pieces placed against walls, at points, at the corners, or in rings and arcs. A piece is a box, an upright cylinder, or a named piece of furniture. Code checks the plan (everything is kept inside the room and resting on the floor, rows are thinned so copies do not overlap, an audience is turned to face a stage) and expands it into the blockout.
2. The blockout is rendered as depth maps from a ring of cameras.
3. Z-Image Turbo with a depth ControlNet paints each view so it follows the blockout. Each view's prompt names only the pieces visible in it. Quick and Standard detail paint at 768x576, Full at 1024x768. A cancelled build resumes from the views already painted.
4. Separately painted views disagree with each other, so each wall, the floor and each furniture piece takes its look from one view only. That view is projected onto the blockout and re-rendered from about 50 cameras, including views pitched up at the ceiling, which is filled with a light flat colour because no picture paints it.
5. msplat trains a splat from those views. The blockout boxes serve as the mesh and collider.

**Viewer** (`thread/viewer`): three.js with Spark for splats and Rapier for physics. Night mode multiplies the splat by the light reaching the mesh, so splat detail survives.

## Models

| Model | Job | Runs through |
|---|---|---|
| Qwen3.5 9B | Layout sentence to furniture placement | Ollama |
| Z-Image Turbo + Z-Image-Turbo-Fun-Controlnet-Union 2.1 | Painting views that follow the blockout | mflux (MLX) |
| Depth Pro | Depth for each photo | mflux (MLX) |

COLMAP, msplat, Open3D, three.js, Spark and Rapier do the rest and have no model weights. Check each model's licence before using this for anything beyond personal use.

## Speed notes

Painting views dominates a prompt build. Measured on an M4 Pro: about 59 s per view at 768x576 and about 110 s at 1024x768, down from about 160 s. The gains come from patches applied to mflux in memory (`speed_patches` in `thread/chisel_ring.py`): the control input is kept in the model's 16-bit format so the transformer does not fall back to 32-bit, each distinct prompt is encoded once, and the blockout depth map is used directly. Peak memory while painting is about 18 GB.

Tried and not adopted: a full-resolution training schedule (2.4 times slower with no gain on a held-out score), the unquantised image model (no faster, 33 GB), and Rapier's internal-edge fix for colliders (it made walls one-sided, so balls rolled out through them).

## Known limits

- **Invented rooms look like a collage up close.** Seams show where surfaces meet, and furniture is painted onto its box, so it looks right from the front and stretched from the side.
- **Invented spaces are box-shaped rooms** from 3 to 24 m across, filled with boxes, cylinders and a fixed set of furniture. Curved walls, sloped roofs, stairs and tiers are not possible; a tent or dome exists only as painted texture.
- **The layout model is small and makes spatial mistakes.** Code catches the common ones, but an unusual description can still give an odd arrangement.
- **Photo meshes have holes** where no photo looked, and their colour is per vertex, so it is blurry. Balls can fall through holes; a flat safety floor catches them.
- **Invented rooms have a plain ceiling.** It is a flat light colour, not painted.
- **Not yet tested with Wi-Fi off.** Nothing calls out after the models are downloaded, but that has not been verified.
- **Doorways are cut only between invented rooms.** Worlds made from photos can be placed in a stitched world but get no doorway, because their walls are not known exactly.
- **A doorway cuts through whatever is there**, including furniture standing against that wall.
- **There is no walking mode yet.** You look around with an orbit camera; moving through a dungeon on foot is not built.
- No export of relit splats, no texture baking, no flythrough video from the app.

## Layout

| Path | What |
|---|---|
| `app/` | The macOS app: `main.swift`, `build.sh`, `make_icon.py` |
| `thread/server.py` | Local server: static files plus the job API |
| `thread/pipeline.py` | The two pipelines |
| `thread/viewer/` | The page |
| `thread/worlds/` | Worlds built in the app (not in git) |
| `thread/scenes.json` | The list of worlds, including stitched ones (not in git) |
| `spike/` | The image-model environment and `blockout.py`, the box renderer |
| `STEEL-THREAD-PLAN.md` | The plan for the spike that first connected everything |
