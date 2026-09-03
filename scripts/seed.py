"""
Seed script for development. One-shot; run on a clean database after ingest_players.py.
Creates bot users, creates leagues, populates the leagues with teams, populates the teams with players,
and generates matchup schedules. Also configures 4 special matchup states for testing purposes.
Usage: python scripts/seed.py
Requires .env with
- SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
- MANAGER_EMAIL_1 and MANAGER_EMAIL_2: emails of 2 real manager accounts that already exist in the system
- BOT_PASSWORD: password to assign to the seeded bot accounts (must satisfy Supabase's password policy)
"""

import os
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import AuthError, create_client

load_dotenv()

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_ROLE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']

REAL_MANAGER_EMAILS = tuple(os.environ[v] for v in ('MANAGER_EMAIL_1', 'MANAGER_EMAIL_2'))
BOT_EMAIL_TEMPLATE = 'bot{}@fantasy-sim.dev'
BOT_COUNT = 18
BOT_PASSWORD = os.environ['BOT_PASSWORD']
OHTANI_MLB_ID = 660271
ROSTER_SIZE = 22
SEASON_WEEKS = 24


def sim_schedule(start_utc: datetime, weeks: int) -> list[datetime]:
    """Tuesdays at 03:00 UTC (= Tuesday 11 PM EDT), starting from the first Tuesday on or after start_utc."""
    days_ahead = (1 - start_utc.weekday()) % 7  # 0 if already Tuesday
    first = (start_utc + timedelta(days=days_ahead)).replace(hour=3, minute=0, second=0, microsecond=0)
    return [first + timedelta(weeks=w) for w in range(weeks)]


def round_robin(teams: list) -> list[list[tuple]]:
    """Standard round-robin schedule. Returns list of rounds; each round is list of (home, road) pairs."""
    n = len(teams)
    if n % 2 == 1:
        teams = teams + [None]
        n += 1
    fixed = teams[0]
    rotating = list(teams[1:])
    rounds = []
    for rnd in range(n - 1):
        pairs = []
        if fixed is not None and rotating[0] is not None:
            # Alternate fixed team between home and road each round
            if rnd % 2 == 0:
                pairs.append((fixed, rotating[0]))
            else:
                pairs.append((rotating[0], fixed))
        for i in range(1, n // 2):
            a, b = rotating[i], rotating[n - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b))
        rounds.append(pairs)
        rotating = [rotating[-1]] + rotating[:-1]  # rotate right by 1
    return rounds


