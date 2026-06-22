<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMatchup, type Matchup, type Player } from '../lib/api'
import { useLineupPanel, splitsStats } from '../composables/useLineupPanel'
import Button from 'primevue/button'
import Tag from 'primevue/tag'

const route = useRoute()
const router = useRouter()
const matchupId = route.params.id as string

const matchup = ref<Matchup | null>(null)
const loading = ref(true)
const errorMsg = ref('')

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    matchup.value = await getMatchup(matchupId)
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : 'Failed to load matchup'
  } finally {
    loading.value = false
  }
}

onMounted(load)

// panels[0] = user's team (or home if no user team), panels[1] = opponent
const panels = computed(() => {
  if (!matchup.value) return []
  const m = matchup.value
  const home = { lineup: m.home_lineup, teamName: m.home_team?.name ?? '', isHome: true,  isMyTeam: m.my_team_id === m.home_team?.id }
  const road = { lineup: m.road_lineup, teamName: m.road_team?.name ?? '', isHome: false, isMyTeam: m.my_team_id === m.road_team?.id }
  return road.isMyTeam ? [road, home] : [home, road]
})

const title = computed(() => {
  if (!matchup.value) return ''
  const m = matchup.value
  const isMyTeamHome = m.my_team_id === m.home_team?.id
  const myName  = isMyTeamHome ? m.home_team?.name : m.road_team?.name
  const oppName = isMyTeamHome ? m.road_team?.name : m.home_team?.name
  return `${myName ?? '—'} vs. ${oppName ?? '—'}`
})

const deadlineItems = computed(() => {
  if (!matchup.value) return []
  const { deadlines } = matchup.value
  return [
    { label: 'Road SP',       iso: deadlines.road_sp },
    { label: 'Home SP',       iso: deadlines.home_sp },
    { label: 'Batting order', iso: deadlines.batting_order },
  ]
})

function deadlinePast(iso: string) { return new Date(iso) < new Date() }

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

// Flat computed for template use — Vue only auto-unwraps top-level script-setup refs;
// nested ComputedRef values inside objects must be accessed via .value, which this computed does.
const es = computed(() => [
  {
    spLocked:        left.spLocked.value,
    spDeadlineIso:   left.spDeadlineIso.value,
    spCandidateIds:  new Set(left.spCandidates.value.map((p) => p.mlb_id)),
    spSaving:        left.spSaving.value,
    boLocked:        left.boLocked.value,
    boDisplayItems:       left.boDisplayItems.value,
    displayPitchingStaff: left.displayPitchingStaff.value,
    displayBench:         left.displayBench.value,
    spInOrder:       left.spInOrder.value,
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
      <div class="flex align-items-start justify-content-between mb-2 gap-3" style="flex-wrap: wrap;">
        <div>
          <h1 class="m-0 text-2xl font-bold">{{ title }}</h1>
          <p class="mt-1 mb-0 text-color-secondary text-sm">
            Week {{ matchup.week_number }} · {{ formatSimDate(matchup.sim_scheduled_at) }}
          </p>
        </div>
        <Tag :severity="statusSeverity(matchup.sim_status)" :value="statusLabel(matchup.sim_status)" />
      </div>

      <!-- Deadlines strip -->
      <div class="flex gap-4 mb-4" style="flex-wrap: wrap;">
        <div v-for="d in deadlineItems" :key="d.label" class="text-sm">
          <span class="text-color-secondary">{{ d.label }}: </span>
          <span :style="deadlinePast(d.iso) ? 'color: var(--red-400);' : 'color: var(--green-500);'">
            {{ deadlineText(d.iso) }}
          </span>
        </div>
      </div>

      <!-- One card per team; subgrid aligns corresponding sections across both columns -->
      <div v-if="panels.length === 2" class="two-col">

        <div v-for="(panel, i) in panels" :key="`team-${i}`"
             class="surface-card border-round team-card"
             :style="`grid-column: ${i + 1}`">

          <!-- Section 1: Header -->
          <div class="tc-section">
            <div class="flex align-items-center gap-2">
              <h2 class="m-0 text-lg font-semibold">{{ panel.teamName }}</h2>
              <Tag :value="panel.isHome ? 'Home' : 'Road'" severity="secondary" style="font-size: 0.7rem;" />
              <Tag v-if="panel.isMyTeam" value="You" severity="info" style="font-size: 0.7rem;" />
            </div>
          </div>

          <!-- Section 2: Starting Pitcher -->
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
                  :value="item.field_position"
                  class="bo-pos-picker"
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
                  v-tooltip.top="item.field_position === 'P' ? 'The pitcher is batting for himself. To use a DH instead, drag a bench player onto this slot.' : undefined"
                  class="bo-pos"
                >{{ item.field_position }}</span>
              </div>
            </div>

            <!-- Save / Revert bar -->
            <div
              v-if="panel.isMyTeam && !es[i].boLocked && es[i].hasBoChanges"
              class="flex align-items-center justify-content-between mt-3"
            >
              <span v-if="es[i].boError" class="text-sm" style="color: var(--red-500);">{{ es[i].boError }}</span>
              <div class="flex gap-2 ml-auto">
                <Button label="Revert" severity="secondary" outlined size="small"
                  :disabled="es[i].boSaving"
                  @click="editors[i].revertBattingOrder()" />
                <Button label="Save order" size="small"
                  :loading="es[i].boSaving"
                  @click="editors[i].saveBattingOrder()" />
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

      </div>

    </template>
  </div>
</template>

<style scoped>
/* 5 named row tracks — one per section. team-card subgrid cells align to these tracks,
   so corresponding sections (sp, bullpen, batting order, bench) are always the same height. */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(5, auto);
  column-gap: 1.5rem;
}

/* Span all 5 rows; subgrid means the card's 5 direct children use the parent's row tracks */
.team-card {
  grid-row: 1 / 6;
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

/* Divider only between bullpen (child 3) and batting order (child 4) */
.team-card > .tc-section:nth-child(4) {
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
</style>
