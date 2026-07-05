# Bug Index

Conflicts between the implementation and the specs (`specs/architecture.md`,
`specs/data-model.md`, `specs/api-spec.md`, `specs/mini-prd-lineup-and-sim.md`,
`specs/build-plan.md`), identified during the pre-Phase-6 spec audit.

## High severity

| ID | Component | Title | Status |
|---|---|---|---|
| [bug-sim-1](bug-sim-1.md) | Sim engine | Bullpen never populated — AI manager cannot change pitchers | Open |
| [bug-sim-2](bug-sim-2.md) | Sim engine | Pre-lock stats used for probabilities and appearance caps; post-lock never read | Open |
| [bug-sim-11](bug-sim-11.md) | Sim engine | Batter `r` (runs scored) never incremented — box score R column always zero | Fixed |
| [bug-sim-12](bug-sim-12.md) | Sim engine | Bases-loaded walk/HBP doesn't move any runners and drops the batter from the base state | Open |
| [bug-api-1](bug-api-1.md) | API server | Server-side batting-order validation far weaker than spec | Open |

## Medium severity

| ID | Component | Title | Status |
|---|---|---|---|
| [bug-sim-3](bug-sim-3.md) | Sim engine | Platoon probability model does not match specified algorithm | Open |
| [bug-sim-4](bug-sim-4.md) | Sim engine | `sim_batter_positions` never records "PH" and drops position history | Open |
| [bug-sim-5](bug-sim-5.md) | Sim engine | Walk/HBP-forced runs not attributed to R/ER/RBI | Open |
| [bug-sim-6](bug-sim-6.md) | Sim engine | PA event sequencing corrupted by post-PA steal events | Open |
| [bug-sim-7](bug-sim-7.md) | Sim engine | Extra-innings termination doesn't match spec (18-inning cap, no forced-HR rule) | Open |
| [bug-sim-8](bug-sim-8.md) | Sim engine | Baserunner outcomes on outs not modelled (no sac flies, double plays, or advancement on outs) | Open |
| [bug-sim-9](bug-sim-9.md) | Sim engine | HBP credited to batter's `bb` bucket but not the pitcher's | Open |
| [bug-sim-10](bug-sim-10.md) | Sim engine | Runner advancement on hits is deterministic, not probabilistic | Open |
| [bug-sim-13](bug-sim-13.md) | Sim engine, API server | Play-by-Play never narrates baserunner outcomes (schema, text-gen, and API all missing) | Fixed |
| [bug-api-2](bug-api-2.md) | API server | `GET /teams/:id/matchups` always returns `final_score: null` | Open |

## Low severity

| ID | Component | Title | Status |
|---|---|---|---|
| [bug-api-3](bug-api-3.md) | API server | PATCH lineup endpoints don't conform to response/status-code contract | Open |

## Notes

- `bug-sim-2` and `bug-sim-3` are coupled: the platoon-model fix (`bug-sim-3`) depends on
  post-lock stats being wired first (`bug-sim-2`).
- `bug-sim-5` and `bug-sim-9` overlap: both touch the `bb`/`hbp` branches of `_apply_pa_outcome`.
  `bug-sim-5` is about R/ER/RBI not being attributed on forced walks/HBP; `bug-sim-9` is about
  the batter/pitcher `bb` bucket asymmetry on HBP specifically. They can be fixed together or
  independently.
- `bug-sim-1` and `bug-api-1` are pure correctness gaps independent of the Phase 6
  stats-pipeline work and can be fixed now.
- `bug-sim-11` and `bug-sim-5` both touch the `hit`/`bb`/`hbp` branches of
  `_apply_pa_outcome` and the `runs_on_play` value: `bug-sim-5` is pitcher R/ER and
  batter RBI not attributed on forced bb/hbp runs; `bug-sim-11` is that no batter's own
  `r` is ever incremented on any play type. A single pass through those branches can
  fix both.
- `bug-sim-8` and `bug-sim-10` both touch `_advance_runners`: `bug-sim-8` is runner outcomes
  on outs (not modelled at all); `bug-sim-10` is runner advancement on hits (modelled, but
  deterministic instead of probabilistic). They can be fixed together or independently.
- `bug-sim-13` is independent of `bug-sim-8`/`bug-sim-10`: those are about the *engine* not
  computing realistic runner outcomes; `bug-sim-13` is about the existing runner outcomes
  (whatever they are) never being narrated in the Play-by-Play feed at all. Fixing `bug-sim-8`
  first would give `bug-sim-13`'s narration more interesting outcomes to describe (sac flies,
  double plays), but isn't a prerequisite — narration can be built against today's simplified
  `_build_runner_outcomes` output and will pick up richer outcomes automatically once
  `bug-sim-8` lands.
- `bug-sim-12` was found while fixing `bug-sim-11` and touches the same bases-loaded
  `bb`/`hbp` branch of `_advance_runners` as `bug-sim-5`. It's independent of both: the
  `r`-crediting fix for `bug-sim-11` reads scorer identity before this branch's bad
  reassignment happens, so it isn't affected by `bug-sim-12`; and `bug-sim-5`'s pitcher
  R/ER + batter RBI attribution doesn't depend on the base-state bug either.
- The SP two-week ineligibility item is spec-acknowledged-deferred and not tracked here;
  see the audit discussion.
- The deadline DST assumption is documented as a code comment in
  `api/src/lib/deadlines.ts` rather than tracked as a bug (near-zero in-season impact).
