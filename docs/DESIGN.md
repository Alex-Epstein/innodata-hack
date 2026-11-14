# Art direction: "Field Survey" (every surface: site, 3D, report, slides)

Inspired by what made Red Ledger look great: **one committed visual idea applied everywhere**, colour that carries
meaning, restraint in the UI, a filmic finish on the 3D, and a choreographed camera. Our world isn't a palace. It's the
**surveyor's map room and the incident command post**: USGS quadrangles, Swiss relief maps (Eduard Imhof's shaded
relief), field notebooks, ICS briefing sheets. Precise, quiet, beautiful, and slightly urgent.

## Type (three voices, each with one job). Google Fonts, pinned in the page
- **Labels and headings:** `IBM Plex Sans Condensed`, 600, UPPERCASE, letter-spacing 0.14em. The voice of map titles ("BEAR MOUNTAIN QUADRANGLE").
- **Numbers, coordinates, elevations, scores:** `IBM Plex Mono`, tabular. Every figure looks surveyed: `395 m`, `41°18'30"N`, `0 / 10`.
- **Reading text and the narrative line:** `Source Serif 4`, italic for the one-line story beats ("This is what the AI sees.").

## Colour is information (never decoration)
| Token | Hex | Means |
|---|---|---|
| `--paper` | `#F3EEDF` | map paper (light surfaces) |
| `--ink` | `#1E1B16` | text, frames |
| `--contour` | `#9A5B2E` | terrain, contours (index lines darker, `#6E3F1E`) |
| `--wood` | `#DCE8C8` | land tint |
| `--truth` | `#2F7FC1` | **the truth**: the computed answer, the real water path, a clear sight line |
| `--model` | `#D2412C` | **the models**: their answers and wrong paths (Haiku and Luna share the red; label them) |
| `--you` | `#D9A441` | **the human player** (gold), and anything waiting on a decision |
| `--night` | `#0E1116` | the 3D stage background, dusk |
Rules: the truth is always blue, the AI always red, you always gold. Nothing else uses those three colours.

## UI restraint (2D overlays, the report, the phone game)
Hairline rules (1 px `--ink` at 25%), double rules for frames, square corners, no drop shadows, no glassmorphism, no
gradients on controls. Generous margins like a printed map collar. Captions set like map marginalia (small caps, mono
numbers). Every screen has a "map collar": title top-left, scale or legend bottom, coordinates in the corners.

## The 3D stage ("The map vs the mountain")
- **Terrain:** the elevation grid as a mesh (vertical exaggeration about 1.6x, so ridges read on a projector), with our
  generated map draped as the albedo texture. For beauty, multiply in an **Imhof-style hillshade** (light from the
  north-west at 45°, computed from the same grid) at about 35%. Contours stay crisp.
- **Light:** low golden-hour sun from the west (`#FFD2A1`), cool sky fill, `FogExp2` toward a dusk horizon (`#C9A27A` →
  `--night`), so the far ridges fade like real distance.
- **Finish:** ACES filmic tone mapping, a gentle vignette, fine film grain, light bloom only on the emissive paths
  (truth water, AI ghost, sight lines). Postprocessing via `postprocessing` (pinned) if it costs under ~5 ms per frame; otherwise tone mapping plus a CSS vignette and grain.
- **Motion:** the truth flows as particles (water) or a drawn line (sight, trail) with a soft glow; the AI's answer is a
  red ghost trail that fades. Crossings on a trail pulse once each as a mono counter ticks up. Easing everywhere:
  `cubic-bezier(0.2, 0.7, 0.2, 1)`.
- **Camera:** a Catmull-Rom flight for the intro (low over a valley, along the ridge, rising to the establishing shot),
  ending exactly top-down on the 2D map frame ("This is what the AI sees"). Then OrbitControls with damping.

## The flow (like Red Ledger's loader → intro → tour → arena, scaled to us)
1. **Loader:** a mono elevation counter climbing to the summit height (`0 m → 395 m`) on a thin hairline bar, with the title in condensed caps.
2. **Title lockup:** "THE MAP" slides in from the left and "THE MOUNTAIN" from the right over the flyover, then they part as the camera descends.
3. **Play:** the flat 2D map, the question in serif italic, gold answer buttons, a mono 10 s / 60 s timer.
4. **Reveal:** the map lifts into the mountain (texture to terrain morph, about 1.5 s), the truth flows in blue, the AI ghost in red, and a score card: `YOU ✓ · HAIKU ✗ C1 · LUNA ✗ C4`.
5. **Factory chapter:** tasks fall through the seven checks like sheets through a survey office (rejected ones drop out with their reason), ending in the funnel numbers.
6. **Show mode:** press `S` for the 90-second auto tour used in the pitch; `R` restarts; `F` toggles fullscreen.

## Slides
The organizers' template is required. Put our art inside it: full-bleed map or 3D stills, numbers in Plex Mono, one
serif italic line per slide, truth blue and AI red used exactly as above.
