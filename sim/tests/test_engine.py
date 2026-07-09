"""
Correctness tests for sim/src/engine.py.

These assert intended/expected behavior, including regression tests for fixed
bugs (tagged `# bug-sim-N` where applicable). Tests that instead pin down
current, still-open, known-wrong behavior belong in
test_engine_characterization.py.
"""

import random

import engine
from engine import (
    BatterSlot,
    PitcherSlot,
    TeamState,
    _apply_pa_outcome,
    _apply_pinch_hit_substitution,
    _apply_pitcher_change,
    _apply_steal_attempt,
    _build_runner_outcomes,
    _find_slot,
    _make_event,
    simulate_game,
)
from outcomes import Outcome

from engine_test_support import (
    _RUNNER_PLAYER_INFO,
    _base_sim_inputs,
    _cycle_fn,
    _make_team_state,
    _plate_appearance_outcomes,
    _run_with_per_side_outcomes,
)


def test_simulate_game_all_strikeouts_are_consistent(monkeypatch):
    # A game of nothing but strikeouts can never produce a winner in 9 innings, so one
    # exception is unavoidable: home's very first plate appearance (leadoff, bottom of
    # the 1st) is forced to a solo home run, deciding the game outright. Every other PA,
    # for both sides, is a strikeout.
    result = _run_with_per_side_outcomes(
        monkeypatch,
        home_fn=lambda n: Outcome.HR if n == 0 else Outcome.K,
        road_fn=lambda n: Outcome.K,
    )

    pa_events = [e for e in result['events'] if e['event_type'] == 'plate_appearance']
    pa_count = len(pa_events)
    k_events = [e for e in pa_events if e['description'] == Outcome.K]
    assert pa_count > 0, 'a full game forcing strikeouts should still play at least one PA'
    assert len(k_events) == pa_count - 1, 'every PA except the one deciding home run should be a strikeout'

    total_batter_ab = sum(r['ab'] for r in result['batter_stats'])
    total_batter_k = sum(r['k'] for r in result['batter_stats'])
    total_pitcher_outs = sum(r['outs_recorded'] for r in result['pitcher_stats'])

    assert total_batter_ab == pa_count, 'every PA (strikeout or the deciding HR) is an AB, so total batter AB should equal the number of PAs'
    assert total_batter_k == pa_count - 1, 'every PA but the deciding HR was a strikeout, so total batter K should be one less than the number of PAs'
    assert total_pitcher_outs == pa_count - 1, 'every strikeout is one out and the HR is not, so total pitcher outs_recorded should be one less than the number of PAs'
    assert result['final_score'] == {'home': 1, 'road': 0}, 'home should win 1-0 on the sole deciding home run, with every other PA a scoreless strikeout'
    assert sum(r['runs'] for r in result['line_score']) == 1, 'the only run in the game should be the deciding home run'
    assert sum(r['hits'] for r in result['line_score']) == 1, 'the only hit in the game should be the deciding home run'


def test_caught_stealing_outs_are_credited_to_pitcher_outs_recorded(monkeypatch):
    # Every PA follows a repeating walk/strikeout/strikeout pattern (a leadoff walk
    # always draws a forced-failed steal attempt, i.e. a caught stealing), except the
    # 4th PA (home's leadoff batter in the bottom of the 1st), which is a solo home run.
    # Home leads 1-0 from then on, so — same as the walk-off/skip-9th scenario — the game
    # ends after the top of the 9th without ever reaching extra innings. That keeps this
    # test's outcome independent of whatever extra-innings/tie-breaking rule the engine
    # uses (see bug-sim-7), since it never gets there.
    pa_index = {'n': 0}

    def fake_simulate_pa(*_args, **_kwargs):
        if pa_index['n'] == 3:
            outcome = Outcome.HR
        else:
            outcome = [Outcome.BB, Outcome.K, Outcome.K][pa_index['n'] % 3]
        pa_index['n'] += 1
        return outcome

    monkeypatch.setattr(engine, '_simulate_pa', fake_simulate_pa)
    monkeypatch.setattr(engine, 'describe_pa', lambda outcome, *_args, **_kwargs: outcome)
    monkeypatch.setattr(engine, '_try_steal', lambda *_args, **_kwargs: False)

    result = simulate_game(**_base_sim_inputs())

    assert result['final_score'] == {'home': 1, 'road': 0}, (
        'home should lead 1-0 wire-to-wire off the forced 1st-inning HR, with every other '
        'PA a strikeout or a caught-stealing (never a run), so the game ends after the top '
        'of the 9th without ever reaching extra innings'
    )

    caught_stealing_events = [e for e in result['events'] if e['event_type'] == 'caught_stealing']
    strikeout_events = [
        e for e in result['events']
        if e['event_type'] == 'plate_appearance' and e['description'] == Outcome.K
    ]
    assert len(caught_stealing_events) > 0, 'the forced BB/K/K pattern should produce at least one caught-stealing out'

    total_pitcher_outs = sum(r['outs_recorded'] for r in result['pitcher_stats'])
    expected_outs = len(strikeout_events) + len(caught_stealing_events)
    assert total_pitcher_outs == expected_outs, (
        'every strikeout and every caught-stealing is a defensive out, so total pitcher outs_recorded '
        'must count both — a pitcher who is part of a caught-stealing play should not have their IP undercounted'
    )


