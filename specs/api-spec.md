# API Spec: [Working Title] Fantasy Baseball Sim

## Overview

All endpoints are served by the Node.js + Express API server. The web client is the only consumer.

**Base URL:** `/api/v1`

**Authentication:** All endpoints require a valid Supabase JWT in the `Authorization: Bearer <token>` header. The API verifies the JWT with Supabase on every request.

**Authorization:**
- Any endpoint operating on league data requires the requester to be a member of that league
- Any endpoint that modifies team data (lineup updates, roster changes) requires the requester to be the manager of that specific team

**Conventions:**
- All timestamps are ISO 8601 / UTC
- Player IDs are integers (MLB IDs)
- All other IDs are UUIDs
- Deadline timestamps in responses are computed from `sim_scheduled_at` using hardcoded offsets; they are not stored in the database. Deadline timestamps are always returned, even when the deadline has passed
- Lock state is derived from the current time vs. the relevant deadline; it is not stored in the database

**Known limitation:** Player stats included in lineup responses (platoon splits, OBP allowed, SLG allowed) are drawn from pre-lock stats captured at the batting order lock time. These may be up to a week out of date. A more frequently updated stats dataset is a post-MVP improvement.

---

## Endpoints

### Profiles

#### GET /me
Returns the current user's profile.

**Response:**
```json
{
  "id": "uuid",
  "username": "string",
  "display_name": "string"
}
```

---

### Leagues

