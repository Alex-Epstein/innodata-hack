# explainer/: how the Visual Task Factory works, on one page

A single HTML page for teammates (and judges) to learn the pipeline and see the pilot results: the idea, the eight
stations of the factory, what survived each check, the scores per template for both models, real tasks with the
computed answer next to each model's wrong answer (with the truth overlay), how we chose the families, and where the
results are weak.

```bash
python3 explainer/build.py      # reads results/ and tasks/ in your checkout, writes explainer/index.html
open explainer/index.html       # macOS; on Windows: start explainer\index.html
```

- **Every number is read from files** (`results/pilot_*/`, `tasks/pilot_*/`, `results/spikes/README.md`), nothing
  is typed by hand. Rebuild after a new run; the commit is printed at the top of the page.
- Images are linked from `tasks/`, not copied, so open the page from inside the repo.
- These are **pilot** numbers (10 seeds per template), not the final evaluation. Slide and README numbers still come
  from `docs/EVIDENCE.md`.
- Standard library only. Fonts load from Google Fonts; offline, the page uses system fonts.
