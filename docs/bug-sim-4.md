# bug-sim-4: sim_batter_positions never records "PH" and drops position history

**Severity:** Medium
**Component:** Sim engine
**Status:** Open

## Summary

`sim_batter_positions` is meant to capture the *sequence* of fielding positions each
batter played, including `PH` for pinch hitters. The engine writes a single row per
final batting slot with `position_sequence = 1`, never emits `PH`, and loses the
position record for any starter who was substituted out.

## Spec references

- `specs/data-model.md` §sim_batter_positions — "Tracks the sequence of fielding
  positions each batter played during the sim … (e.g. 'CF-LF' for a player who started
  in center and moved to left)."
- `specs/data-model.md` §Enums — "`PH` (pinch hitter) is valid only in
  `sim_batter_positions`."
- `specs/api-spec.md` GET /matchups/:id/results — box score example shows
  `"positions": ["PH", "LF"]` for a substitute.
- `specs/mini-prd-lineup-and-sim.md` §Post-Sim Mode — box score batting table.

## Location

- `sim/src/engine.py:743-753` — `_build_batter_position_rows`
- `sim/src/engine.py:384-406` — pinch-hit substitution replaces the slot object

## Details

`_build_batter_position_rows` iterates the final `batting_order` and emits one row each:

```python
for slot in team.batting_order:
    pid = slot.ph_player_id or slot.player_id
    rows.append({
        'matchup_id': matchup_id,
        'player_id': pid,
        'position_sequence': 1,          # always 1
        'field_position': slot.field_position,
    })
```

Problems:

1. **No `PH` ever.** When a pinch hitter enters, the substitution logic *replaces* the
   slot with the sub's `BatterSlot` and sets `sub.field_position` to the outgoing
   player's field position. `ph_player_id` is never set. So the sub is recorded at a
   fielding position, not `PH`.
2. **Substituted starters get no position row.** The original batter's slot is
   overwritten, so he has a `sim_batter_stats` row but no `sim_batter_positions` row —
   his box-score `positions` come back empty.
3. **No multi-position sequences.** Mid-game position changes (e.g. two-way SP → DH)
   are not recorded as additional `position_sequence` rows; only the final state
   survives.

## Expected vs actual

| Scenario | Expected positions | Actual |
|---|---|---|
| Starter plays CF all game | `["CF"]` | `["CF"]` ✓ |
| Pinch hitter enters, then plays LF | `["PH", "LF"]` | `["LF"]` |
| Starter capped, replaced | starter `["CF"]`, sub `["PH", …]` | starter `[]`, sub at fielding pos |
| Two-way SP pulled → DH | `["P", "DH"]` (or similar) | single final position |

## Suggested fix

Track a position history per player as the game proceeds rather than reconstructing from
the final slot state:

- When a pinch hitter enters, append a `PH` position entry for the incoming player
  (sequence 1), and a subsequent fielding-position entry if he stays in the field.
- Preserve the outgoing starter's accumulated position entries.
- When a player's `field_position` changes mid-game (DH transition), append a new
  `position_sequence` row rather than overwriting.

Emit rows keyed by `(matchup_id, player_id, position_sequence)` per the primary key.

## Verification

Add a test that caps a starter mid-game and asserts the substitute has
`position_sequence = 1, field_position = 'PH'` and that the starter retains his own
position row.
