# Build Plan: [Working Title] Fantasy Baseball Sim

## Overview

The build is organized into seven phases. Each phase produces a testable deliverable and builds directly on the previous one. The primary validation target throughout is the Mini-PRD scenario: a manager sets their starting lineup and views the simulated game result.

Phases 1–5 focus on getting that scenario working end-to-end. Phases 6–7 build out the broader product around it.

---

## Hardcoded Deadline Offsets

Lineup lock deadlines are computed from `sim_scheduled_at` using these fixed offsets. All deadlines must fall before the first MLB game of the relevant week.

| Deadline | Offset from sim time | Time (ET) |
|---|---|---|
| Road team SP deadline | − 8 days | 6:00 PM |
| Home team SP deadline | − 8 days | 9:00 PM |
| Batting order deadline | − 7 days | 12:00 PM |

Example with a Tuesday 11pm ET sim: road SP locks previous Monday at 6pm, home SP locks previous Monday at 9pm, batting order locks the following Tuesday at noon.

These are defined here rather than in the codebase so they are easy to find and change. They should be stored as named constants in the API server.

---

## Phase 1: Foundation

**Goal:** A running, authenticated full-stack skeleton with the complete database schema in place.

### Tasks

**Deployment**
- Create Supabase project; configure environment variables
- Scaffold Node.js + Express API project with TypeScript
- Scaffold Vue frontend project with TypeScript (using Vite); install and configure PrimeVue for UI components
- Set up Docker Compose for local development (Node.js API, Python sim service)
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
- Schedule pipeline to run weekly (Render cron job service)

**Seed data for development**
- Create a seed script that inserts:
  - Two test leagues of different sizes (e.g. 10 and 12 teams) to illustrate that league size can vary
  - Two real test manager accounts (each in both leagues) plus placeholder bot managers filling the remaining slots in each league (8 in the 10-team league, 10 in the 12-team league)
  - Realistic 22-player rosters for each team drawn from the players table; Shohei Ohtani must be included on one of the human-managed teams to enable interactive testing of two-way player logic
  - A matchup schedule for the current season
  - Multiple matchups in pre-configured states to allow testing any screen without waiting for real time to pass:
    - One matchup with SP deadline upcoming (lineups unlocked)
    - One matchup with SP deadline passed, batting order deadline upcoming
    - One matchup fully locked, awaiting sim
    - One matchup post-sim with seeded play-by-play results and box score

**Dev-only utilities** (not exposed in production)
- Manual sim trigger endpoint: immediately runs the sim for a specified matchup, bypassing the cron schedule
- Deadline override endpoint: sets a matchup's deadlines to the past so lineups appear locked on demand, enabling testing of locked states without waiting

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
- Two-column lineup panel (own lineup editable, opponent read-only); each column clearly labelled as Home or Road
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
- Matchup card for current week showing both teams with Home/Road labels, sim date, and "action required" indicator if deadline is approaching

**Validation:** A manager can log in, see their current matchup, change their SP, rearrange their batting order, assign field positions, and have the lineup auto-save. The opponent's lineup is visible in read-only form. Lock state updates automatically when a deadline passes.

---

## Phase 4: Sim Engine

**Goal:** The sim runs for a matchup and produces play-by-play events, a box score, and a line score. Sim results are viewable on the Matchup Screen.

### Tasks

**Sim engine (Python)**
- Set up Python FastAPI service
- Set up Python FastAPI service to receive sim requests via HTTP POST from the Node.js API server
- Implement core plate appearance resolution:
  - Probability model: for each plate appearance, first apply platoon adjustment factors to the batter's and pitcher's post-lock rates independently — the batter's rates are adjusted using their pre-lock vs. LHP or vs. RHP splits (depending on the pitcher's handedness), and the pitcher's rates are adjusted using their pre-lock vs. LHB or vs. RHB splits (depending on the batter's handedness). The adjustment factor for each outcome is the ratio of the relevant pre-lock split rate to the pre-lock overall rate. The platoon-adjusted rates are then combined via a log5-style formula to derive outcome probabilities (single, double, triple, HR, BB, HBP, K, GO, FO). Applying platoon adjustments before log5 ensures the combination operates on true-talent estimates that already reflect the handedness matchup
  - Use seeded placeholder stats for both pre-lock and post-lock stats in this phase
