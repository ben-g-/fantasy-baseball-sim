# Mini-PRD: Setting a Starting Lineup & Viewing Sim Results

**Product:** [Working Title] Fantasy Baseball Sim  
**Scenario:** A manager reviews and adjusts their default starting lineup across two deadlines, then views the simulated game result.  
**Purpose:** UX/flow validation and Lovable build reference.

---

## Product Context

A season-long fantasy baseball league where weekly head-to-head matchups are resolved by simulating an actual 9-inning game between the two fantasy rosters. Each manager selects their starting lineup; all in-game decisions are handled by an automated AI manager.

**Roster:** 22 players. The platform does not enforce a fixed breakdown of pitchers vs. batters. Roster composition is up to the manager.

**Starting lineup (10 slots):**
- 1 starting pitcher (SP)
- 9 batters, each assigned a batting order position (1–9) and a field position (C, 1B, 2B, SS, 3B, LF, CF, RF, or DH)

**Platform scope:** Desktop web only (MVP). Mobile is out of scope.

---

## Two-Way Players

A **two-way player** is a player whose eligible positions include both Pitcher and at least one non-Pitcher position (e.g. Shohei Ohtani: SP, DH). This is distinct from a regular pitcher, who has only Pitcher as an eligible position.

- Any player whose eligible positions include Pitcher can be selected as the SP
- The manager may insert the SP into the batting order in a **Pitcher (P)** batting slot, in lieu of using a DH. This applies to any SP — not only two-way players
- A two-way player who is **not** the SP may be inserted into the batting order at one of his non-Pitcher eligible positions
- A two-way player who **is** the SP may only occupy the P batting slot in the batting order, not a non-Pitcher position
- Use of a DH is therefore optional; the batting order can contain either a DH or the SP in the P slot, but not both
- If the SP is in the P batting slot and is replaced on the mound by a reliever, the AI manager may transition him to DH (only if he is a two-way player and therefore DH-eligible). Otherwise the incoming reliever takes over the P batting slot.

---

## Scenario Overview

Each weekly matchup has two lineup-locking phases, both occurring **the week before the sim runs**:

| Phase | What locks | Notes |
|---|---|---|
| Phase 1 | Starting pitcher | Road team deadline is earlier than home team deadline |
| Phase 2 | Batting order + field positions | Both teams share the same deadline |

The sim runs on a **fixed weekly schedule** (e.g. every Tuesday night). After it runs, all managers in the league can view the results.

**Sensible defaults are pre-populated for both phases:**
- SP default: the pitcher who most recently started among the currently eligible pitchers
- Batting order default: same order and field positions as the previous sim

The typical user flow involves *reviewing and adjusting* defaults rather than building a lineup from scratch.

---

## Key Rules

### Starting Pitcher Eligibility

Any player whose eligible positions include Pitcher may be selected as the SP, with one constraint: a player who started in either of the two preceding weeks' sims is ineligible to start this week. Ineligible pitchers are displayed but clearly marked as unavailable. Typically 2 pitchers will be ineligible, but this varies.

### Field Position Assignment

Each batter in the starting lineup must be assigned a field position. Valid positions for a given player are constrained to his real-life eligible positions (excluding Pitcher) plus DH. Invalid assignments are highlighted inline; hovering over a highlighted element shows a tooltip describing the specific conflict (e.g. "Two SS — no 3B").

### Lineup Validity

A lineup is valid when:
- Exactly 1 SP is selected
- Exactly 9 batters fill positions 1–9 in the batting order
- Each batter is assigned a field position he is eligible to play
- No two batters share the same field position
- Either a DH is used or the SP occupies the Pitcher batting slot (not both)

---

## Screens

### Screen 1: Matchup Screen

The central screen for this scenario. The manager reaches this by clicking their current matchup from the home screen. The screen has two modes: **pre-sim** (lineup editing) and **post-sim** (results display), determined by whether the sim has run.

**Common elements (both modes):**
- Header: week number, matchup dates, sim run date/time (e.g. "Week 11 · Sim runs Tue Jun 10, 9:00 PM")
- Both team names and manager names, each clearly labelled as Home or Road

---

#### Pre-Sim Mode

**Additional layout elements:**
- Next upcoming deadline with countdown (e.g. "SP locks in 2d 4h 12m")
- Unsaved changes indicator: visible when local edits differ from last saved valid state
- Two-column lineup panel:
  - Left column: manager's own lineup (editable)
  - Right column: opponent's lineup (read-only)
- Each column shows:
  - SP slot (top): player name, key stats, lock status
  - Batting order slots 1–9: batting order number, player name, field position
  - Bench: rostered players that are eligible to play a non-Pitcher position and are not in the starting lineup (excludes the SP, who is never shown on the bench)

**Lineup slot states:**

| State | Visual treatment |
|---|---|
| Default/selected (unlocked) | Player name + info; editable in own column; lock deadline shown |
| Locked | Player name + info; lock icon; not editable |
| Invalid | Highlighted; hover tooltip describes the specific conflict |

The opponent's column is always read-only, reflecting whatever state they are in.

