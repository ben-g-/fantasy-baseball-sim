# bug-sim-1: Bullpen is never populated — AI manager cannot change pitchers

**Severity:** High
**Component:** Sim engine
**Status:** Open

## Summary

The bullpen for each team is always empty, so the AI manager can never bring in a
reliever. Every downstream pitching-management behavior is silently disabled.

## Spec references

- `specs/architecture.md` §Sim Engine — "AI manager logic (pitching changes, DH
  transitions, substitutions for unavailable players) is implemented here."
- `specs/architecture.md` §AI manager rules (MVP) — "Enforce pitcher appearance caps…
  Reliever sequencing: use bullpen in order of availability."
- `specs/build-plan.md` Phase 5 — "Pitcher management: enforce appearance caps;
  reliever sequencing in order of availability."
- `specs/mini-prd-lineup-and-sim.md` §Two-Way Players — "If the SP is in the P
  batting slot and is replaced on the mound by a reliever, the AI manager may
  transition him to DH…"

## Location

- `sim/src/engine.py:248-256` (`_build_team_state`, bullpen construction)
- `sim/src/engine.py:258-275` (bench construction that excludes pure pitchers)

## Details

The bullpen is built by scanning the **batting order** for pitcher slots:

```python
bullpen: list[PitcherSlot] = []
for slot in batting_order:
    if slot.field_position == 'P' and slot.player_id != sp_id:
        pinfo = player_info.get(slot.player_id, {})
        bullpen.append(PitcherSlot(...))
```

Per the data model, only one batting slot can ever have `field_position == 'P'`, and
that slot is the SP. Relievers are roster players who are **not** in the batting order;
they reach the engine via `bench_player_ids`. But the bench builder then excludes any
player whose only eligible position is Pitcher:

```python
eligible = pinfo.get('eligible_positions', [])
if not any(p != 'P' for p in eligible):
    continue  # pure pitchers don't pinch-hit
```

So relievers appear in neither the bullpen nor the bench. The bullpen is always `[]`.

### Consequences

- `TeamState.change_pitcher()` (`sim/src/engine.py:155-161`) always returns `None`.
- `should_change_pitcher()` may fire, but no substitution occurs, so the pitcher
  appearance-cap "compelled removal" never happens.
- Reliever sequencing never happens.
- The DH-transition-when-SP-is-pulled branch (`sim/src/engine.py:415-430`) is dead code.

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| Reliever available mid-game | Yes, from roster pitchers not in lineup | Never |
| Starter pulled at BF+pitch cap | Yes | Never (no reliever to insert) |
| DH transition for two-way SP | Possible | Never reached |

## Suggested fix

Build the bullpen from roster pitcher-eligible players who are not in the lineup —
the same set the API already computes in `api/src/routes/matchups.ts:108-115`. Pass
those IDs into `_build_team_state` (separately from batter bench IDs, or derive both
from the full roster inside the function using `player_info` eligibility), and
construct `PitcherSlot`s for them ordered by availability.

## Verification

Add a sim engine test where a starter's pre-/post-lock BF and pitch counts guarantee
the cap triggers, and assert that (a) a `pitching_change` event is emitted and
(b) a second pitcher appears in `sim_pitcher_stats` with `pitching_sequence = 2`.
