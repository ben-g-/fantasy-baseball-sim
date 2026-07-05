# bug-sim-8: Baserunner outcomes on outs not modelled (missing Phase 5 base-running deliverable)

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

The sim treats every batter out as exactly one out with no effect on the runners: no
runner ever advances on an out, no runner is ever retired on an out, and no runner is
ever caught off a base. Real baseball produces several outcomes on batted-ball outs that
the engine never generates:

- Runners tagging up / advancing on **flyouts** (sacrifice flies) and on **groundouts**,
  sometimes succeeding and sometimes being thrown out advancing.
- Runners **forced** to advance on ground balls, which can convert a groundout into a
  **double or triple play** or a **force play** (a lead runner retired in addition to — or instead of — the
  batter).
- Runners **caught off their base on lineouts** (doubled off).

These are part of the Phase 5 base-running deliverable, not a post-MVP nicety. Phase 5's
validation target is a believable box score and play-by-play; a game in which no runner
ever advances or is retired on an out is visibly wrong (zero sacrifice flies, zero double
plays, runners frozen in place on every groundout).

This bug covers runner outcomes on outs specifically. The companion gap on the hits side —
runner advancement on hits is modelled but deterministic rather than probabilistic — is
tracked separately as [bug-sim-10](bug-sim-10.md), since it's a narrower, differently-shaped
problem (advancement exists but has no randomness, vs. not existing at all here). Both bugs
touch `_advance_runners` and can be fixed together or independently.

## Spec references

- `specs/build-plan.md` Phase 5 → "Implement base-running resolution". This task must
  cover runner advancement and retirement on outs (sac flies, advancing/being thrown out
  on grounders, force plays and the resulting double/triple plays, and runners doubled off
  on lineouts) — not only advancement on hits.
- `specs/architecture.md` §Simulation Design → §Extra innings: the termination guarantee
  is deliberately independent of the number of outs, so it remains sound once multi-out
  plays exist (a double/triple play cannot end a tied bottom-of-the-30th without the
  forced-HR rule firing) and once plays exist that both score a run and make an out (which
  would otherwise potentially tie the score up and end the inning on the same play). This
  soundness depends on the road-leading forced-out rule added in `bug-sim-7`.

## Location

- `sim/src/engine.py:588-637` — `_apply_pa_outcome`: on any out (`k`/`go`/`fo`) it does
  `outs += 1` and records the AB/out, but never touches `runners`. Runners neither advance
  nor are retired, and no runs (e.g. a sac fly with a runner on 3rd) ever score on an out.
- `sim/src/engine.py:640-702` — `_build_runner_outcomes`: on outs, every existing runner gets
  `final_base = base_before` (line 689: "runners stay on outs (no DP modelled)"), and
  runner rows never carry a `putout_at_base`/`putout_type`. The batter row is always
  emitted with `putout_type: 'force'` at base 1 for *every* out type, which is also wrong
  — a strikeout is not a force out and a caught flyout is not a putout at first.
- `sim/src/engine.py:29-89` — `_advance_runners`: the advancement lookup only handles hits and
  bb/hbp force advances; there is no branch for advancement or retirement on outs.

## Details

Current behavior in `_apply_pa_outcome`:

```python
is_out = outcome in ('k', 'go', 'fo')
...
if is_out:
    outs += 1
    fielding_team.record_pitcher(outs=1, k=(1 if outcome == 'k' else 0))
    batting_team.record_batter(batter_slot, ab=1, k=(1 if outcome == 'k' else 0))
    # runners is returned unchanged
```

Consequences:

- **No sacrifice flies.** A flyout with a runner on 3rd and fewer than 2 outs never scores
  the runner; `sim_batter_stats` has no path to record a sac fly and pitcher R/ER is never
  charged for it.
- **No advancement on groundouts.** A runner on 1st on a groundout stays on 1st instead of
  moving to 2nd; a runner on 2nd never advances to 3rd on a grounder to the right side.
- **No force plays or double plays.** With a runner on 1st and a ground ball, the lead
  runner is never forced/retired, so the engine produces zero double plays. This is the
  same gap the former "Multi-out plays" deferred item described, now folded here because
  force outs are one case of the broader "runner outcomes on outs" model.
- **No runners caught off on lineouts.** A line drive caught with a runner off the base
  never doubles the runner off.
