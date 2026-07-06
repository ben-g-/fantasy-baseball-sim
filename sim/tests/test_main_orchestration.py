"""Characterization tests for service orchestration and endpoint error mapping."""

import pytest
from fastapi import HTTPException

import main
import sim_service


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


def test_run_matchup_happy_path_orchestrates_and_writes_results(monkeypatch):
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

    monkeypatch.setattr(sim_service.db, 'fetch_matchup', lambda _mid: matchup)

    def fake_mark_pending(mid):
        assert mid == matchup_id
        call_log.append('mark_sim_pending')

    monkeypatch.setattr(sim_service.db, 'mark_sim_pending', fake_mark_pending)
    monkeypatch.setattr(sim_service.db, 'mark_sim_error', lambda _mid: call_log.append('mark_sim_error'))

    def fake_fetch_lineup(mid, team_id):
        assert mid == matchup_id
        return home_lineup if team_id == matchup['home_team_id'] else road_lineup

    monkeypatch.setattr(sim_service.db, 'fetch_lineup', fake_fetch_lineup)
    monkeypatch.setattr(
        sim_service.db,
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

    monkeypatch.setattr(sim_service.db, 'fetch_batter_stats', fake_fetch_batter_stats)

    def fake_fetch_pitcher_stats(player_ids, sim_date):
        assert sim_date == '2026-07-01'
        assert set(player_ids) == {10, 30}
        return {}

    monkeypatch.setattr(sim_service.db, 'fetch_pitcher_stats', fake_fetch_pitcher_stats)
    monkeypatch.setattr(sim_service.db, 'fetch_player_info', lambda _ids: {})
    monkeypatch.setattr(sim_service.db, 'fetch_league_batter_averages', lambda _date: None)
    monkeypatch.setattr(sim_service.db, 'fetch_league_pitcher_averages', lambda _date: None)

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

    monkeypatch.setattr(sim_service, 'simulate_game', fake_simulate_game)

    def fake_write_results(**kwargs):
        call_log.append('write_results')
        captured_write_kwargs.update(kwargs)

    monkeypatch.setattr(sim_service.db, 'write_results', fake_write_results)

    monkeypatch.setattr(
        sim_service.db,
        'fetch_team_names',
        lambda team_ids: {'home-team': 'Home Squad', 'road-team': 'Road Squad'},
    )
    captured_prompt: dict = {}

    def fake_generate_text(prompt):
        captured_prompt['value'] = prompt
        return 'A thrilling 2-1 game.'

    monkeypatch.setattr(sim_service.llm_client, 'generate_text', fake_generate_text)

    def fake_write_recap(matchup_id_arg, recap_text, model):
        call_log.append('write_recap')
        assert matchup_id_arg == matchup_id
        assert recap_text == 'A thrilling 2-1 game.'
        assert model == sim_service.llm_client.MODEL_ID

    monkeypatch.setattr(sim_service.db, 'write_recap', fake_write_recap)

    response = sim_service.run_matchup(matchup_id)

    assert response == {'matchup_id': matchup_id, 'final_score': {'home': 2, 'road': 1}}
    assert captured_sim_kwargs['home_bench_ids'] == [11]
    assert captured_sim_kwargs['road_bench_ids'] == [31]
    assert captured_sim_kwargs['matchup_id'] == matchup_id
    assert captured_write_kwargs['matchup_id'] == matchup_id

    assert 'mark_sim_error' not in call_log
    assert call_log.index('mark_sim_pending') < call_log.index('write_results')
    assert call_log.index('write_results') < call_log.index('write_recap'), (
        "the recap must be generated after the box score / play-by-play are written, "
        "so a recap failure can never affect the results already persisted"
    )
    assert 'Home Squad' in captured_prompt['value'] and 'Road Squad' in captured_prompt['value'], (
        "the recap prompt should be built from the team names fetched via the repository, "
        "not left as opaque team IDs"
    )


def test_run_matchup_recap_failure_is_isolated_from_sim_success(monkeypatch):
    matchup_id = 'matchup-recap-fail'
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

    monkeypatch.setattr(sim_service.db, 'fetch_matchup', lambda _mid: matchup)
    monkeypatch.setattr(sim_service.db, 'mark_sim_pending', lambda _mid: call_log.append('mark_sim_pending'))
    monkeypatch.setattr(sim_service.db, 'mark_sim_error', lambda _mid: call_log.append('mark_sim_error'))
    monkeypatch.setattr(sim_service.db, 'fetch_lineup', lambda _mid, team_id: home_lineup if team_id == 'home-team' else road_lineup)
    monkeypatch.setattr(
        sim_service.db,
        'fetch_roster_player_ids',
        lambda team_id, _league_id: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] if team_id == 'home-team' else [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
    )
    monkeypatch.setattr(sim_service.db, 'fetch_batter_stats', lambda _ids, _date: {})
    monkeypatch.setattr(sim_service.db, 'fetch_pitcher_stats', lambda _ids, _date: {})
    monkeypatch.setattr(sim_service.db, 'fetch_player_info', lambda _ids: {})
    monkeypatch.setattr(sim_service.db, 'fetch_league_batter_averages', lambda _date: None)
    monkeypatch.setattr(sim_service.db, 'fetch_league_pitcher_averages', lambda _date: None)
    monkeypatch.setattr(sim_service, 'simulate_game', lambda **_kwargs: {
        'events': [],
        'runner_outcomes': [],
        'batter_stats': [],
        'batter_positions': [],
        'pitcher_stats': [],
        'line_score': [],
        'final_score': {'home': 2, 'road': 1},
    })
    monkeypatch.setattr(sim_service.db, 'write_results', lambda **_kwargs: call_log.append('write_results'))
    monkeypatch.setattr(sim_service.db, 'fetch_team_names', lambda _ids: {'home-team': 'Home Squad', 'road-team': 'Road Squad'})

    def fake_generate_text(_prompt):
        raise RuntimeError('LLM request timed out')

    monkeypatch.setattr(sim_service.llm_client, 'generate_text', fake_generate_text)
    monkeypatch.setattr(sim_service.db, 'write_recap', lambda *_a, **_k: call_log.append('write_recap'))

    print_exc_calls: list[int] = []
    monkeypatch.setattr(sim_service.traceback, 'print_exc', lambda: print_exc_calls.append(1))

    response = sim_service.run_matchup(matchup_id)

    assert response == {'matchup_id': matchup_id, 'final_score': {'home': 2, 'road': 1}}, (
        "a recap generation failure must not prevent run_matchup from returning its normal "
        "success response"
    )
    assert 'write_recap' not in call_log, "a failed generate_text call should never reach write_recap"
    assert 'mark_sim_error' not in call_log, (
        "a recap failure must never flip the matchup to sim_error — it's a non-critical "
        "enhancement on top of an already-successful sim"
    )
    assert call_log == ['mark_sim_pending', 'write_results']
    assert print_exc_calls == [1], "the recap failure should still be logged, not silently dropped"


def test_run_matchup_marks_error_and_raises_execution_error(monkeypatch):
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

    monkeypatch.setattr(sim_service.db, 'fetch_matchup', lambda _mid: matchup)
    monkeypatch.setattr(sim_service.db, 'mark_sim_pending', lambda _mid: call_log.append('mark_sim_pending'))
    monkeypatch.setattr(sim_service.db, 'mark_sim_error', lambda _mid: call_log.append('mark_sim_error'))
    monkeypatch.setattr(sim_service.db, 'fetch_lineup', lambda _mid, team_id: home_lineup if team_id == 'home-team' else road_lineup)
    monkeypatch.setattr(
        sim_service.db,
        'fetch_roster_player_ids',
        lambda team_id, _league_id: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] if team_id == 'home-team' else [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
    )
    monkeypatch.setattr(sim_service.db, 'fetch_batter_stats', lambda _ids, _date: {})
    monkeypatch.setattr(sim_service.db, 'fetch_pitcher_stats', lambda _ids, _date: {})
    monkeypatch.setattr(sim_service.db, 'fetch_player_info', lambda _ids: {})
    monkeypatch.setattr(sim_service.db, 'fetch_league_batter_averages', lambda _date: None)
    monkeypatch.setattr(sim_service.db, 'fetch_league_pitcher_averages', lambda _date: None)
    monkeypatch.setattr(sim_service, 'simulate_game', lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('sim exploded')))
    monkeypatch.setattr(sim_service.db, 'write_results', lambda **_kwargs: call_log.append('write_results'))
    monkeypatch.setattr(sim_service.traceback, 'print_exc', lambda: None)

    with pytest.raises(sim_service.SimExecutionError) as exc_info:
        sim_service.run_matchup(matchup_id)

    assert str(exc_info.value) == 'sim exploded'
    assert 'write_results' not in call_log
    assert call_log == ['mark_sim_pending', 'mark_sim_error']


