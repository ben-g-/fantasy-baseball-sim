import { Router, Request, Response } from 'express';
import { supabase } from '../lib/supabase';
import { requireAuth, AuthenticatedRequest } from '../middleware/auth';
import { computeDeadlines } from '../lib/deadlines';
import { apiError } from '../lib/errors';
import {
  PLACEHOLDER_BATTER_STATS,
  PLACEHOLDER_PITCHER_STATS,
} from '../lib/placeholderStats';

export const matchupsRouter = Router();

// ── Helpers ──────────────────────────────────────────────────────────────────

interface PlayerRow {
  mlb_id: number;
  full_name: string;
  last_name: string;
  throws: string;
  bats: string;
  mlb_team: string;
}

async function fetchPlayerMaps(playerIds: number[]) {
  if (!playerIds.length) return { players: {} as Record<number, PlayerRow>, eligible: {} as Record<number, string[]>, display: {} as Record<number, string[]> };

  const [playersRes, positionsRes] = await Promise.all([
    supabase.from('players').select('mlb_id, full_name, last_name, throws, bats, mlb_team').in('mlb_id', playerIds),
    supabase.from('player_positions').select('player_id, position, source').in('player_id', playerIds),
  ]);

  const players: Record<number, PlayerRow> = {};
  for (const p of playersRes.data ?? []) players[p.mlb_id] = p as PlayerRow;

  const eligible: Record<number, string[]> = {};
  const display: Record<number, string[]> = {};
  for (const r of positionsRes.data ?? []) {
    (eligible[r.player_id] ??= []).push(r.position);
    if (r.source === 'api') (display[r.player_id] ??= []).push(r.position);
  }

  return { players, eligible, display };
}

function enrichPlayer(
  mlbId: number,
  players: Record<number, PlayerRow>,
  eligible: Record<number, string[]>,
  display: Record<number, string[]>,
) {
  const p = players[mlbId];
  if (!p) return null;
  const eligiblePositions = eligible[mlbId] ?? [];
  const displayPositions = display[mlbId] ?? [];
  const isPitcherEligible = eligiblePositions.includes('P');
  const isBatterEligible = eligiblePositions.some((pos) => pos !== 'P');
  return {
    mlb_id: p.mlb_id,
    full_name: p.full_name,
    last_name: p.last_name,
    throws: p.throws,
    bats: p.bats,
    mlb_team: p.mlb_team,
    eligible_positions: eligiblePositions,
    display_positions: displayPositions,
    ...(isPitcherEligible && { is_sp_eligible_this_week: true, ...PLACEHOLDER_PITCHER_STATS }),
    ...(isBatterEligible && { ...PLACEHOLDER_BATTER_STATS }),
  };
}

function buildLineup(
  lineup: { id: string; team_id: string; sp_player_id: number | null },
  isHome: boolean,
  battingOrderRows: { lineup_id: string; batting_position: number; player_id: number; field_position: string }[],
  rosterPlayerIds: number[],
  players: Record<number, PlayerRow>,
  eligible: Record<number, string[]>,
  display: Record<number, string[]>,
  deadlines: ReturnType<typeof computeDeadlines>,
) {
  const spDeadline = isHome ? deadlines.home_sp : deadlines.road_sp;
  const now = new Date();
  const spIsLocked = now > new Date(spDeadline);
  const boIsLocked = now > new Date(deadlines.batting_order);

  const order = battingOrderRows
    .filter((r) => r.lineup_id === lineup.id)
    .map((r) => ({
      batting_position: r.batting_position,
      field_position: r.field_position,
      player: enrichPlayer(r.player_id, players, eligible, display),
      is_locked: boIsLocked,
      locks_at: deadlines.batting_order,
    }));

  const inOrderPids = new Set(order.map((r) => r.player?.mlb_id).filter(Boolean) as number[]);
  const spPid = lineup.sp_player_id ?? undefined;

  const bench = rosterPlayerIds
    .filter(
      (pid) =>
        !inOrderPids.has(pid) &&
        pid !== spPid &&
        (eligible[pid] ?? []).some((pos) => pos !== 'P'),
    )
    .map((pid) => ({ player: enrichPlayer(pid, players, eligible, display) }));

  const bullpen = rosterPlayerIds
    .filter(
      (pid) =>
        (eligible[pid] ?? []).includes('P') &&
        pid !== spPid &&
        !inOrderPids.has(pid),
    )
    .map((pid) => ({ player: enrichPlayer(pid, players, eligible, display) }));

  return {
    id: lineup.id,
    sp: spPid != null
      ? {
          player: enrichPlayer(spPid, players, eligible, display),
          is_locked: spIsLocked,
          locks_at: spDeadline,
        }
      : null,
    batting_order: order,
    bench,
    bullpen,
  };
}

// ── GET /matchups/:id ─────────────────────────────────────────────────────────

