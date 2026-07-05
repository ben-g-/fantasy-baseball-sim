# bug-sim-10: Runner advancement on hits is deterministic, not probabilistic

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

`_advance_runners` resolves every hit with a fixed rule: a runner on 3rd always
scores on a single, a runner on 1st always reaches exactly 2nd (3rd with 0
outs) on a single, and every runner always scores on a double/triple/HR. No
runner is ever thrown out advancing, and a runner on 1st never takes the extra
base (e.g. 1st-to-3rd on a single) beyond the one fixed rule for zero outs.
The sim is specified as a probabilistic, stat-driven model — this corner of
base-running is the one part of plate-appearance resolution that isn't
sampled from a distribution at all; it's a lookup table with no randomness.

This is the companion gap to [bug-sim-8](bug-sim-8.md), which covers the other
half of base-running (runner outcomes on outs — currently not modelled at
all). This bug is narrower: advancement on hits *is* modelled, just not
probabilistically.

## Spec references

- `specs/architecture.md` §Simulation Design (line 101): "The sim engine uses
  a **probabilistic, stat-driven model** to resolve each plate appearance.
  This is the core IP of the product." Line 150 explicitly separates
  "Base-running outcomes (stolen bases, advancing on hits)" out as their own
  resolution step, implying the same probabilistic standard applies to them,
  not just to the plate-appearance outcome itself.
- `specs/build-plan.md` Phase 5 → "Implement base-running resolution" (now
  split into explicit sub-bullets after this bug was filed): "Runner
  advancement on hits: probabilistic, not fixed by hit type alone — a runner
  might or might not attempt to advance an extra base (e.g. go first-to-third
  on a single) and might or might not be thrown out when attempting it. On
  rare occasions, a runner might advance zero bases (e.g. remain at second
  base on an infield single) or three bases on a single. A runner (including
  the batter, who becomes a runner upon getting the hit) might attempt to
  advance on a throw that results from another runner attempting to advance
  an extra base on the hit." Contrast with the adjacent "Runner outcomes on
  outs" bullet, which was already explicit about "sometimes succeeding and
  sometimes being thrown out advancing" — the hits bullet was under-specified
  relative to it until this edit, which is likely why the implementation
  never got a probabilistic pass.

## Location

- `sim/src/engine.py:30-90` — `_advance_runners`: the `SINGLE`, `DOUBLE`,
  `TRIPLE`, and `HR` branches are unconditional. The only situational
  variation anywhere in the function is `2 if outs >= 1 else 3` in the
  `SINGLE` branch (runner on 1st goes to 3rd with 0 outs, 2nd otherwise) —
  and even that is a fixed rule, not a probability.

  ```python
  if outcome is Outcome.SINGLE:
      # r3 always scores
      if runners[3]:
          runs += 1
      # r2 scores
      if runners[2]:
          runs += 1
      # r1 advances to 2nd (3rd with 0 outs)
      if runners[1]:
          new_runners[2 if outs >= 1 else 3] = runners[1]
      new_runners[1] = -1  # batter placeholder
      return new_runners, runs
  ```

  Compare to the `bb`/`hbp` branch just below it in the same function, which
  is already situational (forced-advance logic keyed off which bases are
  occupied) but still has no random component — thrown-out-advancing risk
  doesn't apply to forced advances, so that branch is arguably already
  correct as written.

## Details

Consequences of the current fixed-rule model:

- **No risk on the bases.** A runner is never thrown out trying to advance
  on a hit (e.g. gunned down at home trying to score from 2nd on a single).
  Real base-running carries real risk; the sim currently has none.
- **No situational extra-base advancement.** A fast runner on 1st with two
  outs and a ball in the gap should sometimes score from 1st on a double or
  take 3rd on a single; a plodding runner should advance more conservatively.
  The engine has no mechanism for this at all — advancement is a function of
  hit type and out count only, never of the runner.
- **Runner identity/speed is invisible to base-running**, even though batter
  stats (available via `batter_slot.stats`) could inform an attempt/success
  rate the same way `sb_attempt_rate`/`sb_success_rate` already do for stolen
  bases.
