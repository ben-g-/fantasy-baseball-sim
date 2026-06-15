# Architecture Document: [Working Title] Fantasy Baseball Sim

## System Overview

The system has four primary layers:

1. **Web client** — Vue SPA (desktop web, MVP)
2. **API server** — Node.js + Express, handles all application logic and data access
3. **Sim engine** — Python service, executes game simulations
4. **Data store** — PostgreSQL via Supabase

Communication between layers:
- The web client talks exclusively to the Node.js API server via REST
- The API server dispatches sims by making a direct HTTP POST to the Python sim service at the scheduled sim time via a cron job
- The Python sim service runs the simulation synchronously and writes results to PostgreSQL
- The API server reads results from PostgreSQL and serves them to the client
- Lineup lock state changes are pushed to the client via Supabase Realtime

---

## Tech Stack

| Component | Technology |
|---|---|
| Web client | Vue |
| Component library | PrimeVue |
| API server | Node.js + Express |
| Auth | Supabase Auth (JWT, Google/Apple OAuth) |
| Database | PostgreSQL via Supabase |
| Realtime | Supabase Realtime (PostgreSQL-backed pub/sub) |
| Sim engine | Python (FastAPI service + simulation logic) |
| Text generation | Python module (post-sim step within sim service) |
| Stat modeling | NumPy, pandas, pybaseball |
| Data pipeline | Python scripts (scheduled) |

---

## Components

### Web Client (Vue)

Responsibilities:
- Render the Matchup Screen in pre-sim and post-sim modes
- Manage local lineup state (unsaved edits tracked client-side)
- When the lineup is edited, if the resulting state is valid, auto-save to the API
- Subscribe to Supabase Realtime to detect lineup lock state changes without polling
- Display the home screen with matchup cards showing current status or final score

### API Server (Node.js + Express)

Responsibilities:
- All REST endpoints consumed by the web client (auth, leagues, rosters, lineups, matchups, sim results)
- Server-side lineup validation (mirrors client-side validation; never trust the client alone)
- Deadline enforcement: deadline timestamps are computed from `sim_scheduled_at` using hardcoded offsets (never stored); the API treats a lineup as locked if the current time is past the computed deadline (lazy enforcement — no cron job required)
- Sim dispatch: at the scheduled sim time, a node-cron job makes a direct HTTP POST to the Python sim service for each pending matchup; sets matchup status to `sim_pending` before the call and `sim_complete` on success
- Serves sim results from PostgreSQL once available

### Sim Engine (Python)

Responsibilities:
- Exposes a FastAPI service; receives sim requests via HTTP POST from the Node.js API server
- For each request: fetches the locked lineups, full rosters (bench and bullpen players are needed for AI manager substitutions), and the relevant weekly stats from PostgreSQL, then runs the simulation and writes the structured play-by-play event log and box score back to PostgreSQL
- Simulation logic uses a probabilistic, stat-driven model (see Simulation Design below)
- AI manager logic (pitching changes, DH transitions, substitutions for unavailable players) is implemented here
- After the sim completes, triggers the text-generation step (see below) before returning a success response to the API server

### Text-Generation Component (Python)

A lightweight Python module that runs as a post-sim step within the same Python service as the sim engine. It is not a separate service.

Responsibilities:
- Reads structured sim events from `sim_events` and `sim_event_runner_outcomes`
- Generates a natural-language description for each event using templates (e.g. "Shohei Ohtani homers to left — 2 runs score", "[Reliever] replaces [Pitcher] pitching")
- Writes the generated descriptions to the `description` column of `sim_events`
- Keeping text generation separate from the sim engine preserves a clean separation of concerns: the sim engine produces structured facts; the text-generation step turns them into readable narrative

### Database (PostgreSQL via Supabase)

Primary data store for all persistent data. Key entity groups:
- Users, leagues, teams, rosters
- Players (MLB master data + weekly performance stats)
- Matchups (teams involved, home/road designation, sim status, scheduled sim time)
- Lineups (SP selection, batting order, field positions)
- Sim results (play-by-play event log, box score)

