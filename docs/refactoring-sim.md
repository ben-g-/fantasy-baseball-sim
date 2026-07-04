# Sim Refactoring Recommendations

## Status Update (Completed In This Session)

The following refactors are already done and should be treated as baseline:

- Extracted the plate-appearance outcome branch into `_apply_pa_outcome` in `sim/engine.py`.
- Added direct unit tests for `_apply_pa_outcome` branches (out, bb, hbp, hit) in `sim/tests/test_engine_characterization.py`.
- Made `POST /sim` endpoint in `sim/main.py` thin: it now delegates to a service and maps domain exceptions to HTTP status codes.
- Moved orchestration into `run_matchup` in `sim/sim_service.py`.
- Added domain exceptions in service layer (`MatchupNotFoundError`, `MatchupNotScheduledError`, `SimExecutionError`).
- Introduced `SimRepository` contract and `DbSimRepository` adapter to reduce direct data-access coupling.
- Added orchestration and mapping tests in `sim/tests/test_main_orchestration.py`, including a DIP regression test that fails if module-level db access leaks back into orchestration.

## Remaining High-Value Refactors

### 1. Break `run_matchup` into smaller service functions

`run_matchup` is improved but still does many things in one function.

Recommended split:

- `_load_matchup_context(matchup_id, repo)`
- `_build_player_inputs(context, repo)`
- `_compute_league_averages(sim_date, repo)`
- `_persist_sim_result(matchup_id, result, repo)`

Benefits:

- Better SRP and easier unit testing of each step.
- Clear orchestration flow with lower cognitive load.

### 2. Continue decomposing `simulate_game` control flow

After extracting `_apply_pa_outcome`, the half-inning loop still has dense logic.

Next extractions:

- Stolen-base/caught-stealing block into `_apply_steal_attempt(...)`.
- Pitcher-change/substitution emission into dedicated helper(s).
- Event-row construction into small pure helpers.

Benefits:

- Reduced nesting and easier regression diagnosis.
- More deterministic unit tests around each behavior boundary.

### 3. Formalize repository boundaries

`DbSimRepository` currently forwards one-to-one to db functions.

Next step:

- Move higher-level query composition into repository methods (for example, a single method that returns all matchup simulation inputs).
- Keep `sim_service` focused on orchestration decisions, not retrieval choreography.

### 4. Add service-focused test coverage around edge rules

Keep existing tests, then add:

- Walk-off edge cases (tie vs go-ahead behavior).
- Pitcher-change threshold behavior when one cap is reached and the other is not.
- Pinch-hit substitution sequencing and stat attribution.

## Suggested Next Iteration Order

1. Extract stolen-base helper from `simulate_game`.
2. Split `run_matchup` into private service sub-functions.
3. Add service-level tests for edge rules.