# bug-sim-6: the PA event is appended after any caught-stealing/stolen-base event
# from the same iteration and re-reads the mutated `seq`/`outs` counters, so a PA that
# puts a runner on base can end up with a sequence_number that collides with (or comes
# after) the very steal attempt it created, and an outs_before_play that wrongly
# absorbs the later caught-stealing out.
def test_pa_event_sequencing_is_not_corrupted_by_its_own_caught_stealing(monkeypatch):
    # PA 0 (road's leadoff batter, top of the 1st) is a single, and every steal
    # attempt is forced to fail, so the very next thing that happens is a caught
    # stealing off the runner that single just put on 1st. PA 3 (home's leadoff,
    # bottom of the 1st) is a forced solo home run so the game resolves 1-0 after the
    # top of the 9th, independent of extra-innings/tie-breaking behavior (see
    # bug-sim-7). Every other PA is a strikeout.
    pa_index = {'n': 0}

    def fake_simulate_pa(*_args, **_kwargs):
        if pa_index['n'] == 0:
            outcome = Outcome.SINGLE
        elif pa_index['n'] == 3:
            outcome = Outcome.HR
        else:
            outcome = Outcome.K
        pa_index['n'] += 1
        return outcome

    monkeypatch.setattr(engine, '_simulate_pa', fake_simulate_pa)
    monkeypatch.setattr(engine, 'describe_pa', lambda outcome, *_args, **_kwargs: outcome)
    monkeypatch.setattr(engine, '_try_steal', lambda *_args, **_kwargs: False)

    result = simulate_game(**_base_sim_inputs())

    assert result['final_score'] == {'home': 1, 'road': 0}, (
        'home should lead 1-0 wire-to-wire off the forced 1st-inning HR, with every '
        'other PA a strikeout or a caught-stealing (never a run), so the game ends '
        'after the top of the 9th without ever reaching extra innings'
    )

    single_event = next(e for e in result['events'] if e['event_type'] == 'plate_appearance' and e['description'] == Outcome.SINGLE)
    cs_event = next(e for e in result['events'] if e['event_type'] == 'caught_stealing')

    assert single_event['sequence_number'] < cs_event['sequence_number'], (
        'the single created the runner that then got caught stealing, so the single\'s '
        'plate_appearance event must sort strictly before the caught_stealing event, '
        'not collide with or come after it'
    )
    assert single_event['outs_before_play'] == 0, (
        'no outs had occurred before the leadoff single itself, so its outs_before_play '
        'must be 0 — it should not absorb the caught-stealing out that happened after it'
    )


# The Matchup Screen's box score renders "x" for a half-inning a team didn't bat (e.g.
# home already leading entering the bottom of the 9th). That depends on this: such a
# half-inning should produce no plate appearances and no line-score row at all.
def test_home_already_leading_entering_9th_does_not_bat_or_get_a_line_score_row(monkeypatch):
    pa_index = {'n': 0}

    def fake_simulate_pa(*_args, **_kwargs):
        # Every PA is a strikeout except the 4th (home's leadoff batter in the bottom
        # of the 1st), which is a solo home run — home leads 1-0 from then on.
        outcome = Outcome.HR if pa_index['n'] == 3 else Outcome.K
        pa_index['n'] += 1
        return outcome

    monkeypatch.setattr(engine, '_simulate_pa', fake_simulate_pa)
    monkeypatch.setattr(engine, 'describe_pa', lambda outcome, *_args, **_kwargs: outcome)
    monkeypatch.setattr(engine, '_try_steal', lambda *_args, **_kwargs: None)

    result = simulate_game(**_base_sim_inputs())

    assert result['final_score'] == {'home': 1, 'road': 0}, (
        'home scores its only run on the forced 1st-inning HR and the road team is '
        'strikeout-only for the rest of the game'
    )

    bottom_9th_home_pas = [
        e for e in result['events']
        if e['event_type'] == 'plate_appearance' and e['inning'] == 9 and e['half'] == 'bottom'
    ]
    assert bottom_9th_home_pas == [], (
        'home already led entering the bottom of the 9th, so the game should end after '
        'the top half without home ever batting'
    )

    home_9th_line = [r for r in result['line_score'] if r['team_id'] == 'home-team' and r['inning'] == 9]
    assert home_9th_line == [], (
        'a half-inning the team never batted in should have no line-score row at all, so '
        'the box score can distinguish "did not bat" (x) from "batted and scored zero" (0)'
    )

    road_9th_line = [r for r in result['line_score'] if r['team_id'] == 'road-team' and r['inning'] == 9]
    assert len(road_9th_line) == 1, 'the road team did play the top of the 9th, so it should still get a line-score row for it'


