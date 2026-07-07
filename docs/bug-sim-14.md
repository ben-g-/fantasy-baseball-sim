# bug-sim-14: AI-generated game recaps contain factual errors

**Severity:** Medium
**Component:** Sim engine (recap generation)
**Status:** Open

## Summary

After a real completed matchup was simulated, the AI-generated recap stored in `sim_recaps`
and shown on the Matchup Screen's Recap tab was reported as "not of usable quality due to
factual errors." No specific example was captured before the investigation was deferred, so
the exact nature of the error(s) — misattributed player/team, wrong score, invented event,
etc. — is unknown.

This follows shortly after four structural gaps in the recap prompt were identified and
fixed in `sim/src/recap.py`: the home team wasn't explicitly labeled, batting/pitching lines
weren't attributed to a team, play-by-play lacked half-inning labels, and play-by-play
omitted baserunner-advancement events (`sim_event_runner_outcomes`). Whether this report is a
further symptom of a related gap, a new formatting problem, an upstream data bug (wrong stats
or events actually persisted for this matchup), or the model hallucinating despite a
well-formed prompt, has not been determined.

## Location

- `sim/src/recap.py` — `build_prompt`, `build_play_by_play_text`
- `sim/src/llm_client.py` — `generate_text` (model: `claude-sonnet-5`)
- `sim/src/sim_service.py` — `_generate_and_write_recap`
- `scripts/generate_recap_variants.py` — standalone tool that reproduces the prompt (both the
  production "filtered" notable-performances variant and a "full box score" comparison
  variant) against a real completed matchup in Supabase, and prints the prompt and generated
  recap without writing to `sim_recaps` — the intended way to reproduce this without needing
  to re-run a live sim.

## Details

No concrete example (recap text, matchup ID, or the prompt that produced it) was captured in
the session where this was reported. Investigation was explicitly deferred by the user before
a repro could be gathered.

## Suggested fix

- Reproduce: run `scripts/generate_recap_variants.py --matchup-id <id> --variant filtered`
  against the same completed matchup that produced the bad recap (add `--variant full` for a
  side-by-side comparison), and capture the full printed prompt alongside the generated recap.
- Diff the recap's claims against the printed prompt's notable performances and play-by-play
  line by line, and classify each error as:
  - present in the prompt but misstated by the model (hallucination),
  - absent from the prompt (a remaining data/formatting gap in `build_prompt`), or
  - wrong even in the prompt (an upstream bug in what was persisted to `sim_events`,
    `sim_batter_stats`, `sim_pitcher_stats`, etc. for this matchup).
- Fix at whichever layer the classification points to. If it's (a), note the prompt already
  includes "Do not invent any statistics or events not present above" and this still occurred,
  so a stricter instruction alone may not be sufficient — consider what else about the prompt
  or model choice could be adjusted.

## Verification

Blocked on capturing a concrete example (recap text + matchup ID + the corresponding prompt)
before a fix can be attempted or verified.
