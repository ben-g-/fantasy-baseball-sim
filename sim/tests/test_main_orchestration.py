"""Characterization tests for orchestration behavior in sim/main.py."""

import pytest
from fastapi import HTTPException

import main


def _make_lineup(team_id: str, sp_player_id: int, batter_ids: list[int]) -> dict:
    return {
        'id': f'lineup-{team_id}',
        'team_id': team_id,
        'sp_player_id': sp_player_id,
        'batting_order': [
            {
                'batting_position': i + 1,
                'player_id': pid,
                'field_position': 'DH',
            }
            for i, pid in enumerate(batter_ids)
        ],
    }


def test_run_sim_happy_path_orchestrates_and_writes_results(monkeypatch):
    matchup_id = 'matchup-1'
    matchup = {
        'id': matchup_id,
        'league_id': 'league-1',
        'home_team_id': 'home-team',
        'road_team_id': 'road-team',
        'sim_scheduled_at': '2026-07-01T12:00:00Z',
        'sim_status': 'scheduled',
    }

    home_lineup = _make_lineup('home-team', 10, [1, 2, 3, 4, 5, 6, 7, 8, 9])
    road_lineup = _make_lineup('road-team', 30, [21, 22, 23, 24, 25, 26, 27, 28, 29])
    home_roster = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    road_roster = [21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]

    call_log: list[str] = []
    captured_sim_kwargs: dict = {}
    captured_write_kwargs: dict = {}

    monkeypatch.setattr(main.db, 'fetch_matchup', lambda mid: matchup)

    def fake_mark_pending(mid):
        assert mid == matchup_id
        call_log.append('mark_sim_pending')

    monkeypatch.setattr(main.db, 'mark_sim_pending', fake_mark_pending)
    monkeypatch.setattr(main.db, 'mark_sim_error', lambda _mid: call_log.append('mark_sim_error'))

    def fake_fetch_lineup(mid, team_id):
        assert mid == matchup_id
        return home_lineup if team_id == matchup['home_team_id'] else road_lineup

    monkeypatch.setattr(main.db, 'fetch_lineup', fake_fetch_lineup)
    monkeypatch.setattr(
        main.db,
        'fetch_roster_player_ids',
        lambda team_id, _league_id: home_roster if team_id == matchup['home_team_id'] else road_roster,
    )

    def fake_fetch_batter_stats(player_ids, sim_date):
        assert sim_date == '2026-07-01'
        assert set(player_ids) == {
            1, 2, 3, 4, 5, 6, 7, 8, 9,
            11,
            21, 22, 23, 24, 25, 26, 27, 28, 29,
            31,
        }
        return {}

    monkeypatch.setattr(main.db, 'fetch_batter_stats', fake_fetch_batter_stats)

    def fake_fetch_pitcher_stats(player_ids, sim_date):
        assert sim_date == '2026-07-01'
        assert set(player_ids) == {10, 30}
        return {}

    monkeypatch.setattr(main.db, 'fetch_pitcher_stats', fake_fetch_pitcher_stats)
    monkeypatch.setattr(main.db, 'fetch_player_info', lambda _ids: {})
    monkeypatch.setattr(main.db, 'fetch_league_batter_averages', lambda _date: None)
    monkeypatch.setattr(main.db, 'fetch_league_pitcher_averages', lambda _date: None)

    def fake_simulate_game(**kwargs):
        captured_sim_kwargs.update(kwargs)
        return {
            'events': [],
            'runner_outcomes': [],
            'batter_stats': [],
            'batter_positions': [],
            'pitcher_stats': [],
            'line_score': [],
            'final_score': {'home': 2, 'road': 1},
        }

    monkeypatch.setattr(main, 'simulate_game', fake_simulate_game)

    def fake_write_results(**kwargs):
        call_log.append('write_results')
        captured_write_kwargs.update(kwargs)

    monkeypatch.setattr(main.db, 'write_results', fake_write_results)

    response = main.run_sim(main.SimRequest(matchup_id=matchup_id))

    assert response == {'matchup_id': matchup_id, 'final_score': {'home': 2, 'road': 1}}
    assert captured_sim_kwargs['home_bench_ids'] == [11]
    assert captured_sim_kwargs['road_bench_ids'] == [31]
    assert captured_sim_kwargs['matchup_id'] == matchup_id
    assert captured_write_kwargs['matchup_id'] == matchup_id

    assert 'mark_sim_error' not in call_log
    assert call_log.index('mark_sim_pending') < call_log.index('write_results')


