<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'
import { getMatchup, getMatchupResults, type Matchup, type SimResults, type Player } from '../lib/api'
import { useLineupPanel, splitsStats } from '../composables/useLineupPanel'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'

const route = useRoute()
const router = useRouter()
const matchupId = route.params.id as string

const matchup = ref<Matchup | null>(null)
const loading = ref(true)
const errorMsg = ref('')
const results = ref<SimResults | null>(null)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    matchup.value = await getMatchup(matchupId)
    if (matchup.value.sim_status === 'sim_complete') {
      results.value = await getMatchupResults(matchupId)
    }
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : 'Failed to load matchup'
  } finally {
    loading.value = false
  }
}

let _realtimeCh: ReturnType<typeof supabase.channel> | null = null

onMounted(() => {
  load()
  _realtimeCh = supabase
    .channel(`matchup-sim-${matchupId}`)
    .on(
      'postgres_changes',
      { event: 'UPDATE', schema: 'public', table: 'matchups', filter: `id=eq.${matchupId}` },
      (payload) => {
        const newStatus = (payload.new as Record<string, unknown>)?.sim_status as string | undefined
        if (newStatus === 'sim_complete' || newStatus === 'sim_error') load()
      },
    )
    .subscribe((status, err) => {
      if (err) console.error('Realtime error:', err)
      else console.log('Realtime status:', status)
    })
})

onUnmounted(() => {
  if (_realtimeCh) supabase.removeChannel(_realtimeCh)
})

// panels[0] = user's team (or home if no user team), panels[1] = opponent
const panels = computed(() => {
  if (!matchup.value) return []
  const m = matchup.value
  const home = { lineup: m.home_lineup, teamName: m.home_team?.name ?? '', isHome: true,  isMyTeam: m.my_team_id === m.home_team?.id }
  const road = { lineup: m.road_lineup, teamName: m.road_team?.name ?? '', isHome: false, isMyTeam: m.my_team_id === m.road_team?.id }
  return road.isMyTeam ? [road, home] : [home, road]
})



function deadlineText(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (d < new Date()) return 'Locked'
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function formatSimDate(iso: string) {
  return new Date(iso).toLocaleString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  })
}

function statusSeverity(status: string): 'info' | 'success' | 'warn' | 'danger' | 'secondary' {
  if (status === 'scheduled')    return 'info'
  if (status === 'sim_pending')  return 'warn'
  if (status === 'sim_complete') return 'success'
  if (status === 'sim_error')    return 'danger'
  return 'secondary'
}

function statusLabel(status: string) {
  if (status === 'scheduled')    return 'Upcoming'
  if (status === 'sim_pending')  return 'Simulating'
  if (status === 'sim_complete') return 'Final'
  if (status === 'sim_error')    return 'Error'
  return status
}

// ── Tooltip helpers ──────────────────────────────────────────────────────────
// TODO: disabled case should read "Started Week X — unavailable" once recent-start
// history is available in the composable.
function startTooltip(
  player: Player | null | undefined,
  candidateIds: Set<number>,
  currentSpName: string | undefined,
): string {
  if (!player) return ''
  if (candidateIds.has(player.mlb_id)) {
    return `Start ${player.full_name} instead of ${currentSpName ?? 'current SP'}`
  }
  return 'Not eligible to start'
}

// ── Sorting helpers ──────────────────────────────────────────────────────────
function sortedByLastName<T extends { player: { last_name: string; full_name: string } | null }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const opts: Intl.CollatorOptions = { sensitivity: 'base' }
    const last = (a.player?.last_name ?? '').localeCompare(b.player?.last_name ?? '', 'en', opts)
    if (last !== 0) return last
    return (a.player?.full_name ?? '').localeCompare(b.player?.full_name ?? '', 'en', opts)
  })
}

// ── Player display helpers ───────────────────────────────────────────────────
// Line 2: "PHI · LHP" for pitchers, "PHI · L" for batters
function playerDetail(player: Player | null | undefined): string {
  if (!player) return ''
  const isPitcher = player.obp_allowed != null
  const descriptor = isPitcher ? player.throws : player.bats
  return [player.mlb_team, descriptor].filter(Boolean).join(' · ')
}