#### GET /leagues
Returns all leagues the current user belongs to (as manager or commissioner).

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "string",
    "season_year": 2026,
    "roster_size": 22,
    "commissioner": { "id": "uuid", "display_name": "string" },
    "my_team": {
      "id": "uuid",
      "name": "string"
    }
  }
]
```

---

#### POST /leagues
Creates a new league. The current user becomes the commissioner and their team is created automatically.

**Request body:**
```json
{
  "name": "string",
  "season_year": 2026,
  "roster_size": 22,
  "my_team_name": "string"
}
```

**Response:** The created league object (same shape as GET /leagues item).

---

#### GET /leagues/:id
Returns league details.

**Response:**
```json
{
  "id": "uuid",
  "name": "string",
  "season_year": 2026,
  "roster_size": 22,
  "commissioner": {
    "id": "uuid",
    "display_name": "string"
  },
  "teams": [
    {
      "id": "uuid",
      "name": "string",
      "manager": { "id": "uuid", "display_name": "string" }
    }
  ]
}
```

---

#### GET /leagues/:id/matchups?week=:week_number
Returns all matchups in the league for a given week. Defaults to the current week if the `week` parameter is omitted. Used for league scoreboard views.

**Response:**
```json
[
  {
    "id": "uuid",
    "week_number": 11,
    "sim_scheduled_at": "2026-06-10T01:00:00Z",
    "sim_status": "scheduled",
    "home_team": { "id": "uuid", "name": "string", "manager": { "id": "uuid", "display_name": "string" } },
    "road_team": { "id": "uuid", "name": "string", "manager": { "id": "uuid", "display_name": "string" } },
    "final_score": null
  }
]
```

`final_score` is null until `sim_status` is `sim_complete`, then `{ "home": 4, "road": 2 }`.

---

#### GET /leagues/:id/standings
Returns the current standings for the league, ordered by wins descending. Derived from all `sim_complete` matchups for the season. Used as the primary team list on the league dashboard.

**Response:**
```json
[
  {
    "rank": 1,
    "team": { "id": "uuid", "name": "string", "manager": { "id": "uuid", "display_name": "string" } },
    "w": 7,
    "l": 3
  }
]
```

---

### Teams

#### GET /teams/:id/roster
Returns the team's current roster with player details and eligible positions.

**Response:**
```json
{
  "team": { "id": "uuid", "name": "string" },
  "players": [
    {
      "mlb_id": 123,
      "full_name": "string",
      "last_name": "string",
      "throws": "R",
      "bats": "R",
      "mlb_team": "LAD",
      "eligible_positions": ["P", "DH"],
      "display_positions": ["P"],
      "is_sp_eligible_this_week": true
    }
  ]
}
```

`is_sp_eligible_this_week` is included only for players with Pitcher among their eligible positions. It is false if the player started in either of the two preceding weeks' sims.

---

#### GET /teams/:id/matchups
Returns all matchups for the team's current season, ordered by week. Used to populate the home screen matchup list.

**Response:**
```json
[
  {
    "id": "uuid",
    "week_number": 11,
    "sim_scheduled_at": "2026-06-10T01:00:00Z",
    "sim_status": "scheduled",
    "home_team": { "id": "uuid", "name": "string" },
    "road_team": { "id": "uuid", "name": "string" },
    "final_score": null
  }
]
```

---

### Matchups

#### GET /matchups/:id
Returns full matchup details including both teams' lineups. This is the primary data source for the Matchup Screen.

**Response:**
```json
{
  "id": "uuid",
  "week_number": 11,
  "sim_scheduled_at": "2026-06-10T01:00:00Z",
  "sim_status": "scheduled",
  "my_team_id": "uuid or null",
  "deadlines": {
    "road_sp": "2026-06-03T01:00:00Z",
    "home_sp": "2026-06-04T01:00:00Z",
    "batting_order": "2026-06-07T01:00:00Z"
  },
  "home_team": {
    "id": "uuid",
    "name": "string",
    "manager": { "id": "uuid", "display_name": "string" }
  },
  "road_team": { ... },
  "home_lineup": { ... },
  "road_lineup": { ... }
}
```

**Lineup object:**
```json
{
  "id": "uuid",
  "sp": {
    "player": {
      "mlb_id": 123,
      "full_name": "string",
      "throws": "R",
      "eligible_positions": ["P", "DH"],
      "display_positions": ["P", "DH"],
      "is_sp_eligible_this_week": true,
      "obp_allowed": 0.298,
      "slg_allowed": 0.412
    },
    "is_locked": false,
    "locks_at": "2026-06-04T01:00:00Z"
  },
  "batting_order": [
    {
      "batting_position": 1,
      "player": {
        "mlb_id": 456,
        "full_name": "string",
        "bats": "L",
        "eligible_positions": ["CF", "DH"],
        "display_positions": ["CF"],
        "vs_lhp": { "pa": 120, "singles": 20, "doubles": 5, "triples": 0, "hr": 3, "bb": 12, "hbp": 1, "k": 25, "go": 30, "fo": 24 },
        "vs_rhp": { ... }
      },
      "field_position": "CF",
      "is_locked": false,
      "locks_at": "2026-06-07T01:00:00Z"
    }
  ],
  "bench": [
    {
      "player": {
        "mlb_id": 789,
        "full_name": "string",
        "bats": "R",
        "eligible_positions": ["1B", "DH"],
        "display_positions": ["1B"],
        "vs_lhp": { ... },
        "vs_rhp": { ... }
      }
    }
  ],
  "bullpen": [
    {
      "player": {
        "mlb_id": 321,
        "full_name": "string",
        "throws": "R",
        "eligible_positions": ["P"],
        "display_positions": ["P"],
        "is_sp_eligible_this_week": true,
        "obp_allowed": 0.310,
        "slg_allowed": 0.445
      }
    }
  ]
}
```

Notes:
- `eligible_positions` contains all positions the player may be assigned in the lineup, including DH added programmatically for all batter-eligible players. The frontend uses this for the field position picker and for lineup validation.
- `display_positions` contains only positions sourced from the MLB Stats API. The frontend uses this for player card display. DH appears in `display_positions` only if the API explicitly lists it, indicating the player regularly DHs in real life.
- Batter stats (platoon splits) and pitcher stats (OBP allowed, SLG allowed) are drawn from pre-lock stats for the current week's sim date. See known limitation noted above.
- OBP allowed = (singles + doubles + triples + hr + bb + hbp) / bf; SLG allowed = (singles + 2×doubles + 3×triples + 4×hr) / (bf − bb − hbp). Both use BF as a proxy for AB/PA, which is a minor approximation.
- The bench excludes the SP and excludes pure pitchers (players with no non-Pitcher eligible positions)
- The bullpen contains all Pitcher-eligible players on the roster who are not the SP; two-way players who are not in the starting lineup (either as SP or in the batting order) appear in both bench and bullpen
- `is_sp_eligible_this_week` is included only for Pitcher-eligible players
- For the opponent's lineup, the same structure is returned but edits are not permitted
- Any league member may access this endpoint, not only the two participating teams. For a non-participating manager, both lineup columns are read-only
- `my_team_id` identifies which team belongs to the requesting user; null for non-participating managers. The frontend uses this to determine column order (the requesting manager's team on the left if participating, otherwise the home team on the left) and whether the left column is editable (editable only if `my_team_id` is non-null and the relevant deadline has not passed)

---

### Lineups

#### PATCH /lineups/:id/sp
Updates the starting pitcher selection. Rejected if the relevant SP deadline has passed.

**Request body:**
```json
{
  "sp_player_id": 123
}
```

**Validation:**
- Player must be on the team's roster
- Player must have Pitcher as an eligible position
- Player must not have started in either of the two preceding weeks' sims
- SP deadline for this team (home or road) must not have passed

**Response:** Updated lineup object (same shape as lineup object in GET /matchups/:id).

**Errors:**
- `403` — SP deadline has passed
- `422` — Player ineligible to start (with reason)

---

#### PATCH /lineups/:id/batting-order
Replaces the full batting order. The client sends all 9 slots; the server validates the complete lineup and saves only if valid. Rejected if the batting order deadline has passed.

**Request body:**
```json
{
  "batting_order": [
    { "batting_position": 1, "player_id": 456, "field_position": "CF" },
    { "batting_position": 2, "player_id": 789, "field_position": "1B" },
    ...
  ]
}
```

**Validation:**
- Exactly 9 slots must be provided, each with a distinct batting position between 1 and 9
- All players must be on the team's roster
- Each player's assigned field_position must be among their eligible positions (excluding Pitcher, unless they are the SP and field_position is P)
- No two slots may share a field_position
- Either a DH is present or the SP occupies a slot with field_position = P (not both)
- Batting order deadline must not have passed

**Response:** Updated lineup object.

**Errors:**
- `403` — Batting order deadline has passed
- `422` — Lineup invalid (with specific reason, e.g. `"two_players_same_position"`, `"player_ineligible_for_position"`)

---

### Sim Results

#### GET /matchups/:id/results
Returns the full sim results for a completed matchup. Available to all managers in the league once `sim_status` is `sim_complete`.

**Errors:**
- `404` — Matchup not found
- `409` — Sim has not yet run (`sim_status` is not `sim_complete`)

**Response:**
```json
{
  "matchup_id": "uuid",
  "final_score": { "home": 4, "road": 2 },
  "line_score": {
    "home": [0, 0, 2, 0, 1, 0, 0, 1, 0],
    "road": [1, 0, 0, 0, 0, 1, 0, 0, 0],
    "home_totals": { "r": 4, "h": 9, "e": 0 },
    "road_totals": { "r": 2, "h": 7, "e": 1 }
  },
  "box_score": {
    "home": {
      "batting": [
        {
          "player": { "mlb_id": 123, "full_name": "string" },
          "batting_order_position": 1,
          "sequence_within_spot": 1,
          "positions": ["CF"],
          "ab": 4, "r": 1, "h": 2, "doubles": 1, "triples": 0, "hr": 0, "rbi": 1, "bb": 0, "k": 1, "sb": 0
        },
        {
          "player": { "mlb_id": 124, "full_name": "string" },
          "batting_order_position": 1,
          "sequence_within_spot": 2,
          "positions": ["PH", "LF"],
          "ab": 1, "r": 0, "h": 0, "doubles": 0, "triples": 0, "hr": 0, "rbi": 0, "bb": 0, "k": 1, "sb": 0
        }
      ],
      "pitching": [
        {
          "player": { "mlb_id": 456, "full_name": "string" },
          "pitching_sequence": 1,
          "outs_recorded": 18,
          "h": 5, "r": 1, "er": 1, "bb": 2, "k": 7, "hr": 0
        }
      ]
    },
    "road": { ... }
  },
  "play_by_play": [
    {
      "inning": 1,
      "half": "top",
      "sequence_number": 1,
      "event_type": "plate_appearance",
      "description": "Shohei Ohtani singles to center field",
      "runs_scored": 0,
      "outs_before_play": 0
    }
  ]
}
```

---

## Error Format

All errors return a consistent shape:

```json
{
  "error": {
    "code": "string",
    "message": "string"
  }
}
```

Common codes: `unauthorized`, `forbidden`, `not_found`, `conflict`, `validation_error`.

---

## Out of Scope for This Spec

- Draft endpoints
- Waiver wire and trade endpoints
- Commissioner tools (schedule generation, league settings)
- Player search/browse endpoints (needed for draft; deferred)