Note: lineup lock state is never stored explicitly. It is always derived by comparing the current time to the deadline computed from the matchup's `sim_scheduled_at`.

### Data Pipeline (Python scripts)

Responsibilities:
- Ingests MLB player master data (name, MLB ID, eligible positions, handedness, team) from the MLB Stats API on a periodic basis
- Ingests two stat snapshots per player per matchup: a pre-lock snapshot (season stats up to the lineup lock date, for AI manager decisions) and a post-lock stat line (stats from the period after lineup lock, for probability estimation). The weekly stat line must include all metrics required by the sim engine — PA, BF, pitch count, and performance stats
- Critically, the pipeline run that feeds each sim must execute *after* the relevant real-life games have concluded but *before* the sim fires. Its schedule is therefore tightly coupled to the sim schedule, not a background weekly batch
- Writes directly to PostgreSQL

---

## Simulation Design

The sim engine uses a **probabilistic, stat-driven model** to resolve each plate appearance. This is the core IP of the product.

### Stat Window

The sim is a prediction game: managers select lineups based on how they expect their players to perform in the subsequent period. This requires two separate stat snapshots per player per matchup, used in distinct contexts:

**Post-lock stats** (stats from the period between lineup lock and sim run): used exclusively to estimate outcome probabilities (likelihood of a hit, strikeout, home run, etc.). These stats are unknowable at lineup-set time and are deliberately withheld from the AI manager.

**Pre-lock stats** (season stats up to the lineup lock date): used exclusively by the AI manager for in-game decisions (whether to pull a pitcher, whether to pinch hit, etc.), supplemented by each player's performance in the sim so far. Giving the AI manager access to post-lock stats would be clairvoyance — it would be making tactically optimal decisions based on information that wasn't available when the lineup was set.

The data pipeline must capture both snapshots, and the sim engine must be careful to use each only in the appropriate context.

### Player Appearance Caps

Since a single sim game corresponds to a full real-life week of MLB play, appearance counts are capped to reflect each player's actual real-life workload that week. Players who barely played in real life barely play in the sim; players who didn't play at all are unavailable.

**Batters — hard cap on sim PAs:**

| Real-life PAs | Sim PA cap |
|---|---|
| 0 | 0 (scratched before game) |
| 1–3 | 1 |
| 4–6 | 2 |
| 7–9 | 3 |
| 10+ | Unlimited |

**Pitchers — compelled removal threshold:**

The AI manager is compelled to remove a pitcher once he has exceeded 110% of his real-life weekly volume on **both** of the following metrics simultaneously (AND condition):
- Batters faced (BF)
- Pitches thrown

Innings pitched is not used as the removal metric, as it does not capture pitch count.

A pitcher with 0 real-life appearances is unavailable for the sim entirely.

**Narrative handling:** When a player is removed due to hitting his appearance cap, the play-by-play includes a note such as "[Player] removed himself in the 5th inning due to illness."

**Data pipeline requirement:** PA, BF, and pitch count are among the weekly stats that must be ingested for the sim engine.

### Inputs per matchup
- Both teams' locked lineups (batting order, field positions, SP)
- Both teams' full rosters (for AI manager substitutions)
- Post-lock stat lines for all players on both rosters (for probability estimation)
- Pre-lock stat snapshots for all players on both rosters (for AI manager decisions)
- Lineup lock timestamp (to correctly window the stats)
- Pitcher handedness and batter platoon splits

### Plate appearance resolution
Each at-bat is resolved by sampling from a probability distribution derived from the batter's and pitcher's weekly stats. Outcomes include: single, double, triple, home run, walk, strikeout, ground out, fly out, etc. Base-running outcomes (stolen bases, advancing on hits) are resolved separately.

### AI manager rules (MVP)
- Enforce pitcher appearance caps as described above
- Enforce batter appearance caps: sub in a bench player when a batter hits his cap mid-game
- DH transition: if SP is batting and is pulled from pitching, transition him to DH rather than replacing him in the batting order with the reliever
- Reliever sequencing: use bullpen in order of availability (no closer logic at MVP)