def test_apply_pa_outcome_strikeout_updates_outs_and_k_buckets():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.K,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 0, 2: 0, 3: 0},
        outs=0,
        inning_hits=0,
    )

    assert outs == 1, 'a strikeout should add exactly one out'
    assert runs_on_play == 0, 'a strikeout cannot score a run'
    assert inning_hits == 0, 'a strikeout is not a hit'
    assert runners == {1: 0, 2: 0, 3: 0}, 'a strikeout with the bases empty should leave the bases empty'
    assert batting_team.batter_stats[111]['ab'] == 1, 'a strikeout counts as an at-bat'
    assert batting_team.batter_stats[111]['k'] == 1, 'a strikeout should increment the batter k bucket'
    assert fielding_team.pitcher_stats[2]['outs_recorded'] == 1, 'the pitcher should be credited with the out'
    assert fielding_team.pitcher_stats[2]['k'] == 1, 'the pitcher should be credited with the strikeout'


def test_apply_pa_outcome_walk_forces_runner_and_increments_bb_buckets():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.BB,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 0, 3: 0},
        outs=1,
        inning_hits=0,
    )

    assert outs == 1, 'a walk does not add an out'
    assert runs_on_play == 0, 'forcing a runner from 1st to 2nd with 2nd/3rd empty cannot score a run'
    assert inning_hits == 0, 'a walk is not a hit'
    assert runners == {1: 111, 2: 77, 3: 0}, 'the batter should take 1st and the existing runner should be forced to 2nd'
    assert batting_team.batter_stats[111]['bb'] == 1, 'a walk should increment the batter bb bucket'
    assert fielding_team.pitcher_stats[2]['bb'] == 1, 'a walk should increment the pitcher bb bucket'


def test_apply_pa_outcome_double_updates_hits_and_run_accounting():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batting_team.batting_order[0].player_id = 77  # register the runner so a run credit can resolve to it
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.DOUBLE,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 0, 3: 0},
        outs=1,
        inning_hits=0,
    )

    assert outs == 1, 'a double does not add an out'
    assert runs_on_play == 1, 'the runner on 1st should score on a double'
    assert inning_hits == 1, 'a double should count as one inning hit'
    assert runners == {1: 0, 2: 111, 3: 0}, 'the batter should end up on 2nd with 1st now empty'
    assert batting_team.batter_stats[111]['ab'] == 1, 'a double counts as an at-bat'
    assert batting_team.batter_stats[111]['h'] == 1, 'a double should increment the batter hit bucket'
    assert batting_team.batter_stats[111]['doubles'] == 1, 'a double should increment the batter doubles bucket'
    assert batting_team.batter_stats[111]['rbi'] == 1, 'the batter should be credited an RBI for the run scored'
    assert fielding_team.pitcher_stats[2]['h'] == 1, 'the pitcher should be charged a hit allowed'
    assert fielding_team.pitcher_stats[2]['r'] == 1, 'the pitcher should be charged the run scored'
    assert fielding_team.pitcher_stats[2]['er'] == 1, 'the run scored on a double should be earned'
    # bug-sim-11: the runner who scored (not the batter, who ends up on 2nd) should get the run credit
    assert batting_team.batter_stats[77]['r'] == 1, 'the runner who scored from 1st should be credited with a run'
    assert batting_team.batter_stats[111]['r'] == 0, 'the batter ends up on 2nd (not home) on a double, so should not be credited a run himself'


# bug-sim-11: no code path ever increments a batter's `r` bucket, so the box
# score Batting section's R column is always zero regardless of runs scored.
def test_apply_pa_outcome_home_run_credits_batter_and_all_runners_with_runs():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batting_team.batting_order.append(BatterSlot(2, 77, 'OF', 'R', None))
    batting_team.batting_order.append(BatterSlot(3, 88, 'OF', 'R', None))
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.HR,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 88, 3: 0},
        outs=0,
        inning_hits=0,
    )

    assert runs_on_play == 3, 'a home run with runners on 1st and 2nd should score all three (both runners plus the batter)'
    assert batting_team.batter_stats[111]['r'] == 1, 'the batter should be credited his own run scored on a home run'
    assert batting_team.batter_stats[111]['rbi'] == 3, 'the batter should be credited 3 RBI for the two runners plus himself'
    assert batting_team.batter_stats[77]['r'] == 1, 'the runner who was on 1st should be credited with a run scored on the home run'
    assert batting_team.batter_stats[88]['r'] == 1, 'the runner who was on 2nd should be credited with a run scored on the home run'


# bug-sim-11
def test_apply_pa_outcome_bases_loaded_walk_credits_forced_run_to_runner_on_third():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batting_team.batting_order.append(BatterSlot(2, 77, 'OF', 'R', None))
    batting_team.batting_order.append(BatterSlot(3, 88, 'OF', 'R', None))
    batting_team.batting_order.append(BatterSlot(4, 99, 'OF', 'R', None))
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.BB,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 88, 3: 99},
        outs=0,
        inning_hits=0,
    )

    assert runs_on_play == 1, 'a bases-loaded walk forces in exactly one run'
    assert batting_team.batter_stats[99]['r'] == 1, 'the runner forced home from 3rd should be credited with a run'


