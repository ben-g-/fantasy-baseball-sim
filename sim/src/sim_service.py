"""Application service for matchup simulation orchestration."""

import traceback
from typing import Callable, Protocol

import db
import llm_client
import recap
from engine import simulate_game
from stats import LeagueAverages


class SimRepository(Protocol):
    """Repository contract for simulation orchestration data access."""

    def fetch_matchup(self, matchup_id: str) -> dict: ...

    def mark_sim_pending(self, matchup_id: str) -> None: ...

    def fetch_lineup(self, matchup_id: str, team_id: str) -> dict: ...

    def fetch_roster_player_ids(self, team_id: str, league_id: str) -> list[int]: ...

    def fetch_batter_stats(self, player_ids: list[int], sim_date: str) -> dict[int, dict]: ...

    def fetch_pitcher_stats(self, player_ids: list[int], sim_date: str) -> dict[int, dict]: ...

    def fetch_player_info(self, player_ids: list[int]) -> dict[int, dict]: ...

    def fetch_league_batter_averages(self, sim_date: str) -> dict | None: ...

    def fetch_league_pitcher_averages(self, sim_date: str) -> dict | None: ...

    def fetch_team_names(self, team_ids: list[str]) -> dict[str, str]: ...

    def write_recap(self, matchup_id: str, recap_text: str, model: str) -> None: ...

    def write_results(
        self,
        matchup_id: str,
        events: list[dict],
        runner_outcomes: list[dict],
        batter_stats: list[dict],
        batter_positions: list[dict],
        pitcher_stats: list[dict],
        line_score: list[dict],
    ) -> None: ...

    def mark_sim_error(self, matchup_id: str) -> None: ...


class DbSimRepository:
    """Concrete repository adapter backed by sim/src/db.py functions."""

    def fetch_matchup(self, matchup_id: str) -> dict:
        return db.fetch_matchup(matchup_id)

    def mark_sim_pending(self, matchup_id: str) -> None:
        db.mark_sim_pending(matchup_id)

    def fetch_lineup(self, matchup_id: str, team_id: str) -> dict:
        return db.fetch_lineup(matchup_id, team_id)

    def fetch_roster_player_ids(self, team_id: str, league_id: str) -> list[int]:
        return db.fetch_roster_player_ids(team_id, league_id)

    def fetch_batter_stats(self, player_ids: list[int], sim_date: str) -> dict[int, dict]:
        return db.fetch_batter_stats(player_ids, sim_date)

    def fetch_pitcher_stats(self, player_ids: list[int], sim_date: str) -> dict[int, dict]:
        return db.fetch_pitcher_stats(player_ids, sim_date)

    def fetch_player_info(self, player_ids: list[int]) -> dict[int, dict]:
        return db.fetch_player_info(player_ids)

    def fetch_league_batter_averages(self, sim_date: str) -> dict | None:
        return db.fetch_league_batter_averages(sim_date)

    def fetch_league_pitcher_averages(self, sim_date: str) -> dict | None:
        return db.fetch_league_pitcher_averages(sim_date)

    def fetch_team_names(self, team_ids: list[str]) -> dict[str, str]:
        return db.fetch_team_names(team_ids)

    def write_recap(self, matchup_id: str, recap_text: str, model: str) -> None:
        db.write_recap(matchup_id, recap_text, model)

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
        db.write_results(
            matchup_id=matchup_id,
            events=events,
            runner_outcomes=runner_outcomes,
            batter_stats=batter_stats,
            batter_positions=batter_positions,
            pitcher_stats=pitcher_stats,
            line_score=line_score,
        )

    def mark_sim_error(self, matchup_id: str) -> None:
        db.mark_sim_error(matchup_id)


class MatchupNotFoundError(Exception):
    """Raised when a matchup ID does not exist."""


class MatchupNotScheduledError(Exception):
    """Raised when attempting to simulate a matchup outside scheduled status."""

    def __init__(self, sim_status: str):
        self.sim_status = sim_status
        super().__init__(f"Matchup is in status '{sim_status}'")


class SimExecutionError(Exception):
    """Raised when simulation execution fails after marking pending."""


DEFAULT_REPOSITORY: SimRepository = DbSimRepository()


