"""
Characterization tests for sim/engine.py.

These tests lock in current behavior so we can safely refactor the outcome
branch logic inside simulate_game.
"""

import random
from itertools import cycle

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
from stats import LeagueAverages


def _make_lineup(team_id: str, sp_player_id: int, batter_ids: list[int]) -> dict:
    positions = ['C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF', 'DH']
    return {
        'team_id': team_id,
        'sp_player_id': sp_player_id,
        'batting_order': [
            {
                'batting_position': i + 1,
                'player_id': pid,
                'field_position': positions[i],
            }
            for i, pid in enumerate(batter_ids)
        ],
    }


def _make_player_info(player_ids: list[int], pitcher_ids: list[int]) -> dict[int, dict]:
    pitcher_set = set(pitcher_ids)
    info: dict[int, dict] = {}
    for pid in player_ids:
        info[pid] = {
            'full_name': f'Player {pid}',
            'throws': 'R',
            'bats': 'R',
            'eligible_positions': ['P'] if pid in pitcher_set else ['1B', 'DH'],
        }
    return info


def _base_sim_inputs() -> dict:
    home_sp = 1001
    road_sp = 2001
    home_batters = [1101, 1102, 1103, 1104, 1105, 1106, 1107, 1108, 1109]
    road_batters = [2101, 2102, 2103, 2104, 2105, 2106, 2107, 2108, 2109]

    all_players = [home_sp, road_sp, *home_batters, *road_batters]
    player_info = _make_player_info(all_players, [home_sp, road_sp])

    return {
        'matchup_id': 'matchup-test',
        'home_lineup': _make_lineup('home-team', home_sp, home_batters),
        'road_lineup': _make_lineup('road-team', road_sp, road_batters),
        'player_info': player_info,
        'batter_stats_map': {},
        'pitcher_stats_map': {},
        'league': LeagueAverages.from_mlb_fallback(),
        'home_bench_ids': [],
        'road_bench_ids': [],
        'seed': 7,
    }


def _make_team_state(team_id: str, pitcher_id: int) -> TeamState:
    return TeamState(
        team_id=team_id,
        batting_order=[
            BatterSlot(
                batting_position=1,
                player_id=9000 + pitcher_id,
                field_position='DH',
                bats='R',
                stats=None,
            )
        ],
        bullpen=[],
        current_pitcher=PitcherSlot(player_id=pitcher_id, throws='R', stats=None),
    )


def _run_with_outcome_cycle(monkeypatch, outcomes: list[str]) -> dict:
    outcome_cycle = cycle(outcomes)
    monkeypatch.setattr(engine, '_simulate_pa', lambda *args, **kwargs: next(outcome_cycle))
    monkeypatch.setattr(engine, 'describe_pa', lambda outcome, *_args, **_kwargs: outcome)
    monkeypatch.setattr(engine, '_try_steal', lambda *_args, **_kwargs: None)
    return simulate_game(**_base_sim_inputs())


def _plate_appearance_outcomes(result: dict) -> list[str]:
    return [
        e['description']
        for e in result['events']
        if e['event_type'] == 'plate_appearance'
    ]


def test_simulate_game_all_strikeouts_are_consistent(monkeypatch):
    monkeypatch.setattr(engine, '_simulate_pa', lambda *args, **kwargs: 'k')
    monkeypatch.setattr(engine, 'describe_pa', lambda outcome, *_args, **_kwargs: outcome)

    result = simulate_game(**_base_sim_inputs())

    pa_events = [e for e in result['events'] if e['event_type'] == 'plate_appearance']
    pa_count = len(pa_events)
    assert pa_count > 0
    assert all(e['description'] == 'k' for e in pa_events)

    total_batter_ab = sum(r['ab'] for r in result['batter_stats'])
    total_batter_k = sum(r['k'] for r in result['batter_stats'])
    total_pitcher_outs = sum(r['outs_recorded'] for r in result['pitcher_stats'])

    assert total_batter_ab == pa_count
    assert total_batter_k == pa_count
    assert total_pitcher_outs == pa_count
    assert result['final_score'] == {'home': 0, 'road': 0}
    assert sum(r['runs'] for r in result['line_score']) == 0
    assert sum(r['hits'] for r in result['line_score']) == 0


