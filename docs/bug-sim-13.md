# bug-sim-13: Play-by-Play never narrates baserunner outcomes

**Severity:** Medium
**Component:** Sim engine, API server
**Status:** Fixed

## Fix

All four links in the chain were built:

- `supabase/schema.sql` — added a nullable `description TEXT` column to
  `sim_event_runner_outcomes`.
- `sim/src/text_gen.py` — added `describe_runner_outcome(outcome, runner_name,
  base_before, final_base, ends_half_inning)`, implementing the narration
  rule from `specs/data-model.md:329-338`. It returns a complete,
  ready-to-render sentence including the runner's own name (e.g. `"Carson
  Kelly advances to third base"`), the same way `describe_pa` already
  composes the batter's own line — deliberately not split into a bare clause
  plus a separately-rendered name, so the consumer never has to assemble the
  final string or assume where in it the name goes.
- `sim/src/engine.py` — `_build_runner_outcomes` now takes `player_info` (to
  resolve each runner's name) and an `ends_half_inning` flag, and attaches
  `description` (via `describe_runner_outcome`) to each pre-existing
  runner's row; the batter's own row (`base_before = 0`) always gets
  `description: None`, since the batter is narrated on
  `sim_events.description` instead. The call site in `_simulate_half_inning`
  computes `ends_half_inning = outs >= 3` immediately after
  `_apply_pa_outcome` (before the subsequent stolen-base attempt can further
  change `outs`), since the flag describes whether the plate appearance
  itself ended the half-inning.
- `api/src/routes/matchups.ts` — the `/matchups/:id/results` query now also
  fetches `sim_event_runner_outcomes` (filtered to non-null `description`,
  keyed by `sim_event_id`), and each `play_by_play` entry gets a
  `runner_notes` array of complete sentence strings, per
  `specs/api-spec.md:414-443`. No player identity is attached to a note.
- `web/src/lib/api.ts` / `web/src/views/MatchupView.vue` — `runner_notes` is
  typed as `string[]`, and the Play-by-Play tab renders each entry directly
  (no concatenation) as its own indented, italicized, muted-color line
  beneath the batter's line (`.pbp-runner-note`), per
  `specs/mini-prd-lineup-and-sim.md:140-148`.

Two design corrections were made after review, both in the direction of
consistency with how `play_by_play` already treats the batter:

- An earlier version had `describe_runner_outcome` return a name-less clause
  (e.g. `"advances to third base"`) with the frontend concatenating
  `player.full_name` and `description` itself. This forced the consumer to
  assemble the rendered string and baked a word-order assumption ("name,
  then clause") into the API contract, unlike the batter's
  `sim_events.description`, which is always a complete sentence. Fixed by
  making `describe_runner_outcome` return the full sentence, name included.
- A later version still attached a structured `player: {mlb_id, full_name}`
  to each note alongside the now-complete sentence — redundant once the name
  was in the text, and an asymmetry in the other direction: `play_by_play`
  exposes no structured identity for the batter or the pitcher either (both
  are only identifiable via prose), so singling out the runner for
  structured identity had no principled justification. Fixed by dropping
  `player` entirely; `runner_notes` is just an ordered array of strings.
- The order of that array was, until this point, an accident of
  implementation: `_build_runner_outcomes` happened to iterate
  `runners_before` in ascending base order (1st, 2nd, 3rd) because the dict
  it iterates is initialized `{1: 0, 2: 0, 3: 0}` and never re-created, and
  the API query had no `ORDER BY` at all, so the order the frontend received
  was whatever Postgres happened to return. Deciding the ideal narration
  order is the sim engine's domain — it's the only layer with the game-state
  knowledge to judge what's natural to narrate first — so a `narration_sequence`
  integer column was added to `sim_event_runner_outcomes`, assigned by
  `_build_runner_outcomes` (closest-to-home first: a runner on 3rd is
  sequenced before one on 2nd, before one on 1st), independent of
  `base_before` so a future ordering rule isn't tied to it. The API now
  orders explicitly by `narration_sequence` instead of relying on incidental
  row order — `sim_event_id` doesn't need to be part of the sort, since notes
  are bucketed into a per-event array by `sim_event_id` as a map key, not by
  slicing a flat ordered list, so only the relative order *within* an event's
  rows matters, and `narration_sequence` is unique within an event.

Covered by new/updated tests in `sim/tests/test_text_gen.py` (new file) and
`sim/tests/test_engine_characterization.py`
(`test_build_runner_outcomes_for_out_keeps_existing_runners_stationary`
updated;
`test_build_runner_outcomes_narrates_an_advance_and_a_score_on_a_single`,
`test_build_runner_outcomes_narrates_holds_on_non_inning_ending_groundout`,
`test_build_runner_outcomes_silent_on_inning_ending_groundout` added). The
API and web changes have no test harness in this repo (neither `api/` nor
`web/` has a test runner configured) — verified via `tsc --noEmit` /
`vue-tsc --noEmit` and `eslint` on both, and by reading the rendered
template against the mini-PRD's example lines rather than an automated test.

## Summary

The spec (updated in `8c89b77`, "clarify specs: play-by-play should include
baserunning outcomes") requires each plate-appearance entry in the
Play-by-Play feed to carry a `runner_notes` array — one narrated line per
pre-existing baserunner whose outcome is notable (they advanced, scored, were
put out, or held when an advance would typically be expected). None of the
three layers this feature spans have been built: the database has no column
to store the text, the text-generation component has no code path that
produces it, and the API endpoint that serves the Play-by-Play feed doesn't
even query the table the text would live on. Today's Play-by-Play output is
exactly what it was before the spec change — batter outcome only, e.g.
"Shohei Ohtani singles to center field" — with no indication of what any
other baserunner did on the play.

## Spec references

- `specs/data-model.md:324` — `sim_event_runner_outcomes.description`: a
  nullable text column meant to hold this narration, populated by the
  text-generation component.
- `specs/data-model.md:329-338` — "Baserunner narration rule": the exact
  condition for which runner rows get a `description` (base changed; or held
  on a hit / non-inning-ending groundout).
- `specs/api-spec.md:414-443` — `GET /matchups/:id/results` response shape:
  each `play_by_play` entry should include a `runner_notes` array of
  `{ player, description }` objects.
- `specs/mini-prd-lineup-and-sim.md:140-148` — Tab 2: Play-by-Play should
  render each runner note as its own indented, distinctly-styled line below
  the batter's outcome line.
- `specs/architecture.md:73` — the text-generation component's description
  lists baserunning examples ("Carson Kelly advances to third base", "Mookie
  Betts scores from second") among what it's expected to generate.

## Location

- `supabase/schema.sql:251-261` — `sim_event_runner_outcomes` has no
  `description` column; there's nowhere to store the text even if it were
  generated.
- `sim/src/text_gen.py` — only exports `describe_pa`, `describe_stolen_base`,
  and `describe_caught_stealing`. There is no function that narrates a single
  runner's advance/score/hold outcome.
- `sim/src/engine.py:717-779` (`_build_runner_outcomes`) — builds each
  `sim_event_runner_outcomes` row (`base_before`, `final_base`,
  `putout_at_base`, etc.) but never computes or attaches any narration text,
  and the dict it returns has no `description` key at all.
- `sim/src/db.py:184` — inserts the `runner_outcomes` dicts as-is; since
  `_build_runner_outcomes` never sets a `description`, nothing is ever
  written even though the surrounding insert code would happily persist one.
- `api/src/routes/matchups.ts:278` — the query backing `/matchups/:id/results`
  only selects from `sim_events` (`inning, half, sequence_number, event_type,
  description, runs_scored, outs_before_play`); it never joins or queries
  `sim_event_runner_outcomes`, so even a populated `description` column
  would be unreachable from this endpoint.
- `api/src/routes/matchups.ts:348-356` — the `play_by_play` response mapper
  only copies fields off of `e` (a `sim_events` row); there is no
  `runner_notes` key in the emitted objects.

## Details

Consequences of the gap, end to end:

- **No data is ever generated.** Even if the API were fixed, there's nothing
  to serve — `_build_runner_outcomes` doesn't compute narration text for any
  runner outcome, notable or not.
- **No storage exists.** Even if `text_gen.py` were extended to produce the
  text, `sim_event_runner_outcomes` has no column to hold it; the insert in
  `db.py:184` would need a schema migration first.
- **No API surface exists.** Even with the schema and sim-side generation in
  place, `/matchups/:id/results` doesn't select the table at all, so the
  response would still omit `runner_notes` until the query and mapper are
  updated.
- **Frontend has nothing to render.** `web/src/views/MatchupView.vue` (per
  the Play-by-Play tab) has no source data for the indented/styled runner
  lines the mini-PRD describes, since the API never sends them.

This isn't a case of one broken link in an otherwise-working chain — none of
the four links (schema, generation, API, and by extension the frontend) has
been started.

## Expected vs actual

| Play | Expected Play-by-Play entry | Actual |
|---|---|---|
| Single with a runner on 1st who takes third | "Shohei Ohtani singles to center field" + runner note "Carson Kelly advances to third base" | "Shohei Ohtani singles to center field" only |
| Double that scores a runner from 2nd | "Mookie Betts hits a double..." + runner note "Carson Kelly scores from second base" | "Mookie Betts hits a double..." only, no mention of the run's origin |
| Groundout, runner on 2nd, 1 out, runner doesn't advance | groundout line + runner note "Freddie Freeman holds at second base" | groundout line only |

## Suggested fix

- Add a `description` column to `sim_event_runner_outcomes` in
  `supabase/schema.sql` (nullable text, same shape as `sim_events.description`).
- Add a narration function to `sim/src/text_gen.py` (e.g.
  `describe_runner_outcome`) implementing the rule in
  `specs/data-model.md:329-338`: always narrate a base change (advance,
  score, or — once modelled per `bug-sim-8` — a putout), and narrate a
  non-change only on a hit or on a groundout that doesn't end the
  half-inning.
- Wire it into `_build_runner_outcomes` in `sim/src/engine.py` so each
  qualifying row carries a `description` before being handed to `db.py`.
- Update the `sim_events` query in `api/src/routes/matchups.ts:278` to also
  fetch `sim_event_runner_outcomes` (joined or queried alongside, keyed by
  `sim_event_id`) and extend the `play_by_play` mapper at
  `matchups.ts:348-356` to attach a `runner_notes` array (player + text) per
  event, per `specs/api-spec.md:414-443`.
- Update the Play-by-Play tab in the web client to render `runner_notes`
  entries as indented, visually distinct lines beneath the batter's line, per
  `specs/mini-prd-lineup-and-sim.md:140-148`.

## Verification

- After a single with a runner on base who takes an extra base, the
  `sim_event_runner_outcomes` row for that runner has a non-null
  `description`, and `GET /matchups/:id/results` returns it in that play's
  `runner_notes`.
- A strikeout with runners on base produces no `runner_notes` for those
  runners (per the "unforced runner on a K" exclusion).
- A groundout that ends the half-inning (the third out) produces no "holds"
  note for any runner left on base.
- The web client's Play-by-Play tab renders at least one visibly indented,
  distinctly-styled runner-note line in a game with extra-base advancement.
