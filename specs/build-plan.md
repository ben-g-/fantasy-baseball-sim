# Build Plan: [Working Title] Fantasy Baseball Sim

## Overview

The build is organized into seven phases. Each phase produces a testable deliverable and builds directly on the previous one. The primary validation target throughout is the Mini-PRD scenario: a manager sets their starting lineup and views the simulated game result.

Phases 1–5 focus on getting that scenario working end-to-end. Phases 6–7 build out the broader product around it.

---

## Hardcoded Deadline Offsets

Lineup lock deadlines are computed from `sim_scheduled_at` using these fixed offsets:

| Deadline | Offset from sim time |
|---|---|
| Road team SP deadline | − 7 days |
| Home team SP deadline | − 6 days |
| Batting order deadline | − 2 days |

These are defined here rather than in the codebase so they are easy to find and change. They should be stored as named constants in the API server.

---

## Phase 1: Foundation

**Goal:** A running, authenticated full-stack skeleton with the complete database schema in place.

### Tasks

**Infrastructure**
- Create Supabase project; configure environment variables
- Scaffold Node.js + Express API project with TypeScript
- Scaffold React frontend project
- Set up Docker Compose for local development (Node.js API, Python sim service, Redis)
- Configure ESLint, Prettier, and basic CI

**Auth**
- Enable Supabase Auth with email/password and Google OAuth
- Implement JWT verification middleware in the Node.js API (verify token with Supabase on every request)
- Implement GET /me endpoint
- Frontend: login and signup screens

**Database**
- Create all enums, tables, constraints, and indexes defined in the data model
- Enable Row Level Security (RLS) on all tables; define initial policies
- Enable Supabase Realtime on `matchups`, `lineups`, and `lineup_batting_order` tables. Supabase Realtime uses PostgreSQL logical replication to stream row-level changes to subscribed clients. Enabling it requires adding these tables to the Realtime publication in the Supabase dashboard. The frontend then subscribes to specific rows — e.g. the current matchup row (to detect `sim_status` changing to `sim_complete` and switch the Matchup Screen to post-sim mode) and the current lineup and batting order rows (to detect opponent SP and batting order updates without polling). Note: lock state itself does not require Realtime — it is derived from deadline timestamps and can be computed locally with a countdown timer

**Validation:** A user can sign up, log in, and receive a valid JWT. The database schema is fully in place. The API returns the user's profile via GET /me.

---

## Phase 2: Player Data Pipeline

**Goal:** MLB player master data in the database, with eligible positions, ready to be assigned to rosters.

### Tasks

**Data pipeline (Python)**
- Build MLB Stats API client (Python) targeting `statsapi.mlb.com`
- Ingest all active MLB players: mlb_id, full_name, last_name, throws, bats, mlb_team
- Ingest eligible fantasy positions for each player and populate `player_positions` with `source = 'api'`
- For every batter-eligible player (any player with at least one non-Pitcher position from the API), also insert a DH row with `source = 'derived'` if DH is not already present. Pure pitchers (Pitcher as their only eligible position) do not get DH added
- Player cards display only positions where `source = 'api'`; all positions regardless of source are used for lineup eligibility logic
- Schedule pipeline to run weekly (ECS scheduled task or Lambda)

**Seed data for development**
- Create a seed script that inserts:
  - Two test leagues of different sizes (e.g. 10 and 12 teams) to illustrate that league size can vary
  - Two real test manager accounts (each in both leagues) plus placeholder bot managers filling the remaining slots in each league (8 in the 10-team league, 10 in the 12-team league)
  - Realistic 22-player rosters for each team drawn from the players table
  - A matchup schedule for the current season
  - Default lineups for the current week's matchup

**Validation:** The database contains real MLB players with correct eligible positions. Seed script produces a fully populated development environment with two leagues of different sizes (e.g. 10 and 12 teams), two real test manager accounts in both leagues, placeholder bot managers filling remaining slots, realistic rosters for all teams, a matchup schedule for the current season, and default lineups for the current week's matchups — without requiring a draft or league management UI.

---

## Phase 3: Matchup & Lineup

**Goal:** The Matchup Screen works end-to-end in pre-sim mode. A manager can view both lineups, select their SP, and set their batting order.

### Tasks