**Editing interactions (own column only, pre-deadline):**
- Click SP slot → opens SP Selection panel
- Drag a player to reorder batting slots
- Drag a bench player into a batting slot → places him there; if his eligible positions don't include the slot's current field position, the slot retains the previous field position (now invalid), highlighted for the manager to resolve
- Drag a bench player onto the SP's Pitcher batting slot → bench player becomes DH, SP exits the batting order (SP is not shown on the bench)
- Click the SP's Pitcher batting slot → shows "P" as read-only; no action
- Click any other batting slot → opens an inline field position picker showing only that player's eligible non-Pitcher positions plus DH
- Click a "Use SP instead" control on the DH slot card → DH returns to bench, SP takes that batting position as "P"
- All edits are tracked locally and reflected immediately in the UI
- Invalid elements are highlighted inline; hovering over them shows a tooltip describing the conflict
- Auto-saves to backend only when the lineup is fully valid
- On navigation away with unsaved/invalid changes: silently reverts to last saved valid state

---

#### Post-Sim Mode

The Matchup Screen transforms after the sim runs to display results. The lineup editing panel is replaced by the sim results. The starting lineups are implicit in the box score and play-by-play.

**Layout — two tabs:**

**Tab 1: Box Score**
- Final score, prominent, with both team names
- Line score: a grid showing runs scored by each team in each inning, plus totals for R (runs), H (hits), and E (errors)
- Batting stats table: one row per batter showing AB, R, H, RBI, BB, K
- Pitching stats table: one row per pitcher showing IP, H, R, ER, BB, K

**Tab 2: Play-by-Play**
- Chronological text feed of every at-bat outcome, grouped by half-inning (e.g. "Top of the 3rd")
- Each entry shows batter name and outcome (e.g. "Shohei Ohtani homers to left — 2 runs score")
- Pitching changes in the format: "[Reliever] replaces [Pitcher] pitching"
- Other notable events (stolen bases, SP transitioning to DH) included as feed items

---

### Screen 2: SP Selection

Accessed by clicking the SP slot in the manager's own column (only before the SP deadline).

**Layout:**
- Modal or slide-up panel
- Lists all Pitcher-eligible players on the manager's roster
- Each player card shows: name, key stats (ERA, WHIP, K/9), handedness (L/R)
- Ineligible players (started in either of the two preceding weeks) are shown but greyed out with a label such as "Started Week 9 — unavailable"
- The currently selected (default) SP is highlighted
- Clicking an eligible player selects them and returns to the Matchup Screen

---

## User Flow (Step by Step)

### Phase 1: SP Selection

1. Manager opens app → clicks current matchup on home screen → lands on **Matchup Screen (pre-sim mode)**
2. Matchup Screen shows both lineups pre-populated with defaults; own SP slot shows the default SP (unlocked); countdown to SP deadline visible
3. Manager reviews the default SP and decides to change it
4. Manager clicks own SP slot → **SP Selection panel** opens
5. Manager sees all Pitcher-eligible players; ineligible ones are greyed out; the current default is highlighted
6. Manager clicks a different eligible player to select them
7. Returns to Matchup Screen — own SP slot now shows the newly selected pitcher (unlocked)
8. Manager can return and change their SP at any time before the deadline
9. **[Road team SP deadline passes]** — road team's SP slot locks
10. **[Home team SP deadline passes]** — home team's SP slot locks; both SP slots now show locked state

### Phase 2: Batting Order & Field Position Editing

11. Manager opens app → Matchup Screen shows both SP slots locked; batting order slots show defaults (unlocked); opponent's SP visible with lock status; countdown to batting order deadline visible
12. Manager reviews the default batting order and decides to make changes
13. Manager drags a batter lower in the order and promotes another player with better matchup splits; lineup remains valid; changes auto-save
14. Manager clicks a batting slot to adjust a field position; inline picker shows eligible positions for that player
15. Manager makes a position change that temporarily creates a conflict (two SS, no 3B); the conflicting slots are highlighted and the unsaved changes indicator appears
16. Manager hovers over a highlighted slot to read the tooltip ("Two SS — no 3B"), then resolves the conflict by changing the other SS's position to 3B
17. Lineup becomes valid; auto-saves; unsaved changes indicator clears
18. Manager can continue adjusting until the batting order deadline
19. **[Batting order deadline passes]** — both teams' batting orders lock; Matchup Screen enters a waiting state showing all slots locked and countdown to sim run time

### Phase 3: Viewing Results

20. Sim runs on schedule
21. Manager opens app → home screen matchup card shows the final score
22. Manager clicks matchup → **Matchup Screen (post-sim mode)**, Box Score tab
23. Manager reviews the line score and player stats, confirming the box score reflects the starting lineup they specified
24. Manager clicks Play-by-Play tab to read the game narrative
25. Manager can return to the home screen at any time

---

## Future Enhancements (Out of Scope for MVP)

- AI-generated narrative game recap (third tab on post-sim Matchup Screen)
- Push notifications
- Mobile support
- Live/real-time sim watching
- In-game managerial decisions by the human manager

## Out of Scope for This Scenario

- Viewing league standings
- Viewing other matchups, including ones not involving the manager's own team
- Draft screen (separate scenario)
- Waiver wire and trade flows
- Commissioner tools (schedule setup, league settings)
