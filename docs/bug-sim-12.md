# bug-sim-12: Bases-loaded walk/HBP doesn't move any runners and drops the batter from the base state

**Severity:** High
**Component:** Sim engine
**Status:** Open

## Summary

When the bases are loaded and the batter walks or is hit by a pitch, the
force-advance branch of `_advance_runners` computes the correct run count
(the runner on 3rd scores) but never actually updates the base state to
match: every existing runner is reassigned to the *same* base he started on
(instead of advancing one base), and the batter — who should take 1st — is
never placed on base at all. The runner who scored is left showing as still
occupying 3rd, and the batter who drew the bases-loaded walk/HBP vanishes
from the game state entirely instead of becoming the new runner on 1st.

This was noticed while fixing [bug-sim-11](bug-sim-11.md) (batter `r` never
credited) — the run-scoring credit itself is unaffected, since it's read
from `runners` before this branch overwrites it, but the base-state
corruption is a distinct, still-open defect in the same code.

## Spec references

- `specs/architecture.md` §Simulation Design — base-running/force-advance
  logic is expected to correctly track which runners occupy which bases from
  play to play; subsequent plays' probabilities and advancement decisions
  key off `runners`, so a corrupted base state cascades into the rest of the
  half-inning.
- `specs/data-model.md` §sim_event_runner_outcomes — expects a per-runner
  `final_base` reflecting where each runner actually ends up; a runner who
  scored but is recorded as remaining at 3rd, or a batter who reached base
  but is never tracked as a runner, violates this.

## Location

- `sim/src/engine.py:71-89` — `_advance_runners`, the bases-loaded branch of
  the `bb`/`hbp` case:

  ```python
  if outcome in (Outcome.BB, Outcome.HBP):
      if runners[1] and runners[2] and runners[3]:
          scorers.append(runners[3])
          new_runners[3] = runners[3]
          new_runners[2] = runners[2]
          new_runners[1] = runners[1]
      elif runners[1] and runners[2]:
          ...
  ```

  Every assignment here puts each runner back on the base he already
  occupied (`new_runners[3] = runners[3]`, `new_runners[2] = runners[2]`,
  `new_runners[1] = runners[1]`), including the runner who was just credited
  with scoring. `new_runners[1]` is never set to `-1` (the batter
  placeholder used by `_apply_batter_to_runners`), so unlike every other
  branch of this function, the caller's `_apply_batter_to_runners(new_runners,
  batter_slot.player_id)` call has no `-1` to replace and the batter is
  never inserted into `runners` at all.

  Compare to the non-bases-loaded branches just below, which correctly shift
  each runner up one base and set `new_runners[1] = -1` for the batter:

  ```python
      elif runners[1] and runners[2]:
          new_runners[3] = runners[2]
          new_runners[2] = runners[1]
          new_runners[1] = -1
  ```

## Details

Consequences of the current bases-loaded branch:

- **The scoring runner is left "on base."** The player who scored from 3rd
  is still recorded at `new_runners[3]`. If he later "scores" again from
  3rd on a subsequent play in the same inning, `batting_team.record_batter`
  would credit him a second run for the same trip around the bases (via the
  [bug-sim-11](bug-sim-11.md) fix, which reads scorer identity straight from
  `runners`) despite already having scored — a double-count.
- **The other two runners never advance.** The runner originally on 2nd
  should move to 3rd and the runner on 1st should move to 2nd; instead both
  stay exactly where they were.
- **The batter disappears.** A bases-loaded walk/HBP always puts the batter
  on 1st in real baseball. Here, `new_runners[1]` keeps the *old* runner's
  id (not `-1`), so `_apply_batter_to_runners` finds no placeholder to
  replace and the batter is dropped — he isn't on any base and isn't the
  batter at the plate anymore either, so he's simply gone from the
  simulation's base-running state for the rest of the inning.
- **Downstream state for the rest of the half-inning is wrong.** Every
  subsequent plate appearance in the inning resolves against this corrupted
  `runners` dict (occupancy affects steal-attempt eligibility, force-play
  logic, and future advancement), so one bases-loaded walk/HBP can desync
  the simulated inning from a legal game state for its remainder.

## Expected vs actual

| Base before | Expected after a bases-loaded BB/HBP | Actual after |
|---|---|---|
| 1st: A, 2nd: B, 3rd: C | 1st: batter, 2nd: A, 3rd: B (C scores, base empty) | 1st: A (unchanged), 2nd: B (unchanged), 3rd: C (unchanged, despite having scored); batter not present anywhere |

## Suggested fix

In the bases-loaded branch of `_advance_runners`, shift each runner up one
base and clear 3rd (the runner who scored), then set the batter placeholder
on 1st, matching the pattern already used in the other force-advance
branches:

```python
if runners[1] and runners[2] and runners[3]:
    scorers.append(runners[3])
    new_runners[3] = runners[2]
    new_runners[2] = runners[1]
    new_runners[1] = -1
```

## Verification

- A bases-loaded walk/HBP: the runner who started on 3rd is no longer
  present in `runners` afterward (he scored and left the bases); the runner
  who started on 2nd ends up on 3rd; the runner who started on 1st ends up
  on 2nd; the batter ends up on 1st.
- Team invariant: no player ID ever appears twice in the box score credited
  with scoring from the same base-running trip (i.e. a runner can't be
  "left on 3rd" after already being counted as having scored).
- Add a characterization/regression test asserting the exact `new_runners`
  shape for a bases-loaded walk and a bases-loaded HBP (today's tests for
  this bug and bug-sim-11 deliberately avoid asserting on `runners` for this
  case, to avoid encoding this defect as expected behavior).
