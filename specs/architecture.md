# Architecture Document: [Working Title] Fantasy Baseball Sim

## System Overview

The system has four primary layers:

1. **Web client** — React SPA (desktop web, MVP)
2. **API server** — Node.js + Express, handles all application logic and data access
3. **Sim engine** — Python service, executes game simulations
4. **Data stores** — PostgreSQL (via Supabase) and Redis

Communication between layers:
- The web client talks exclusively to the Node.js API server via REST
- The API server dispatches sim jobs asynchronously via a Redis-backed job queue (BullMQ)
- The Python sim engine consumes jobs from the queue, runs simulations, and writes results to PostgreSQL
- The API server reads results from PostgreSQL and serves them to the client
- Lineup lock state changes are pushed to the client via Supabase Realtime

---

## Tech Stack

| Component | Technology |
|---|---|
| Web client | React |
| API server | Node.js + Express |
| Auth | Supabase Auth (JWT, Google/Apple OAuth) |
| Database | PostgreSQL via Supabase |
| Realtime | Supabase Realtime (PostgreSQL-backed pub/sub) |
| Cache | Redis |
| Job queue | BullMQ (Redis-backed) |
| Sim engine | Python (FastAPI wrapper + simulation logic) |
| Stat modeling | NumPy, pandas, pybaseball |
| Data pipeline | Python scripts (scheduled) |

---

## Components

### Web Client (React)

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
- Deadline enforcement: deadline timestamps are stored in the database; the API treats a lineup as locked if the current time is past the deadline (lazy enforcement — no cron job required)
- Sim job dispatch: enqueues a sim job in BullMQ at the scheduled sim time via a cron job (node-cron)
- Writes a "sim pending" status to the matchup record when a job is enqueued
- Serves sim results from PostgreSQL once available

### Sim Engine (Python)

Responsibilities:
- Exposes a lightweight FastAPI service; not called directly by the web client
- Consumes sim jobs from the BullMQ queue via a Python worker
- For each job: fetches the locked lineups, full rosters (bench and bullpen players are needed for AI manager substitutions), and the relevant weekly stats from PostgreSQL, then runs the simulation and writes the play-by-play event log and box score back to PostgreSQL
- Simulation logic uses a probabilistic, stat-driven model (see Simulation Design below)
- AI manager logic (pitching changes, DH transitions, substitutions for unavailable players) is implemented here

### Job Queue (BullMQ + Redis)

Responsibilities:
- Decouples sim job dispatch (Node.js) from sim job execution (Python)
- Provides retry logic in case of sim worker failure
- Each job payload contains: matchup ID, sim scheduled time

### Database (PostgreSQL via Supabase)

Primary data store for all persistent data. Key entity groups:
- Users, leagues, teams, rosters
- Players (MLB master data + weekly performance stats)
- Matchups (schedule, home/road designation, sim status, lineup lock deadline timestamps)
- Lineups (SP selection, batting order, field positions)
- Sim results (play-by-play event log, box score)

Note: lineup lock state is never stored explicitly. It is always derived by comparing the current time to the relevant deadline timestamp on the matchup record.

### Data Pipeline (Python scripts)

Responsibilities:
- Ingests MLB player master data (name, MLB ID, eligible positions, handedness, team) from the MLB Stats API on a periodic basis
- Ingests weekly performance stats for all rostered players — see Simulation Design for the specific metrics required
- Critically, the pipeline run that feeds each sim must execute *after* the relevant real-life games have concluded but *before* the sim fires. Its schedule is therefore tightly coupled to the sim schedule, not a background weekly batch
- Writes directly to PostgreSQL

---

## Simulation Design

The sim engine uses a **probabilistic, stat-driven model** to resolve each plate appearance. This is the core IP of the product.

### Stat Window

The sim is a prediction game: managers select lineups based on how they expect their players to perform in the subsequent period. Accordingly, the sim uses each player's **real-life stats from the period between lineup lock and sim run** — not season-to-date stats — as the basis for simulation probabilities.

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

**Data pipeline requirement:** Weekly PA counts (for batters) and weekly BF and pitch counts (for pitchers) must be ingested alongside stat lines.

### Inputs per matchup
- Both teams' locked lineups (batting order, field positions, SP)
- Both teams' full rosters (for AI manager substitutions)
- Weekly stat lines and appearance counts for all players on both rosters
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

1. Deadlines are stored as timestamps on the matchup record
2. When the client or API receives a request involving a lineup, it compares the current time to the deadline timestamp
3. If the deadline has passed, the lineup is treated as locked — no further edits are accepted
4. Supabase Realtime publishes the lock event to subscribed clients, who update the UI immediately

### 4. Sim Dispatch and Execution

1. A node-cron job fires at the scheduled sim time
2. The data pipeline has already run, ingesting that week's stats for all rostered players
3. For each matchup scheduled for that time, the API verifies both lineups are locked and enqueues a sim job in BullMQ
4. The API sets the matchup status to `sim_pending`
5. The Python sim worker picks up the job from the queue
6. The worker fetches both teams' locked lineups, full rosters, and weekly player stats from PostgreSQL
7. The worker runs the simulation and writes the play-by-play event log and box score to PostgreSQL
8. The worker updates the matchup status to `sim_complete`
9. Supabase Realtime notifies subscribed clients; the Matchup Screen transitions to post-sim mode

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

## Infrastructure

All components run on AWS for MVP:

| Component | Service |
|---|---|
| Web client | S3 + CloudFront (static hosting) |
| API server | ECS (Docker container) |
| Sim engine | ECS (Docker container, separate service) |
| Database | Supabase (hosted PostgreSQL) |
| Redis | ElastiCache |
| Job queue | BullMQ on ElastiCache Redis |
| Data pipeline | ECS scheduled tasks (or Lambda for simplicity) |

---

## What Is Not in This Architecture (MVP)

- Real-time sim watching (play-by-play is viewable after the fact only)
- Push notifications
- Mobile client
- In-game managerial decisions by the human manager
- AI-generated game recap (post-MVP)
