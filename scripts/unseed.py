"""
Undoes everything seed.py did. Run this, then re-run seed.py.
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# Delete in dependency order.
# teams and matchups are both independent ON DELETE CASCADE children of
# leagues, and Postgres doesn't guarantee it cascades matchups before teams.
# sim_batter_stats/sim_pitcher_stats/sim_line_score/matchups.home_team_id
# reference teams(id) with no cascade of their own, only cleaned up
# transitively via matchups' cascade — so matchups must be deleted explicitly
# first, or a league delete can fail with a dangling teams reference.
# And teams.manager_id → profiles(id) has no ON DELETE CASCADE, so leagues
# (and their teams) must be deleted before bot auth users.
league_names = ['Alpha League', 'Beta League']

print('Deleting matchups...')
leagues = client.table('leagues').select('id').in_('name', league_names).execute()
league_ids = [row['id'] for row in leagues.data]
if league_ids:
    client.table('matchups').delete().in_('league_id', league_ids).execute()
print('  Done.')

print('Deleting leagues...')
client.table('leagues').delete().in_('name', league_names).execute()
print('  Done.')

# Now delete bot auth users (cascades to their profiles)
print('Deleting bot users...')
all_users = client.auth.admin.list_users()
deleted = 0
for user in all_users:
    if user.email and user.email.endswith('@fantasy-sim.dev'):
        client.auth.admin.delete_user(user.id)
        deleted += 1
print(f'  Deleted {deleted} bot users.')
