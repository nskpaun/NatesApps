# Steel-thread spike: 4 hours, checkpoint every 30 minutes

Goal: one thin, connected pass through all four demos on this Mac, using the 20 office photos in `~/Downloads/myoffice-20-photos`. Every link may be ugly; it must connect.

## Checkpoints

| # | Time | Demo | What gets done | What you can open | Fallback if it breaks |
|---|---|---|---|---|---|
| 1 | 0:30 | 1 | Photos converted; camera positions solved with COLMAP | Picture of the solved cameras and point cloud; count of photos that registered | Feed-forward geometry model for cameras |
| 2 | 1:00 | 1 | First splat trained with msplat | Three renders from viewpoints that were not photographed | Brush as trainer |
| 3 | 1:30 | 1 | Bare web page loads the splat; scripted flythrough | The page, and an MP4 | three.js's own splat renderer instead of Spark |
| 4 | 2:00 | 2 | Depth rendered from the splat, fused into a mesh, saved as GLB | The GLB, and a picture of the mesh | Mesh from the solved point cloud instead of splat depth |
| 5 | 2:30 | 2 | Balls drop onto the mesh on the page | The page with a "drop balls" button | Simplified floor-and-boxes collider |
| 6 | 3:00 | 3 | One draggable lamp with shadows cast against the mesh | The page with a lamp you can drag | Light without shadows |
| 7 | 3:30 | 4 | Local LLM turns one sentence into boxes; ring of depth-guided views; splat trained from them | The boxes, the ring of pictures, the splat | Hand-written boxes from spike 1 |
| 8 | 4:00 | All | Chisel splat loaded into the same page with balls and lamp; written summary | The page, and a list of what is thin or broken per demo | — |

## Rules

- At each checkpoint I post a short report: what works, what you can open, what slipped.
- I keep going after each report unless a link is broken with no fallback, or you step in.
- If a link overruns its slot by one full checkpoint, I take the fallback or stub it, say so, and move on. Connecting the thread beats polishing a link.

## Background work

- The local LLM (Ollama plus a model, several GB) downloads during checkpoint 1.
- The ring of depth-guided views (about 2 minutes each) generates in the background during checkpoints 3 and 5, when the GPU is otherwise idle.

## Installs and downloads

- Homebrew: COLMAP, Ollama.
- Python: msplat, Open3D.
- npm: three.js, Spark, a physics library.
- Models: one local LLM. The image model from spike 1 is already downloaded.

## Deliberately thin

- Views in demo 4 will still disagree, so that splat will be blurry. Consistency is the next spike.
- The agent is one shot from sentence to boxes, with no live placement.
- No relit-splat export and no texture baking.
- 20 photos is a modest capture; expect holes where the photos do not look.
