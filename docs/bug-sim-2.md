# bug-sim-2: Sim uses pre-lock stats for probabilities and appearance caps; post-lock is never read

**Severity:** High
**Component:** Sim engine / data access
**Status:** Open

## Summary

The sim collapses the two required stat snapshots into one. It reads only the
`*_pre_lock_stats` tables and uses them for outcome probabilities and appearance caps —
both of which the spec says must come from post-lock stats. Pre-lock stats are supposed
to be reserved for AI-manager decisions only.

## Spec references

- `specs/architecture.md` §Stat Window:
  - "**Post-lock stats** … used exclusively to estimate outcome probabilities … These
    stats are unknowable at lineup-set time and are deliberately withheld from the AI
    manager."
  - "**Pre-lock stats** … used exclusively by the AI manager for in-game decisions …
    Giving the AI manager access to post-lock stats would be clairvoyance."
- `specs/data-model.md` §4 — `batter_post_lock_stats.pa` / `pitcher_post_lock_stats.bf`
  and `pitches_thrown` are annotated "used for appearance cap"; pre-lock tables carry
  the platoon splits for the AI manager.
- `specs/build-plan.md` Phase 6 — "Replace seeded placeholder stats with real pre-lock
  and post-lock stats from the database."

## Location

- `sim/db.py:54-83` — `fetch_batter_stats` / `fetch_pitcher_stats` read
  `batter_pre_lock_stats` / `pitcher_pre_lock_stats` only. No post-lock reader exists.
- `sim/sim_service.py:161-163` — fetches the single stat map and passes it to the engine.
- `sim/engine.py` — the same `batter_stats_map` / `pitcher_stats_map` feed
  `pa_probabilities` (`_simulate_pa`), `batter_pa_cap`, `pitcher_bf_cap`,
  `pitcher_pitch_cap`, and the AI's `_best_bench_player`.

## Details

`run_matchup` fetches exactly one batter map and one pitcher map, both pre-lock, and
hands them to `simulate_game`. The engine has no parameter to receive a second
snapshot, so:

1. Plate-appearance probabilities are derived from pre-lock stats (should be post-lock).
2. Batter PA caps and pitcher BF/pitch caps are derived from pre-lock stats (should be
   post-lock — the cap models that week's *actual* workload).
3. The AI manager also reads the same pre-lock map, which is correct for it — but there
   is no separation, so fixing 1–2 without regressing 3 requires a structural change.

This is partially expected before Phase 6 (real stats), but the **single-stat-map
structure** is itself the divergence: swapping in real data later is not enough, because
the engine cannot hold both snapshots at once.

## Expected vs actual

| Consumer | Expected snapshot | Actual snapshot |
|---|---|---|
| PA outcome probabilities | Post-lock | Pre-lock |
| Batter PA cap | Post-lock | Pre-lock |
| Pitcher BF / pitch cap | Post-lock | Pre-lock |
| AI manager decisions | Pre-lock | Pre-lock (correct) |

## Suggested fix

- Add `fetch_batter_post_lock_stats` / `fetch_pitcher_post_lock_stats` in `sim/db.py`
  (and matching methods on `SimRepository` / `DbSimRepository`).
- Thread two maps through `run_matchup` → `simulate_game`: a post-lock map for
  probabilities and caps, and a pre-lock map for AI-manager logic only.
- Update `_simulate_pa`, `batter_pa_cap`, `pitcher_bf_cap`, `pitcher_pitch_cap` to take
  the post-lock map; keep `_best_bench_player` and future AI logic on the pre-lock map.
- See also `bug-sim-3` (platoon adjustment), which depends on having both snapshots.

## Verification

Once both snapshots are wired, add a test where a player's pre-lock and post-lock lines
differ sharply and assert that outcome frequencies track the post-lock line while the
appearance cap reflects post-lock PA/BF.