def test_run_sim_marks_error_and_returns_500_on_internal_failure(monkeypatch):
    matchup_id = 'matchup-2'
    matchup = {
        'id': matchup_id,
        'league_id': 'league-1',
        'home_team_id': 'home-team',
        'road_team_id': 'road-team',
        'sim_scheduled_at': '2026-07-01T12:00:00Z',
        'sim_status': 'scheduled',
    }

    home_lineup = _make_lineup('home-team', 10, [1, 2, 3, 4, 5, 6, 7, 8, 9])
    road_lineup = _make_lineup('road-team', 30, [21, 22, 23, 24, 25, 26, 27, 28, 29])

    call_log: list[str] = []

    monkeypatch.setattr(main.db, 'fetch_matchup', lambda _mid: matchup)
    monkeypatch.setattr(main.db, 'mark_sim_pending', lambda _mid: call_log.append('mark_sim_pending'))
    monkeypatch.setattr(main.db, 'mark_sim_error', lambda _mid: call_log.append('mark_sim_error'))
    monkeypatch.setattr(main.db, 'fetch_lineup', lambda _mid, team_id: home_lineup if team_id == 'home-team' else road_lineup)
    monkeypatch.setattr(
        main.db,
        'fetch_roster_player_ids',
        lambda team_id, _league_id: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] if team_id == 'home-team' else [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
    )
    monkeypatch.setattr(main.db, 'fetch_batter_stats', lambda _ids, _date: {})
    monkeypatch.setattr(main.db, 'fetch_pitcher_stats', lambda _ids, _date: {})
    monkeypatch.setattr(main.db, 'fetch_player_info', lambda _ids: {})
    monkeypatch.setattr(main.db, 'fetch_league_batter_averages', lambda _date: None)
    monkeypatch.setattr(main.db, 'fetch_league_pitcher_averages', lambda _date: None)
    monkeypatch.setattr(main, 'simulate_game', lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('sim exploded')))
    monkeypatch.setattr(main.db, 'write_results', lambda **_kwargs: call_log.append('write_results'))
    monkeypatch.setattr(main.traceback, 'print_exc', lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        main.run_sim(main.SimRequest(matchup_id=matchup_id))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'sim exploded'
    assert 'write_results' not in call_log
    assert call_log == ['mark_sim_pending', 'mark_sim_error']


def test_run_sim_non_scheduled_matchup_returns_409_without_status_changes(monkeypatch):
    matchup = {
        'id': 'matchup-3',
        'league_id': 'league-1',
        'home_team_id': 'home-team',
        'road_team_id': 'road-team',
        'sim_scheduled_at': '2026-07-01T12:00:00Z',
        'sim_status': 'sim_pending',
    }

    call_log: list[str] = []
    monkeypatch.setattr(main.db, 'fetch_matchup', lambda _mid: matchup)
    monkeypatch.setattr(main.db, 'mark_sim_pending', lambda _mid: call_log.append('mark_sim_pending'))
    monkeypatch.setattr(main.db, 'mark_sim_error', lambda _mid: call_log.append('mark_sim_error'))

    with pytest.raises(HTTPException) as exc_info:
        main.run_sim(main.SimRequest(matchup_id='matchup-3'))

    assert exc_info.value.status_code == 409
    assert "sim_pending" in exc_info.value.detail
    assert call_log == []