### Outputs
- Play-by-play event log (one record per plate appearance and notable event)
- Box score (batting and pitching stat lines per player)

---

## Key Data Flows

### 1. Authentication

1. User signs in via Supabase Auth (email/password or Google/Apple OAuth)
2. Supabase issues a JWT
3. Web client includes JWT in the Authorization header of every API request
4. Node.js API verifies the JWT with Supabase on each request

### 2. Lineup Auto-Save

1. Manager edits their lineup on the Matchup Screen
2. Client tracks all edits in local state and validates the lineup client-side
3. When the lineup is edited, if the resulting state is valid, the client sends a `PATCH /lineups/:id` request to the API
4. API validates the lineup server-side and checks that the relevant deadline has not passed
5. If valid and pre-deadline, API writes the lineup to PostgreSQL
6. API returns the saved lineup; client clears the unsaved changes indicator

### 3. Deadline Locking

1. Deadlines are computed from `sim_scheduled_at` using hardcoded offsets and included in the `GET /matchups/:id` response; they are not stored in the database
2. When the API receives a lineup write request, it computes the relevant deadline and rejects the request if the current time is past it
3. When the client receives a matchup response, it compares the current time to the returned deadline timestamps to determine lock state and enable/disable editing
4. Supabase Realtime notifies subscribed clients when the matchup record changes, prompting a re-fetch so the UI reflects current lock state without polling

### 4. Sim Dispatch and Execution

1. A node-cron job fires at the scheduled sim time
2. The data pipeline has already run, ingesting that week's stats for all rostered players
3. For each matchup scheduled for that time, the API sets the matchup status to `sim_pending` and makes a direct HTTP POST to the Python sim service
4. The Python sim service fetches both teams' locked lineups, full rosters, and weekly player stats from PostgreSQL
5. The sim service runs the simulation, runs the text-generation step, and writes the play-by-play event log and box score to PostgreSQL
6. The sim service returns a success response; the API sets the matchup status to `sim_complete`
7. Supabase Realtime notifies subscribed clients; the Matchup Screen transitions to post-sim mode

### 5. Results Display

1. Client requests `GET /matchups/:id/results`
2. API fetches the box score and play-by-play event log from PostgreSQL
3. API returns structured results to the client
4. Client renders the post-sim Matchup Screen (Box Score and Play-by-Play tabs)

---

## External Dependencies

### MLB Stats API

- **Source:** `statsapi.mlb.com` (free, official MLB API)
- **Used for:** Player master data (name, MLB ID, positions, handedness, team); weekly performance stats including PA, BF, pitch counts, and stat lines
- **Access pattern:** Python data pipeline scripts, triggered on a schedule tightly coupled to the sim run time
- **Fallback:** `pybaseball` library provides an alternative access path to Baseball Reference and FanGraphs data if needed

---

## Deployment

**Render** is recommended for MVP. It is a Platform as a Service (PaaS) that supports Node.js services and Python Docker containers natively, with deployment via GitHub push and minimal configuration overhead. This is significantly simpler than AWS for a small team and allows engineering effort to stay focused on the sim engine and product rather than deployment setup.

| Component | Render Service |
|---|---|
| Web client | Static site (built-in CDN) |
| API server | Web service (Node.js) |
| Sim engine | Web service (Python Docker container) |
| Database | Supabase (external managed PostgreSQL) |
| Data pipeline | Cron job service (Python Docker container) |

**Migration path:** If the product scales beyond Render's cost-effective range, migrating to AWS (ECS for containers, S3 + CloudFront for static hosting) is straightforward since all components are containerized. This migration is a post-MVP concern.

---

## What Is Not in This Architecture (MVP)

- Real-time sim watching (play-by-play is viewable after the fact only)
- Push notifications
- Mobile client
- In-game managerial decisions by the human manager
- AI-generated game recap (post-MVP)
