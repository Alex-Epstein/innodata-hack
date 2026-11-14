# Real-terrain topo spike (Nov 14, about 12:15 to 13:10)

Question: can the topo crossings task use real US elevation instead of synthetic Gaussian hills, stay fully
offline and reproducible, and still stump both models? **Yes on all three, with one caveat about a fairness rule.**

## Download
- 16 terrarium tiles at z13 (2x2 per area), 1.9 MB total, 99 to 132 KB each, all HTTP 200, no key.
- Areas: Bear Mountain NY, Breakneck Ridge NY, Harriman State Park NY, Mount Tamalpais CA.
- `tiles/SOURCES.md` lists every URL, z/x/y, size and the license (USGS 3DEP, public domain). `tiles/SHA256SUMS` has the checksums.
- The data matches real peaks: the Bear Mountain summit comes out at 395 m and Tam East Peak at 785 m.
- One data problem: river and sea pixels carry blended bathymetry artifacts. The Hudson has values down to
  -11 674 m plus smooth fake ramps. The generator clamps values at 0 and rejects crops that are more than 10% water.

## Generator (`gen.py`)
- Reads only `tiles/`. Run with `uv run python -I gen.py --seeds 1-10 --out tasks` from the innodata-hack root.
  It takes about 20 s for 10 tasks.
- Each crop is 3.2 x 2.4 km and always contains the named spot.
- The grid spacing is 14.6 m (NY) or 15.1 m (CA). Elevation gets a Gaussian blur (sigma 1 px), is stored as
  float32 in `data/<id>.npy`, and is read with bilinear interpolation.
- Contours are drawn from a 3x bilinear upsample of the same field.
- Each map has a light green woodland tint, water (sea level plus hydro-flattened lakes, so Hessian Lake and the
  Harriman lakes show up), labeled index contours, spot heights at local maxima, DMS lat/lon ticks, a 1 km scale bar
  with the scale ratio, a north arrow, a legend, and the title "<AREA> QUADRANGLE · <STATE>" with
  "data: USGS 3DEP via AWS Terrain Tiles". Images are 1600x1200 and all text is at least 8 pt.
- `data/<id>.json` holds the crop bounds, the elevation summary, the levels, the trail, every crossing (arc
  position, level, x, y), labels and spot heights. The PNG is rendered from the saved json and npy only.
- Contour interval follows relief: 20 m (index 100) when the crop has more than 250 m of relief, else 10 m (index 50).
  Bear, Breakneck and Tam came out at 20 m and Harriman at 10 m.
- The answer is computed two ways:
  1. Walk the trail in 1 m steps on the bilinear field and count sign changes of (z - level) for every level.
  2. Intersect the trail polyline with the contourpy paths that are actually drawn.
  All 10 tasks agree; seeds where the two disagree are rejected.
- How the trail is built: a long Catmull-Rom route steered to sidehill at a steady grade, like a built trail.
  The generator then picks S and E on it so that the piece between them passes every rule: 8 to 20 crossings,
  crossings at least 40 m apart and at least 40 m from S and E, no water, and no grazing.

### Deviation: the grazing rule
- **The literal rule "within 2 m of a level for over 15 m" cannot be met on real terrain.**
  - A 2 m band shorter than 15 m needs an along-trail grade above 27% at every crossing. Measured on these
    tiles, only 46 to 54% of single crossings pass (16% at Harriman). A 10-crossing trail almost never passes
    (0 of about 1 600 candidates).
  - With a 10 m interval the rule also contradicts the 40 m spacing rule: grade would have to be above 0.27
    and below 0.25 at the same time.
- **What I used instead:**
  - Within 2 m of a level for at most **40 m** of trail, which equals the minimum crossing spacing.
  - No turnaround (local high or low along the trail) within 0.25 x CI of a level, so the trail never touches
    a contour without crossing it.
  - Every crossing at an angle of at least 25 degrees to the contour.
- Together these cover what the 15 m rule was meant to catch.

### Reproducibility
- I generated the set twice in separate processes (`tasks/` and `tasks_rerun/`). All 40 files (10 PNG,
  10 json, 20 npy) and `tasks.jsonl` are **byte-identical**.
- This holds for matplotlib 3.11.2 and numpy 2.5.4 from the repo's uv.lock. Pin them in Docker.

## Model results (`results/`, temperature 0, reasoning high, max_tokens 64000)
| task | area | CI | truth | haiku-5.5 | gpt-6-luna |
|---|---|---|---|---|---|
| 000001 | Bear Mountain | 20 | 12 | 10 | 10 |
| 000002 | Breakneck Ridge | 20 | 14 | 12 | **14** |
| 000003 | Harriman | 10 | 8 | 7 | 11 |
| 000004 | Mount Tamalpais | 20 | 9 | 6 | 10 |
| 000005 | Bear Mountain | 20 | 14 | 9 | 11 |
| 000006 | Breakneck Ridge | 20 | 10 | 6 | **10** |
| 000007 | Harriman | 10 | 8 | 7 | **8** |
| 000008 | Mount Tamalpais | 20 | 10 | 5 | 7 |
| 000009 | Bear Mountain | 20 | 12 | 16 | 8 |
| 000010 | Breakneck Ridge | 20 | 10 | 7 | 11 |

- **Haiku 0/10. Luna 3/10.** Haiku undercounts on 9 of 10, by 1 to 5. Luna is off by 1 to 4 when wrong, and its
  answers cluster near 10, so some of its 3 hits may be luck.
- All 20 finish reasons are `stop`, with no errors, retries or truncation.
- Cost: 20 calls, **$0.0516** (Haiku $0.014, Luna $0.037). Well under the $0.40 cap.
- `scripts/budget` read $0.97 before and $1.29 after. The extra $0.27 is someone else's spend during the same
  window; run_config.json totals this run at $0.0516.
- Compared with the synthetic L3 spike (0/3 and 0/3): real terrain is still hard. Luna did a little better here,
  probably because these trails are short (600 to 1 350 m, 8 to 14 crossings) and often run straight downhill.

## Judgment
- **It clearly looks more real.** The synthetic maps are concentric ovals. These have real drainages, the
  Bear Mountain dome with Hessian Lake and the Hudson, Breakneck's ridge, and Tam's East Peak at 785 m.
  The DMS ticks put the maps at true coordinates. Best map: `tasks/images/realtopo-cross-000005.png`
  (Bear Mountain).
- **Can a careful person count it in about 3 minutes? Yes.**
  - Crossings are at least 40 m apart (16 px or more at this scale), every crossing is at 25 degrees or more,
    and the trails are short and mostly climb or descend steadily.
  - Counting 8 to 14 lines takes 1 to 2 minutes with zoom. See `review/zoom2.png`: 14 clean crossings.
  - The tight spots are dense index-plus-normal bands on steep slopes, where the lines run about 16 to 20 px apart.
- **Caveats:**
  - The "<AREA> QUADRANGLE" titles are area names, not the official USGS quad names. Bear Mountain is really in
    the Peekskill quad.
  - The trail is synthetic, not a real trail. The map says so in small print.
  - Answers cluster at 8 to 14. To push toward 20, keep searching after the first valid trail and take the one
    with the most crossings.
  - CI 10 (Harriman) only gives about 8-crossing tasks.

## Files
`gen.py` · `tiles/` (+ SOURCES.md, SHA256SUMS) · `tasks/` (tasks.jsonl, images/, data/) · `tasks_rerun/`
(byte-compare copy) · `results/` (responses.csv, run_config.json, raw/, summary.json) · `cache/` · `tools/`
(throwaway rejection-rate diagnostics) · `review/zoom2.png`
