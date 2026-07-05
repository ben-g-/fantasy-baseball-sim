# bug-sim-11: Batter `r` (runs scored) is never incremented — box score R column is always zero

**Severity:** High
**Component:** Sim engine
**Status:** Open

## Summary

No code path in the sim engine ever increments a batter's `r` stat. Every
run scored in a game — on a home run, a triple, a double, a single, a
bases-loaded walk, or a bases-loaded HBP — updates the line score, the
pitcher's `r`/`er` (partially; see [bug-sim-5](bug-sim-5.md)), and the
scoring batter's `rbi`, but never the `r` bucket of the player(s) who
actually crossed the plate. `sim_batter_stats.r` is initialized to 0 for
every batter and stays 0 for the rest of the game, so the Batting section's
R column in the box score is always all zeroes, regardless of how many runs
were scored.

## Spec references

- `specs/data-model.md` §sim_batter_stats — `r` (runs) is a tracked column.
- `specs/mini-prd-lineup-and-sim.md` §Post-Sim Mode — the batting box score
  is expected to show standard counting stats including runs scored.

## Location

- `sim/src/engine.py:177-201` — `TeamState.record_batter` accepts an `r`
  parameter and stores it in the per-batter stats dict, but grep across the
  file shows it is **never called with `r=`** anywhere:

  ```python
  def record_batter(self, batter_slot: BatterSlot, ab: int = 0, r: int = 0, h: int = 0,
                    doubles: int = 0, triples: int = 0, hr: int = 0,
                    rbi: int = 0, bb: int = 0, k: int = 0, sb: int = 0) -> None:
  ```

- `sim/src/engine.py:656-703` — `_apply_pa_outcome`: every branch that scores
  a run (`hit`, `bb`, `hbp`) computes `runs_on_play` and applies it to
  `rbi` (hits only today) and to the pitcher's `r`/`er` (hits only today),
  but never attributes it to any batter's `r`:

  ```python
  fielding_team.record_pitcher(
      h=h_flag, hr=hr_flag,
      r=runs_on_play, er=runs_on_play,
  )
  batting_team.record_batter(
      batter_slot, ab=1, h=h_flag,
      doubles=d_flag, triples=t_flag, hr=hr_flag,
      rbi=runs_on_play,
  )
  ```

  Note this call only touches `batter_slot` — the batter at the plate. On a
  double/triple/single, the batter himself doesn't score (he ends up on
  base), so even if `r=runs_on_play` were added here it would credit the
  *wrong* player. The runner(s) who actually scored are whichever players
  were in `runners` before `_advance_runners` ran; that identity is
  discarded today (see Details).

## Details

`_advance_runners` (`sim/src/engine.py:30-90`) returns `(new_runners, runs)`
— only a *count* of runs scored, not *which* player IDs scored. By the time
`_apply_pa_outcome` calls `record_batter`, there is no remaining reference to
the specific runner(s) who crossed the plate on that play (except on a walk
where at most one player scores and it's derivable from bases-loaded state,
today that path doesn't even try).

Confirmed via `sim/tests/test_engine_characterization.py::test_apply_pa_outcome_double_updates_hits_and_run_accounting`:
a runner on 1st (`player_id=77`) scores on a double hit by the batter
(`player_id=111`). The test asserts `runs_on_play == 1` and
`fielding_team.pitcher_stats[2]['r'] == 1`, but `batting_team.batter_stats`
never gets an entry for player 77 at all — `record_batter` is only ever
called with `batter_slot` (player 111), so the scoring runner isn't just
missing an `r` credit, he has no batter-stats row created for this play
whatsoever.

This is broader than [bug-sim-5](bug-sim-5.md) (pitcher R/ER and batter RBI
not attributed on forced bb/hbp runs specifically) — this bug means **no
batter ever accumulates any `r` value, on any play type, for the entire
game**. Fixing bug-sim-5 alone (adding `r=`/`er=`/`rbi=` to the bb/hbp
branches) would not fix this, since bug-sim-5's fix targets the pitcher's
`r` and the batter-at-the-plate's `rbi`, not the scoring runner's `r`.

## Expected vs actual

| Event | Line score run | Batter (scoring player) `r` |
|---|---|---|
| Solo home run | +1 | 0 (should be +1, batter himself) |
| Double scoring a runner from 1st | +1 | 0 (should be +1, the runner on 1st — not the batter) |
| Bases-loaded walk forcing in a run | +1 | 0 (should be +1, the runner forced home) |

Team invariant that should hold but doesn't: `sum(batter_stats.r)` for a team
equals that team's total runs scored (the line-score total). Today
`sum(batter_stats.r)` is always 0 regardless of the final score.

## Suggested fix

`_advance_runners` needs to report *which* player IDs scored, not just a
count, so the caller can credit each one individually:

- Change `_advance_runners` (or wrap it) to also return a list of scoring
  `player_id`s, computed from which entries in `runners` (plus the batter,
  on a HR) are cleared to "scored" rather than moved to a new base.
- In `_apply_pa_outcome`, for each scoring player id, call
  `batting_team.record_batter(_find_slot(player_id, batting_team), r=1)` —
  using `_find_slot` (already used in `_apply_steal_attempt`) to resolve the
  `BatterSlot` for a runner who isn't necessarily the current `batter_slot`.
- Apply this in the `hit`, `bb`, and `hbp` branches alike (the bb/hbp
  branches currently score zero or one forced runner; the hit branches can
  score up to three existing runners plus the batter on a HR).
- Coordinate with [bug-sim-5](bug-sim-5.md)'s fix (same bb/hbp branches,
  adding pitcher `r`/`er` and batter `rbi`) since both touch the same code
  and the same `runs_on_play` value — a single pass through these branches
  can fix both.

## Verification

- A game with a solo home run: the batter's own `r` increases by 1.
- A game with a runner on base who scores on a teammate's hit: the *runner's*
  `r` increases by 1, not the batter's (unless it's a HR, where both credit).
- A bases-loaded walk/HBP forcing in a run: the forced runner's `r` increases
  by 1.
- Team invariant, checked across many simulated games: `sum(batter_stats.r)`
  for a team equals that team's final score (and its line-score run total).
- Update `test_apply_pa_outcome_double_updates_hits_and_run_accounting` to
  additionally assert `batting_team.batter_stats[77]['r'] == 1`.
