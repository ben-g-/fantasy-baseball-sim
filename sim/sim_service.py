"""Application service for matchup simulation orchestration."""

import traceback

import db
from engine import simulate_game
from stats import LeagueAverages


class MatchupNotFoundError(Exception):
    """Raised when a matchup ID does not exist."""


class MatchupNotScheduledError(Exception):
    """Raised when attempting to simulate a matchup outside scheduled status."""

    def __init__(self, sim_status: str):
        self.sim_status = sim_status
        super().__init__(f"Matchup is in status '{sim_status}'")


class SimExecutionError(Exception):
    """Raised when simulation execution fails after marking pending."""


def run_matchup(matchup_id: str) -> dict:
    """Run simulation workflow for one matchup and persist results."""
    try:
        matchup = db.fetch_matchup(matchup_id)
    except Exception as exc:
        raise MatchupNotFoundError() from exc

    if matchup['sim_status'] != 'scheduled':
        raise MatchupNotScheduledError(matchup['sim_status'])

    db.mark_sim_pending(matchup_id)

    try:
        sim_date = matchup['sim_scheduled_at'][:10]  # YYYY-MM-DD

        home_lineup = db.fetch_lineup(matchup_id, matchup['home_team_id'])
        road_lineup = db.fetch_lineup(matchup_id, matchup['road_team_id'])

        league_id = matchup['league_id']
        home_roster_ids = db.fetch_roster_player_ids(matchup['home_team_id'], league_id)
        road_roster_ids = db.fetch_roster_player_ids(matchup['road_team_id'], league_id)

        batting_order_ids = [e['player_id'] for e in home_lineup['batting_order'] + road_lineup['batting_order']]
        pitcher_ids = [home_lineup['sp_player_id'], road_lineup['sp_player_id']]
        all_player_ids = list({*home_roster_ids, *road_roster_ids})

        # Bench = roster players not in the batting order and not the SP
        in_lineup = set(batting_order_ids) | set(pitcher_ids)
        home_bench_ids = [pid for pid in home_roster_ids if pid not in in_lineup]
        road_bench_ids = [pid for pid in road_roster_ids if pid not in in_lineup]

        batter_ids = list({*batting_order_ids, *home_bench_ids, *road_bench_ids})
        batter_stats_map = db.fetch_batter_stats(batter_ids, sim_date)
        pitcher_stats_map = db.fetch_pitcher_stats(pitcher_ids, sim_date)
        player_info = db.fetch_player_info(all_player_ids)

        batter_agg = db.fetch_league_batter_averages(sim_date)
        pitcher_agg = db.fetch_league_pitcher_averages(sim_date)

        if batter_agg and pitcher_agg:
            league = LeagueAverages.from_db_rows(batter_agg, pitcher_agg)
        else:
            league = LeagueAverages.from_mlb_fallback()

        result = simulate_game(
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

        db.write_results(
            matchup_id=matchup_id,
            events=result['events'],
            runner_outcomes=result['runner_outcomes'],
            batter_stats=result['batter_stats'],
            batter_positions=result['batter_positions'],
            pitcher_stats=result['pitcher_stats'],
            line_score=result['line_score'],
        )

        return {
            'matchup_id': matchup_id,
            'final_score': result['final_score'],
        }

    except Exception as exc:
        traceback.print_exc()
        db.mark_sim_error(matchup_id)
        raise SimExecutionError(str(exc)) from exc