**API**
- GET /matchups/:id — full matchup response including both lineups, computed deadlines, player stats from pre-lock snapshots (use seeded placeholder stats for now)
- PATCH /lineups/:id/sp — validate and save SP selection
- PATCH /lineups/:id/batting-order — validate and save full batting order
- GET /teams/:id/matchups — for home screen matchup list

**Frontend — Matchup Screen (pre-sim mode)**
- Two-column lineup panel (own lineup editable, opponent read-only)
- SP slot with lock status and countdown to deadline
- Batting order slots 1–9 with field position display
- Bench and bullpen sections
- SP Selection panel (modal): list of pitcher-eligible players, ineligibility indicators, stats
- Inline batting order editing: drag to reorder, drag bench player into batting slot (retaining previous field position if ineligible, for manager to resolve), drag bench player onto Pitcher slot → DH; "Use SP instead" control on DH slot card
- Field position picker per slot (inline dropdown)
- Inline validation highlighting with hover tooltips
- Unsaved changes indicator; auto-save on valid state; silent revert on navigation away
- SP-switching rules: when a new SP is selected, if the old SP was in the P batting slot, the new SP automatically takes that slot; if the new SP was in the batting order at a non-Pitcher position, his field_position automatically changes to P, and lineup validity is re-evaluated (clean if he was DH; invalid if he was at a defensive position, for the manager to resolve). Note: a new SP who was the DH and an old SP in the P slot cannot coexist in a valid saved lineup, so this scenario only arises from an already-invalid unsaved state
- Supabase Realtime subscription: update lock state when deadline passes without page refresh

**Frontend — Home Screen**
- Matchup card for current week showing both teams, sim date, and "action required" indicator if deadline is approaching

**Validation:** A manager can log in, see their current matchup, change their SP, rearrange their batting order, assign field positions, and have the lineup auto-save. The opponent's lineup is visible in read-only form. Lock state updates automatically when a deadline passes.

---

## Phase 4: Sim Engine

**Goal:** The sim runs for a matchup and produces play-by-play events, a box score, and a line score. Sim results are viewable on the Matchup Screen.

### Tasks

**Sim engine (Python)**
- Set up Python FastAPI service
- Implement BullMQ Redis consumer (Python worker picks up sim jobs)
- Implement core plate appearance resolution:
  - Probability model: derive outcome probabilities (single, double, triple, HR, BB, HBP, K, GO, FO) from post-lock batter and pitcher stats using a log5-style combination
  - Use seeded placeholder stats for post-lock stats in this phase
- Special handling for any player in the P batting slot: auto-out every PA with varied out type (approximately 20% strikeout, 45% groundout, 35% flyout); PA appearance cap does not apply. This reflects that pitchers essentially never have meaningful batting stats in the current universal DH era
- Implement base-running resolution (stolen bases, runner advancement on hits)
- Implement player appearance cap logic:
  - Batters: PA cap table (0→0, 1–3→1, 4–6→2, 7–9→3, 10+→unlimited)
  - Pitchers: compelled removal when exceeding 110% of real-life BF AND pitches thrown (AND condition)
  - Players with 0 appearances unavailable; narrative note for mid-game removals
- Implement AI manager:
  - Pitcher management: enforce appearance caps; reliever sequencing in order of availability
  - DH transition: if SP is in the P batting slot and is pulled from pitching, transition him to DH if he is a two-way player (DH-eligible); otherwise replace him in the batting order with a bench player
  - Batter substitution: replace capped batters from bench
  - Use pre-lock stats (seeded placeholders) for AI manager decisions
- Write play-by-play events and runner outcomes to `sim_events` and `sim_event_runner_outcomes`
- Write box score stats to `sim_batter_stats`, `sim_pitcher_stats`, `sim_line_score`
- Update `matchups.sim_status` to `sim_complete`

**Text generation component (Python, runs after sim)**
- Template-based generator: reads structured sim events, writes `description` to each `sim_events` row
- Templates for: plate appearance outcomes, pitching changes, substitutions, stolen bases, caught stealing, pickoffs, errors, player removals

**Job dispatch (Node.js)**
- Implement node-cron job: at each scheduled sim time, find pending matchups and enqueue sim jobs via BullMQ
- Update matchup status to `sim_pending` when job is enqueued
- Supabase Realtime: publish `sim_complete` event to subscribed clients

**API**
- GET /matchups/:id/results — box score, line score, play-by-play