matchupsRouter.get('/matchups/:id', requireAuth, async (req: Request, res: Response) => {
  const { userId } = req as AuthenticatedRequest;
  const { id } = req.params;

  const { data: matchup } = await supabase
    .from('matchups')
    .select('id, league_id, week_number, sim_scheduled_at, sim_status, home_team_id, road_team_id')
    .eq('id', id)
    .single();

  if (!matchup) {
    res.status(404).json(apiError('not_found', 'Matchup not found'));
    return;
  }

  // Verify league membership; determine which team (if any) belongs to the requester
  const { data: userTeam } = await supabase
    .from('teams')
    .select('id')
    .eq('league_id', matchup.league_id)
    .eq('manager_id', userId)
    .maybeSingle();

  if (!userTeam) {
    res.status(404).json(apiError('not_found', 'Matchup not found'));
    return;
  }

  const myTeamId =
    userTeam.id === matchup.home_team_id || userTeam.id === matchup.road_team_id
      ? userTeam.id
      : null;

  // Fetch both teams with their managers
  const { data: teams } = await supabase
    .from('teams')
    .select('id, name, manager_id')
    .in('id', [matchup.home_team_id, matchup.road_team_id]);

  const managerIds = (teams ?? []).map((t) => t.manager_id);
  const { data: profiles } = await supabase
    .from('profiles')
    .select('id, display_name')
    .in('id', managerIds);

  const profileMap = Object.fromEntries((profiles ?? []).map((p) => [p.id, p]));
  const homeTeam = teams?.find((t) => t.id === matchup.home_team_id);
  const roadTeam = teams?.find((t) => t.id === matchup.road_team_id);

  // Fetch lineups
  const { data: lineups } = await supabase
    .from('lineups')
    .select('id, team_id, sp_player_id, updated_at')
    .eq('matchup_id', id);

  const homeLineup = lineups?.find((l) => l.team_id === matchup.home_team_id);
  const roadLineup = lineups?.find((l) => l.team_id === matchup.road_team_id);

  if (!homeLineup || !roadLineup) {
    res.status(404).json(apiError('not_found', 'Lineups not found for this matchup'));
    return;
  }

  // Fetch batting orders for both lineups
  const { data: battingOrderRows } = await supabase
    .from('lineup_batting_order')
    .select('lineup_id, batting_position, player_id, field_position')
    .in('lineup_id', [homeLineup.id, roadLineup.id])
    .order('batting_position');

  // Fetch full rosters for both teams, then player data
  const { data: rosterRows } = await supabase
    .from('roster_players')
    .select('team_id, player_id')
    .eq('league_id', matchup.league_id)
    .in('team_id', [matchup.home_team_id, matchup.road_team_id]);

  const allPlayerIds = [...new Set((rosterRows ?? []).map((r) => r.player_id))];
  const { players, eligible, display } = await fetchPlayerMaps(allPlayerIds);

  const homeRoster = (rosterRows ?? []).filter((r) => r.team_id === matchup.home_team_id).map((r) => r.player_id);
  const roadRoster = (rosterRows ?? []).filter((r) => r.team_id === matchup.road_team_id).map((r) => r.player_id);

  const deadlines = computeDeadlines(new Date(matchup.sim_scheduled_at));

  res.json({
    id: matchup.id,
    week_number: matchup.week_number,
    sim_scheduled_at: matchup.sim_scheduled_at,
    sim_status: matchup.sim_status,
    my_team_id: myTeamId,
    deadlines,
    home_team: homeTeam
      ? { id: homeTeam.id, name: homeTeam.name, manager: profileMap[homeTeam.manager_id] ?? null }
      : null,
    road_team: roadTeam
      ? { id: roadTeam.id, name: roadTeam.name, manager: profileMap[roadTeam.manager_id] ?? null }
      : null,
    home_lineup: buildLineup(homeLineup, true, battingOrderRows ?? [], homeRoster, players, eligible, display, deadlines),
    road_lineup: buildLineup(roadLineup, false, battingOrderRows ?? [], roadRoster, players, eligible, display, deadlines),
  });
});

// ── GET /teams/:id/matchups ───────────────────────────────────────────────────

matchupsRouter.get('/teams/:id/matchups', requireAuth, async (req: Request, res: Response) => {
  const { userId } = req as AuthenticatedRequest;
  const { id } = req.params;

  const { data: team } = await supabase
    .from('teams')
    .select('id, league_id')
    .eq('id', id)
    .eq('manager_id', userId)
    .maybeSingle();

  if (!team) {
    res.status(404).json(apiError('not_found', 'Team not found'));
    return;
  }

  const { data: matchups } = await supabase
    .from('matchups')
    .select('id, week_number, sim_scheduled_at, sim_status, home_team_id, road_team_id')
    .eq('league_id', team.league_id)
    .or(`home_team_id.eq.${id},road_team_id.eq.${id}`)
    .order('week_number');

  if (!matchups?.length) {
    res.json([]);
    return;
  }

  const matchupIds = matchups.map((m) => m.id);

  const [allTeamsRes, lineupRows] = await Promise.all([
    supabase.from('teams').select('id, name').in('id', [
      ...new Set(matchups.flatMap((m) => [m.home_team_id, m.road_team_id])),
    ]),
    supabase.from('lineups').select('matchup_id').in('matchup_id', matchupIds),
  ]);

  const teamMap = Object.fromEntries(
    (allTeamsRes.data ?? []).map((t) => [t.id, { id: t.id, name: t.name }]),
  );

  const lineupCountMap: Record<string, number> = {};
  for (const row of lineupRows.data ?? []) {
    lineupCountMap[row.matchup_id] = (lineupCountMap[row.matchup_id] ?? 0) + 1;
  }

  res.json(
    matchups.map((m) => ({
      id: m.id,
      week_number: m.week_number,
      sim_scheduled_at: m.sim_scheduled_at,
      sim_status: m.sim_status,
      home_team: teamMap[m.home_team_id] ?? null,
      road_team: teamMap[m.road_team_id] ?? null,
      final_score: null,
      has_lineup: (lineupCountMap[m.id] ?? 0) >= 2,
    })),
  );
});