- **Occupancy-ordering constraint applies here too.** Whatever resolves runner movement on
  outs must guarantee a trailing runner never advances past (or onto the same base as) a
  more-advanced runner who doesn't also advance — e.g. a runner tagging from 2nd on a
  flyout cannot reach 3rd if the runner who started on 3rd holds there instead of scoring.
  Force-play logic already imposes an ordering in the double/triple-play case (the batter's
  presence forces the lead runner), but unforced advancement — tag-ups on flyouts, and a
  trailing runner advancing on a groundout with no runner ahead of him to be forced — has
  the same independent-sampling risk documented in [bug-sim-10](bug-sim-10.md): sampling
  each runner's advance separately, without capping trailing runners by where the runner(s)
  ahead of them land, can produce an invalid state.
- **Throw-derived secondary advancement is also missing here.** A tag-up throw aimed at
  retiring one runner can let a different runner take an extra base while the defense is
  occupied with it — e.g. a runner on 1st takes 2nd while the catcher's throw goes to 3rd
  trying to catch a tagging runner. This is the same mechanic identified for hits in
  bug-sim-10 and needs the same sequential (not independent) resolution.

The `sim_event_runner_outcomes` schema already supports multiple putouts per event
(`putout_type`, `putout_at_base`) and an `intermediate_base`/`final_base` per runner, so
this is an engine change, not a schema migration.

## Expected vs actual

| Situation | Expected | Actual |
|---|---|---|
| Flyout, runner on 3rd, < 2 outs | runner sometimes tags and scores (sac fly), sometimes holds | runner always holds; never scores |
| Groundout, runner on 1st, no force behind | runner sometimes advances to 2nd | runner always holds |
| Ground ball, runner on 1st | lead runner forced; sometimes a double play | one out, both runners safe |
| Lineout, runner off base | runner sometimes doubled off | never |
| Batter putout on a strikeout / flyout | `putout_type` reflects K / catch | always recorded as `force` at base 1 |

## Suggested fix

- Extend `_apply_pa_outcome` so `go` and `fo` resolve runner movement and retirement
  probabilistically, mutating `runners`, incrementing `outs` by more than one where a
  double/triple play occurs, and scoring runs (sac fly) where appropriate. Attribute the
  resulting runs to pitcher R/ER and any sac-fly/RBI credit to the batter.
- Add out-type branches to `_advance_runners` (or a parallel helper) encoding: tag-up
  advancement on flyouts, situational advancement on groundouts, force logic on grounders
  with a runner on 1st (and 1st+2nd, bases loaded), and doubling a runner off on lineouts.
  Success/failure should be probabilistic (a runner thrown out advancing is an extra out).
- As with bug-sim-10, per-runner sampling for tag-ups and unforced groundout advancement
  must resolve from the most-advanced runner backward and cap each trailing runner's
  advancement by where the runner(s) ahead of him ended up, to avoid invalid states (two
  runners on one base, or a trailing runner passing one who held). Force-play/DP logic
  already has a natural ordering; the non-forced advancement cases don't yet.
- Fix `_build_runner_outcomes` to emit correct `putout_type`/`putout_at_base` per retired
  runner (including the batter), rather than hardcoding `force` at base 1 for all outs, and
  to reflect advanced runners' `final_base`.
- Keep the extra-innings termination guarantee independent of out count (already the case);
  confirm it still holds once a double/triple play can take a tied inning from < 2 outs to
  3 (see `bug-sim-7`).

## Verification

- Sac fly: flyout with a runner on 3rd and < 2 outs sometimes scores the runner and credits
  the pitcher with a run; never scores with 2 outs.
- Groundout advancement: runner on 1st with no force sometimes reaches 2nd on a groundout.
- Double play: ground ball with a runner on 1st sometimes records two outs and clears the
  lead runner; the `sim_event_runner_outcomes` rows carry the correct putouts.
- Lineout: a runner is sometimes doubled off on a lineout.
- Over many simulated games, aggregate sac-fly and double-play rates fall in a plausible
  range rather than being identically zero.
- Batter putout rows carry a `putout_type` consistent with the out type (not always
  `force`).
- Invariant, checked across many simulated games: no play — including one that also
  produces an out — ever results in two runners occupying the same base, or a trailing
  runner ending up ahead of a runner who started ahead of him and did not score. Same
  invariant as bug-sim-10; if both bugs are fixed together, verify it holds jointly since a
  single play can be resolved by both hit- and out-side logic across an inning.