**Frontend — Matchup Screen (post-sim mode)**
- Screen transforms to results view after sim completes (via Supabase Realtime)
- Box Score tab: line score grid, batting stats table, pitching stats table
- Play-by-Play tab: chronological event feed grouped by half-inning

**Validation:** A sim job can be manually triggered for a seeded matchup. The sim runs, produces play-by-play events and a box score, and the Matchup Screen switches to post-sim mode and displays the results.

---

## Phase 5: Stats Pipeline

**Goal:** The sim uses real weekly stats instead of seeded placeholders. The full prediction-game mechanic is operational.

### Tasks

**Data pipeline (Python)**
- Extend MLB Stats API client to ingest weekly stats for all rostered players
- Ingest and store `batter_pre_lock_stats` at batting order lock time:
  - Counting stats: pa, singles, doubles, triples, hr, bb, hbp, k, go, fo, sb, cs
  - Platoon splits: vs_lhp_* and vs_rhp_* variants (excluding sb, cs)
- Ingest and store `pitcher_pre_lock_stats` at batting order lock time:
  - Counting stats: bf, pitches_thrown, singles, doubles, triples, hr, bb, hbp, k, go, fo, po
- Ingest and store `batter_post_lock_stats` and `pitcher_post_lock_stats` just before sim fires:
  - Same stat sets as above; keyed by (player_id, sim_date)
- Trigger post-lock ingestion as part of the sim dispatch pipeline, before enqueuing sim jobs
- Handle players with 0 post-lock appearances (appearance cap = 0, unavailable in sim)

**Sim engine update**
- Replace seeded placeholder stats with real pre-lock and post-lock stats from the database
- Confirm probability model behaves correctly with real data

**Validation:** A full end-to-end run uses real MLB weekly stats. Managers who select players with strong real-life performance in the lock period see that reflected in sim outcomes.

---

## Phase 6: League & Team Management

**Goal:** Managers can create leagues, invite other managers, and navigate the full app without relying on seed data.

### Tasks

**API**
- POST /leagues — create league and commissioner's team
- GET /leagues — list user's leagues
- GET /leagues/:id — league details
- GET /leagues/:id/matchups?week= — all matchups in a league for a given week
- GET /teams/:id/roster — team roster with player details

**Schedule generation**
- Implement matchup schedule generator: round-robin schedule for a league's teams, run at season start
- Generates all matchup records with `sim_scheduled_at` timestamps for the season

**Default lineup generation**
- When a matchup is created, auto-generate default lineups for each team:
  - SP default: most recently started pitcher among eligible pitchers
  - Batting order default: same as previous sim (or alphabetical for first matchup of season)

**League invitation flow**
- Invite managers to a league via email link
- Accept/decline invitation; create team on acceptance

**Frontend**
- League creation screen
- League dashboard: team list, current week's matchups (all matchups in the league)
- Team roster view
- Navigation: league switcher, home screen per league

**Validation:** A commissioner can create a league, invite managers, and the season schedule is generated automatically. Managers can browse their league, view rosters, and navigate to their current matchup without seed data.

---

## Phase 7: Draft

**Goal:** Managers can build their rosters through a snake draft before the season begins.

### Tasks

**Data model additions**
- `draft_picks` table: league_id, round, pick_number, team_id, player_id, picked_at
- Draft state tracking on the league record (draft_status, draft_started_at, current_pick_number)

**API**
- GET /leagues/:id/draft — current draft state (pick order, picks made, on the clock)
- POST /leagues/:id/draft/picks — make a pick (commissioner or on-the-clock manager)
- Player search endpoint: GET /players?search=&position=&available=true

**Draft room (frontend)**
- Live draft board showing all picks made and available players
- Player search and filter (by position, team, name)
- On-the-clock indicator and pick timer
- Supabase Realtime: all managers see picks in real time

**Validation:** A league can run a full snake draft. All picks are reflected in real time for all participants. Rosters are populated correctly in `roster_players`.

---

## Deferred (Post-MVP)

- Waiver wire and trade flows
- AI-generated game recap (third tab on post-sim Matchup Screen)
- Mobile support
- Live/real-time sim watching
- In-game managerial decisions by the human manager
- Configurable deadline offsets per league
- Multi-game series matchups
- ERA/WHIP/K9 display (requires adding `outs_recorded` and `er` to pitcher stats tables)
- Pitcher ordering in box score
- Push notifications