# bug-sim-12
def test_apply_pa_outcome_bases_loaded_walk_advances_runners_and_places_batter_on_first():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batting_team.batting_order.append(BatterSlot(2, 77, 'OF', 'R', None))
    batting_team.batting_order.append(BatterSlot(3, 88, 'OF', 'R', None))
    batting_team.batting_order.append(BatterSlot(4, 99, 'OF', 'R', None))
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.BB,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 88, 3: 99},
        outs=0,
        inning_hits=0,
    )

    assert runners == {1: 111, 2: 77, 3: 88}, (
        'a bases-loaded walk forces every runner up one base and the batter onto 1st: '
        'the runner on 3rd scores and leaves the bases, the runner on 2nd moves to 3rd, '
        'the runner on 1st moves to 2nd, and the batter who drew the walk takes 1st'
    )


# bug-sim-12
def test_apply_pa_outcome_bases_loaded_hbp_advances_runners_and_places_batter_on_first():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batting_team.batting_order.append(BatterSlot(2, 77, 'OF', 'R', None))
    batting_team.batting_order.append(BatterSlot(3, 88, 'OF', 'R', None))
    batting_team.batting_order.append(BatterSlot(4, 99, 'OF', 'R', None))
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome=Outcome.HBP,
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 88, 3: 99},
        outs=1,
        inning_hits=0,
    )

    assert runners == {1: 111, 2: 77, 3: 88}, (
        'a bases-loaded HBP forces every runner up one base and the batter onto 1st, '
        'the same as a bases-loaded walk'
    )


# bug-sim-11
def test_simulate_game_batter_runs_sum_to_team_score(monkeypatch):
    # Home gets the HR-heavy cycle under test; road is strikeout-only so the game
    # always resolves home-ahead in regulation (see _run_with_per_side_outcomes).
    result = _run_with_per_side_outcomes(
        monkeypatch,
        home_fn=_cycle_fn([Outcome.HR, Outcome.K, Outcome.K, Outcome.K]),
        road_fn=lambda n: Outcome.K,
    )

    home_batter_runs = sum(r['r'] for r in result['batter_stats'] if r['team_id'] == 'home-team')
    road_batter_runs = sum(r['r'] for r in result['batter_stats'] if r['team_id'] == 'road-team')

    assert result['final_score']['home'] > 0, 'the forced HR-heavy outcome cycle should produce a nonzero home score, or this invariant check would be vacuous'
    assert home_batter_runs == result['final_score']['home'], 'summed batter r for the home team should equal the home team final score'
    assert road_batter_runs == result['final_score']['road'], 'summed batter r for the road team should equal the road team final score'


def test_outcome_branch_bb_increments_batter_and_pitcher_bb(monkeypatch):
    # Road generates the bb occurrences under test; home is forced to a decisive early
    # HR so the game resolves in regulation (see _run_with_per_side_outcomes).
    result = _run_with_per_side_outcomes(
        monkeypatch,
        home_fn=_cycle_fn([Outcome.HR, Outcome.K, Outcome.K, Outcome.K]),
        road_fn=_cycle_fn([Outcome.BB, Outcome.K, Outcome.K, Outcome.K]),
    )
    pa_outcomes = _plate_appearance_outcomes(result)

    bb_count = pa_outcomes.count('bb')
    assert bb_count > 0, 'the forced outcome cycle includes bb, so at least one should appear in the play-by-play'
    assert sum(r['bb'] for r in result['batter_stats']) == bb_count, 'total batter bb across a full game should equal the number of walk events'
    assert sum(r['bb'] for r in result['pitcher_stats']) == bb_count, 'total pitcher bb across a full game should equal the number of walk events'
    assert sum(r['ab'] for r in result['batter_stats']) + bb_count == len(pa_outcomes), 'every PA is either an AB or a walk, so AB + bb should equal total PAs'


def test_outcome_branch_double_increments_hit_buckets(monkeypatch):
    # Road generates the double occurrences under test; home is forced to a decisive
    # early HR so the game resolves in regulation (see _run_with_per_side_outcomes).
    result = _run_with_per_side_outcomes(
        monkeypatch,
        home_fn=_cycle_fn([Outcome.HR, Outcome.K, Outcome.K, Outcome.K]),
        road_fn=_cycle_fn([Outcome.DOUBLE, Outcome.K, Outcome.K, Outcome.K]),
    )
    pa_outcomes = _plate_appearance_outcomes(result)

    double_count = pa_outcomes.count('double')
    assert double_count > 0, 'the forced outcome cycle includes double, so at least one should appear in the play-by-play'

    # Scoped to the road team specifically, since home's forced HRs also add to the
    # combined `h` bucket (a home run is a hit too) and would make an unscoped total
    # overcount relative to double_count.
    road_batter_stats = [r for r in result['batter_stats'] if r['team_id'] == 'road-team']
    home_pitcher_stats = [r for r in result['pitcher_stats'] if r['team_id'] == 'home-team']
    assert sum(r['h'] for r in road_batter_stats) == double_count, 'total road batter hits should equal the number of doubles'
    assert sum(r['doubles'] for r in road_batter_stats) == double_count, 'total road batter doubles should equal the number of double events'
    assert sum(r['h'] for r in home_pitcher_stats) == double_count, "total hits allowed by home's pitcher(s) should equal the number of doubles road hit off them"
    assert sum(r['ab'] for r in result['batter_stats']) == len(pa_outcomes), 'every PA in this cycle (double, HR, or strikeout) is an AB, so total AB should equal total PAs'


