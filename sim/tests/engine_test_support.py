"""
Shared fixtures/helpers for sim/src/engine.py tests.

Used by both test_engine.py (correctness tests, including regression tests for
fixed bugs) and test_engine_characterization.py (tests that pin down current,
still-open, known-wrong behavior). Not itself a test module.
"""

import engine
from engine import BatterSlot, PitcherSlot, TeamState, simulate_game
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


def _run_with_per_side_outcomes(monkeypatch, home_fn, road_fn, try_steal_result=None) -> dict:
    """
    Run a full game where each home PA's outcome comes from home_fn(n) and each road
    PA's outcome comes from road_fn(n) — n being that side's own plate-appearance
    count, independent of the other side's. This lets a test give one side a
    decisive, early edge without having to work out how many PAs the other side's
    pattern consumes per half-inning. That independence matters because a *symmetric*
    outcome pattern between the two sides never produces a winner in regulation, so the
    game would only "end" via the engine's extra-innings/tie-breaking behavior — today
    that's the max_innings safety cap, but bug-sim-7 replaces it with a forced-HR rule
    these tests bypass entirely (they stub out `_simulate_pa`), so relying on it is
    fragile. Deciding the game within regulation sidesteps that dependency altogether.
    """
    home_ids = {slot['player_id'] for slot in _base_sim_inputs()['home_lineup']['batting_order']}
    counters = {'home': 0, 'road': 0}

    def fake_simulate_pa(batter_slot, *_args, **_kwargs):
        side = 'home' if batter_slot.player_id in home_ids else 'road'
        n = counters[side]
        counters[side] += 1
        return (home_fn if side == 'home' else road_fn)(n)

    monkeypatch.setattr(engine, '_simulate_pa', fake_simulate_pa)
    monkeypatch.setattr(engine, 'describe_pa', lambda outcome, *_args, **_kwargs: outcome)
    monkeypatch.setattr(engine, '_try_steal', lambda *_args, **_kwargs: try_steal_result)
    return simulate_game(**_base_sim_inputs())


def _cycle_fn(pattern: list):
    return lambda n: pattern[n % len(pattern)]


def _plate_appearance_outcomes(result: dict) -> list[str]:
    return [
        e['description']
        for e in result['events']
        if e['event_type'] == 'plate_appearance'
    ]


_RUNNER_NAMES = {11: 'Runner Eleven', 22: 'Runner Twenty-Two', 33: 'Runner Thirty-Three'}
_RUNNER_PLAYER_INFO = {pid: {'full_name': name} for pid, name in _RUNNER_NAMES.items()}
