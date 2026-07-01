# bug-api-3: PATCH lineup endpoints don't conform to the response and status-code contract

**Severity:** Low
**Component:** API server
**Status:** Open

## Summary

Both lineup mutation endpoints deviate from the api-spec contract in two ways: they
return a minimal stub instead of the full lineup object, and they use `400` for
validation failures where the spec specifies `422`.

## Spec references

- `specs/api-spec.md` PATCH /lineups/:id/sp — "**Response:** Updated lineup object (same
  shape as lineup object in GET /matchups/:id)." Errors: `403`, `422`.
- `specs/api-spec.md` PATCH /lineups/:id/batting-order — "**Response:** Updated lineup
  object." Errors: `403`, `422`.
- `specs/api-spec.md` §Error Format — common codes include `validation_error`; the PATCH
  endpoints document `422` for invalid input.

## Location

- `api/src/routes/lineups.ts:111` — `PATCH /sp` returns `{ id, sp_player_id, locks_at }`
- `api/src/routes/lineups.ts:213` — `PATCH /batting-order` returns `{ id, batting_order, locks_at }`
- `api/src/routes/lineups.ts` — validation failures use `res.status(400)` throughout
  (e.g. lines 34, 73, 83, 140, 174, 182, 198)

## Details

### Response shape

The spec says both endpoints return the full lineup object (`sp`, `batting_order`,
`bench`, `bullpen`, enriched players, lock state) — the same structure
`GET /matchups/:id` produces via `buildLineup` in `api/src/routes/matchups.ts`. The
handlers instead return small stubs:

```typescript
// PATCH /sp
res.json({ id, sp_player_id, locks_at: spDeadline });

// PATCH /batting-order
res.json({ id, batting_order: entries, locks_at: deadlines.batting_order });
```

A client relying on the documented contract (rather than re-fetching the matchup) would
not receive the enriched lineup it expects.

### Status codes

Validation failures return `400` with `apiError('validation_error', …)`, but the spec
lists `422` for invalid input on these endpoints (`403` remains correct for a passed
deadline). This is a cross-cutting inconsistency rather than a logic bug — `400` is
defensible REST, so the resolution may instead be to amend the spec to `400`. Either
way, spec and implementation should agree.

Note: `bug-api-1` covers the *missing* batting-order validation checks; this item is
only about the shape of the success response and the status code of failures.

## Expected vs actual

| | Spec | Actual |
|---|---|---|
| PATCH /sp success body | full lineup object | `{ id, sp_player_id, locks_at }` |
| PATCH /batting-order success body | full lineup object | `{ id, batting_order, locks_at }` |
| Validation failure status | `422` | `400` |
| Deadline-passed status | `403` | `403` ✓ |

## Suggested fix

- Extract the lineup-building logic from `matchups.ts` (`buildLineup` +
  `fetchPlayerMaps`) into a shared helper, and have both PATCH handlers return the full
  lineup object after a successful write.
- Reconcile the status code: either change validation failures to `422` to match the
  spec, or update the spec to `400`. Apply the choice consistently across the API.

## Verification

Add an API integration test asserting a successful `PATCH /sp` / `PATCH /batting-order`
returns a body with the full lineup shape (`sp`, `batting_order`, `bench`, `bullpen`),
and that an invalid payload returns the agreed status code.