def test_make_event_builds_expected_shape():
    event = _make_event(
        'matchup-1', 3, 'top', 7, 'plate_appearance', 'X singles',
        pitcher_player_id=42, runs_scored=1, outs_before_play=1,
    )

    assert event['matchup_id'] == 'matchup-1', 'matchup_id should be passed through unchanged'
    assert event['inning'] == 3, 'inning should be passed through unchanged'
    assert event['half'] == 'top', 'half should be passed through unchanged'
    assert event['sequence_number'] == 7, 'sequence_number should be set from the seq argument'
    assert event['event_type'] == 'plate_appearance', 'event_type should be passed through unchanged'
    assert event['description'] == 'X singles', 'description should be passed through unchanged'
    assert event['pitcher_player_id'] == 42, 'pitcher_player_id should be set from the keyword argument'
    assert event['runs_scored'] == 1, 'runs_scored should be set from the keyword argument'
    assert event['outs_before_play'] == 1, 'outs_before_play should be set from the keyword argument'
    assert isinstance(event['id'], str) and event['id'], 'a fresh uuid string id should be generated when none is supplied'


def test_make_event_defaults_pitcher_and_runs_and_generates_id():
    event = _make_event('matchup-1', 1, 'bottom', 1, 'pitching_change', None, outs_before_play=0)

    assert event['pitcher_player_id'] is None, 'pitcher_player_id should default to None when omitted'
    assert event['runs_scored'] == 0, 'runs_scored should default to 0 when omitted'
    assert event['id'], 'an id should still be generated even when event_id is omitted'


def test_make_event_uses_provided_event_id():
    event = _make_event(
        'matchup-1', 3, 'top', 7, 'plate_appearance', None,
        outs_before_play=0, event_id='fixed-id',
    )

    assert event['id'] == 'fixed-id', 'an explicitly supplied event_id should be used instead of generating a new uuid (needed so the PA event and its runner-outcome rows share one id)'


def test_apply_pinch_hit_substitution_swaps_in_highest_pa_bench_bat():
    bench_low = BatterSlot(0, 501, '', 'R', {'pa': 10}, dh_eligible=True)
    bench_high = BatterSlot(0, 502, '', 'R', {'pa': 50}, dh_eligible=True)
    batter_slot = BatterSlot(1, 111, '1B', 'R', {'pa': 3}, pa_used=1)
    other_slots = [BatterSlot(i + 2, 200 + i, 'OF', 'R', None) for i in range(8)]
    team = TeamState(
        team_id='bat',
        batting_order=[batter_slot, *other_slots],
        bullpen=[],
        current_pitcher=PitcherSlot(1, 'R', None),
        bench=[bench_low, bench_high],
    )
    team.current_batting_spot = 1  # next_batter() already advanced past batter_slot's index 0

    result_slot, seq, events = _apply_pinch_hit_substitution(
        team, batter_slot, {}, 'matchup-1', 3, 'top', outs=1, seq=5,
    )

    assert result_slot is bench_high, 'the bench player with the most pre-lock PA should be chosen as the pinch hitter'
    assert seq == 6, 'emitting a substitution event should advance the sequence counter by one'
    assert bench_high not in team.bench, 'the pinch hitter should be removed from the bench once subbed in'
    assert team.batting_order[0] is bench_high, "the pinch hitter should take over the original batter's lineup slot"
    assert bench_high.batting_position == 1, 'the pinch hitter should inherit the batting position of the batter they replaced'
    assert bench_high.field_position == '1B', 'the pinch hitter should inherit the field position of the batter they replaced'
    assert len(events) == 1, 'exactly one substitution event should be emitted'
    assert events[0]['event_type'] == 'substitution', 'the emitted event should be a substitution event'
    assert events[0]['sequence_number'] == 6, 'the substitution event should carry the newly advanced sequence number'
    assert events[0]['outs_before_play'] == 1, 'the substitution event should record the outs at the time of the substitution'


def test_apply_pinch_hit_substitution_noop_below_cap():
    bench = BatterSlot(0, 501, '', 'R', {'pa': 50}, dh_eligible=True)
    batter_slot = BatterSlot(1, 111, '1B', 'R', {'pa': 3}, pa_used=0)
    team = TeamState(
        team_id='bat',
        batting_order=[batter_slot],
        bullpen=[],
        current_pitcher=PitcherSlot(1, 'R', None),
        bench=[bench],
    )

    result_slot, seq, events = _apply_pinch_hit_substitution(
        team, batter_slot, {}, 'matchup-1', 3, 'top', outs=0, seq=5,
    )

    assert result_slot is batter_slot, 'a batter below their PA cap should not be substituted'
    assert seq == 5, 'no event means the sequence counter should not advance'
    assert events == [], 'no substitution should mean no event is emitted'
    assert team.bench == [bench], 'the bench should be untouched when no substitution occurs'


