# bug-sim-9: HBP is credited to the batter's `bb` bucket but not the pitcher's

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

A hit-by-pitch is recorded asymmetrically: the batter is credited with a walk
(`bb += 1`) since there is no `hbp` column on `sim_batter_stats`, but the
pitcher side calls `record_pitcher()` with no arguments at all, so the
pitcher's `bb` is left unchanged. A team's total pitching `bb` will not equal
the opposing team's total batting `bb` whenever an HBP occurs, and a pitcher
who hits a batter receives no statistical charge of any kind for it.

This was raised as a "normalize stat semantics for HBP" refactor candidate in
`docs/refactoring-sim.md`, but it is a correctness bug, not a style/structure
issue — reclassifying it here. It overlaps with the "secondary issue" noted in
[bug-sim-5](bug-sim-5.md) (which focuses on R/ER/RBI attribution on
bases-loaded bb/hbp); this doc splits out the bucket/schema semantics decision
specifically, since it can be fixed independently of the run-attribution fix.

## Spec references

- `specs/data-model.md` §sim_batter_stats / §sim_pitcher_stats — neither table
  has an `hbp` column; both only have `bb`. The columns are explicitly marked
  "to be refined when the sim results display is built," so there is no
  spec mandate either way — this is an open decision, not a spec violation.
- `specs/data-model.md` §batter_post_lock_stats / §pitcher_post_lock_stats —
  the *input* historical stats already track `bb` and `hbp` as distinct
  counting stats, so the sim has HBP-vs-BB information available upstream; it
  is only the sim's own output box score that collapses them.

## Location

- `sim/engine.py:608-617` — `_apply_pa_outcome`, `bb` and `hbp` branches:

  ```python
  elif outcome == 'bb':
      ...
      fielding_team.record_pitcher(bb=1)
      batting_team.record_batter(batter_slot, bb=1)
  elif outcome == 'hbp':
      ...
      fielding_team.record_pitcher()                     # no bb
      batting_team.record_batter(batter_slot, bb=1)       # bb bucket for HBP
  ```

## Expected vs actual

| Side | On a walk | On an HBP |
|---|---|---|
| Batter `bb` | +1 | +1 (no `hbp` column exists) |
| Pitcher `bb` | +1 | **+0** |

Team-level invariant that should hold but doesn't: `sum(pitcher.bb)` for a
team equals `sum(batter.bb)` for the opposing team. It only holds when there
are zero HBP events in the game.

## Characterization tests (current behavior, already in place)

`sim/tests/test_engine_characterization.py` already locks in the current
(buggy) behavior from the prior refactoring session:

- `test_hbp_currently_counts_in_batter_bb_bucket`
- `test_apply_pa_outcome_hbp_updates_batter_bb_but_not_pitcher_bb`
- `test_outcome_branch_hbp_increments_batter_bb_only` — asserts
  `sum(pitcher_stats.bb) == 0` even when HBP events occurred, which is the bug
  made explicit as a test assertion.

These should be updated (not just deleted) once a fix lands, to assert the
corrected invariant instead.

## Suggested fix

Decision required (same two options identified in `docs/refactoring-sim.md`
item 3), either is a valid fix for this bug:

1. **Keep combined free-pass semantics.** Make the pitcher side symmetric with
   the batter side: `fielding_team.record_pitcher(bb=1)` in the `hbp` branch
   too. No schema change. Cheapest fix; box scores stay accurate in aggregate
   but a reader can't distinguish BB from HBP in either team's line.
2. **Track HBP explicitly.** Add an `hbp` column to `sim_batter_stats` and
   `sim_pitcher_stats`, record it separately from `bb` on both sides, and
   update the API response shape and any UI box-score rendering that reads
   these tables.

## Verification

- A game with at least one HBP event has `sum(pitcher_stats.bb)` (or, under
  option 2, `sum(pitcher_stats.bb) + sum(pitcher_stats.hbp)`) equal to
  `sum(batter_stats.bb)` (`+ sum(batter_stats.hbp)`) for the opposing team.
- Update the three characterization tests listed above to assert the fixed
  invariant instead of the current asymmetric one.
