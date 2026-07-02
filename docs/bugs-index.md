# Bug Index

Conflicts between the implementation and the specs (`specs/architecture.md`,
`specs/data-model.md`, `specs/api-spec.md`, `specs/mini-prd-lineup-and-sim.md`,
`specs/build-plan.md`), identified during the pre-Phase-6 spec audit.

## High severity

| ID | Component | Title | Status |
|---|---|---|---|
| [bug-sim-1](bug-sim-1.md) | Sim engine | Bullpen never populated — AI manager cannot change pitchers | Open |
| [bug-sim-2](bug-sim-2.md) | Sim engine | Pre-lock stats used for probabilities and appearance caps; post-lock never read | Open |
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
| [bug-api-2](bug-api-2.md) | API server | `GET /teams/:id/matchups` always returns `final_score: null` | Open |

## Low severity

| ID | Component | Title | Status |
|---|---|---|---|
| [bug-api-3](bug-api-3.md) | API server | PATCH lineup endpoints don't conform to response/status-code contract | Open |

## Notes

- `bug-sim-2` and `bug-sim-3` are coupled: the platoon-model fix (`bug-sim-3`) depends on
  post-lock stats being wired first (`bug-sim-2`).
- `bug-sim-1` and `bug-api-1` are pure correctness gaps independent of the Phase 6
  stats-pipeline work and can be fixed now.
- The SP two-week ineligibility item is spec-acknowledged-deferred and not tracked here;
  see the audit discussion.
- The deadline DST assumption is documented as a code comment in
  `api/src/lib/deadlines.ts` rather than tracked as a bug (near-zero in-season impact).
