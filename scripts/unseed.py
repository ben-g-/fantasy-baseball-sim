"""
Undoes everything seed.py did. Run this, then re-run seed.py.
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# Delete in dependency order.
# lineups.team_id → teams(id) has no ON DELETE CASCADE, so lineups must be
# deleted before teams. And teams.manager_id → profiles(id) has no ON DELETE
# CASCADE, so leagues (and their teams) must be deleted before bot auth users.
print('Deleting leagues...')
client.table('leagues').delete().in_('name', ['Alpha League', 'Beta League']).execute()
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