def main() -> None:
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    now = datetime.now(timezone.utc)
    season = date.today().year

    # ── 1. Look up real managers ──────────────────────────────────────────────
    print('Looking up real managers...')
    all_users = client.auth.admin.list_users()
    manager_ids: dict[str, str] = {}
    for email in REAL_MANAGER_EMAILS:
        user = next((u for u in all_users if u.email == email), None)
        if user is None:
            raise SystemExit(f'Manager account not found: {email}. Sign up first, then run this script.')
        manager_ids[email] = user.id
    m1_id = manager_ids[REAL_MANAGER_EMAILS[0]]
    m2_id = manager_ids[REAL_MANAGER_EMAILS[1]]

    # ── 2. Create bot users ───────────────────────────────────────────────────
    print(f'Creating {BOT_COUNT} bot users...')
    bot_ids: list[str] = []
    try:
        for n in range(1, BOT_COUNT + 1):
            resp = client.auth.admin.create_user({
                'email': BOT_EMAIL_TEMPLATE.format(n),
                'password': BOT_PASSWORD,
                'email_confirm': True,
                'user_metadata': {'display_name': f'Bot {n}'},
            })
            bot_ids.append(resp.user.id)
    except AuthError as e:
        # As of 2026-09, admin.create_user doesn't actually enforce the project's password
        # policy (unlike admin.update_user/sign_up), so this branch is currently unreachable —
        # see https://github.com/supabase/auth/issues/1959. Kept for if/when that's fixed.
        if e.code == 'weak_password':
            reasons = getattr(e, 'reasons', None)
            detail = f' ({", ".join(reasons)})' if reasons else ''
            raise SystemExit(f'BOT_PASSWORD was rejected by Supabase as too weak{detail}. Set a stronger password.')
        raise

    # ── 3. Create leagues ─────────────────────────────────────────────────────
    print('Creating leagues...')
    l10 = client.table('leagues').insert({
        'name': 'Alpha League', 'commissioner_id': m1_id,
        'season_year': season, 'roster_size': ROSTER_SIZE,
    }).execute().data[0]
    l12 = client.table('leagues').insert({
        'name': 'Beta League', 'commissioner_id': m2_id,
        'season_year': season, 'roster_size': ROSTER_SIZE,
    }).execute().data[0]
    l10_id, l12_id = l10['id'], l12['id']

    # ── 4. Create teams ───────────────────────────────────────────────────────
    print('Creating teams...')
    # Alpha League (10 teams): m1, m2, bots 1–8
    # Beta League (12 teams):  m1, m2, bots 9–18
    l10_managers = [m1_id, m2_id] + bot_ids[:8]
    l12_managers = [m1_id, m2_id] + bot_ids[8:18]

    def insert_teams(league_id: str, mgr_ids: list[str]) -> list[dict]:
        rows = [{'league_id': league_id, 'manager_id': mid, 'name': f'Team {i + 1}'}
                for i, mid in enumerate(mgr_ids)]
        return client.table('teams').insert(rows).execute().data

    l10_teams = insert_teams(l10_id, l10_managers)
    l12_teams = insert_teams(l12_id, l12_managers)
    l10_tids = [t['id'] for t in l10_teams]
    l12_tids = [t['id'] for t in l12_teams]
    m1_l10_tid = l10_teams[0]['id']

    # ── 5. Assign rosters ─────────────────────────────────────────────────────
    print('Assigning rosters...')

    def fetch_all(table: str, columns: str) -> list:
        """Paginates around PostgREST's default max-rows setting, which caps a single
        request at (commonly) 1000 rows regardless of a larger client-side .limit()."""
        rows = []
        page_size = 1000
        start = 0
        while True:
            page = client.table(table).select(columns).range(start, start + page_size - 1).execute().data
            rows.extend(page)
            if len(page) < page_size:
                break
            start += page_size
        return rows

    all_player_ids: list[int] = [p['mlb_id'] for p in fetch_all('players', 'mlb_id')]
    all_player_ids.sort()

    # Fetch all position eligibility upfront — reused for both roster assignment and
    # lineup building in step 8, avoiding a second round-trip.
    pos_rows = fetch_all('player_positions', 'player_id, position')
    player_pos_map: dict[int, set[str]] = {}
    for row in pos_rows:
        player_pos_map.setdefault(row['player_id'], set()).add(row['position'])

    REQUIRED_POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'P']

    ohtani_present = OHTANI_MLB_ID in all_player_ids
    all_teams = [(l10_id, tid) for tid in l10_tids] + [(l12_id, tid) for tid in l12_tids]

    # Ohtani is pre-assigned to m1; everyone else goes into the shared pool.
    available: set[int] = set(all_player_ids)
    if ohtani_present:
        available.discard(OHTANI_MLB_ID)

    team_rosters: dict[str, list[int]] = {tid: [] for _, tid in all_teams}
    if ohtani_present:
        team_rosters[m1_l10_tid].append(OHTANI_MLB_ID)

    # Greedy core assignment: process positions scarcest-first; for each team that
    # lacks coverage at that position, pick the least-versatile eligible player so
    # that flexible players are preserved for later positions.
    pos_scarcity = sorted(
        REQUIRED_POSITIONS,
        key=lambda p: sum(1 for pid in available if p in player_pos_map.get(pid, set())),
    )
    for pos in pos_scarcity:
        for _, tid in all_teams:
            if any(pos in player_pos_map.get(pid, set()) for pid in team_rosters[tid]):
                continue  # already covered (Ohtani may cover P and an OF slot for m1)
            candidates = [pid for pid in available if pos in player_pos_map.get(pid, set())]
            if not candidates:
                raise SystemExit(
                    f'Ran out of {pos}-eligible players during roster assignment. '
                    'Run ingest_players.py first or reduce team count.'
                )
            chosen = min(candidates, key=lambda pid: len(player_pos_map.get(pid, set())))
            team_rosters[tid].append(chosen)
            available.discard(chosen)

    # Fill remaining slots from the unassigned pool (sorted for determinism).
    filler_pool = sorted(available)
    total_filler_needed = sum(ROSTER_SIZE - len(team_rosters[tid]) for _, tid in all_teams)
    if len(filler_pool) < total_filler_needed:
        raise SystemExit(
            f'Not enough remaining players: need {total_filler_needed} filler slots, '
            f'have {len(filler_pool)}. Run ingest_players.py first.'
        )
    filler_iter = iter(filler_pool)

    roster_rows: list[dict] = []
    for lid, tid in all_teams:
        filler_count = ROSTER_SIZE - len(team_rosters[tid])
        for _ in range(filler_count):
            team_rosters[tid].append(next(filler_iter))
        roster_rows.extend(
            {'team_id': tid, 'player_id': pid, 'league_id': lid}
            for pid in team_rosters[tid]
        )

    # Insert in batches of 500 to stay within API limits
    for i in range(0, len(roster_rows), 500):
        client.table('roster_players').insert(roster_rows[i:i + 500]).execute()

    # ── 6. Generate matchup schedules ─────────────────────────────────────────
    print('Generating matchup schedules...')
    times = sim_schedule(now, SEASON_WEEKS)

    def create_schedule(league_id: str, team_ids: list[str]) -> list[dict]:
        rounds = round_robin(team_ids)
        rows = []
        for w in range(SEASON_WEEKS):
            for home_tid, road_tid in rounds[w % len(rounds)]:
                rows.append({
                    'league_id': league_id,
                    'week_number': w + 1,
                    'home_team_id': home_tid,
                    'road_team_id': road_tid,
                    'sim_scheduled_at': times[w].isoformat(),
                })
        return client.table('matchups').insert(rows).execute().data

    l10_matchups = create_schedule(l10_id, l10_tids)
    l12_matchups = create_schedule(l12_id, l12_tids)

    # ── 7. Configure 4 special matchup states for manager 1 in Alpha League ──
    # Deadline offsets (from build plan):
    #   Road/home SP deadline:   sim_time − 8 days
    #   Batting order deadline:  sim_time − 7 days
    print('Configuring special matchup states...')
    m1_matchups = sorted(
        [m for m in l10_matchups
         if m['home_team_id'] == m1_l10_tid or m['road_team_id'] == m1_l10_tid],
        key=lambda m: m['week_number'],
    )[:4]

    if len(m1_matchups) < 4:
        raise SystemExit('Could not find 4 matchups for manager 1 in Alpha League.')

    # sim_scheduled_at values that put the current time in each desired state:
    #   State 1 (SP upcoming):           now + 12d → SP deadline ≈ now + 4d (future)
    #   State 2 (SP passed, BO upcoming): now + 7d 12h → SP deadline ≈ now − 12h (past),
    #                                                     BO deadline ≈ now + 12h (future)
    #   State 3 (fully locked):           now + 5d → BO deadline ≈ now − 2d (past)
    #   State 4 (post-sim):               now − 1d, sim_status = sim_complete
    special_times = [
        now + timedelta(days=12),
        now + timedelta(hours=180),   # 7.5 days
        now + timedelta(days=5),
        now - timedelta(days=1),
    ]
    for i, matchup in enumerate(m1_matchups):
        update: dict = {'sim_scheduled_at': special_times[i].isoformat()}
        if i == 3:
            update['sim_status'] = 'sim_complete'
        client.table('matchups').update(update).eq('id', matchup['id']).execute()

    # ── 8. Create lineups (with SP and batting order) for both teams in all 4 matchups ─
    # Reuse the position map fetched in step 5 — no additional DB query needed.
    eligible = player_pos_map

    def find_sp(team_id: str) -> int | None:
        pids = [r['player_id'] for r in roster_rows
                if r['team_id'] == team_id and r['league_id'] == l10_id]
        return next((pid for pid in pids if 'P' in eligible.get(pid, set())), None)

    def insert_lineup_with_batting_order(matchup_id: str, team_id: str, sp_id: int | None) -> None:
        row: dict = {'matchup_id': matchup_id, 'team_id': team_id}
        if sp_id:
            row['sp_player_id'] = sp_id
        lineup_id = client.table('lineups').insert(row).execute().data[0]['id']

        roster_pids = [r['player_id'] for r in roster_rows
                       if r['team_id'] == team_id and r['league_id'] == l10_id]
        available = set(roster_pids) - ({sp_id} if sp_id else set())

        # Greedy fill: assign most positionally restricted slots first.
        # Conventional batting order: C 1B 2B 3B SS LF CF RF P
        required = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF']
        slot: dict[str, int] = {}
        if sp_id:
            slot['P'] = sp_id

        for pos in sorted(required, key=lambda p: sum(1 for pid in available if p in eligible.get(pid, set()))):
            candidates = [pid for pid in available if pos in eligible.get(pid, set())]
            if not candidates:
                candidates = sorted(available)  # fallback: positionally ineligible but fills the slot
            chosen = candidates[0]
            slot[pos] = chosen
            available.discard(chosen)

        batting_slots = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'P']
        order_rows = [
            {'lineup_id': lineup_id, 'batting_position': i + 1,
             'player_id': slot[pos], 'field_position': pos}
            for i, pos in enumerate(batting_slots) if pos in slot
        ]
        if order_rows:
            client.table('lineup_batting_order').insert(order_rows).execute()

    m1_sp_id = find_sp(m1_l10_tid)
    if not m1_sp_id:
        print('  Warning: no pitcher found on manager 1 roster.')

    for matchup in m1_matchups:
        opp_tid = (matchup['road_team_id'] if matchup['home_team_id'] == m1_l10_tid
                   else matchup['home_team_id'])
        insert_lineup_with_batting_order(matchup['id'], m1_l10_tid, m1_sp_id)
        insert_lineup_with_batting_order(matchup['id'], opp_tid, find_sp(opp_tid))

    # ── Summary ───────────────────────────────────────────────────────────────
    print('Done.')
    print(f'  Alpha League (10 teams): {l10_id}')
    print(f'  Beta League  (12 teams): {l12_id}')
    print(f'  Teams created: {len(l10_teams) + len(l12_teams)}')
    print(f'  Roster players inserted: {len(roster_rows)}')
    print(f'  Matchups created: {len(l10_matchups) + len(l12_matchups)}')
    print(f'  Lineups created: 8 (both teams × 4 special matchups), each with a batting order')


if __name__ == '__main__':
    main()
