# site-fable: The Map vs the Mountain (issue #60)

The 3D demo. The model only ever sees a flat map; the answer lives in the terrain. This page makes that physical:
a flight over the real mountain that settles straight down on the task image ("This is what the AI sees"), the
question, then the map lifts into the mountain and the computed truth plays out in blue next to what each model
said in red.

Static files only. No server, no network calls at run time, no model calls. Open `index.html` from disk or serve the
folder (GitHub Pages works as is).

```bash
uv run python site-fable/build.py            # tasks/final + results/final if present, else the three topo pilots
open site-fable/index.html                   # or: python3 -m http.server -d site-fable 8763
```

## Keys and links
| | |
|---|---|
| `S` | show mode: the 90-second tour (flight, flood, trail count, the seven checks, the results) |
| `N` / `→`, `←` | next / previous mission |
| `R` | restart from the cold open |
| `F` | fullscreen |
| `1` to `6`, `↑` `↓` `Enter` | answer from the keyboard |
| `?task=topo-flood-000000` | open one task |
| `?show=1` | start in show mode |
| `?intro=0` | skip the flight |
| `?fx=0` | no bloom or film pass (slow machines) |
| `?speed=3` | run the choreography faster (testing) |

After a reveal, drag to orbit the mountain and scroll to zoom.

## What is on screen, and where each number comes from
| On screen | Source |
|---|---|
| The flat map | the task PNG, byte for byte (`tasks/<set>/images/`), the same file the models were sent |
| The mountain | the elevation of the map window, rebuilt by `gen.topo.real.window_of` from the USGS 3DEP tiles in `gen/topo/tiles/` |
| Blue water path, crossings, clock | recomputed by `gen.topo.real.answer` / `answer_flood`; `build.py` stops if the result differs from the stored answer |
| Red answers, the models' replies | `results/<set>/responses.csv` |
| Score table in show mode | counted from `responses.csv` per mission |
| Seven checks and their counts | `tasks/<set>/validation_report.json` |
| "unfair draws discarded" | the `attempt` field in each task's data JSON |

Nothing is typed by hand. The red dotted line is a straight line from the dam to the camp a model named: we know its
answer, not the route it imagined, so we don't draw one. The relief is exaggerated 2x vertically (shown in the corner).

## Which tasks appear
`build.py --per-template 4` (default) keeps four tasks per mission, picked by a rule in code: both models wrong on
the same answer first, then both wrong, then the rest, by seed. `--per-template 0` keeps all.

## A fresh task in the live demo
```bash
uv run python -m factory fresh --seed 41 --family topo --out /tmp/fresh
uv run python site-fable/build.py --add /tmp/fresh:/tmp/fresh/results           # task folder : results folder
```
then open `index.html?task=<task id>`.

## Files
| File | What |
|---|---|
| `build.py` | task and result folders → `data/index.js` + one `data/<task>.js` per task |
| `index.html`, `style.css`, `app.js` | the page (art direction: `docs/DESIGN.md`) |
| `vendor/three-0.160.0.bundle.js` | Three.js 0.160.0 with OrbitControls, EffectComposer, UnrealBloomPass (MIT), bundled once with esbuild from `vendor/three-entry.js` |
| `fonts/` | IBM Plex Sans Condensed, IBM Plex Mono, Source Serif 4 (SIL OFL), from `@fontsource` |

## Limits
- Topo family only; other families stay on the report page.
- Scores are kept in this browser's localStorage; there is no shared leaderboard.
- Data files are about 0.8 MB per task because the exact PNG is embedded (so the page also opens from disk).