def _generate_and_write_recap(
    repo: SimRepository,
    matchup: dict,
    result: dict,
    player_info: dict[int, dict],
) -> None:
    home_team_id = matchup['home_team_id']
    road_team_id = matchup['road_team_id']
    team_names = repo.fetch_team_names([home_team_id, road_team_id])

    prompt = recap.build_prompt(
        home_team_name=team_names.get(home_team_id, 'Home'),
        road_team_name=team_names.get(road_team_id, 'Road'),
        final_score=result['final_score'],
        home_batter_stats=[b for b in result['batter_stats'] if b['team_id'] == home_team_id],
        road_batter_stats=[b for b in result['batter_stats'] if b['team_id'] == road_team_id],
        home_pitcher_stats=[p for p in result['pitcher_stats'] if p['team_id'] == home_team_id],
        road_pitcher_stats=[p for p in result['pitcher_stats'] if p['team_id'] == road_team_id],
        events=result['events'],
        runner_outcomes=result['runner_outcomes'],
        player_info=player_info,
    )
    recap_text = llm_client.generate_text(prompt)
    repo.write_recap(matchup['id'], recap_text, llm_client.MODEL_ID)


def run_matchup(
    matchup_id: str,
    repo: SimRepository | None = None,
    simulate_fn: Callable[..., dict] | None = None,
) -> dict:
    """Run simulation workflow for one matchup and persist results."""
    if repo is None:
        repo = DEFAULT_REPOSITORY

    if simulate_fn is None:
        simulate_fn = simulate_game

    try:
        matchup = repo.fetch_matchup(matchup_id)
    except Exception as exc:
        raise MatchupNotFoundError() from exc

    if matchup['sim_status'] != 'scheduled':
        raise MatchupNotScheduledError(matchup['sim_status'])

    repo.mark_sim_pending(matchup_id)

    try:
        sim_date = matchup['sim_scheduled_at'][:10]  # YYYY-MM-DD

        home_lineup = repo.fetch_lineup(matchup_id, matchup['home_team_id'])
        road_lineup = repo.fetch_lineup(matchup_id, matchup['road_team_id'])

        league_id = matchup['league_id']
        home_roster_ids = repo.fetch_roster_player_ids(matchup['home_team_id'], league_id)
        road_roster_ids = repo.fetch_roster_player_ids(matchup['road_team_id'], league_id)

        batting_order_ids = [e['player_id'] for e in home_lineup['batting_order'] + road_lineup['batting_order']]
        pitcher_ids = [home_lineup['sp_player_id'], road_lineup['sp_player_id']]
        all_player_ids = list({*home_roster_ids, *road_roster_ids})

        # Bench = roster players not in the batting order and not the SP
        in_lineup = set(batting_order_ids) | set(pitcher_ids)
        home_bench_ids = [pid for pid in home_roster_ids if pid not in in_lineup]
        road_bench_ids = [pid for pid in road_roster_ids if pid not in in_lineup]

        batter_ids = list({*batting_order_ids, *home_bench_ids, *road_bench_ids})
        batter_stats_map = repo.fetch_batter_stats(batter_ids, sim_date)
        pitcher_stats_map = repo.fetch_pitcher_stats(pitcher_ids, sim_date)
        player_info = repo.fetch_player_info(all_player_ids)

        batter_agg = repo.fetch_league_batter_averages(sim_date)
        pitcher_agg = repo.fetch_league_pitcher_averages(sim_date)

        if batter_agg and pitcher_agg:
            league = LeagueAverages.from_db_rows(batter_agg, pitcher_agg)
        else:
            league = LeagueAverages.from_mlb_fallback()

        result = simulate_fn(
            matchup_id=matchup_id,
            home_lineup=home_lineup,
            road_lineup=road_lineup,
            player_info=player_info,
            batter_stats_map=batter_stats_map,
            pitcher_stats_map=pitcher_stats_map,
            league=league,
            home_bench_ids=home_bench_ids,
            road_bench_ids=road_bench_ids,
        )

        repo.write_results(
            matchup_id=matchup_id,
            events=result['events'],
            runner_outcomes=result['runner_outcomes'],
            batter_stats=result['batter_stats'],
            batter_positions=result['batter_positions'],
            pitcher_stats=result['pitcher_stats'],
            line_score=result['line_score'],
        )

        # Recap generation is a non-critical enhancement on top of an already-
        # successful sim: a failure here (timeout, API error, refusal) is logged
        # and simply leaves no sim_recaps row — it must never reach the except
        # clause below, which would incorrectly mark this successful sim as
        # errored.
        try:
            _generate_and_write_recap(repo, matchup, result, player_info)
        except Exception:
            traceback.print_exc()

        return {
            'matchup_id': matchup_id,
            'final_score': result['final_score'],
        }

    except Exception as exc:
        traceback.print_exc()
        repo.mark_sim_error(matchup_id)
        raise SimExecutionError(str(exc)) from exc