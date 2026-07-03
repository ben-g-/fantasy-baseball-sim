import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


class LineupNotFoundError(Exception):
    """Raised when a matchup team has no lineup row (e.g. lineup was never created)."""


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ['SUPABASE_URL']
        key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
        _client = create_client(url, key)
    return _client


def fetch_matchup(matchup_id: str) -> dict:
    sb = get_client()
    row = (
        sb.table('matchups')
        .select('id, league_id, week_number, home_team_id, road_team_id, sim_scheduled_at, sim_status')
        .eq('id', matchup_id)
        .single()
        .execute()
    )
    return row.data


def fetch_lineup(matchup_id: str, team_id: str) -> dict:
    """Return lineup row with sp_player_id and batting order entries."""
    sb = get_client()
    lineup = (
        sb.table('lineups')
        .select('id, team_id, sp_player_id')
        .eq('matchup_id', matchup_id)
        .eq('team_id', team_id)
        .maybe_single()
        .execute()
    )
    if lineup is None or lineup.data is None:
        raise LineupNotFoundError(
            f"No lineup found for team {team_id} in matchup {matchup_id}"
        )
    data = lineup.data
    bo = (
        sb.table('lineup_batting_order')
        .select('batting_position, player_id, field_position')
        .eq('lineup_id', data['id'])
        .order('batting_position')
        .execute()
    )
    data['batting_order'] = bo.data
    return data


def fetch_batter_stats(player_ids: list[int], sim_date: str) -> dict[int, dict]:
    sb = get_client()
    rows = (
        sb.table('batter_pre_lock_stats')
        .select(
            'player_id, pa, singles, doubles, triples, hr, bb, hbp, k, go, fo, sb, cs,'
            'vs_lhp_pa, vs_lhp_singles, vs_lhp_doubles, vs_lhp_triples, vs_lhp_hr, vs_lhp_bb, vs_lhp_hbp, vs_lhp_k, vs_lhp_go, vs_lhp_fo,'
            'vs_rhp_pa, vs_rhp_singles, vs_rhp_doubles, vs_rhp_triples, vs_rhp_hr, vs_rhp_bb, vs_rhp_hbp, vs_rhp_k, vs_rhp_go, vs_rhp_fo'
        )
        .eq('sim_date', sim_date)
        .in_('player_id', player_ids)
        .execute()
    )
    return {r['player_id']: r for r in rows.data}


def fetch_pitcher_stats(player_ids: list[int], sim_date: str) -> dict[int, dict]:
    sb = get_client()
    rows = (
        sb.table('pitcher_pre_lock_stats')
        .select(
            'player_id, bf, pitches_thrown, singles, doubles, triples, hr, bb, hbp, k, go, fo,'
            'vs_lhb_bf, vs_lhb_singles, vs_lhb_doubles, vs_lhb_triples, vs_lhb_hr, vs_lhb_bb, vs_lhb_hbp, vs_lhb_k, vs_lhb_go, vs_lhb_fo,'
            'vs_rhb_bf, vs_rhb_singles, vs_rhb_doubles, vs_rhb_triples, vs_rhb_hr, vs_rhb_bb, vs_rhb_hbp, vs_rhb_k, vs_rhb_go, vs_rhb_fo'
        )
        .eq('sim_date', sim_date)
        .in_('player_id', player_ids)
        .execute()
    )
    return {r['player_id']: r for r in rows.data}


def fetch_player_info(player_ids: list[int]) -> dict[int, dict]:
    sb = get_client()
    rows = (
        sb.table('players')
        .select('mlb_id, full_name, throws, bats')
        .in_('mlb_id', player_ids)
        .execute()
    )
    info = {r['mlb_id']: {**r, 'eligible_positions': []} for r in rows.data}
    pos_rows = (
        sb.table('player_positions')
        .select('player_id, position')
        .in_('player_id', player_ids)
        .execute()
    )
    for r in pos_rows.data:
        if r['player_id'] in info:
            info[r['player_id']]['eligible_positions'].append(r['position'])
    return info


def fetch_roster_player_ids(team_id: str, league_id: str) -> list[int]:
    sb = get_client()
    rows = (
        sb.table('roster_players')
        .select('player_id')
        .eq('team_id', team_id)
        .eq('league_id', league_id)
        .execute()
    )
    return [r['player_id'] for r in rows.data]


def fetch_league_batter_averages(sim_date: str) -> dict | None:
    """Aggregate batting stats across all batters for this sim_date. Returns None if no rows."""
    sb = get_client()
    rows = (
        sb.table('batter_pre_lock_stats')
        .select('pa, singles, doubles, triples, hr, bb, hbp, k, go, fo')
        .eq('sim_date', sim_date)
        .execute()
    )
    if not rows.data:
        return None
    totals: dict[str, int] = {k: 0 for k in ('pa', 'singles', 'doubles', 'triples', 'hr', 'bb', 'hbp', 'k', 'go', 'fo')}
    for r in rows.data:
        for k in totals:
            totals[k] += r[k]
    return totals if totals['pa'] > 0 else None


def fetch_league_pitcher_averages(sim_date: str) -> dict | None:
    """Aggregate pitching stats across all pitchers for this sim_date. Returns None if no rows."""
    sb = get_client()
    rows = (
        sb.table('pitcher_pre_lock_stats')
        .select('bf, singles, doubles, triples, hr, bb, hbp, k, go, fo')
        .eq('sim_date', sim_date)
        .execute()
    )
    if not rows.data:
        return None
    totals: dict[str, int] = {k: 0 for k in ('bf', 'singles', 'doubles', 'triples', 'hr', 'bb', 'hbp', 'k', 'go', 'fo')}
    for r in rows.data:
        for k in totals:
            totals[k] += r[k]
    return totals if totals['bf'] > 0 else None


def mark_sim_pending(matchup_id: str) -> None:
    get_client().table('matchups').update({'sim_status': 'sim_pending'}).eq('id', matchup_id).execute()


def mark_sim_error(matchup_id: str) -> None:
    get_client().table('matchups').update({'sim_status': 'sim_error'}).eq('id', matchup_id).execute()


def write_results(
    matchup_id: str,
    events: list[dict],
    runner_outcomes: list[dict],
    batter_stats: list[dict],
    batter_positions: list[dict],
    pitcher_stats: list[dict],
    line_score: list[dict],
) -> None:
    sb = get_client()
    if events:
        sb.table('sim_events').insert(events).execute()
    if runner_outcomes:
        sb.table('sim_event_runner_outcomes').insert(runner_outcomes).execute()
    if batter_stats:
        sb.table('sim_batter_stats').insert(batter_stats).execute()
    if batter_positions:
        sb.table('sim_batter_positions').insert(batter_positions).execute()
    if pitcher_stats:
        sb.table('sim_pitcher_stats').insert(pitcher_stats).execute()
    if line_score:
        sb.table('sim_line_score').insert(line_score).execute()
    sb.table('matchups').update({'sim_status': 'sim_complete'}).eq('id', matchup_id).execute()
