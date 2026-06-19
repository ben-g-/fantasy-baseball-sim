"""
Ingest active MLB players and their eligible positions from the MLB Stats API.
Run weekly as a Render cron job.
"""
import os
from datetime import date, datetime, timezone

import statsapi
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_ROLE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']

# Maps MLB Stats API position abbreviations to field_position enum values.
# One abbreviation can map to multiple fantasy positions (e.g. OF → LF/CF/RF).
POSITION_MAP: dict[str, list[str]] = {
    'P':   ['P'],
    'SP':  ['P'],
    'RP':  ['P'],
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
    'TWP': ['P'],
}

BATTER_POSITIONS = {'C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF', 'DH'}

BATCH_SIZE = 500


def fetch_active_players(season: int) -> list[dict]:
    response = statsapi.get('sports_players', {'sportId': 1, 'season': season, 'gameType': 'R'})
    return response.get('people', [])


def main() -> None:
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    season = date.today().year
    now = datetime.now(timezone.utc).isoformat()

    print(f'Fetching active players for {season}...')
    people = fetch_active_players(season)
    print(f'Fetched {len(people)} players.')

    player_rows: list[dict] = []
    position_rows: list[dict] = []

    for p in people:
        mlb_id = p.get('id')
        throws = p.get('pitchHand', {}).get('code', '')
        bats = p.get('batSide', {}).get('code', '')

        if not mlb_id or throws not in ('L', 'R') or bats not in ('L', 'R', 'S'):
            continue

        team = p.get('currentTeam', {})
        mlb_team = team.get('abbreviation') or team.get('name') or 'FA'

        player_rows.append({
            'mlb_id':     mlb_id,
            'full_name':  p.get('fullName', ''),
            'last_name':  p.get('lastName', ''),
            'throws':     throws,
            'bats':       bats,
            'mlb_team':   mlb_team,
            'updated_at': now,
        })

        abbrev = p.get('primaryPosition', {}).get('abbreviation', '')
        positions = POSITION_MAP.get(abbrev, [])

        for pos in positions:
            position_rows.append({'player_id': mlb_id, 'position': pos, 'source': 'api'})

        if any(pos in BATTER_POSITIONS for pos in positions) and 'DH' not in positions:
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