- **No sub-standard advancement.** A runner is never held to fewer bases than
  the fixed rule grants (e.g. a runner on 2nd never holds at 2nd on an
  infield single) — every hit type produces exactly one baseline advancement
  amount, with the single 0-outs/≥1-out variation being the only exception.
- **No advancement beyond the fixed rule**, either — a runner on 1st never
  scores on a single (a three-base advance), since the rule caps him at 2nd
  or 3rd.
- **No throw-derived secondary advancement.** Real base-running lets a
  second runner (or the batter-runner) take an extra base while the defense
  is occupied throwing to stop a different runner's advance. The engine has
  no concept of a "throw" as an intermediate event at all — `_advance_runners`
  computes every runner's final base in one deterministic pass, with no
  interaction between runners.

## Expected vs actual

| Situation | Expected | Actual |
|---|---|---|
| Runner on 1st, single, 0 outs | usually reaches 3rd, sometimes only 2nd, rarely scores (3 bases), rarely thrown out | always reaches 3rd |
| Runner on 1st, single, ≥1 out | usually reaches 2nd, sometimes 3rd (extra-base take), rarely scores, rarely thrown out | always reaches 2nd |
| Runner on 2nd, single | usually scores, sometimes held at 3rd, occasionally holds at 2nd (infield single), sometimes thrown out at home | always scores |
| Runner on 1st, double | usually scores, sometimes held at 3rd, rarely thrown out | always scores |
| Any runner advancing on a hit | non-zero chance of being thrown out (an extra out, ending the runner's advance) | never thrown out |
| Runner attempts an extra base on a hit | the resulting throw can let a *different* runner (or the batter-runner) take an additional base while the defense is occupied with it | no such interaction exists — each runner's final base is computed independently, with no shared "throw" event |

## Characterization tests (current behavior, already in place)

`sim/tests/test_engine_characterization.py::test_apply_pa_outcome_double_updates_hits_and_run_accounting`
asserts `runs_on_play == 1` for a runner on 1st scoring unconditionally on a
double — this locks in the current deterministic behavior described here and
will need updating (to assert a plausible range or to inject a seeded RNG)
once a probabilistic model lands.

## Suggested fix

- Extend `_advance_runners` (or a parallel helper it delegates to) to sample
  advancement outcomes per runner rather than applying a fixed rule, similar
  in spirit to the existing `sb_attempt_rate`/`sb_success_rate` pattern for
  steals: an attempt/hold decision, then a success/thrown-out decision when a
  runner attempts the extra base.
- A thrown-out-advancing result should add an out (mirroring how bug-sim-8's
  double/triple plays add outs) and needs a `sim_event_runner_outcomes` row
  with the correct `putout_at_base`/`putout_type`, not just a `final_base`.
- The throw-derived secondary advance (a second runner or the batter taking
  an extra base off a throw generated by a different runner's attempt) is
  not independent per-runner sampling — it requires a sequential resolution
  order: resolve the lead runner's attempt first, and only if that attempt
  generates a throw does a second runner get an opportunity to advance on
  it. This is a materially different shape from the attempt/success model
  above and could reasonably be scoped as a follow-up increment within this
  bug rather than a blocking requirement for an initial probabilistic pass.
- Since bug-sim-8 and this bug touch the same function and the same
  underlying "how do runners move on a batted ball" concern, consider fixing
  them in one base-running pass; they can also be fixed independently since
  they're disjoint outcome categories (hits vs. outs).

## Verification

- Over many simulated games, first-to-third-on-a-single rate and
  runner-thrown-out-advancing rate both fall in a plausible non-zero,
  non-100% range (neither always happens nor never happens).
- A runner is sometimes retired attempting to advance on a hit, producing a
  `sim_event_runner_outcomes` row with a putout rather than a `final_base`.
- Over many simulated games, a runner on 2nd occasionally holds at 2nd on a
  single instead of always advancing, and a runner on 1st occasionally
  scores from 1st on a single — both rare but non-zero.
- If the throw-derived secondary advance is implemented in this pass (see
  Suggested fix), at least some games show a second runner or the
  batter-runner advancing an extra base attributable to a throw drawn by a
  different runner's attempt.
- Update the characterization test listed above to assert the new
  probabilistic invariant (e.g. a range over many trials with a seeded RNG)
  instead of the current unconditional `runs_on_play == 1`.
