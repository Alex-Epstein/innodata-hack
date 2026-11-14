# Hand check of the final 10 (tasks/final)

**How this was done:** Alex's Claude agent pre-checked every task by viewing the map exactly as the models saw it
(`tasks/final/images/`) and the computed truth overlay (`tasks/final/overlays/`), and compared them with the data
(`steps` in tasks.jsonl). **A team member then confirmed each line by eye:** ☐ Alex Epstein (tick each row before
packaging, edit anything you disagree with). Question per task: is the answer visible in the image, unique, and fair
for a careful person? Model answers from `results/final/responses.csv`.

| Task | Place | Truth | Haiku · Luna | Visible, unique, fair? | Why it stumped the models | Confirmed |
|---|---|---|---|---|---|---|
| topo-crossings-000100 | Breakneck Ridge NY | 11 | 7 · 5 | Yes. Short trail (644 m) straight down a steep slope; all 11 crossings are downhill. The middle crossings sit about 15 px apart, so a careful person needs to zoom, but every one is a clean crossing with the solid magenta trail | Both undercount badly in the dense middle (7 and 5) | ☐ |
| topo-crossings-000101 | Mt Tamalpais CA | 11 | 5 · **11** ✓ | Yes. One subtle spot: near E the trail crosses the 560 m line, turns back and recrosses (counted every time, as the question says). 10 up, 1 down | Haiku counted 5 (missed most); Luna got it right | ☐ |
| topo-crossings-000102 | Bear Mountain NY | 16 | 12 · 10 | Yes. 16 uphill crossings, 3 of them index lines; spacing is wider than in 000100 | Both undercount (12, 10), consistent with losing count along a long winding trail | ☐ |
| topo-sunset-000100 | Breakneck Ridge NY | 37 min | 45 · 45 | Yes. Box gives now 14:30, sunset 15:59 (89 min), 16 min flat walk. 9 uphill + 4 downhill crossings; the downhill ones (near H) are clear | Both said 45: two uphill crossings missed (each is 4 min) | ☐ |
| topo-sunset-000101 | Mt Tamalpais CA | 9 min | 13 · 25 | Yes, but the hardest sunset: 12 up + 4 down, with the downhill crossings spread along the trail, so the direction of each crossing has to be read from the nearby labels (700) | Missed 1 and 4 uphill crossings | ☐ |
| topo-sunset-000102 | Bear Mountain NY | 29 min | 49 · 57 | Yes. All 12 crossings are uphill (no downhill trap); 15:25 to 16:57 is 92 min, 15 min flat | Missed 5 and 7 uphill crossings: the climb up the steep east face is undercounted | ☐ |
| topo-flood-000100 | Bear Mountain NY | C4 | **C4 ✓** · **C4 ✓** | Yes. Water leaves D to the south-east, crosses the steep slope at right angles and runs east along the valley floor into C4 by the lake. Note: C4 is also the lowest camp, so a "lowest camp" shortcut also gives the right answer | Both right (the easiest flood) | ☐ |
| topo-flood-000101 | Breakneck Ridge NY | C5 | **C5 ✓** · **C5 ✓** | Yes. Water heads east off D, then turns south down a clear valley to C5 | Both right | ☐ |
| topo-flood-000102 | Harriman NY | C1 | C6 · C6 | Yes, the hardest flood: 10 m contour interval (stated on the map), the water first runs south-west into a small hollow, then turns east along a winding valley to C1. Zoom near D | Both chose **C6, the decoy**: the nearest camp and the dry camp most directly below the dam | ☐ |
| topo-flood-000103 | Mt Tamalpais CA | C1 | C3 · C3 | Yes. Water follows one long drainage south from D straight to C1; C1 is also the lowest camp | Both chose **C3, the decoy**: the nearest camp and the dry camp most directly below the dam | ☐ |

**Summary:** all 10 answers are visible, unique and computed from the data; none needs anything outside the image and
the question. The weakest as a reasoning test is topo-flood-000100 (the "lowest camp" shortcut also works there).
Patterns: on crossings and sunset both models **undercount crossings**; on the hard floods both **pick the planted decoy
nearest the dam**.
