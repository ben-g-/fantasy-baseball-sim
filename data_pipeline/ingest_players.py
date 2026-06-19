"""
Ingest active MLB players and their eligible positions from the MLB Stats API.
Run weekly as a Render cron job.
"""
import os
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_ROLE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']

MLB_API_BASE = 'https://statsapi.mlb.com/api/v1'
BATCH_SIZE = 500

# Minimum games at a position in the current season to qualify as eligible there.
MIN_GAMES_FOR_ELIGIBILITY = 10

# Maps MLB Stats API position abbreviations to field_position enum values.
# One abbreviation can map to multiple fantasy positions (e.g. OF → LF/CF/RF).
POSITION_MAP: dict[str, list[str]] = {
    'P':   ['P'],
    'SP':  ['P'],
    'RP':  ['P'],
    'TWP': ['P'],
    'C':   ['C'],
    '1B':  ['1B'],
    '2B':  ['2B'],
    'SS':  ['SS'],
    '3B':  ['3B'],
    'LF':  ['LF'],
    'CF':  ['CF'],
    'RF':  ['RF'],
    'OF':  ['LF', 'CF', 'RF'],
    'IF':  ['1B', '2B', 'SS', '3B'],
    'DH':  ['DH'],
}

BATTER_POSITIONS = {'C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF', 'DH'}


def fetch_team_abbreviations(session: requests.Session, season: int) -> dict[int, str]:
    """Returns a mapping of team id → abbreviation for all MLB teams."""
    r = session.get(
        f'{MLB_API_BASE}/teams',
        params={'sportId': 1, 'season': season},
        timeout=30,
    )
    r.raise_for_status()
    return {t['id']: t.get('abbreviation', t.get('name', 'UNK')) for t in r.json().get('teams', [])}


def fetch_active_players(session: requests.Session, season: int) -> list[dict]:
    r = session.get(
        f'{MLB_API_BASE}/sports/1/players',
        params={'season': season, 'gameType': 'R'},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get('people', [])


def fetch_fielding_positions(session: requests.Session, season: int) -> dict[int, set[str]]:
    """Returns mlb_id → set of fantasy positions earned via fielding stats this season."""
    r = session.get(
        f'{MLB_API_BASE}/stats',
        params={
            'stats': 'season',
            'group': 'fielding',
            'season': season,
            'sportId': 1,
            'playerPool': 'All',  # all players, as opposed to only statistically qualified ones
            'limit': 5000,
        },
        timeout=30,
    )
    r.raise_for_status()

    positions_by_player: dict[int, set[str]] = {}
    for entry in r.json().get('stats', []):
        all_splits = entry.get('splits', []) + entry.get('splitsTiedWithLimit', [])
        for split in all_splits:
            player_id = split.get('player', {}).get('id')
            pos_abbrev = split.get('position', {}).get('abbreviation', '')
            games = split.get('stat', {}).get('gamesPlayed', 0)
            if not player_id or games < MIN_GAMES_FOR_ELIGIBILITY:
                continue
            for pos in POSITION_MAP.get(pos_abbrev, []):
                positions_by_player.setdefault(player_id, set()).add(pos)
    return positions_by_player


def main() -> None:
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    season = date.today().year
    now = datetime.now(timezone.utc).isoformat()

    with requests.Session() as http:
        print(f'Fetching team abbreviations for {season}...')
        team_abbreviations = fetch_team_abbreviations(http, season)

        print(f'Fetching active players for {season}...')
        people = fetch_active_players(http, season)
        print(f'Fetched {len(people)} players.')

        print('Fetching fielding stats...')
        fielding_positions = fetch_fielding_positions(http, season)
        print(f'Fetched fielding data for {len(fielding_positions)} players.')

    player_rows: list[dict] = []
    position_rows: list[dict] = []

    for p in people:
        mlb_id = p.get('id')
        throws = p.get('pitchHand', {}).get('code', '')
        bats = p.get('batSide', {}).get('code', '')

        if not mlb_id or throws not in ('L', 'R') or bats not in ('L', 'R', 'S'):
            continue

        team_id = p.get('currentTeam', {}).get('id')
        mlb_team = team_abbreviations.get(team_id) if team_id else None

        player_rows.append({
            'mlb_id':     mlb_id,
            'full_name':  p.get('fullName', ''),
            'last_name':  p.get('lastName', ''),
            'throws':     throws,
            'bats':       bats,
            'mlb_team':   mlb_team,
            'updated_at': now,
        })

        # Union of primary position and any additional positions from fielding stats.
        primary_abbrev = p.get('primaryPosition', {}).get('abbreviation', '')
        all_positions = set(POSITION_MAP.get(primary_abbrev, [])) | fielding_positions.get(mlb_id, set())

        for pos in all_positions:
            position_rows.append({'player_id': mlb_id, 'position': pos, 'source': 'api'})

        # Derived DH for all batter-eligible players who don't already have DH from the API.
        if any(pos in BATTER_POSITIONS for pos in all_positions) and 'DH' not in all_positions:
            position_rows.append({'player_id': mlb_id, 'position': 'DH', 'source': 'derived'})

    print(f'Upserting {len(player_rows)} players...')
    for i in range(0, len(player_rows), BATCH_SIZE):
        client.table('players').upsert(player_rows[i:i + BATCH_SIZE]).execute()

    print(f'Upserting {len(position_rows)} positions...')
    for i in range(0, len(position_rows), BATCH_SIZE):
        client.table('player_positions').upsert(position_rows[i:i + BATCH_SIZE]).execute()

    print('Done.')


if __name__ == '__main__':
    main()
