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
  > "There is no fixed inning cap. Termination is instead guaranteed by a special rule:
  > in the bottom of the 30th inning, with two outs and the game tied, the next plate
  > appearance is resolved as a home run automatically … The forced home run takes
  > precedence over all other plate-appearance rules, including the pure-pitcher
  > auto-out."
- `specs/api-spec.md` GET /leagues/:id/standings — standings are derived from
  `sim_complete` matchups ordered by wins, which assumes every completed matchup has a
  winner. A tie has no defined W/L mapping.

## Location

- `sim/engine.py:543` — `max_innings = 18` safety cap
- `sim/engine.py:545` — `while inning <= max_innings:` loop bound
- `sim/engine.py:557-561` — end-of-inning break condition
- `sim/engine.py:286-305` — `_simulate_pa` (where the forced-HR override must live,
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

Required behavior: remove the fixed cap and add the bottom-of-the-30th forced-HR rule.
The rule guarantees termination because a tie with two outs in the bottom of the 30th is
converted into a home-team walk-off, so the 30th can never end tied and the loop cannot
reach the 31st.

## Expected vs actual

| Situation | Expected | Actual |
|---|---|---|
| Tied after 18 innings | play continues | game ends as a tie |
| Bottom 30th, 2 outs, tied | forced HR → home wins | (unreachable; capped at 18) |
| Max game length | ends by end of 30th | 18 innings |
| Tie possible? | No | Yes |

## Suggested fix

- Remove `max_innings` / the `while inning <= max_innings` bound; drive the loop purely
  by the end-of-inning break condition (the forced-HR rule guarantees it terminates).
  Optionally keep a defensive assertion (e.g. error out past inning 40) that should
  never fire, to avoid a hang if the rule ever regresses.
- Add the forced-HR override at the top of the per-PA path, before the pure-pitcher
  auto-out: when `inning == 30`, `half == 'bottom'`, `outs == 2`, and
  `home_score == road_score` at that moment, resolve the PA as `hr`.
- Confirm the walk-off check already ends the game as soon as the forced HR scores.

## Verification

- Add a test that forces a tie deep into extra innings and asserts the game ends by the
  bottom of the 30th with `home_score != road_score` (home team ahead), and that no
  simulated game is ever recorded as a tie.
- Add a test where a pure pitcher is due up in the bottom of the 30th with two outs and
  the game tied, asserting the forced HR fires rather than the auto-out.
