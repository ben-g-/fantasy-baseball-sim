# bug-api-2: GET /teams/:id/matchups always returns final_score: null

**Severity:** Medium
**Component:** API server
**Status:** Open

## Summary

The home-screen matchup list hardcodes `final_score: null` for every matchup, including
completed ones. The spec says a completed matchup returns its score, and the home screen
is supposed to display it.

## Spec references

- `specs/api-spec.md` GET /teams/:id/matchups — response includes `final_score`;
  GET /leagues/:id/matchups (same field) states: "`final_score` is null until
  `sim_status` is `sim_complete`, then `{ "home": 4, "road": 2 }`."
- `specs/mini-prd-lineup-and-sim.md` §User Flow, step 18 — "Manager opens app → home
  screen matchup card shows the final score."

## Location

- `api/src/routes/matchups.ts:408-419` — `GET /teams/:id/matchups` response mapping
  (`final_score: null` on line 416)

## Details

The handler maps each matchup with a literal `final_score: null` and never queries
results for `sim_complete` matchups:

```typescript
res.json(
  matchups.map((m) => ({
    id: m.id,
    week_number: m.week_number,
    sim_scheduled_at: m.sim_scheduled_at,
    sim_status: m.sim_status,
    home_team: teamMap[m.home_team_id] ?? null,
    road_team: teamMap[m.road_team_id] ?? null,
    final_score: null,          // always null
    has_lineup: (lineupCountMap[m.id] ?? 0) >= 2,
  })),
);
```

As a result the home-screen card cannot show a final score for completed matchups.

## Expected vs actual

| Matchup status | Expected final_score | Actual |
|---|---|---|
| scheduled / pending | `null` | `null` ✓ |
| sim_complete | `{ home, road }` | `null` |

## Suggested fix

For matchups with `sim_status === 'sim_complete'`, compute the final score from
`sim_line_score` (sum of `runs` per team) — the same derivation used in
`GET /matchups/:id/results` (`api/src/routes/matchups.ts:323-333`). Batch-fetch line
scores for all completed matchup IDs in the list, aggregate per team, and populate
`final_score` as `{ home, road }`; leave `null` for all other statuses.

## Verification

Add an integration test with one `sim_complete` matchup (seeded `sim_line_score`) and
one `scheduled` matchup, and assert the completed one returns `{ home, road }` matching
the line-score totals while the scheduled one returns `null`.
