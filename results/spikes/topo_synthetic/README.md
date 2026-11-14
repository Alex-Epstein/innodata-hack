# Topo family on a synthetic field: pilot results (generator replaced)

Before the real-terrain base (`gen/topo` 2.0.0, directive #53) the topo family drew its maps on a made-up field
(a tilted plane plus Gaussian hills). These are the pilot runs of that generator: 10 seeds (0 to 9), difficulty 3,
both models, through `factory eval`. Kept as evidence; the generator code is in git history
(`gen/topo` at commit `6730b40`, files `terrain.py`, `render.py`, `missions.py`).

Each folder holds `tasks.jsonl` (questions, computed answers, `steps`), `responses.csv`, `summary.json`,
`run_config.json` and `raw/` (full model replies). The images are not stored here; rebuild them from that commit
with `factory generate --family topo --template <t> --difficulty 3 --seeds 0-9`.

| Folder | Template | Haiku | Luna | Cost | What happened next |
|---|---|---|---|---|---|
| `v1.0.0/crossings` | count the contour lines a trail crosses | 2/10 | 2/10 | $0.0924 | answers bunched at 14, fixed in 1.0.1 |
| `v1.0.0/sunset` | Naismith's rule with the uphill crossings | 0/10 | 1/10 | $0.1017 | kept |
| `v1.0.0/flood` | follow the water from a failed dam to a camp | 4/10 | 3/10 | $0.0577 | kept, moved to real terrain |
| `v1.0.0/wildfire` | which escape trail stays below the fire | 8/10 | 7/10 | $0.0373 | **dropped**: too easy (rule: keep only if at most 5 of 10 for at least one model) |
| `v1.0.1/crossings` | same, crossing counts spread evenly | 1/10 | 0/10 | $0.0753 | kept, moved to real terrain |
| `v1.0.1/sunset` | same | 1/10 | 1/10 | $0.0937 | kept, moved to real terrain |

The scores are recounted from each `responses.csv` (column `correct`); the costs are `cost_usd_all_calls` in each
`summary.json`.

Also tried and not kept: line of sight (on this field a visible hiker never clears the ground by the 60 m a
person needs; see `results/spikes/missions/summary.md`).
