<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMatchup, type Matchup, type Player } from '../lib/api'
import { useLineupPanel, splitsStats } from '../composables/useLineupPanel'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'

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

// ── Player display helpers ───────────────────────────────────────────────────
// Line 2: "PHI · LHP" for pitchers, "PHI · L" for batters
function playerDetail(player: Player | null | undefined): string {
  if (!player) return ''
  const isPitcher = player.obp_allowed != null
  const descriptor = isPitcher ? (player.throws === 'L' ? 'LHP' : 'RHP') : player.bats
  return [player.mlb_team, descriptor].filter(Boolean).join(' · ')
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
    spLocked:      left.spLocked.value,
    boLocked:      left.boLocked.value,
    spDeadlineIso: left.spDeadlineIso.value,
    boDisplayItems: left.boDisplayItems.value,
    hasBoChanges:  left.hasBoChanges.value,
    boError:       left.boError.value,
    boSaving:      left.boSaving.value,
    dragIndex:     left.dragIndex.value,
    dragOverIndex: left.dragOverIndex.value,
  },
  {
    spLocked:      right.spLocked.value,
    boLocked:      right.boLocked.value,
    spDeadlineIso: right.spDeadlineIso.value,
    boDisplayItems: right.boDisplayItems.value,
    hasBoChanges:  right.hasBoChanges.value,
    boError:       right.boError.value,
    boSaving:      right.boSaving.value,
    dragIndex:     right.dragIndex.value,
    dragOverIndex: right.dragOverIndex.value,
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

          <!-- Section 2: SP + Bullpen side-by-side -->
          <div class="tc-section">
            <div class="pitcher-section">

              <!-- SP -->
              <div style="flex: 1; min-width: 0;">
                <div class="sp-header mb-2">
                  <span class="section-label">Starting Pitcher</span>
                  <div class="flex align-items-center gap-1">
                    <span class="text-xs" :style="es[i].spLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'">
                      {{ deadlineText(es[i].spDeadlineIso) }}
                    </span>
                    <Button
                      label="Change"
                      size="small"
                      text
                      :style="panel.isMyTeam && !es[i].spLocked ? '' : 'visibility: hidden; pointer-events: none;'"
                      @click="panel.isMyTeam && !es[i].spLocked ? (editors[i].showSpDialog.value = true) : undefined"
                    />
                  </div>
                </div>
                <div v-if="panel.lineup.sp?.player" class="player-card">
                  <span class="player-name">{{ panel.lineup.sp.player.full_name }}</span>
                  <span class="player-detail">{{ playerDetail(panel.lineup.sp.player) }}</span>
                  <span v-if="playerStats(panel.lineup.sp.player)" class="player-detail">{{ playerStats(panel.lineup.sp.player) }}</span>
                </div>
                <div v-else class="player-card">
                  <span class="player-name" style="font-style: italic; color: var(--p-surface-400);">No SP set</span>
                </div>
              </div>

              <!-- Bullpen -->
              <div style="flex: 1; min-width: 0;">
                <div class="section-label mb-2">Bullpen</div>
                <div v-if="!panel.lineup.bullpen.length" class="text-color-secondary text-sm" style="font-style: italic;">Empty</div>
                <div class="player-list">
                  <div v-for="(b, bi) in panel.lineup.bullpen" :key="bi" class="player-card">
                    <span class="player-name">{{ b.player?.full_name ?? '—' }}</span>
                    <span class="player-detail">{{ playerDetail(b.player) }}</span>
                    <span v-if="playerStats(b.player)" class="player-detail">{{ playerStats(b.player) }}</span>
                  </div>
                </div>
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
                <span class="bo-pos">{{ item.field_position }}</span>
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

          <!-- Section 4: Bench -->
          <div class="tc-section">
            <div class="section-label mb-2">Bench</div>
            <div v-if="!panel.lineup.bench.length" class="text-color-secondary text-sm" style="font-style: italic;">Empty</div>
            <div class="player-list">
              <div v-for="(b, bi) in panel.lineup.bench" :key="bi" class="player-card">
                <span class="player-name">{{ b.player?.full_name ?? '—' }}</span>
                <span class="player-detail">{{ playerDetail(b.player) }}</span>
                <span v-if="playerStats(b.player)" class="player-detail">{{ playerStats(b.player) }}</span>
              </div>
            </div>
          </div>

        </div>

      </div>

      <!-- SP selection dialog (only ever needed for the user's team = panels[0] = left editor) -->
      <Dialog v-model:visible="left.showSpDialog.value" header="Select Starting Pitcher" :style="{ width: '360px' }" modal>
        <p v-if="left.spError.value" class="mt-0 text-sm" style="color: var(--red-500);">{{ left.spError.value }}</p>
        <p v-if="!left.spCandidates.value.length" class="text-color-secondary text-sm mt-0">No pitcher-eligible players available.</p>
        <div
          v-for="player in left.spCandidates.value"
          :key="player.mlb_id"
          class="player-card mb-1"
          style="cursor: pointer;"
          @click="!left.spSaving.value && left.selectSP(player)"
        >
          <span class="player-name">{{ player.full_name }}</span>
          <span class="player-detail">{{ playerDetail(player) }}</span>
          <span v-if="playerStats(player)" class="player-detail">{{ playerStats(player) }}</span>
        </div>
      </Dialog>
    </template>
  </div>
</template>

<style scoped>
/* 4 named row tracks — one per section. team-card subgrid cells align to these tracks,
   so corresponding sections (pitchers, batting order, bench) are always the same height. */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(4, auto);
  column-gap: 1.5rem;
}

/* Span all 4 rows; subgrid means the card's 4 direct children use the parent's row tracks */
.team-card {
  grid-row: 1 / 5;
  display: grid;
  grid-template-rows: subgrid;
  overflow: hidden; /* clips content to border-round radius */
}

.tc-section {
  padding: 0.75rem;
}

.tc-section + .tc-section {
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

/* ── Pitcher section (SP + Bullpen side-by-side) ────── */
.pitcher-section {
  display: flex;
  gap: 0.75rem;
  align-items: start;
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
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.player-detail {
  font-size: 0.7rem;
  color: var(--p-surface-500);
}

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
</style>
