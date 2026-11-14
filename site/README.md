# Beat the AI: phone page for the demo (#40)

Static page judges open from `qr.png`: one mission map at a time, a 60-second timer, tap or type an answer, then the
reveal: the true answer, Claude Haiku 5.5's and GPT-6 Luna's real scored answers, the truth overlay (when the family
provides one) and "the working" from the task's `steps`. A "You vs Haiku vs Luna" score is kept in the browser
(localStorage; the page works without it).

- `index.html`: the whole page (no libraries, no server). Reads only `tasks.json`.
- `tasks.json` + `img/`: built by `scripts/build-site` from the task folders and their `responses.csv`, so the page
  always matches the reported results. Default source: `tasks/final` + `results/final`; until those exist, the topo
  spike sets.
- `qr.png`: QR code for `https://alex-epstein.github.io/innodata-hack/site/`.

```bash
scripts/build-site                                  # rebuild tasks.json and img/ (run after the final eval)
cd site && python -m http.server 8765               # local test: http://localhost:8765
```

Model answers and correct/incorrect come straight from `responses.csv` (scored by `eval/`). The page re-implements the
same scoring rules only to score the viewer; a check in the browser confirmed it agrees with `eval/` on all 42 model
answers and accepts every reference answer.

**Hosting:** GitHub Pages, deploy from branch `main`, folder `/ (root)`; the page is then at `/innodata-hack/site/`.
