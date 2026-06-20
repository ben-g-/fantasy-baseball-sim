import { Router, Request, Response } from 'express';
import { supabase } from '../lib/supabase';

export const devRouter = Router();

// POST /api/v1/dev/matchups/:id/sim
// Immediately triggers the sim for a matchup, bypassing the cron schedule.
// Requires SIM_SERVICE_URL to be set; wired to the sim service in Phase 5.
devRouter.post('/dev/matchups/:id/sim', async (req: Request, res: Response) => {
  const { id } = req.params;
  const simUrl = process.env.SIM_SERVICE_URL;
  if (!simUrl) {
    res.status(503).json({ error: 'SIM_SERVICE_URL not configured' });
    return;
  }

  const { data: matchup, error: fetchError } = await supabase
    .from('matchups')
    .select('id, sim_status')
    .eq('id', id)
    .single();

  if (fetchError || !matchup) {
    res.status(404).json({ error: 'Matchup not found' });
    return;
  }
  if (matchup.sim_status !== 'scheduled') {
    res.status(409).json({ error: `Matchup is already in status '${matchup.sim_status}'` });
    return;
  }

  await supabase.from('matchups').update({ sim_status: 'sim_pending' }).eq('id', id);

  try {
    const simResp = await fetch(`${simUrl}/sim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ matchup_id: id }),
    });
    if (!simResp.ok) throw new Error(`Sim service returned ${simResp.status}`);
    await supabase.from('matchups').update({ sim_status: 'sim_complete' }).eq('id', id);
    res.json({ matchup_id: id, sim_status: 'sim_complete' });
  } catch (err) {
    await supabase.from('matchups').update({ sim_status: 'sim_error' }).eq('id', id);
    res.status(502).json({ error: 'Sim service error', details: String(err) });
  }
});

// POST /api/v1/dev/matchups/:id/lock
// Sets sim_scheduled_at 9 days in the past so all deadlines appear passed,
// enabling testing of locked lineup states without waiting for real time to pass.
devRouter.post('/dev/matchups/:id/lock', async (req: Request, res: Response) => {
  const { id } = req.params;
  const lockedAt = new Date(Date.now() - 9 * 24 * 60 * 60 * 1000).toISOString();

  const { data, error } = await supabase
    .from('matchups')
    .update({ sim_scheduled_at: lockedAt })
    .eq('id', id)
    .select('id, week_number, sim_scheduled_at, sim_status')
    .single();

  if (error || !data) {
    res.status(404).json({ error: 'Matchup not found' });
    return;
  }
  res.json(data);
});
