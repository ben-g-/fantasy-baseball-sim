# bug-api-1: Server-side batting-order validation is far weaker than the spec

**Severity:** High
**Component:** API server
**Status:** Open

## Summary

`PATCH /lineups/:id/batting-order` omits most of the validation the spec requires. Most
critically, it never checks that a player's assigned `field_position` is one he is
eligible to play, so an invalid lineup can be persisted directly via the API.

## Spec references

- `specs/architecture.md` §API Server — "Server-side lineup validation (mirrors
  client-side validation; never trust the client alone)."
- `specs/api-spec.md` PATCH /lineups/:id/batting-order, Validation:
  - "Exactly 9 slots must be provided, each with a distinct batting position between 1 and 9"
  - "All players must be on the team's roster"
  - "Each player's assigned field_position must be among their eligible positions
    (excluding Pitcher, unless they are the SP and field_position is P)"
  - "No two slots may share a field_position"
  - "Either a DH is present or the SP occupies a slot with field_position = P (not both)"
- `specs/api-spec.md` Errors — `422` with reasons such as `player_ineligible_for_position`,
  `two_players_same_position`.

## Location

- `api/src/routes/lineups.ts:122-214` — `PATCH /lineups/:id/batting-order`

## Details

Currently enforced:

- `batting_order` is a non-empty array with well-typed entries.
- DH/P XOR (`hasDH === hasP` rejected).
- If a `P` slot exists, its player must be the lineup SP.
- All players are on the team's roster.

Missing versus the spec:

1. **Field-position eligibility is never checked.** A player can be saved at a position
   not in his eligible set. Should return `422 player_ineligible_for_position`.
2. **"Exactly 9 slots"** is not enforced — any non-empty length is accepted.
3. **Distinct batting positions 1–9** are not validated (duplicates or out-of-range
   values are not rejected in code).
4. **"No two slots share a field_position"** is not checked in code. It relies on the DB
   unique constraint `(lineup_id, field_position)`, which surfaces as an unhandled
   insert error (HTTP 500) rather than the spec's `422 two_players_same_position`.

Additionally, validation failures return `400` where the spec specifies `422` (see also
`bug-api-2` / error-code consistency), and the success response is a stub
(`{ id, batting_order, locks_at }`) rather than the full lineup object the spec defines.

## Expected vs actual

| Check | Spec | Actual |
|---|---|---|
| Field-position eligibility | `422` | not checked |
| Exactly 9 distinct slots 1–9 | `422` | not checked |
| No duplicate field positions | `422` | DB constraint → unhandled 500 |
| Roster membership | `422`/validation | checked (`400`) |
| DH/P XOR | validation | checked (`400`) |
| Success response body | full lineup object | `{ id, batting_order, locks_at }` |

## Suggested fix

Before the delete/insert:

- Reject unless exactly 9 entries with distinct `batting_position` values covering 1–9.
- Fetch `player_positions` for all `player_id`s; for each entry, require
  `field_position` to be in that player's eligible set (allowing `P` only for the SP,
  and `DH` for any batter-eligible player). Return `422 player_ineligible_for_position`.
- Reject duplicate `field_position` values in code with `422 two_players_same_position`
  instead of relying on the DB constraint.
- Align status codes with the spec (`422` for validation failures) and return the full
  lineup object.

## Verification

Add API integration tests (Phase 6 test target) that submit: a player at an ineligible
position, a duplicate field position, and a lineup with 8 slots — each should return the
appropriate `422`, and no partial write should be visible afterward.
