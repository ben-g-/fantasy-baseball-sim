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

  try {
    const simResp = await fetch(`${simUrl}/sim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ matchup_id: id }),
    });
    const body = await simResp.json().catch(() => null);
    if (!simResp.ok) {
      res.status(502).json({ error: 'Sim service error', details: body ?? `HTTP ${simResp.status}` });
      return;
    }
    res.json(body);
  } catch (err) {
    res.status(502).json({ error: 'Sim service error', details: String(err) });
  }
});

// POST /api/v1/dev/matchups/:id/seed-lineups
// Creates empty lineup records for both teams in a matchup (dev only).
// Populates each batting order with up to 9 batters from each team's roster.
devRouter.post('/dev/matchups/:id/seed-lineups', async (req: Request, res: Response) => {
  const { id } = req.params;

  const { data: matchup } = await supabase
    .from('matchups')
    .select('id, home_team_id, road_team_id, league_id')
    .eq('id', id)
    .single();

  if (!matchup) { res.status(404).json({ error: 'Matchup not found' }); return; }

  // Delete any existing lineups for idempotency
  await supabase.from('lineups').delete().eq('matchup_id', id);

  // Fetch rosters for both teams
  const { data: rosterRows } = await supabase
    .from('roster_players')
    .select('team_id, player_id')
    .in('team_id', [matchup.home_team_id, matchup.road_team_id]);

  const { data: posRows } = await supabase
    .from('player_positions')
    .select('player_id, position')
    .in('player_id', (rosterRows ?? []).map(r => r.player_id));

  const posMap: Record<number, string[]> = {};
  for (const r of posRows ?? []) (posMap[r.player_id] ??= []).push(r.position);

  const batters = (teamId: string) =>
    (rosterRows ?? [])
      .filter(r => r.team_id === teamId && (posMap[r.player_id] ?? []).some(p => p !== 'P'))
      .map(r => r.player_id)
      .slice(0, 9);
  const pitchers = (teamId: string) =>
    (rosterRows ?? [])
      .filter(r => r.team_id === teamId && (posMap[r.player_id] ?? []).includes('P'))
      .map(r => r.player_id);

  const results = [];
  for (const [teamId, isHome] of [[matchup.home_team_id, true], [matchup.road_team_id, false]] as [string, boolean][]) {
    const batterIds = batters(teamId);
    const pitcherIds = pitchers(teamId);
    const spId = pitcherIds[0] ?? null;

    const { data: lineup } = await supabase
      .from('lineups')
      .insert({ matchup_id: id, team_id: teamId, sp_player_id: spId })
      .select('id')
      .single();

    if (lineup && batterIds.length > 0) {
      const useP = spId != null && batterIds.length === 9;
      const order = batterIds.map((pid, i) => ({
        lineup_id: lineup.id,
        batting_position: i + 1,
        player_id: pid,
        field_position: useP && pid === spId ? 'P' : (i === 8 ? 'DH' : ['C','1B','2B','SS','3B','LF','CF','RF','DH'][i]),
      }));
      await supabase.from('lineup_batting_order').insert(order);
    }

    results.push({ team_id: teamId, is_home: isHome, lineup_id: lineup?.id });
  }

  res.json({ matchup_id: id, lineups: results });
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