# bug-sim-9: pitcher side never gets `bb` credit for HBP; see docs/bug-sim-9.md.
def test_hbp_currently_counts_in_batter_bb_bucket(monkeypatch):
    outcomes = cycle(['bb', 'hbp', 'k', 'k', 'k'])
    monkeypatch.setattr(engine, '_simulate_pa', lambda *args, **kwargs: next(outcomes))
    monkeypatch.setattr(engine, 'describe_pa', lambda outcome, *_args, **_kwargs: outcome)

    result = simulate_game(**_base_sim_inputs())

    pa_outcomes = [
        e['description']
        for e in result['events']
        if e['event_type'] == 'plate_appearance'
    ]

    expected_bb_bucket = sum(1 for o in pa_outcomes if o in ('bb', 'hbp'))
    observed_bb_bucket = sum(r['bb'] for r in result['batter_stats'])

    assert 'bb' in pa_outcomes
    assert 'hbp' in pa_outcomes
    assert observed_bb_bucket == expected_bb_bucket


def test_apply_pa_outcome_strikeout_updates_outs_and_k_buckets():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome='k',
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 0, 2: 0, 3: 0},
        outs=0,
        inning_hits=0,
    )

    assert outs == 1
    assert runs_on_play == 0
    assert inning_hits == 0
    assert runners == {1: 0, 2: 0, 3: 0}
    assert batting_team.batter_stats[111]['ab'] == 1
    assert batting_team.batter_stats[111]['k'] == 1
    assert fielding_team.pitcher_stats[2]['outs_recorded'] == 1
    assert fielding_team.pitcher_stats[2]['k'] == 1


def test_apply_pa_outcome_walk_forces_runner_and_increments_bb_buckets():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome='bb',
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 0, 3: 0},
        outs=1,
        inning_hits=0,
    )

    assert outs == 1
    assert runs_on_play == 0
    assert inning_hits == 0
    assert runners == {1: 111, 2: 77, 3: 0}
    assert batting_team.batter_stats[111]['bb'] == 1
    assert fielding_team.pitcher_stats[2]['bb'] == 1


# bug-sim-9
def test_apply_pa_outcome_hbp_updates_batter_bb_but_not_pitcher_bb():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome='hbp',
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 0, 2: 0, 3: 0},
        outs=2,
        inning_hits=0,
    )

    assert outs == 2
    assert runs_on_play == 0
    assert inning_hits == 0
    assert runners == {1: 111, 2: 0, 3: 0}
    assert batting_team.batter_stats[111]['bb'] == 1
    assert fielding_team.pitcher_stats[2]['bb'] == 0


def test_apply_pa_outcome_double_updates_hits_and_run_accounting():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    batter_slot = BatterSlot(1, 111, 'DH', 'R', None)

    outs, runners, inning_hits, runs_on_play = _apply_pa_outcome(
        outcome='double',
        batter_slot=batter_slot,
        fielding_team=fielding_team,
        batting_team=batting_team,
        runners={1: 77, 2: 0, 3: 0},
        outs=1,
        inning_hits=0,
    )

    assert outs == 1
    assert runs_on_play == 1
    assert inning_hits == 1
    assert runners == {1: 0, 2: 111, 3: 0}
    assert batting_team.batter_stats[111]['ab'] == 1
    assert batting_team.batter_stats[111]['h'] == 1
    assert batting_team.batter_stats[111]['doubles'] == 1
    assert batting_team.batter_stats[111]['rbi'] == 1
    assert fielding_team.pitcher_stats[2]['h'] == 1
    assert fielding_team.pitcher_stats[2]['r'] == 1
    assert fielding_team.pitcher_stats[2]['er'] == 1


