import cron from 'node-cron';
import { supabase } from './supabase';

const SIM_SERVICE_URL = process.env.SIM_SERVICE_URL ?? 'http://sim:8000';

async function dispatchDueMatchups(): Promise<void> {
  const now = new Date().toISOString();

  const { data: due } = await supabase
    .from('matchups')
    .select('id')
    .eq('sim_status', 'scheduled')
    .lte('sim_scheduled_at', now);

  if (!due?.length) return;

  for (const matchup of due) {
    try {
      const resp = await fetch(`${SIM_SERVICE_URL}/sim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matchup_id: matchup.id }),
      });
      if (!resp.ok) {
        console.error(`Sim dispatch failed for ${matchup.id}: HTTP ${resp.status}`);
      } else {
        console.log(`Sim dispatched for matchup ${matchup.id}`);
      }
    } catch (err) {
      console.error(`Sim dispatch error for ${matchup.id}:`, err);
    }
  }
}

export function startSimDispatcher(): void {
  // Check every minute
  cron.schedule('* * * * *', () => {
    dispatchDueMatchups().catch((err) => console.error('dispatchDueMatchups error:', err));
  });
  console.log('Sim dispatcher started');
}