def test_apply_pinch_hit_substitution_noop_with_no_bench():
    batter_slot = BatterSlot(1, 111, '1B', 'R', {'pa': 3}, pa_used=1)
    team = TeamState(
        team_id='bat',
        batting_order=[batter_slot],
        bullpen=[],
        current_pitcher=PitcherSlot(1, 'R', None),
        bench=[],
    )

    result_slot, seq, events = _apply_pinch_hit_substitution(
        team, batter_slot, {}, 'matchup-1', 3, 'top', outs=1, seq=5,
    )

    assert result_slot is batter_slot, 'a batter at their PA cap with no bench available has no one to sub in, so they should keep batting'
    assert seq == 5, 'no event means the sequence counter should not advance'
    assert events == [], 'no substitution should mean no event is emitted'


def test_apply_pinch_hit_substitution_exempts_pure_pitcher_at_cap():
    bench = BatterSlot(0, 501, '', 'R', {'pa': 50}, dh_eligible=True)
    batter_slot = BatterSlot(1, 111, 'P', 'R', {'pa': 3}, dh_eligible=False, pa_used=1)
    team = TeamState(
        team_id='bat',
        batting_order=[batter_slot],
        bullpen=[],
        current_pitcher=PitcherSlot(1, 'R', None),
        bench=[bench],
    )

    result_slot, seq, events = _apply_pinch_hit_substitution(
        team, batter_slot, {}, 'matchup-1', 3, 'top', outs=1, seq=5,
    )

    assert result_slot is batter_slot, 'pure pitchers are exempt from the PA cap and should never be pinch-hit for'
    assert seq == 5, 'no event means the sequence counter should not advance'
    assert events == [], 'no substitution should mean no event is emitted'
    assert team.bench == [bench], 'the bench should be untouched when a pure pitcher is exempted from substitution'


def test_apply_pitcher_change_noop_when_caps_not_reached():
    current = PitcherSlot(1, 'R', {'bf': 100, 'pitches_thrown': 100}, bf_used=10, pitches_used=10)
    reliever = PitcherSlot(2, 'R', None)
    team = TeamState(
        team_id='fld',
        batting_order=[BatterSlot(9, 1, 'P', 'R', None, dh_eligible=False)],
        bullpen=[reliever],
        current_pitcher=current,
    )

    seq, events = _apply_pitcher_change(team, {}, {}, 'matchup-1', 3, 'top', outs=1, seq=5)

    assert seq == 5, 'no pitching change means the sequence counter should not advance'
    assert events == [], 'no pitching change should mean no event is emitted'
    assert team.current_pitcher is current, 'the pitcher should stay in the game until both caps are reached'
    assert team.bullpen == [reliever], 'the bullpen should be untouched when no change occurs'


def test_apply_pitcher_change_noop_when_bullpen_empty():
    current = PitcherSlot(1, 'R', {'bf': 10, 'pitches_thrown': 10}, bf_used=20, pitches_used=20)
    team = TeamState(
        team_id='fld',
        batting_order=[BatterSlot(9, 1, 'P', 'R', None, dh_eligible=False)],
        bullpen=[],
        current_pitcher=current,
    )

    seq, events = _apply_pitcher_change(team, {}, {}, 'matchup-1', 4, 'bottom', outs=0, seq=3)

    assert seq == 3, 'with no reliever available there is nothing to change, so the sequence counter should not advance'
    assert events == [], 'with no reliever available, no pitching-change event should be emitted'
    assert team.current_pitcher is current, 'the current pitcher must stay in if there is no reliever to bring in, even past their caps'


def test_apply_pitcher_change_swaps_pure_pitcher_batting_slot():
    current = PitcherSlot(1, 'R', {'bf': 10, 'pitches_thrown': 10}, bf_used=20, pitches_used=20)
    reliever = PitcherSlot(2, 'R', None)
    p_slot = BatterSlot(9, 1, 'P', 'R', None, dh_eligible=False)
    team = TeamState(
        team_id='fld',
        batting_order=[p_slot],
        bullpen=[reliever],
        current_pitcher=current,
    )
    player_info = {
        1: {'eligible_positions': ['P']},
        2: {'eligible_positions': ['P'], 'bats': 'L'},
    }

    seq, events = _apply_pitcher_change(team, player_info, {}, 'matchup-1', 4, 'bottom', outs=2, seq=7)

    assert team.current_pitcher is reliever, 'the reliever should become the current pitcher once caps are reached'
    assert reliever.sequence == current.sequence + 1, "the reliever's pitching sequence should be one more than the outgoing pitcher's"
    assert team.bullpen == [], 'the reliever should be removed from the bullpen once brought in'
    assert team.batting_order[0].player_id == 2, "a pure-pitcher outgoing pitcher's batting slot should be taken over by the incoming reliever"
    assert team.batting_order[0].field_position == 'P', 'the incoming reliever should occupy the P field position in the batting order'
    assert team.batting_order[0].bats == 'L', "the batting-order slot should reflect the incoming reliever's own bats handedness"
    assert team.batting_order[0].batting_position == 9, "the incoming reliever should inherit the outgoing pitcher's batting position"
    assert seq == 8, 'emitting a pitching-change event should advance the sequence counter by one'
    assert len(events) == 1, 'exactly one pitching-change event should be emitted'
    assert events[0]['event_type'] == 'pitching_change', 'the emitted event should be a pitching_change event'
    assert events[0]['pitcher_player_id'] == 2, 'the pitching-change event should identify the incoming reliever'
    assert events[0]['sequence_number'] == 8, 'the pitching-change event should carry the newly advanced sequence number'
    assert events[0]['outs_before_play'] == 2, 'the pitching-change event should record the outs at the time of the change'


