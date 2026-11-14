# Briefing (the latest shared context; Alex's session keeps "Now" current)

## Now
**~11:10 · Spike results are in** (`results/spikes/README.md`):
- **Calendar (A): difficulty climbs.** L1 3/3 both · L2 Haiku 2/3, Luna 3/3 · **L3 Haiku 1/3, Luna 1/3**. The failures are
  reasoning failures: a block edge read 15 minutes off turns a 45-minute near miss into a fake 60-minute slot.
- **Circuit (B): too easy.** 18/18 correct at every level. Ruled out.
- **Power one-line (C): tech-cosmos running the hard version (#5).** It needs the keys in `.env` first (Alex is posting them in the team chat).
- **max_tokens 16000 is too low:** Haiku hit `length` twice on L3. The real eval uses 32000+.
- Spend so far: $0.08 of $100.

**Proposed by Alex's session, Alex to confirm:** family 1 = **calendar/scheduling** (lock now so building starts).
Family 2 = power one-line if spike C shows a similar drop by 11:35; otherwise a second scheduling-type reasoning
family. Architecture D1 to D9 follow the recommendations in `docs/ARCHITECTURE.md` unless #9 says otherwise.

**Claim order** (take the first with no assignee; docs/SETUP.md step 6): #2 eval client → #8 packaging. (#5 tech-cosmos; #3, #4, #6, #7 Alex.)

**Deadline:** ZIP uploaded by 3:10 (hard 3:30). Next gate: **one calendar task end to end on main by 12:15.**

## Where things are
The file table in `AGENTS.md`.
