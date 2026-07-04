# bug-sim-5: Runs forced in by walks/HBP are not attributed in the box score

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

When a walk or hit-by-pitch forces in a run (bases loaded), the run appears on the line
score but is never credited to the pitcher's R/ER or to the batter's RBI in the box
score. Box-score pitching totals will not reconcile with the line score.

## Spec references

- `specs/data-model.md` §sim_pitcher_stats — `r` (runs), `er` (earned runs) per pitcher.
- `specs/data-model.md` §sim_batter_stats — `rbi`.
- `specs/mini-prd-lineup-and-sim.md` §Post-Sim Mode — "Pitching stats table: one row per
  pitcher showing IP, H, R, ER, BB, K."

## Location

- `sim/src/engine.py:606-617` — `_apply_pa_outcome`, `bb` and `hbp` branches

## Details

The hit branch correctly records runs:

```python
elif is_hit:
    ...
    fielding_team.record_pitcher(h=h_flag, hr=hr_flag, r=runs_on_play, er=runs_on_play)
    batting_team.record_batter(batter_slot, ab=1, h=h_flag, ..., rbi=runs_on_play)
```

But the walk and HBP branches do not pass `r` / `er` / `rbi`:

```python
elif outcome == 'bb':
    new_runners, runs_on_play = _advance_runners('bb', runners, outs)
    ...
    fielding_team.record_pitcher(bb=1)                 # no r / er
    batting_team.record_batter(batter_slot, bb=1)      # no rbi
elif outcome == 'hbp':
    new_runners, runs_on_play = _advance_runners('hbp', runners, outs)
    ...
    fielding_team.record_pitcher()                     # no r / er, no bb
    batting_team.record_batter(batter_slot, bb=1)      # no rbi
```

`runs_on_play` from a bases-loaded walk/HBP is added to `inning_runs` (so the line score
and final score are correct), but the pitcher's R/ER and the batter's RBI omit it.

A related but separate issue in the same branches — HBP recorded in the batter's `bb`
bucket while the pitcher's `record_pitcher()` on HBP records no `bb` at all — is tracked
independently as [bug-sim-9](bug-sim-9.md), since it can be fixed without touching
run/RBI attribution.

## Expected vs actual

| Event | Line score run | Pitcher R/ER | Batter RBI |
|---|---|---|---|
| Bases-loaded single scoring 1 | +1 | +1 | +1 (correct) |
| Bases-loaded walk scoring 1 | +1 | 0 | 0 |
| Bases-loaded HBP scoring 1 | +1 | 0 | 0 |

## Suggested fix

Pass `r=runs_on_play, er=runs_on_play` to `record_pitcher` and `rbi=runs_on_play` to
`record_batter` in the `bb` and `hbp` branches. See [bug-sim-9](bug-sim-9.md) for the
separate decision on HBP bucket/schema semantics.

## Verification

Add a test that loads the bases and forces a walk, then assert the pitcher's `r`/`er`
and the batter's `rbi` each increased by 1 and that the sum of pitcher R across a team
equals the opponent's line-score run total.
