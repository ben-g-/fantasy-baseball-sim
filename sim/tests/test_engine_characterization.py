"""
Characterization tests for sim/engine.py.

These tests lock in current behavior so we can safely refactor the outcome
branch logic inside simulate_game.
"""

from itertools import cycle

import engine
from engine import BatterSlot, PitcherSlot, TeamState, _build_runner_outcomes, _find_slot, simulate_game
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


def test_outcome_branch_bb_increments_batter_and_pitcher_bb(monkeypatch):
    result = _run_with_outcome_cycle(monkeypatch, ['bb', 'k', 'k', 'k'])
    pa_outcomes = _plate_appearance_outcomes(result)

    bb_count = pa_outcomes.count('bb')
    assert bb_count > 0
    assert sum(r['bb'] for r in result['batter_stats']) == bb_count
    assert sum(r['bb'] for r in result['pitcher_stats']) == bb_count
    assert sum(r['ab'] for r in result['batter_stats']) + bb_count == len(pa_outcomes)


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
