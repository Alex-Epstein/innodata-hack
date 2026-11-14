# Use cases: where models have to reason over terrain and contour maps

These are needs, stated as the skill a model must have. We name no customers and claim no market figures. Each row
says which of our missions tests the skill today.

| Need | What the model must do | Mission that tests it | The one skill |
|---|---|---|---|
| **Outdoor and navigation assistants** ("how hard is this route, will I make it before dark?") | count the climb along a route on a map and turn it into walking time | `sunset`, `crossings` | count level changes along a route |
| **Emergency management, wildfire and flood planning copilots** (where will water go, which route is safe, who can see what) | follow water downhill from a breach; judge routes by the ground they cross | `flood`, `crossings` | follow steepest descent |
| **Drones and ground robots planning over terrain** (physical AI) | read slope and climb along a candidate path before committing to it | `crossings`, `sunset` | trace a path across contours |
| **Civil and site engineering**: drainage, grading, routing roads and pipelines | see where runoff collects and how many level changes a route takes | `flood`, `crossings` | follow steepest descent; count level changes along a route |
| **Insurance and real estate flood-exposure review** | decide whether a site sits in the path water would take | `flood` | follow steepest descent |
| **Education**: AI tutors for school map reading (contours, gradients, stream direction, a staple of earth-science courses) | explain contour spacing, uphill versus downhill, and which way water runs, step by step | all three; `sft.jsonl` gives worked steps | trace a path across contours |

## One pipeline, many maps
Nothing in the factory is specific to elevation. It needs a scalar field on a grid, lines of equal value drawn from
it, and a question whose answer is computed from the field. The same pattern covers:
- **Weather maps:** isobars instead of contours; wind runs roughly along the isobars, stronger where they crowd.
- **Nautical charts:** depth contours; is there a safe passage deeper than the boat's draft from A to B?
- **Heat, stress or concentration maps:** follow the gradient to the hot spot; count the bands a path crosses.

Each is a new renderer and a new question template on the same skeleton: data first, picture drawn from the data,
answer computed in code, seven checks, two solvers, verifier and worked steps exported the same way.
