# bug-sim-7: Extra-innings termination doesn't match spec (18-inning cap, no forced-HR rule)

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

The engine caps a game at 18 innings and has no tie-resolution rule, so a game tied
after 18 innings ends without a winner. The spec instead calls for no fixed cap plus a
forced-home-run rule in the bottom of the 30th that guarantees a decided result.

## Spec references

- `specs/architecture.md` §Simulation Design → §Extra innings:
  > "There is no fixed inning cap. Termination is instead guaranteed by making every plate
  > appearance in the bottom of the 30th inning deterministic, based on the score at the
  > moment that plate appearance begins: [tied] resolved as a home run automatically …
  > [road team leading] resolved as a guaranteed out with no base-running … Both rules are
  > applied regardless of the number of outs … Both forced outcomes take precedence over
  > all other plate-appearance rules, including the pure-pitcher auto-out."
- `specs/api-spec.md` GET /leagues/:id/standings — standings are derived from
  `sim_complete` matchups ordered by wins, which assumes every completed matchup has a
  winner. A tie has no defined W/L mapping.

## Location

- `sim/engine.py:543` — `max_innings = 18` safety cap
- `sim/engine.py:545` — `while inning <= max_innings:` loop bound
- `sim/engine.py:557-561` — end-of-inning break condition
- `sim/engine.py:286-305` — `_simulate_pa` (where both forced-outcome overrides must live,
  ahead of the pure-pitcher auto-out on lines 293-295)

## Details

Current behavior:

```python
inning = 1
max_innings = 18  # safety cap

while inning <= max_innings:
    ...
    if inning >= 9 and home_score != road_score:
        break
    inning += 1
```

If the score is still tied after inning 18, the loop exits with `home_score ==
road_score` and the game is recorded as a tie. There is no forced-HR rule.

Required behavior: remove the fixed cap and make every plate appearance in the bottom of
the 30th deterministic, based on the score at the moment the PA begins — **both cases
applied regardless of the number of outs**:

- **Tied → forced home run.** Resolve the PA as a home run (walk-off; home wins).
- **Road team leading → forced no-advancement out.** Resolve the PA as an out in which no
  runner advances, scores, or is retired. The score is frozen until the third out ends
  the inning with the road team still ahead.

Both cases must ignore the out count, and both are needed. A single play can change the
score and record outs at the same time, which opens two holes:

1. Tying the forced HR to a specific out count (e.g. two outs) is unsound: a double or
   triple play can take a tied inning from fewer than two outs straight to three, ending
   the inning tied without the rule ever firing.
2. The bottom of the 30th can legitimately begin with the **road team leading** (the road
   team scored in the top of the 30th, which is played normally). If that half were played
   normally, one play could score the tying run *and* record the third out on the bases (a
   runner thrown out advancing), ending the inning tied with no subsequent PA for the
   forced-HR rule to fire on. Forcing a no-advancement out whenever the road team leads
   removes any chance of the score becoming tied, so the inning must end road-ahead.

Together these guarantee the 30th can never end tied: a tie becomes a home walk-off, a
road lead is frozen into a road win. The current engine models only single-out plays with
no base-running on outs (see `bug-sim-8`), but neither rule may depend on that — hole 2 in
particular only becomes reachable once `bug-sim-8` is implemented.

## Expected vs actual

| Situation | Expected | Actual |
|---|---|---|
| Tied after 18 innings | play continues | game ends as a tie |
| Bottom 30th, tied (any out count) | forced HR → home wins | (unreachable; capped at 18) |
| Bottom 30th, road leading (any out count) | forced no-advancement out → road wins | (unreachable; capped at 18) |
| Max game length | ends by end of 30th | 18 innings |
| Tie possible? | No | Yes |

## Suggested fix

- Remove `max_innings` / the `while inning <= max_innings` bound; drive the loop purely
  by the end-of-inning break condition (the forced outcomes below guarantee it terminates).
  Optionally keep a defensive assertion (e.g. error out past inning 40) that should
  never fire, to avoid a hang if the rules ever regress.
- Add both forced-outcome overrides at the top of the per-PA path, before the pure-pitcher
  auto-out, keyed on `inning == 30` and `half == 'bottom'` and the score at that moment
  (regardless of `outs`):
  - `home_score == road_score` → resolve the PA as `hr`.
  - `road_score > home_score` → resolve the PA as an out that advances/retires no runner
    and scores no run (a plain batter out with `runners` left untouched). Do **not** route
    this through any base-running-on-outs logic added by `bug-sim-8`.
- Confirm the walk-off check ends the game as soon as the forced HR scores, and that the
  end-of-inning check ends it as soon as the third forced out is recorded with road ahead.

## Verification

- Add a test that forces a tie deep into extra innings and asserts the game ends by the
  bottom of the 30th with `home_score != road_score` (home team ahead), and that no
  simulated game is ever recorded as a tie.
- Add a test where a pure pitcher is due up in the bottom of the 30th with the game tied
  (at any number of outs), asserting the forced HR fires rather than the auto-out.
- Add a test asserting the forced HR fires on a tie with zero or one out (not only two),
  so a future double-play implementation cannot bypass termination.
- Add a test where the road team leads entering the bottom of the 30th (road scored in the
  top of the 30th): assert the home team's PAs are forced outs, no runner scores, and the
  game ends with the road team ahead — never tied, even when a runner is on base who could
  otherwise score.
- Once `bug-sim-8` lands, add a test that a play scoring the tying run while recording the
  third out on the bases cannot occur in the bottom of the 30th (the forced-out rule
  pre-empts normal base-running whenever the road team leads).