def test_apply_pitcher_change_keeps_two_way_player_as_dh():
    current = PitcherSlot(1, 'R', {'bf': 10, 'pitches_thrown': 10}, bf_used=20, pitches_used=20)
    reliever = PitcherSlot(2, 'R', None)
    p_slot = BatterSlot(9, 1, 'P', 'R', None, dh_eligible=True)
    team = TeamState(
        team_id='fld',
        batting_order=[p_slot],
        bullpen=[reliever],
        current_pitcher=current,
    )
    player_info = {1: {'eligible_positions': ['P', '1B']}}

    seq, events = _apply_pitcher_change(team, player_info, {}, 'matchup-1', 4, 'bottom', outs=0, seq=1)

    assert seq == 2, 'emitting a pitching-change event should advance the sequence counter by one'
    assert team.batting_order[0].field_position == 'DH', 'a two-way outgoing pitcher should convert to DH rather than be removed from the lineup'
    assert team.batting_order[0].player_id == 1, 'the old pitcher stays in the lineup as DH rather than being replaced by the incoming reliever'
    assert len(events) == 1, 'exactly one pitching-change event should be emitted'


def test_apply_steal_attempt_no_attempt_leaves_state_unchanged(monkeypatch):
    monkeypatch.setattr(engine, '_try_steal', lambda *args, **kwargs: None)
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 77, 2: 0, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=0, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == runners, 'when _try_steal declines to attempt (returns None), runners should be unchanged'
    assert outs == 0, 'declining to attempt a steal should not add an out'
    assert seq == 4, 'declining to attempt a steal means no event, so the sequence counter should not advance'
    assert events == [], 'declining to attempt a steal should mean no event is emitted'