const POSITION_ORDER = ['C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF', 'DH']

function benchDetail(player: Player | null | undefined): string {
  if (!player) return ''
  const sorted = [...player.display_positions].sort((a, b) => {
    const ai = POSITION_ORDER.indexOf(a)
    const bi = POSITION_ORDER.indexOf(b)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
  const base = playerDetail(player)
  return sorted.length ? `${base} · ${sorted.join(' ')}` : base
}

// Line 3: OBP / SLG — pitcher allowed stats or batter splits
function playerStats(player: Player | null | undefined): string | null {
  if (!player) return null
  if (player.obp_allowed != null) {
    return `OBP ${player.obp_allowed.toFixed(3)} / SLG ${player.slg_allowed?.toFixed(3) ?? '—'}`
  }
  const s = player.vs_rhp ?? player.vs_lhp
  if (!s) return null
  const { obp, slg } = splitsStats(s)
  return `OBP ${obp.toFixed(3)} / SLG ${slg.toFixed(3)}`
}

// Per-panel composables — panels[0] is always the user's team (left column)
const leftLineup   = computed(() => panels.value[0]?.lineup)
const rightLineup  = computed(() => panels.value[1]?.lineup)
const leftIsHome   = computed(() => panels.value[0]?.isHome   ?? false)
const rightIsHome  = computed(() => panels.value[1]?.isHome   ?? false)
const leftIsMyTeam  = computed(() => panels.value[0]?.isMyTeam ?? false)
const rightIsMyTeam = computed(() => panels.value[1]?.isMyTeam ?? false)
const deadlines    = computed(() => matchup.value?.deadlines)

const left  = useLineupPanel(leftLineup,  leftIsHome,  leftIsMyTeam,  deadlines, load)
const right = useLineupPanel(rightLineup, rightIsHome, rightIsMyTeam, deadlines, load)

// Static function array (doesn't need reactivity — functions are stable references)
const editors = [left, right]

// ── Results helpers ──────────────────────────────────────────────────────────

function formatIP(outs: number): string {
  return `${Math.floor(outs / 3)}.${outs % 3}`
}

const lineScoreInnings = computed(() => {
  if (!results.value) return 9
  return Math.max(results.value.line_score.home.length, results.value.line_score.road.length, 9)
})

const pbpGroups = computed(() => {
  if (!results.value) return []
  const events = results.value.play_by_play
    .filter((e) => e.description)
    .slice()
    .sort((a, b) => a.sequence_number - b.sequence_number)
  type Group = { label: string; inning: number; half: string; runsScored: number; events: typeof events }
  const groups: Group[] = []
  for (const ev of events) {
    const key = `${ev.inning}-${ev.half}`
    let g = groups.find((x) => `${x.inning}-${x.half}` === key)
    if (!g) {
      const n = ev.inning
      const sfx = n === 1 ? 'st' : n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'
      g = { label: `${ev.half === 'top' ? 'Top' : 'Bot'} ${n}${sfx}`, inning: n, half: ev.half, runsScored: 0, events: [] }
      groups.push(g)
    }
    g.events.push(ev)
    g.runsScored += ev.runs_scored
  }
  return groups
})

function sortedBatting(rows: SimResults['box_score']['home']['batting']) {
  return [...rows].sort((a, b) =>
    a.batting_order_position !== b.batting_order_position
      ? a.batting_order_position - b.batting_order_position
      : a.sequence_within_spot - b.sequence_within_spot,
  )
}

const boxScoreSides = computed(() => [
  { key: 'road' as const, name: matchup.value?.road_team?.name ?? '' },
  { key: 'home' as const, name: matchup.value?.home_team?.name ?? '' },
])

// Flat computed for template use — Vue only auto-unwraps top-level script-setup refs;
// nested ComputedRef values inside objects must be accessed via .value, which this computed does.
const es = computed(() => [
  {
    spLocked:        left.spLocked.value,
    spDeadlineIso:   left.spDeadlineIso.value,
    spCandidateIds:  new Set(left.spCandidates.value.map((p) => p.mlb_id)),
    spSaving:        left.spSaving.value,
    spError:         left.spError.value,
    boLocked:        left.boLocked.value,
    boDisplayItems:       left.boDisplayItems.value,
    displayPitchingStaff: left.displayPitchingStaff.value,
    displayBench:         left.displayBench.value,
    spInOrder:       left.spInOrder.value,
    boConflicts:     left.boConflicts.value,
    boIsValid:       left.boIsValid.value,
    hasBoChanges:    left.hasBoChanges.value,
    boError:         left.boError.value,
    boSaving:        left.boSaving.value,
    dragIndex:       left.dragIndex.value,
    dragOverIndex:   left.dragOverIndex.value,
  },
  {
    spLocked:        right.spLocked.value,
    spDeadlineIso:   right.spDeadlineIso.value,
    spCandidateIds:  new Set(right.spCandidates.value.map((p) => p.mlb_id)),
    spSaving:        right.spSaving.value,
    spError:         right.spError.value,
    boLocked:        right.boLocked.value,
    boDisplayItems:       right.boDisplayItems.value,
    displayPitchingStaff: right.displayPitchingStaff.value,
    displayBench:         right.displayBench.value,
    spInOrder:       right.spInOrder.value,
    boConflicts:     right.boConflicts.value,
    boIsValid:       right.boIsValid.value,
    hasBoChanges:    right.hasBoChanges.value,
    boError:         right.boError.value,
    boSaving:        right.boSaving.value,
    dragIndex:       right.dragIndex.value,
    dragOverIndex:   right.dragOverIndex.value,
  },
])
</script>

<template>
  <div style="max-width: 1100px; margin: 0 auto; padding: 1.5rem;">
    <Button icon="pi pi-arrow-left" label="Home" text severity="secondary" class="mb-3" @click="router.push('/')" />

    <div v-if="loading" class="text-color-secondary">Loading…</div>
    <div v-else-if="errorMsg" style="color: var(--red-500);">{{ errorMsg }}</div>

    <template v-else-if="matchup">
      <!-- Header -->
      <div class="flex align-items-center justify-content-between mb-4 gap-3">
        <p class="m-0 text-sm text-color-secondary">Week {{ matchup.week_number }} · {{ formatSimDate(matchup.sim_scheduled_at) }}</p>
        <Tag :severity="statusSeverity(matchup.sim_status)" :value="statusLabel(matchup.sim_status)" />
      </div>

      <!-- Post-sim results view -->
      <template v-if="matchup.sim_status === 'sim_complete' && results">
        <!-- Final score -->
        <div class="sim-scoreboard mb-4">
          <div class="sim-score-row" :class="{ 'sim-score-winner': results.final_score.road > results.final_score.home }">
            <span class="sim-score-name">{{ matchup.road_team?.name }}</span>
            <span class="sim-score-val">{{ results.final_score.road }}</span>
          </div>
          <div class="sim-score-row" :class="{ 'sim-score-winner': results.final_score.home > results.final_score.road }">
            <span class="sim-score-name">{{ matchup.home_team?.name }}</span>
            <span class="sim-score-val">{{ results.final_score.home }}</span>
          </div>
        </div>

        <Tabs value="box">
          <TabList>
            <Tab value="box">Box Score</Tab>
            <Tab value="pbp">Play-by-Play</Tab>
          </TabList>
          <TabPanels>
            <TabPanel value="box">
              <!-- Line score -->
              <div class="ls-wrap mb-5">
                <table class="ls-table">
                  <thead>
                    <tr>
                      <th class="ls-name"></th>
                      <th v-for="n in lineScoreInnings" :key="n" class="ls-inn">{{ n }}</th>
                      <th class="ls-sep ls-tot">R</th>
                      <th class="ls-tot">H</th>
                      <th class="ls-tot">E</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td class="ls-name">{{ matchup.road_team?.name }}</td>
                      <td v-for="n in lineScoreInnings" :key="n" class="ls-inn">{{ results.line_score.road[n - 1] ?? '' }}</td>
                      <td class="ls-sep ls-tot">{{ results.line_score.road_totals.r }}</td>
                      <td class="ls-tot">{{ results.line_score.road_totals.h }}</td>
                      <td class="ls-tot">{{ results.line_score.road_totals.e }}</td>
                    </tr>
                    <tr>
                      <td class="ls-name">{{ matchup.home_team?.name }}</td>
                      <td v-for="n in lineScoreInnings" :key="n" class="ls-inn">{{ results.line_score.home[n - 1] ?? '' }}</td>
                      <td class="ls-sep ls-tot">{{ results.line_score.home_totals.r }}</td>
                      <td class="ls-tot">{{ results.line_score.home_totals.h }}</td>
                      <td class="ls-tot">{{ results.line_score.home_totals.e }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- Box score: road then home -->
              <template v-for="side in boxScoreSides" :key="side.key">
                <h3 class="bs-team-name">{{ side.name }}</h3>

                <p class="bs-section-label">Batting</p>
                <div class="bs-wrap mb-3">
                  <table class="bs-table">
                    <thead>
                      <tr>
                        <th class="bs-l bs-slot-col">#</th>
                        <th class="bs-l bs-player-col">Player</th>
                        <th class="bs-l bs-pos-col">Pos</th>
                        <th>AB</th><th>R</th><th>H</th><th>2B</th><th>3B</th><th>HR</th><th>RBI</th><th>BB</th><th>K</th><th>SB</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="row in sortedBatting(results.box_score[side.key].batting)"
                        :key="`${row.player.mlb_id}-${row.sequence_within_spot}`"
                        :class="{ 'bs-tr-ph': row.sequence_within_spot > 1 }"
                      >
                        <td class="bs-l bs-slot-col">{{ row.sequence_within_spot === 1 ? row.batting_order_position : '' }}</td>
                        <td class="bs-l">
                          <span :class="{ 'bs-ph-indent': row.sequence_within_spot > 1 }">{{ row.player.full_name }}</span>
                        </td>
                        <td class="bs-l bs-pos-col">{{ row.positions.join('-') }}</td>
                        <td>{{ row.ab }}</td><td>{{ row.r }}</td><td>{{ row.h }}</td>
                        <td>{{ row.doubles }}</td><td>{{ row.triples }}</td><td>{{ row.hr }}</td>
                        <td>{{ row.rbi }}</td><td>{{ row.bb }}</td><td>{{ row.k }}</td><td>{{ row.sb }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <p class="bs-section-label">Pitching</p>
                <div class="bs-wrap mb-5">
                  <table class="bs-table">
                    <thead>
                      <tr>
                        <th class="bs-l bs-player-col">Pitcher</th>
                        <th>IP</th><th>H</th><th>R</th><th>ER</th><th>BB</th><th>K</th><th>HR</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="row in [...results.box_score[side.key].pitching].sort((a, b) => a.pitching_sequence - b.pitching_sequence)"
                        :key="row.player.mlb_id"
                      >
                        <td class="bs-l">{{ row.player.full_name }}</td>
                        <td>{{ formatIP(row.outs_recorded) }}</td>
                        <td>{{ row.h }}</td><td>{{ row.r }}</td><td>{{ row.er }}</td>
                        <td>{{ row.bb }}</td><td>{{ row.k }}</td><td>{{ row.hr }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
            </TabPanel>

            <TabPanel value="pbp">
              <div v-for="group in pbpGroups" :key="`${group.inning}-${group.half}`" class="pbp-group">
                <div class="pbp-half-hdr">
                  <span>{{ group.label }}</span>
                  <span v-if="group.runsScored > 0" class="pbp-run-chip">
                    {{ group.runsScored }} run{{ group.runsScored !== 1 ? 's' : '' }}
                  </span>
                </div>
                <div v-for="ev in group.events" :key="ev.sequence_number" class="pbp-ev">{{ ev.description }}</div>
              </div>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </template>

      <!-- Pre/during-sim lineup view -->
      <template v-else>
        <!-- One card per team; subgrid aligns corresponding sections across both columns -->
        <div v-if="panels.length === 2" class="two-col">

        <template v-for="(panel, i) in panels" :key="`team-${i}`">

        <!-- Team header (above card) -->
        <div class="team-col-header" :style="`grid-column: ${i + 1}; grid-row: 1`">
          <div class="flex align-items-center gap-2">
            <h2 class="m-0 text-lg font-semibold">{{ panel.teamName }}</h2>
            <Tag :value="panel.isHome ? 'Home' : 'Road'" severity="secondary" style="font-size: 0.7rem;" />
            <Tag v-if="panel.isMyTeam" value="You" severity="info" style="font-size: 0.7rem;" />
          </div>
        </div>

        <div class="surface-card border-round team-card"
             :style="`grid-column: ${i + 1}`">

          <!-- Section 1: Starting Pitcher -->
          <div class="tc-section tc-sp">
            <div class="sp-header mb-2">
              <span class="section-label">Starting Pitcher</span>
              <span class="text-xs" :style="es[i].spLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'">
                {{ deadlineText(es[i].spDeadlineIso) }}
              </span>
            </div>
            <div v-if="panel.lineup.sp?.player" class="player-card">
              <div class="sp-info">
                <span class="player-name">{{ panel.lineup.sp.player.full_name }}</span>
                <span class="player-detail">{{ playerDetail(panel.lineup.sp.player) }}</span>
                <span v-if="playerStats(panel.lineup.sp.player)" class="player-detail">{{ playerStats(panel.lineup.sp.player) }}</span>
              </div>
              <span v-if="panel.isMyTeam && !es[i].spLocked" class="sp-change-hint">or choose a different pitcher ↓</span>
            </div>
            <div v-else class="player-card">
              <div class="sp-info">
                <span class="player-name" style="font-style: italic; color: var(--p-surface-400);">No SP set</span>
              </div>
              <span v-if="panel.isMyTeam && !es[i].spLocked" class="sp-change-hint">or choose a different pitcher ↓</span>
            </div>
          </div>

          <!-- Section 3: Pitchers -->
          <div class="tc-section tc-sm tc-bullpen">
            <div class="section-label mb-2">Pitchers</div>
            <div v-if="!es[i].displayPitchingStaff.length" class="text-color-secondary text-sm" style="font-style: italic;">Empty</div>
            <div class="player-grid">
              <div v-for="(b, bi) in sortedByLastName(es[i].displayPitchingStaff)" :key="bi" class="player-card">
                <div class="bullpen-info">
                  <span class="player-name">{{ b.player?.full_name ?? '—' }}</span>
                  <span class="player-detail">{{ playerDetail(b.player) }}</span>
                  <span v-if="playerStats(b.player)" class="player-detail">{{ playerStats(b.player) }}</span>
                </div>
                <span
                  v-if="panel.isMyTeam && !es[i].spLocked"
                  v-tooltip.top="startTooltip(b.player, es[i].spCandidateIds, panel.lineup.sp?.player?.full_name)"
                  style="display: inline-block;"
                >
                  <Button
                    label="Start"
                    size="small"
                    outlined
                    severity="warn"
                    :disabled="!b.player || !es[i].spCandidateIds.has(b.player.mlb_id) || es[i].spSaving"
                    @click="b.player && editors[i].selectSP(b.player)"
                  />
                </span>
              </div>
            </div>
          </div>

          <!-- Section 3: Batting Order -->
          <div class="tc-section">
            <div class="flex align-items-center justify-content-between mb-2">
              <span class="section-label">Batting Order</span>
              <span class="text-xs" :style="es[i].boLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'">
                {{ deadlineText(matchup.deadlines.batting_order) }}
              </span>
            </div>

            <div class="player-list">
              <div
                v-for="(item, idx) in es[i].boDisplayItems"
                :key="item.player_id"
                class="bo-row"
                :class="{ 'bo-drag-over': es[i].dragOverIndex === idx && es[i].dragIndex !== idx }"
                :draggable="panel.isMyTeam && !es[i].boLocked"
                @dragstart="panel.isMyTeam && !es[i].boLocked ? editors[i].onDragStart(idx) : undefined"
                @dragend="editors[i].onDragEnd()"
                @dragover.prevent="panel.isMyTeam && !es[i].boLocked ? editors[i].onDragOver(idx) : undefined"
                @drop.prevent="panel.isMyTeam && !es[i].boLocked ? editors[i].onDrop(idx) : undefined"
              >
                <span class="bo-grip" :style="panel.isMyTeam && !es[i].boLocked ? '' : 'visibility: hidden'">⠿</span>
                <span class="bo-num">{{ idx + 1 }}</span>
                <div class="bo-player">
                  <span class="player-name">{{ item.full_name }}</span>
                  <span class="player-detail">{{ item.mlb_team }} · {{ item.bats }}</span>
                  <span v-if="item.obp != null" class="player-detail">
                    OBP {{ item.obp.toFixed(3) }} / SLG {{ item.slg?.toFixed(3) }}
                  </span>
                </div>
                <button
                  v-if="panel.isMyTeam && !es[i].boLocked && item.field_position === 'DH' && panel.lineup.sp?.player && !es[i].spInOrder"
                  v-tooltip.top="`${item.full_name} is batting for the pitcher. To have ${panel.lineup.sp.player.full_name} bat for himself instead, click here.`"
                  class="use-sp-btn"
                  @click.stop="editors[i].useSpInstead(idx)"
                >Use pitcher instead</button>
                <select
                  v-if="panel.isMyTeam && !es[i].boLocked && item.field_position !== 'P'"
                  v-tooltip.top="es[i].boConflicts[idx]?.length ? es[i].boConflicts[idx].join(' · ') : undefined"
                  :value="item.field_position"
                  :class="['bo-pos-picker', { 'bo-pos--invalid': es[i].boConflicts[idx]?.length }]"
                  @change="editors[i].setFieldPosition(idx, ($event.target as HTMLSelectElement).value)"
                >
                  <option
                    v-if="!item.eligible_positions.includes(item.field_position)"
                    :value="item.field_position"
                  >{{ item.field_position }}</option>
                  <option v-for="pos in item.eligible_positions" :key="pos" :value="pos">{{ pos }}</option>
                </select>
                <span
                  v-else
                  v-tooltip.top="es[i].boConflicts[idx]?.length ? es[i].boConflicts[idx].join(' · ') : (item.field_position === 'P' ? 'The pitcher is batting for himself. To use a DH instead, drag a bench player onto this slot.' : undefined)"
                  :class="['bo-pos', { 'bo-pos--invalid': es[i].boConflicts[idx]?.length && item.field_position !== 'P' }]"
                >{{ item.field_position }}</span>
              </div>
            </div>

            <!-- Save / Revert bar -->
            <div
              v-if="panel.isMyTeam && !es[i].boLocked && ((es[i].hasBoChanges && !es[i].boIsValid) || es[i].boError)"
              class="flex align-items-center justify-content-between mt-3"
            >
              <span v-if="es[i].boError" class="text-sm" style="color: var(--red-500);">{{ es[i].boError }}</span>
              <div class="flex gap-2 ml-auto">
                <Button label="Revert" severity="secondary" outlined size="small"
                  :disabled="es[i].boSaving"
                  @click="editors[i].revertBattingOrder()" />
              </div>
            </div>
          </div>

          <!-- Section 5: Bench -->
          <div class="tc-section tc-sm">
            <div class="section-label mb-2">Bench</div>
            <div v-if="!es[i].displayBench.length" class="text-color-secondary text-sm" style="font-style: italic;">Empty</div>
            <div class="player-grid">
              <div
                v-for="(b, bi) in sortedByLastName(es[i].displayBench)"
                :key="bi"
                class="player-card"
                :class="{ 'player-card--draggable': panel.isMyTeam && !es[i].boLocked && !!b.player }"
                :draggable="panel.isMyTeam && !es[i].boLocked && !!b.player"
                @dragstart="panel.isMyTeam && !es[i].boLocked && b.player ? editors[i].onBenchDragStart(b.player.mlb_id) : undefined"
                @dragend="editors[i].onDragEnd()"
              >
                <div class="bench-card-inner">
                  <span class="bench-grip" :style="panel.isMyTeam && !es[i].boLocked ? '' : 'visibility: hidden'">⠿</span>
                  <div class="bench-player">
                      <span class="player-name">{{ b.player?.full_name ?? '—' }}</span>
                    <span class="player-detail">{{ benchDetail(b.player) }}</span>
                    <span v-if="playerStats(b.player)" class="player-detail">{{ playerStats(b.player) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

        </div>

        </template>

        </div>
      </template>

    </template>
  </div>
</template>

<style scoped>
/* Row 1 = team headers (outside cards); rows 2–5 = the 4 card sections.
   Subgrid aligns corresponding sections across both columns. */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(5, auto);
  column-gap: 1.5rem;
}

.team-col-header {
  padding-bottom: 0.5rem;
}

/* Span rows 2–5; subgrid means the card's 4 direct children use the parent's row tracks */
.team-card {
  grid-row: 2 / 6;
  display: grid;
  grid-template-rows: subgrid;
  overflow: hidden; /* clips content to border-round radius */
}

/* Two-column grid for bullpen and bench */
.player-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.3rem;
}

/* Bullpen cards: row layout so the Start button sits on the right */
.tc-bullpen .player-card {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
}

.bullpen-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.tc-section {
  padding: 0.75rem;
}

/* Divider only between pitchers (child 2) and batting order (child 3) */
.team-card > .tc-section:nth-child(3) {
  border-top: 1px solid var(--p-surface-200);
}

/* ── Section labels ─────────────────────────────────── */
.section-label {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--p-surface-400);
}

.tc-sp .player-card {
  flex-direction: row;
  align-items: center;
  gap: 0.75rem;
}

.sp-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.sp-change-hint {
  font-size: 0.7rem;
  color: var(--p-surface-400);
  font-style: italic;
  white-space: nowrap;
  flex-shrink: 0;
}

.sp-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem;
}

/* ── Shared player subcard ──────────────────────────── */
.player-card {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.45rem 0.625rem;
  background: var(--p-surface-50);
  border-radius: 6px;
}

.player-name {
  font-size: 0.875rem; /* batting order baseline */
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.player-detail {
  font-size: 0.7rem; /* batting order baseline */
  color: var(--p-surface-500);
}

.tc-sp .player-name  { font-size: 1.05rem; }
.tc-sp .player-detail { font-size: 0.75rem; }

.tc-sm .player-name  { font-size: 0.75rem; }
.tc-sm .player-detail { font-size: 0.65rem; }

/* ── Player list (bullpen, bench) ───────────────────── */
.player-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

/* ── Batting order rows ──────────────────────────────── */
.bo-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.625rem;
  background: var(--p-surface-50);
  border-radius: 6px;
  border: 1px solid transparent;
  transition: border-color 0.1s;
}

.bo-row[draggable='true'] { cursor: grab; }
.bo-row[draggable='true']:active { cursor: grabbing; }
.tc-sm .player-card[draggable='true'] { cursor: grab; }
.tc-sm .player-card[draggable='true']:active { cursor: grabbing; }

.bench-card-inner {
  display: flex;
  align-items: flex-start;
  gap: 0.25rem;
}

.bench-grip {
  color: var(--p-surface-400);
  font-size: 0.9rem;
  flex-shrink: 0;
  user-select: none;
  margin-top: 0.05rem;
}

.bench-player {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.bo-drag-over { border-color: var(--p-primary-color, #6366f1) !important; }

.bo-grip {
  width: 1rem;
  text-align: center;
  color: var(--p-surface-400);
  font-size: 1rem;
  flex-shrink: 0;
  user-select: none;
}

.bo-num {
  width: 1.1rem;
  text-align: right;
  color: var(--p-surface-400);
  font-size: 0.8rem;
  flex-shrink: 0;
}

.bo-player {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 0;
}

.bo-pos {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.1rem 0.35rem;
  border: 1px solid var(--p-surface-300);
  border-radius: 4px;
  color: var(--p-surface-600);
  background: #ffffff;
  font-family: monospace;
  flex-shrink: 0;
}

.use-sp-btn {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.1rem 0.35rem;
  border: 1px solid var(--p-surface-300);
  border-radius: 4px;
  color: var(--p-primary-color, #6366f1);
  background: #ffffff;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.use-sp-btn:hover { background: var(--p-surface-50); }

.bo-pos--invalid {
  border-color: var(--red-400, #f87171) !important;
  color: var(--red-500, #ef4444) !important;
  background: var(--red-50, #fff5f5) !important;
}

.bo-pos-picker {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.1rem 0.2rem;
  border: 1px solid var(--p-surface-300);
  border-radius: 4px;
  color: var(--p-surface-600);
  background: #ffffff;
  font-family: monospace;
  flex-shrink: 0;
  cursor: pointer;
}

.bo-pos-picker:focus {
  outline: 2px solid var(--p-primary-color, #6366f1);
  outline-offset: 1px;
  border-color: transparent;
}

/* ── Post-sim results ────────────────────────────────────────────────────────── */

.sim-scoreboard {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 1rem 1.25rem;
  background: var(--p-surface-50);
  border: 1px solid var(--p-surface-200);
  border-radius: 8px;
  max-width: 28rem;
}

.sim-score-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 2rem;
}

.sim-score-name {
  font-size: 0.95rem;
  font-weight: 400;
}

.sim-score-val {
  font-size: 1.6rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.sim-score-winner .sim-score-name { font-weight: 700; }
.sim-score-winner .sim-score-val  { color: var(--p-primary-color, #6366f1); }

/* ── Line score ────────────────────────────────────────────────────────────── */

.ls-wrap {
  overflow-x: auto;
  border: 1px solid var(--p-surface-200);
  border-radius: 6px;
}

.ls-table {
  border-collapse: collapse;
  font-size: 0.82rem;
  white-space: nowrap;
}

.ls-table th,
.ls-table td {
  padding: 0.45rem 0.6rem;
  text-align: center;
}

.ls-table th {
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--p-surface-400);
}

.ls-table tbody tr:first-child td {
  border-bottom: 1px solid var(--p-surface-200);
}

.ls-name {
  text-align: left !important;
  font-weight: 500;
  padding-right: 1.5rem !important;
  min-width: 8rem;
}

.ls-inn { min-width: 1.8rem; }

.ls-sep { border-left: 1px solid var(--p-surface-300) !important; }

.ls-tot { font-weight: 600; }

/* ── Box score tables ───────────────────────────────────────────────────────── */

.bs-team-name {
  font-size: 1rem;
  font-weight: 600;
  margin: 1.5rem 0 0.25rem;
}

.bs-section-label {
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--p-surface-400);
  margin: 0 0 0.35rem;
}

.bs-wrap { overflow-x: auto; }

.bs-table {
  border-collapse: collapse;
  font-size: 0.8rem;
  white-space: nowrap;
  width: 100%;
}

.bs-table th {
  text-align: right;
  padding: 0.3rem 0.5rem;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400);
  border-bottom: 1px solid var(--p-surface-200);
}

.bs-table td {
  text-align: right;
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--p-surface-100);
}

.bs-l { text-align: left !important; }

.bs-slot-col  { width: 1.8rem; color: var(--p-surface-400); }
.bs-player-col { min-width: 10rem; }
.bs-pos-col   { min-width: 3rem; color: var(--p-surface-500); font-size: 0.72rem; }

.bs-tr-ph td  { color: var(--p-surface-500); font-size: 0.75rem; }

.bs-ph-indent { padding-left: 0.75rem; display: inline-block; }

/* ── Play-by-play ───────────────────────────────────────────────────────────── */

.pbp-group { margin-bottom: 1.25rem; }

.pbp-half-hdr {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--p-surface-400);
  margin-bottom: 0.35rem;
}

.pbp-run-chip {
  background: var(--p-primary-color, #6366f1);
  color: #fff;
  font-size: 0.62rem;
  padding: 0.1rem 0.45rem;
  border-radius: 99px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
}

.pbp-ev {
  font-size: 0.85rem;
  padding: 0.3rem 0;
  border-bottom: 1px solid var(--p-surface-100);
}
</style>
