import { supabase } from './supabase'

const BASE_URL = import.meta.env.VITE_API_URL as string

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')

  const response = await fetch(`${BASE_URL}/api/v1${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
      ...(options.headers as Record<string, string>),
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? `HTTP ${response.status}`)
  }

  return response.json() as Promise<T>
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface BatterSplits {
  pa: number
  singles: number
  doubles: number
  triples: number
  hr: number
  bb: number
  hbp: number
  k: number
  go: number
  fo: number
}

export interface Player {
  mlb_id: number
  full_name: string
  last_name: string
  throws: string
  bats: string
  mlb_team: string
  eligible_positions: string[]
  display_positions: string[]
  is_sp_eligible_this_week?: boolean
  obp_allowed?: number
  slg_allowed?: number
  vs_lhp?: BatterSplits
  vs_rhp?: BatterSplits
}

export interface SpSlot {
  player: Player | null
  is_locked: boolean
  locks_at: string
}

export interface BattingOrderEntry {
  batting_position: number
  field_position: string
  player: Player | null
  is_locked: boolean
  locks_at: string
}

export interface Lineup {
  id: string
  sp: SpSlot | null
  batting_order: BattingOrderEntry[]
  bench: Array<{ player: Player | null }>
  bullpen: Array<{ player: Player | null }>
}

export interface TeamInfo {
  id: string
  name: string
  manager?: { id: string; display_name: string } | null
}

export interface Deadlines {
  road_sp: string
  home_sp: string
  batting_order: string
}

export interface Matchup {
  id: string
  week_number: number
  sim_scheduled_at: string
  sim_status: string
  my_team_id: string | null
  deadlines: Deadlines
  home_team: TeamInfo | null
  road_team: TeamInfo | null
  home_lineup: Lineup
  road_lineup: Lineup
}

export interface MatchupSummary {
  id: string
  week_number: number
  sim_scheduled_at: string
  sim_status: string
  home_team: { id: string; name: string } | null
  road_team: { id: string; name: string } | null
  final_score: { home: number; road: number } | null
  has_lineup: boolean
}

// ── Calls ─────────────────────────────────────────────────────────────────────

export function getMatchup(id: string): Promise<Matchup> {
  return apiFetch(`/matchups/${id}`)
}

export function getTeamMatchups(teamId: string): Promise<MatchupSummary[]> {
  return apiFetch(`/teams/${teamId}/matchups`)
}

export function patchSP(lineupId: string, spPlayerId: number): Promise<unknown> {
  return apiFetch(`/lineups/${lineupId}/sp`, {
    method: 'PATCH',
    body: JSON.stringify({ sp_player_id: spPlayerId }),
  })
}

export function patchBattingOrder(
  lineupId: string,
  battingOrder: Array<{ batting_position: number; player_id: number; field_position: string }>,
): Promise<unknown> {
  return apiFetch(`/lineups/${lineupId}/batting-order`, {
    method: 'PATCH',
    body: JSON.stringify({ batting_order: battingOrder }),
  })
}