def test_apply_steal_attempt_success_moves_runner_and_credits_sb(monkeypatch):
    monkeypatch.setattr(engine, '_try_steal', lambda *args, **kwargs: True)
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batting_team.batting_order[0].player_id = 77
    runners = {1: 77, 2: 0, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=0, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == {1: 0, 2: 77, 3: 0}, 'a successful steal should move the runner from 1st to 2nd'
    assert outs == 0, 'a successful steal does not add an out'
    assert seq == 5, 'emitting a stolen-base event should advance the sequence counter by one'
    assert batting_team.batter_stats[77]['sb'] == 1, 'a successful steal should credit the runner with a stolen base'
    assert len(events) == 1, 'exactly one stolen-base event should be emitted'
    assert events[0]['event_type'] == 'stolen_base', 'the emitted event should be a stolen_base event'
    assert events[0]['sequence_number'] == 5, 'the stolen-base event should carry the newly advanced sequence number'
    assert events[0]['outs_before_play'] == 0, 'the stolen-base event should record the outs at the time of the steal'


def test_apply_steal_attempt_caught_adds_out_and_removes_runner(monkeypatch):
    monkeypatch.setattr(engine, '_try_steal', lambda *args, **kwargs: False)
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 77, 2: 0, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=1, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == {1: 0, 2: 0, 3: 0}, 'a caught-stealing runner should be removed from the bases entirely'
    assert outs == 2, 'getting caught stealing should add one out'
    assert seq == 5, 'emitting a caught-stealing event should advance the sequence counter by one'
    assert len(events) == 1, 'exactly one caught-stealing event should be emitted'
    assert events[0]['event_type'] == 'caught_stealing', 'the emitted event should be a caught_stealing event'
    assert events[0]['sequence_number'] == 5, 'the caught-stealing event should carry the newly advanced sequence number'
    assert events[0]['outs_before_play'] == 1, 'the caught-stealing event should record the outs before the caught-stealing out itself was added'
    assert fielding_team.pitcher_stats[2]['outs_recorded'] == 1, (
        'a caught-stealing out should be credited to the pitcher\'s outs_recorded just like any other out, '
        'otherwise IP is undercounted for pitchers involved in caught-stealing plays'
    )


def test_should_change_pitcher_requires_both_caps_reached():
    pitcher = PitcherSlot(
        player_id=99,
        throws='R',
        stats={'bf': 100, 'pitches_thrown': 100},
        bf_used=0,
        pitches_used=0,
        sequence=1,
    )
    batting_order = [
        BatterSlot(
            batting_position=i + 1,
            player_id=1000 + i,
            field_position='DH',
            bats='R',
            stats=None,
        )
        for i in range(9)
    ]
    team = TeamState(
        team_id='t',
        batting_order=batting_order,
        bullpen=[],
        current_pitcher=pitcher,
    )

    team.current_pitcher.bf_used = 110
    team.current_pitcher.pitches_used = 90
    assert team.should_change_pitcher() is False, 'reaching only the BF cap (not the pitch cap) should not trigger a change'

    team.current_pitcher.bf_used = 90
    team.current_pitcher.pitches_used = 110
    assert team.should_change_pitcher() is False, 'reaching only the pitch cap (not the BF cap) should not trigger a change'

    team.current_pitcher.bf_used = 110
    team.current_pitcher.pitches_used = 110
    assert team.should_change_pitcher() is True, 'reaching both the BF cap and the pitch cap should trigger a change'


def test_find_slot_falls_back_to_first_batter_when_missing():
    batting_order = [
        BatterSlot(1, 10, 'C', 'R', None),
        BatterSlot(2, 20, '1B', 'R', None),
        BatterSlot(3, 30, '2B', 'R', None),
        BatterSlot(4, 40, 'SS', 'R', None),
        BatterSlot(5, 50, '3B', 'R', None),
        BatterSlot(6, 60, 'LF', 'R', None),
        BatterSlot(7, 70, 'CF', 'R', None),
        BatterSlot(8, 80, 'RF', 'R', None),
        BatterSlot(9, 90, 'DH', 'R', None),
    ]
    team = TeamState(
        team_id='t',
        batting_order=batting_order,
        bullpen=[],
        current_pitcher=PitcherSlot(999, 'R', None),
    )

    slot = _find_slot(123456, team)
    assert slot.player_id == 10, 'a player_id not present in the batting order should fall back to the first batter rather than raising'


def test_build_runner_outcomes_narrates_an_advance_and_a_score_on_a_single():
    # Runner on 1st advances to 3rd (0 outs), runner on 2nd scores.
    rows = _build_runner_outcomes(
        event_id='evt-2',
        batter_id=50,
        outcome=Outcome.SINGLE,
        runners_before={1: 11, 2: 22, 3: 0},
        runners_after={1: 50, 2: 0, 3: 11},
        player_info=_RUNNER_PLAYER_INFO,
        ends_half_inning=False,
    )

    runner_on_first = next(r for r in rows if r['base_before'] == 1)
    assert runner_on_first['description'] == 'Runner Eleven advances to third base', (
        'a runner who took an extra base on a single should have that advance narrated as a complete, '
        "ready-to-render sentence including the runner's name"
    )

    runner_on_second = next(r for r in rows if r['base_before'] == 2)
    assert runner_on_second['final_base'] == 4, 'a runner on 2nd should always score on a single'
    assert runner_on_second['description'] == 'Runner Twenty-Two scores from second base', (
        'a runner who scored should be narrated as scoring from their prior base'
    )

    assert runner_on_second['narration_sequence'] == 0, (
        'narration order is closest-to-home first, so the runner who was on 2nd (and scored) should be sequenced before '
        'the runner who was on 1st'
    )
    assert runner_on_first['narration_sequence'] == 1, (
        'narration order is closest-to-home first, so the runner who was on 1st should be sequenced after '
        'the runner who was on 2nd'
    )
    assert rows.index(runner_on_second) < rows.index(runner_on_first), (
        'the returned rows should themselves be in narration order (closest-to-home first), not just carry a '
        'narration_sequence value that a caller must sort by'
    )


def test_build_runner_outcomes_narrates_holds_on_non_inning_ending_groundout():
    rows = _build_runner_outcomes(
        event_id='evt-3',
        batter_id=50,
        outcome=Outcome.GO,
        runners_before={1: 0, 2: 22, 3: 0},
        runners_after={1: 0, 2: 22, 3: 0},
        player_info=_RUNNER_PLAYER_INFO,
        ends_half_inning=False,
    )

    runner_on_second = next(r for r in rows if r['base_before'] == 2)
    assert runner_on_second['description'] == 'Runner Twenty-Two holds at second base', (
        'a groundout that does not end the half-inning would typically advance a runner, so a non-advance should be narrated'
    )


def test_build_runner_outcomes_silent_on_inning_ending_groundout():
    rows = _build_runner_outcomes(
        event_id='evt-4',
        batter_id=50,
        outcome=Outcome.GO,
        runners_before={1: 0, 2: 22, 3: 0},
        runners_after={1: 0, 2: 22, 3: 0},
        player_info=_RUNNER_PLAYER_INFO,
        ends_half_inning=True,
    )

    runner_on_second = next(r for r in rows if r['base_before'] == 2)
    assert runner_on_second['description'] is None, (
        'a groundout that ends the half-inning is not expected to advance any runner, so a non-advance should not be narrated'
    )