def test_outcome_branch_bb_increments_batter_and_pitcher_bb(monkeypatch):
    result = _run_with_outcome_cycle(monkeypatch, ['bb', 'k', 'k', 'k'])
    pa_outcomes = _plate_appearance_outcomes(result)

    bb_count = pa_outcomes.count('bb')
    assert bb_count > 0
    assert sum(r['bb'] for r in result['batter_stats']) == bb_count
    assert sum(r['bb'] for r in result['pitcher_stats']) == bb_count
    assert sum(r['ab'] for r in result['batter_stats']) + bb_count == len(pa_outcomes)


# bug-sim-9
def test_outcome_branch_hbp_increments_batter_bb_only(monkeypatch):
    result = _run_with_outcome_cycle(monkeypatch, ['hbp', 'k', 'k', 'k'])
    pa_outcomes = _plate_appearance_outcomes(result)

    hbp_count = pa_outcomes.count('hbp')
    assert hbp_count > 0
    assert sum(r['bb'] for r in result['batter_stats']) == hbp_count
    assert sum(r['bb'] for r in result['pitcher_stats']) == 0
    assert sum(r['ab'] for r in result['batter_stats']) + hbp_count == len(pa_outcomes)


def test_outcome_branch_double_increments_hit_buckets(monkeypatch):
    result = _run_with_outcome_cycle(monkeypatch, ['double', 'k', 'k', 'k'])
    pa_outcomes = _plate_appearance_outcomes(result)

    double_count = pa_outcomes.count('double')
    assert double_count > 0
    assert sum(r['h'] for r in result['batter_stats']) == double_count
    assert sum(r['doubles'] for r in result['batter_stats']) == double_count
    assert sum(r['h'] for r in result['pitcher_stats']) == double_count
    assert sum(r['ab'] for r in result['batter_stats']) == len(pa_outcomes)


def test_make_event_builds_expected_shape():
    event = _make_event(
        'matchup-1', 3, 'top', 7, 'plate_appearance', 'X singles',
        pitcher_player_id=42, runs_scored=1, outs_before_play=1,
    )

    assert event['matchup_id'] == 'matchup-1'
    assert event['inning'] == 3
    assert event['half'] == 'top'
    assert event['sequence_number'] == 7
    assert event['event_type'] == 'plate_appearance'
    assert event['description'] == 'X singles'
    assert event['pitcher_player_id'] == 42
    assert event['runs_scored'] == 1
    assert event['outs_before_play'] == 1
    assert isinstance(event['id'], str) and event['id']


def test_make_event_defaults_pitcher_and_runs_and_generates_id():
    event = _make_event('matchup-1', 1, 'bottom', 1, 'pitching_change', None, outs_before_play=0)

    assert event['pitcher_player_id'] is None
    assert event['runs_scored'] == 0
    assert event['id']


def test_make_event_uses_provided_event_id():
    event = _make_event(
        'matchup-1', 3, 'top', 7, 'plate_appearance', None,
        outs_before_play=0, event_id='fixed-id',
    )

    assert event['id'] == 'fixed-id'


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

    assert result_slot is bench_high
    assert seq == 6
    assert bench_high not in team.bench
    assert team.batting_order[0] is bench_high
    assert bench_high.batting_position == 1
    assert bench_high.field_position == '1B'
    assert len(events) == 1
    assert events[0]['event_type'] == 'substitution'
    assert events[0]['sequence_number'] == 6
    assert events[0]['outs_before_play'] == 1


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

    assert result_slot is batter_slot
    assert seq == 5
    assert events == []
    assert team.bench == [bench]


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

    assert result_slot is batter_slot
    assert seq == 5
    assert events == []


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

    assert result_slot is batter_slot
    assert seq == 5
    assert events == []
    assert team.bench == [bench]


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

    assert seq == 5
    assert events == []
    assert team.current_pitcher is current
    assert team.bullpen == [reliever]