- Special handling for any pure pitcher in the P batting slot: auto-out every PA with varied out type (approximately 20% strikeout, 45% groundout, 35% flyout); PA appearance cap does not apply. Two-way players in the P slot are simulated normally using their real batting stats. This reflects that pure pitchers essentially never have meaningful batting stats in the current universal DH era
- Implement base-running resolution (stolen bases, runner advancement on hits)
- Implement player appearance cap logic:
  - Batters: PA cap table (0→0, 1–3→1, 4–6→2, 7–9→3, 10+→unlimited)
  - Pitchers: compelled removal when exceeding 110% of real-life BF AND pitches thrown (AND condition). The sim engine must simulate a pitch count for each plate appearance so the running total can be tracked and compared against the threshold
  - Players with 0 appearances unavailable; narrative note for mid-game removals
- Implement AI manager:
  - Pitcher management: enforce appearance caps; reliever sequencing in order of availability
  - DH transition: if SP is in the P batting slot and is pulled from pitching, transition him to DH if he is a two-way player (DH-eligible); otherwise the incoming reliever takes the P batting slot
  - Batter substitution: replace capped batters from bench
  - Use pre-lock stats (seeded placeholders) for AI manager decisions
- Write play-by-play events and runner outcomes to `sim_events` and `sim_event_runner_outcomes`
- Write box score stats to `sim_batter_stats` (including `batting_order_position`, `sequence_within_spot`), `sim_batter_positions` (fielding position sequence per batter), `sim_pitcher_stats` (including a `pitching_sequence` integer so pitchers are displayed in order of appearance in the box score), `sim_line_score`
- Update `matchups.sim_status` to `sim_complete`

**Text generation component (Python, runs after sim)**
- Template-based generator: reads structured sim events, writes `description` to each `sim_events` row
- Templates for: plate appearance outcomes, pitching changes, substitutions, stolen bases, caught stealing, pickoffs, errors, player removals

**Job dispatch (Node.js)**
- Implement node-cron job: at each scheduled sim time, find pending matchups and make a direct HTTP POST to the Python sim service for each, processed sequentially; set matchup status to `sim_pending` before each call and `sim_complete` on success
- Error handling: if a sim call fails or times out, catch the error, set the matchup status to `sim_error`, and log the failure for investigation. A `sim_error` status prevents the matchup from being retried automatically and flags it for manual intervention at MVP
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
  - Platoon splits: vs_lhb_* and vs_rhb_* variants of the counting stats above (excluding po), e.g. `vs_lhb_bf`, `vs_lhb_k`, `vs_rhb_hr`, etc.
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

**Goal:** Managers can create leagues, invite other managers, and navigate the league and team management features without relying on seed data. Rosters continue to rely on seed data until the draft is built in Phase 7.

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
- Default lineups are generated lazily, not at season start when matchups are created
- Trigger: when the previous week's batting order deadline passes and lineups lock, the system generates default lineups for the next week's matchup for each team. At this point the next week's Matchup Screen also becomes viewable
- SP default: most recently started pitcher among eligible pitchers
- Batting order default: same as the just-locked lineup
- Week 1–3 exception for SP: for the first three weeks, no eligible pitcher has a sim start history yet (the "most recently started among eligible" rule requires at least one eligible pitcher to have started a sim, which isn't possible until week 4 given the 3-man rotation constraint). Use the first pitcher-eligible player alphabetically as the SP default. The manager is expected to review and change this.
- Week 1 exception for batting order: no previous lineup exists. Find an arbitrary valid fielding assignment by greedily filling the most positionally restricted slots first (C, then SS, 2B, 3B, 1B, then outfield, then DH). Assign batting positions in conventional order: C/1B/2B/3B/SS/LF/CF/RF/DH

**League invitation flow**
- Invite managers to a league via email link
- Accept/decline invitation; create team on acceptance

**Frontend**
- League creation screen
- League dashboard: standings table (replaces a plain team list) plus current week's matchups; clicking any matchup opens the Matchup Screen in read-only mode for non-participating managers
- Navigation: league switcher, home screen per league

**Validation:** A commissioner can create a league, invite managers, and the season schedule is generated automatically. Managers can browse their league, view rosters, and navigate to their current matchup. League and team structure no longer requires seed data; rosters still depend on it pending the draft in Phase 7.

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
- Standalone team roster view (not yet designed)
- Push notifications
