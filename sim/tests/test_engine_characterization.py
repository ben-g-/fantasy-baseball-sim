"""
Characterization tests for sim/src/engine.py.

These tests lock in current, still-open, known-wrong behavior — they document
what the engine does today, not what it should do — so a future fix has a
clear "before" to diff against and so refactors don't accidentally change
behavior no one has decided to fix yet. Each test here is tagged with the
`# bug-sim-N` ticket it pins.

Tests that assert intended/correct behavior, including regression tests for
already-fixed bugs, belong in test_engine.py instead.
"""

import random

from engine import BatterSlot, _apply_pa_outcome, _apply_steal_attempt, _build_runner_outcomes
from outcomes import Outcome

from engine_test_support import _RUNNER_PLAYER_INFO, _cycle_fn, _make_team_state, _plate_appearance_outcomes, _run_with_per_side_outcomes


# bug-sim-9: pitcher side never gets `bb` credit for HBP; see docs/bug-sim-9.md.
def test_hbp_currently_counts_in_batter_bb_bucket(monkeypatch):
    # Road generates the bb/hbp occurrences under test; home is forced to a decisive
    # early HR so the game resolves in regulation instead of depending on extra-innings
    # behavior (see _run_with_per_side_outcomes).
    result = _run_with_per_side_outcomes(
        monkeypatch,
        home_fn=_cycle_fn([Outcome.HR, Outcome.K, Outcome.K, Outcome.K]),
        road_fn=_cycle_fn([Outcome.BB, Outcome.HBP, Outcome.K, Outcome.K, Outcome.K]),
    )

    pa_outcomes = [
        e['description']
        for e in result['events']
        if e['event_type'] == 'plate_appearance'
    ]

    expected_bb_bucket = sum(1 for o in pa_outcomes if o in ('bb', 'hbp'))
    observed_bb_bucket = sum(r['bb'] for r in result['batter_stats'])

    assert 'bb' in pa_outcomes, 'the forced outcome cycle includes bb, so at least one should appear in the play-by-play'
    assert 'hbp' in pa_outcomes, 'the forced outcome cycle includes hbp, so at least one should appear in the play-by-play'
    assert observed_bb_bucket == expected_bb_bucket, 'current (bug-sim-9) behavior: HBP is folded into the batter bb bucket alongside real walks'


# bug-sim-9
def test_apply_pa_outcome_hbp_updates_batter_bb_but_not_pitcher_bb():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.HBP,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 0, 2: 0, 3: 0},
        outs=2,
        inning_hits=0,
    )

    assert outs == 2, 'an HBP does not add an out'
    assert runs_on_play == 0, 'an HBP with the bases empty (besides the batter) cannot score a run'
    assert inning_hits == 0, 'an HBP is not a hit'
    assert runners == {1: 111, 2: 0, 3: 0}, 'the batter should be placed on 1st on an HBP'
    assert batting_team.batter_stats[111]['bb'] == 1, 'current (bug-sim-9) behavior: HBP is credited to the batter bb bucket'
    assert fielding_team.pitcher_stats[2]['bb'] == 0, 'current (bug-sim-9) behavior: the pitcher gets no bb credit for an HBP, unlike the batter'


# bug-sim-9
def test_outcome_branch_hbp_increments_batter_bb_only(monkeypatch):
    # Road generates the hbp occurrences under test; home is forced to a decisive early
    # HR so the game resolves in regulation (see _run_with_per_side_outcomes).
    result = _run_with_per_side_outcomes(
        monkeypatch,
        home_fn=_cycle_fn([Outcome.HR, Outcome.K, Outcome.K, Outcome.K]),
        road_fn=_cycle_fn([Outcome.HBP, Outcome.K, Outcome.K, Outcome.K]),
    )
    pa_outcomes = _plate_appearance_outcomes(result)

    hbp_count = pa_outcomes.count('hbp')
    assert hbp_count > 0, 'the forced outcome cycle includes hbp, so at least one should appear in the play-by-play'
    assert sum(r['bb'] for r in result['batter_stats']) == hbp_count, 'current (bug-sim-9) behavior: each HBP adds one to the batter bb bucket'
    assert sum(r['bb'] for r in result['pitcher_stats']) == 0, 'current (bug-sim-9) behavior: HBP events never add to the pitcher bb bucket'
    assert sum(r['ab'] for r in result['batter_stats']) + hbp_count == len(pa_outcomes), 'every PA is either an AB or an HBP, so AB + hbp should equal total PAs'


# bug-sim-15: only 1st-base steal attempts are modeled — a runner on 2nd (like the one
# set up below) is never considered, even though he's on base. See docs/bug-sim-15.md.
def test_apply_steal_attempt_noop_without_runner_on_first():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 0, 2: 5, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=0, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == runners, 'with nobody on 1st there is no runner to attempt a steal, so runners should be unchanged'
    assert outs == 0, 'no steal attempt means no additional out'
    assert seq == 4, 'no steal attempt means no event, so the sequence counter should not advance'
    assert events == [], 'no runner on 1st should mean no steal-related event is emitted'


# bug-sim-15: steal attempts are hard-disabled at 2 outs rather than merely lower-probability;
# see docs/bug-sim-15.md.
def test_apply_steal_attempt_noop_with_two_outs():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 77, 2: 0, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=2, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == runners, 'steal attempts are only modeled with fewer than 2 outs, so runners should be unchanged with 2 outs'
    assert outs == 2, 'no steal attempt means no additional out'
    assert seq == 4, 'no steal attempt means no event, so the sequence counter should not advance'
    assert events == [], 'with 2 outs already, no steal-related event should be emitted'


# bug-sim-8: no double/force play or putout-type modeling on outs; see docs/bug-sim-8.md.
def test_build_runner_outcomes_for_out_keeps_existing_runners_stationary():
    rows = _build_runner_outcomes(
        event_id='evt-1',
        batter_id=50,
        outcome=Outcome.K,
        runners_before={1: 11, 2: 22, 3: 0},
        runners_after={1: 11, 2: 22, 3: 0},
        player_info=_RUNNER_PLAYER_INFO,
        ends_half_inning=False,
    )

    batter_row = next(r for r in rows if r['base_before'] == 0)
    assert batter_row['player_id'] == 50, 'the batter row should identify the batter who made the out'
    assert batter_row['final_base'] is None, 'a batter who is out never reaches a base'
    assert batter_row['putout_at_base'] == 1, 'an out is currently always recorded as a putout at first base'
    assert batter_row['description'] is None, "the batter's own outcome is narrated on sim_events.description, not here"

    runner_on_first = next(r for r in rows if r['base_before'] == 1)
    runner_on_second = next(r for r in rows if r['base_before'] == 2)
    assert runner_on_first['final_base'] == 1, 'no double/force play is modeled on outs, so the runner on 1st should stay on 1st'
    assert runner_on_second['final_base'] == 2, 'no double/force play is modeled on outs, so the runner on 2nd should stay on 2nd'
    assert runner_on_first['description'] is None, 'a strikeout never advances a runner, so staying put should not be narrated'
    assert runner_on_second['description'] is None, 'a strikeout never advances a runner, so staying put should not be narrated'
    assert runner_on_first['narration_sequence'] is None, 'a row with no description has nothing to sequence, so it should carry no narration_sequence'
    assert runner_on_second['narration_sequence'] is None, 'a row with no description has nothing to sequence, so it should carry no narration_sequence'
