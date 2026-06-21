import { Router, Request, Response } from 'express';
import { supabase } from '../lib/supabase';
import { requireAuth, AuthenticatedRequest } from '../middleware/auth';
import { computeDeadlines } from '../lib/deadlines';
import { apiError } from '../lib/errors';

export const lineupsRouter = Router();

async function getLineupWithMatchup(lineupId: string) {
  const { data: lineup } = await supabase
    .from('lineups')
    .select('id, team_id, matchup_id, sp_player_id')
    .eq('id', lineupId)
    .single();
  if (!lineup) return { lineup: null, matchup: null };

  const { data: matchup } = await supabase
    .from('matchups')
    .select('id, home_team_id, road_team_id, sim_scheduled_at, sim_status')
    .eq('id', lineup.matchup_id)
    .single();

  return { lineup, matchup };
}

// ── PATCH /lineups/:id/sp ─────────────────────────────────────────────────────

lineupsRouter.patch('/lineups/:id/sp', requireAuth, async (req: Request, res: Response) => {
  const { userId } = req as AuthenticatedRequest;
  const { id } = req.params;
  const { sp_player_id } = req.body as { sp_player_id?: unknown };

  if (typeof sp_player_id !== 'number') {
    res.status(400).json(apiError('validation_error', 'sp_player_id must be a number'));
    return;
  }

  const { lineup, matchup } = await getLineupWithMatchup(id);
  if (!lineup || !matchup) {
    res.status(404).json(apiError('not_found', 'Lineup not found'));
    return;
  }

  // Verify the requesting user manages this team
  const { data: team } = await supabase
    .from('teams')
    .select('id')
    .eq('id', lineup.team_id)
    .eq('manager_id', userId)
    .maybeSingle();
  if (!team) {
    res.status(403).json(apiError('forbidden', 'You do not manage this team'));
    return;
  }

  const deadlines = computeDeadlines(new Date(matchup.sim_scheduled_at));
  const isHome = matchup.home_team_id === lineup.team_id;
  const spDeadline = isHome ? deadlines.home_sp : deadlines.road_sp;

  if (new Date() > new Date(spDeadline)) {
    res.status(403).json(apiError('forbidden', 'SP deadline has passed'));
    return;
  }

  // Verify the player is on this team's roster and is pitcher-eligible
  const { data: rosterEntry } = await supabase
    .from('roster_players')
    .select('player_id')
    .eq('team_id', lineup.team_id)
    .eq('player_id', sp_player_id)
    .maybeSingle();
  if (!rosterEntry) {
    res.status(400).json(apiError('validation_error', 'Player is not on this team'));
    return;
  }

  const { data: pitcherPos } = await supabase
    .from('player_positions')
    .select('position')
    .eq('player_id', sp_player_id)
    .eq('position', 'P')
    .maybeSingle();
  if (!pitcherPos) {
    res.status(400).json(apiError('validation_error', 'Player is not pitcher-eligible'));
    return;
  }

  await supabase
    .from('lineups')
    .update({ sp_player_id })
    .eq('id', id);

  res.json({ id, sp_player_id, locks_at: spDeadline });
});

// ── PATCH /lineups/:id/batting-order ─────────────────────────────────────────

interface BattingOrderEntry {
  batting_position: number;
  player_id: number;
  field_position: string;
}

lineupsRouter.patch('/lineups/:id/batting-order', requireAuth, async (req: Request, res: Response) => {
  const { userId } = req as AuthenticatedRequest;
  const { id } = req.params;
  const { batting_order } = req.body as { batting_order?: unknown };

  if (!Array.isArray(batting_order) || batting_order.length === 0) {
    res.status(400).json(apiError('validation_error', 'batting_order must be a non-empty array'));
    return;
  }

  for (const entry of batting_order) {
    if (
      typeof entry !== 'object' ||
      entry === null ||
      typeof entry.batting_position !== 'number' ||
      typeof entry.player_id !== 'number' ||
      typeof entry.field_position !== 'string'
    ) {
      res.status(400).json(apiError('validation_error', 'Each batting_order entry must have batting_position, player_id, and field_position'));
      return;
    }
  }

  const entries = batting_order as BattingOrderEntry[];

  const { lineup, matchup } = await getLineupWithMatchup(id);
  if (!lineup || !matchup) {
    res.status(404).json(apiError('not_found', 'Lineup not found'));
    return;
  }

  const { data: team } = await supabase
    .from('teams')
    .select('id')
    .eq('id', lineup.team_id)
    .eq('manager_id', userId)
    .maybeSingle();
  if (!team) {
    res.status(403).json(apiError('forbidden', 'You do not manage this team'));
    return;
  }

  const deadlines = computeDeadlines(new Date(matchup.sim_scheduled_at));
  if (new Date() > new Date(deadlines.batting_order)) {
    res.status(403).json(apiError('forbidden', 'Batting order deadline has passed'));
    return;
  }

  // DH/P XOR: exactly one of DH or P must appear in field positions
  const hasDH = entries.some((e) => e.field_position === 'DH');
  const hasP = entries.some((e) => e.field_position === 'P');
  if (hasDH === hasP) {
    res.status(400).json(apiError('validation_error', 'Batting order must have either DH or P (not both, not neither)'));
    return;
  }

  // Player at P slot must be the SP
  if (hasP) {
    const pEntry = entries.find((e) => e.field_position === 'P');
    if (pEntry && pEntry.player_id !== lineup.sp_player_id) {
      res.status(400).json(apiError('validation_error', 'Player at P must be the lineup SP'));
      return;
    }
  }

  // Verify all players are on the team's roster
  const playerIds = entries.map((e) => e.player_id);
  const { data: rosterEntries } = await supabase
    .from('roster_players')
    .select('player_id')
    .eq('team_id', lineup.team_id)
    .in('player_id', playerIds);

  const onRoster = new Set((rosterEntries ?? []).map((r) => r.player_id));
  const offRoster = playerIds.filter((pid) => !onRoster.has(pid));
  if (offRoster.length > 0) {
    res.status(400).json(apiError('validation_error', `Players not on this team: ${offRoster.join(', ')}`));
    return;
  }

  // Replace batting order atomically: delete existing, insert new
  await supabase.from('lineup_batting_order').delete().eq('lineup_id', id);
  await supabase.from('lineup_batting_order').insert(
    entries.map((e) => ({
      lineup_id: id,
      batting_position: e.batting_position,
      player_id: e.player_id,
      field_position: e.field_position,
    })),
  );

  res.json({ id, batting_order: entries, locks_at: deadlines.batting_order });
});