def test_run_matchup_non_scheduled_raises_conflict_error_without_status_changes(monkeypatch):
    matchup = {
        'id': 'matchup-3',
        'league_id': 'league-1',
        'home_team_id': 'home-team',
        'road_team_id': 'road-team',
        'sim_scheduled_at': '2026-07-01T12:00:00Z',
        'sim_status': 'sim_pending',
    }

    call_log: list[str] = []
    monkeypatch.setattr(sim_service.db, 'fetch_matchup', lambda _mid: matchup)
    monkeypatch.setattr(sim_service.db, 'mark_sim_pending', lambda _mid: call_log.append('mark_sim_pending'))
    monkeypatch.setattr(sim_service.db, 'mark_sim_error', lambda _mid: call_log.append('mark_sim_error'))

    with pytest.raises(sim_service.MatchupNotScheduledError) as exc_info:
        sim_service.run_matchup('matchup-3')

    assert "sim_pending" in str(exc_info.value)
    assert call_log == []


def test_run_matchup_uses_injected_repository_instead_of_module_db(monkeypatch):
    matchup_id = 'matchup-dip'

    class FakeRepo:
        def __init__(self):
            self.calls: list[str] = []

        def fetch_matchup(self, matchup_id: str) -> dict:
            self.calls.append('fetch_matchup')
            return {
                'id': matchup_id,
                'league_id': 'league-1',
                'home_team_id': 'home-team',
                'road_team_id': 'road-team',
                'sim_scheduled_at': '2026-07-01T12:00:00Z',
                'sim_status': 'scheduled',
            }

        def mark_sim_pending(self, matchup_id: str) -> None:
            self.calls.append('mark_sim_pending')

        def fetch_lineup(self, matchup_id: str, team_id: str) -> dict:
            self.calls.append('fetch_lineup')
            if team_id == 'home-team':
                return _make_lineup('home-team', 10, [1, 2, 3, 4, 5, 6, 7, 8, 9])
            return _make_lineup('road-team', 30, [21, 22, 23, 24, 25, 26, 27, 28, 29])

        def fetch_roster_player_ids(self, team_id: str, league_id: str) -> list[int]:
            self.calls.append('fetch_roster_player_ids')
            if team_id == 'home-team':
                return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
            return [21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]

        def fetch_batter_stats(self, player_ids: list[int], sim_date: str) -> dict[int, dict]:
            self.calls.append('fetch_batter_stats')
            return {}

        def fetch_pitcher_stats(self, player_ids: list[int], sim_date: str) -> dict[int, dict]:
            self.calls.append('fetch_pitcher_stats')
            return {}

        def fetch_player_info(self, player_ids: list[int]) -> dict[int, dict]:
            self.calls.append('fetch_player_info')
            return {}

        def fetch_league_batter_averages(self, sim_date: str) -> dict | None:
            self.calls.append('fetch_league_batter_averages')
            return None

        def fetch_league_pitcher_averages(self, sim_date: str) -> dict | None:
            self.calls.append('fetch_league_pitcher_averages')
            return None

        def fetch_team_names(self, team_ids: list[str]) -> dict[str, str]:
            self.calls.append('fetch_team_names')
            return {'home-team': 'Home Squad', 'road-team': 'Road Squad'}

        def write_recap(self, matchup_id: str, recap_text: str, model: str) -> None:
            self.calls.append('write_recap')
            assert matchup_id == 'matchup-dip'

        def write_results(
            self,
            matchup_id: str,
            events: list[dict],
            runner_outcomes: list[dict],
            batter_stats: list[dict],
            batter_positions: list[dict],
            pitcher_stats: list[dict],
            line_score: list[dict],
        ) -> None:
            self.calls.append('write_results')
            assert matchup_id == 'matchup-dip'
            assert events == []
            assert runner_outcomes == []
            assert batter_stats == []
            assert batter_positions == []
            assert pitcher_stats == []
            assert line_score == []

        def mark_sim_error(self, matchup_id: str) -> None:
            self.calls.append('mark_sim_error')

    for name in (
        'fetch_matchup',
        'mark_sim_pending',
        'fetch_lineup',
        'fetch_roster_player_ids',
        'fetch_batter_stats',
        'fetch_pitcher_stats',
        'fetch_player_info',
        'fetch_league_batter_averages',
        'fetch_league_pitcher_averages',
        'fetch_team_names',
        'write_recap',
        'write_results',
        'mark_sim_error',
    ):
        monkeypatch.setattr(
            sim_service.db,
            name,
            lambda *args, _name=name, **kwargs: (_ for _ in ()).throw(
                AssertionError(f'module db should not be used: {_name}')
            ),
        )
    monkeypatch.setattr(sim_service.llm_client, 'generate_text', lambda _prompt: 'A thrilling 3-2 game.')

    fake_repo = FakeRepo()

    result = sim_service.run_matchup(
        matchup_id,
        repo=fake_repo,
        simulate_fn=lambda **kwargs: {
            'events': [],
            'runner_outcomes': [],
            'batter_stats': [],
            'batter_positions': [],
            'pitcher_stats': [],
            'line_score': [],
            'final_score': {'home': 3, 'road': 2},
        },
    )

    assert result == {'matchup_id': 'matchup-dip', 'final_score': {'home': 3, 'road': 2}}
    assert 'write_results' in fake_repo.calls
    assert 'write_recap' in fake_repo.calls, (
        "recap generation should go through the injected repository, same as every other "
        "write in this orchestration — never falling back to the module-level db"
    )
    assert 'mark_sim_error' not in fake_repo.calls


def test_run_sim_maps_not_found_to_404(monkeypatch):
    monkeypatch.setattr(main, 'run_matchup', lambda _mid: (_ for _ in ()).throw(sim_service.MatchupNotFoundError()))

    with pytest.raises(HTTPException) as exc_info:
        main.run_sim(main.SimRequest(matchup_id='missing'))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'Matchup not found'


def test_run_sim_maps_not_scheduled_to_409(monkeypatch):
    monkeypatch.setattr(
        main,
        'run_matchup',
        lambda _mid: (_ for _ in ()).throw(sim_service.MatchupNotScheduledError('sim_pending')),
    )

    with pytest.raises(HTTPException) as exc_info:
        main.run_sim(main.SimRequest(matchup_id='matchup-3'))

    assert exc_info.value.status_code == 409
    assert "sim_pending" in exc_info.value.detail


def test_run_sim_maps_execution_error_to_500(monkeypatch):
    monkeypatch.setattr(
        main,
        'run_matchup',
        lambda _mid: (_ for _ in ()).throw(sim_service.SimExecutionError('sim exploded')),
    )

    with pytest.raises(HTTPException) as exc_info:
        main.run_sim(main.SimRequest(matchup_id='matchup-4'))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'sim exploded'