def test_apply_pitcher_change_noop_when_bullpen_empty():
    current = PitcherSlot(1, 'R', {'bf': 10, 'pitches_thrown': 10}, bf_used=20, pitches_used=20)
    team = TeamState(
        team_id='fld',
        batting_order=[BatterSlot(9, 1, 'P', 'R', None, dh_eligible=False)],
        bullpen=[],
        current_pitcher=current,
    )

    seq, events = _apply_pitcher_change(team, {}, {}, 'matchup-1', 4, 'bottom', outs=0, seq=3)

    assert seq == 3
    assert events == []
    assert team.current_pitcher is current


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

    assert team.current_pitcher is reliever
    assert reliever.sequence == current.sequence + 1
    assert team.bullpen == []
    assert team.batting_order[0].player_id == 2
    assert team.batting_order[0].field_position == 'P'
    assert team.batting_order[0].bats == 'L'
    assert team.batting_order[0].batting_position == 9
    assert seq == 8
    assert len(events) == 1
    assert events[0]['event_type'] == 'pitching_change'
    assert events[0]['pitcher_player_id'] == 2
    assert events[0]['sequence_number'] == 8
    assert events[0]['outs_before_play'] == 2


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

    assert seq == 2
    assert team.batting_order[0].field_position == 'DH'
    assert team.batting_order[0].player_id == 1  # old pitcher stays in the lineup as DH
    assert len(events) == 1


def test_apply_steal_attempt_noop_without_runner_on_first():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 0, 2: 5, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=0, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == runners
    assert outs == 0
    assert seq == 4
    assert events == []


def test_apply_steal_attempt_noop_with_two_outs():
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 77, 2: 0, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=2, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == runners
    assert outs == 2
    assert seq == 4
    assert events == []


def test_apply_steal_attempt_no_attempt_leaves_state_unchanged(monkeypatch):
    monkeypatch.setattr(engine, '_try_steal', lambda *args, **kwargs: None)
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 77, 2: 0, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=0, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == runners
    assert outs == 0
    assert seq == 4
    assert events == []


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

    assert result_runners == {1: 0, 2: 77, 3: 0}
    assert outs == 0
    assert seq == 5
    assert batting_team.batter_stats[77]['sb'] == 1
    assert len(events) == 1
    assert events[0]['event_type'] == 'stolen_base'
    assert events[0]['sequence_number'] == 5
    assert events[0]['outs_before_play'] == 0


def test_apply_steal_attempt_caught_adds_out_and_removes_runner(monkeypatch):
    monkeypatch.setattr(engine, '_try_steal', lambda *args, **kwargs: False)
    batting_team = _make_team_state('bat', pitcher_id=1)
    fielding_team = _make_team_state('fld', pitcher_id=2)
    runners = {1: 77, 2: 0, 3: 0}

    result_runners, outs, seq, events = _apply_steal_attempt(
        batting_team, fielding_team, runners, outs=1, batter_stats_map={}, player_info={},
        matchup_id='m', inning=1, half='top', seq=4, rng=random.Random(1),
    )

    assert result_runners == {1: 0, 2: 0, 3: 0}
    assert outs == 2
    assert seq == 5
    assert len(events) == 1
    assert events[0]['event_type'] == 'caught_stealing'
    assert events[0]['sequence_number'] == 5
    assert events[0]['outs_before_play'] == 1


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
    assert team.should_change_pitcher() is False

    team.current_pitcher.bf_used = 90
    team.current_pitcher.pitches_used = 110
    assert team.should_change_pitcher() is False

    team.current_pitcher.bf_used = 110
    team.current_pitcher.pitches_used = 110
    assert team.should_change_pitcher() is True


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
    assert slot.player_id == 10


def test_build_runner_outcomes_for_out_keeps_existing_runners_stationary():
    rows = _build_runner_outcomes(
        event_id='evt-1',
        batter_id=50,
        outcome='k',
        runners_before={1: 11, 2: 22, 3: 0},
        runners_after={1: 11, 2: 22, 3: 0},
    )

    batter_row = next(r for r in rows if r['base_before'] == 0)
    assert batter_row['player_id'] == 50
    assert batter_row['final_base'] is None
    assert batter_row['putout_at_base'] == 1

    runner_on_first = next(r for r in rows if r['base_before'] == 1)
    runner_on_second = next(r for r in rows if r['base_before'] == 2)
    assert runner_on_first['final_base'] == 1
    assert runner_on_second['final_base'] == 2
