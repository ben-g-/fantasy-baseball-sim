# bug-sim-15: Stolen-base model only covers the single simplest case

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

`_apply_steal_attempt` only ever considers one situation: a runner on 1st, with fewer
than 2 outs, attempting to steal 2nd. Every other real steal situation is either
unmodelled or handled incorrectly:

1. Only 1st→2nd is modelled. A runner on 2nd stealing 3rd, or on 3rd stealing home, never
   happens.
2. A steal is never attempted with 2 outs, a hard cutoff rather than a lower-probability
   case. Real teams do attempt (and succeed at) steals with 2 outs.
3. The attempt never checks whether the base being stolen is already occupied. A
   "successful" steal unconditionally does `runners[2] = runner_id; runners[1] = 0`,
   which silently overwrites — deletes — any runner already standing on 2nd.
4. Double steals (two runners advancing on the same play) aren't modelled at all — a
   consequence of #1 and #3 together, since there's no path for two runners to move on
   one steal attempt.
5. In practice a runner rarely gets more than one or two attempts before losing
   eligibility, not because of an explicit "one attempt per arrival" rule but as a side
   effect of #1 and #2: any teammate's hit/walk/HBP forces him off 1st and (per #1) he's
   then permanently ineligible, and the 2-out cutoff (#2) closes the window fast. This
   should resolve itself once #1 and #2 are fixed and doesn't need independent work.

This is distinct from the Phase 10 build-plan item ("context-aware stolen base
decisions" — suppressing attempts in low-leverage spots, weighting attempt rate by
cost/benefit). That item is about *tuning the rate* of an otherwise-correct model; this
bug is about the model covering only one of several base-occupancy situations, including
one (#3) that corrupts game state.

## Spec references

- `specs/build-plan.md` Phase 10 → "Context-aware stolen base decisions" describes
  weighting/suppressing attempts, which presumes a model that already knows how to
  attempt a steal from any occupied base to any open one. Today it only knows 1st→2nd.

## Location

- `sim/src/engine.py:430-478` — `_apply_steal_attempt`: the `runners[1] and outs < 2`
  guard (line 444) hardcodes the single situation; the success branch (lines 455-465)
  overwrites `runners[2]` with no occupancy check.
- `sim/src/engine.py:584-589` — `_simulate_half_inning`'s per-PA loop calls
  `_apply_steal_attempt` once per iteration, unconditionally, using whichever runner
  currently sits on `runners[1]`.

## Details

```python
def _apply_steal_attempt(...):
    if not (runners[1] and outs < 2):
        return runners, outs, seq, []
    ...
    if sb_result is True:
        runners[2] = runner_id
        runners[1] = 0
        ...
```

Reproduced the occupancy bug directly: starting from `runners = {1: 111, 2: 222, 3: 0}`
(e.g. two consecutive walks force the trailing runner to 2nd), forcing a "successful"
steal produces `runners = {1: 0, 2: 111, 3: 0}` — runner 222 is gone. No out is recorded,
no run scores, and no event describes what happened to him; he simply vanishes from the
game state.

## Expected vs actual

| Situation | Expected | Actual |
|---|---|---|
| Runner on 2nd, < 2 outs | can attempt to steal 3rd | never attempted |
| Runner on 3rd, < 2 outs | can attempt to steal home | never attempted |
| Runner on 1st, 2 outs | can attempt (lower rate is fine, but possible) | never attempted |
| Runner on 1st attempts steal, 2nd already occupied | no attempt (or a modelled double steal) | attempt proceeds and overwrites the runner on 2nd |
| Runners on 1st and 2nd, both eligible | double steal sometimes attempted | never attempted; only the 1st-base runner is ever considered, and unsafely |

## Suggested fix

- Generalize `_apply_steal_attempt` to consider every occupied base with an open base
  ahead of it (1st→2nd, 2nd→3rd, 3rd→home), not just 1st→2nd.
- Drop the hard `outs < 2` cutoff; let `_try_steal`'s attempt-rate model account for outs
  (e.g. a lower rate at 2 outs) rather than excluding it entirely.
- Before crediting a "successful" steal, check that the destination base is open. If it's
  occupied, either skip the attempt (simplest fix) or model a double steal (both runners
  advance together) — the latter is needed to properly close out #4.
- Once occupancy is checked and steals can originate from any base, decide the per-runner
  attempt order deliberately (e.g. lead runner first) so two simultaneous attempts on one
  play don't produce an invalid state (two runners on one base).

## Verification

- A runner on 2nd with < 2 outs can steal 3rd; a runner on 3rd with < 2 outs can steal
  home.
- A steal is sometimes attempted (and can succeed or fail) with 2 outs.
- With runners on 1st and 2nd, a steal attempt by the 1st-base runner never results in two
  runners occupying 2nd, and never causes a runner to disappear from `runners` without a
  corresponding out, advance, or scored run.
- Over many simulated games, no play ever results in two runners on the same base or a
  runner vanishing from the play-by-play/runner-outcomes log without explanation (same
  invariant class as bug-sim-8/bug-sim-10).
