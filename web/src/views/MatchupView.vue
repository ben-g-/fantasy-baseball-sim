<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMatchup, type Matchup } from '../lib/api'
import { useLineupPanel } from '../composables/useLineupPanel'
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

      <!-- Two-column section grid: corresponding sections are CSS siblings → same height -->
      <div v-if="panels.length === 2" class="sections-grid">

        <!-- Column headers (row 1) -->
        <div v-for="(panel, i) in panels" :key="`hdr-${i}`" class="flex align-items-center gap-2 mb-1">
          <h2 class="m-0 text-lg font-semibold">{{ panel.teamName }}</h2>
          <Tag :value="panel.isHome ? 'Home' : 'Road'" severity="secondary" style="font-size: 0.7rem;" />
          <Tag v-if="panel.isMyTeam" value="You" severity="info" style="font-size: 0.7rem;" />
        </div>

        <!-- SP cards (row 2) -->
        <div v-for="(panel, i) in panels" :key="`sp-${i}`" class="surface-card border-round p-3">
          <div class="flex align-items-center justify-content-between mb-2">
            <span class="font-semibold text-sm">Starting Pitcher</span>
            <div class="flex align-items-center gap-2">
              <span class="text-xs" :style="es[i].spLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'">
                {{ deadlineText(es[i].spDeadlineIso) }}
              </span>
              <!-- Always reserve Change button space so both SP cards have equal height -->
              <Button
                label="Change"
                size="small"
                text
                :style="panel.isMyTeam && !es[i].spLocked ? '' : 'visibility: hidden; pointer-events: none;'"
                @click="panel.isMyTeam && !es[i].spLocked ? (editors[i].showSpDialog.value = true) : undefined"
              />
            </div>
          </div>
          <div v-if="panel.lineup.sp?.player">
            <span class="font-medium">{{ panel.lineup.sp.player.full_name }}</span>
            <span class="text-color-secondary text-sm ml-2">{{ panel.lineup.sp.player.mlb_team }}</span>
            <span class="text-color-secondary text-sm ml-1">· {{ editors[i].pitcherHand(panel.lineup.sp.player) }}</span>
            <template v-if="panel.lineup.sp.player.obp_allowed != null">
              <span class="text-color-secondary text-sm ml-1">
                · OBP {{ panel.lineup.sp.player.obp_allowed.toFixed(3) }}
                / SLG {{ panel.lineup.sp.player.slg_allowed?.toFixed(3) }}
              </span>
            </template>
          </div>
          <div v-else class="text-color-secondary text-sm" style="font-style: italic;">No SP set</div>
        </div>

        <!-- Batting order cards (row 3) -->
        <div v-for="(panel, i) in panels" :key="`bo-${i}`" class="surface-card border-round p-3">
          <div class="flex align-items-center justify-content-between mb-2">
            <span class="font-semibold text-sm">Batting Order</span>
            <span class="text-xs" :style="es[i].boLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'">
              {{ deadlineText(matchup.deadlines.batting_order) }}
            </span>
          </div>

          <div class="bo-list">
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
                <span class="bo-name">{{ item.full_name }}</span>
                <span v-if="item.obp != null" class="bo-stats">
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

        <!-- Bench cards (row 4) -->
        <div v-for="(panel, i) in panels" :key="`bench-${i}`" class="surface-card border-round p-3">
          <div class="font-semibold text-sm mb-2">Bench</div>
          <div v-if="!panel.lineup.bench.length" class="text-color-secondary text-sm" style="font-style: italic;">Empty</div>
          <div
            v-for="(b, bi) in panel.lineup.bench"
            :key="bi"
            class="flex align-items-center justify-content-between py-1"
            :style="`font-size: 0.875rem;${bi > 0 ? ' border-top: 1px solid var(--p-surface-200);' : ''}`"
          >
            <span>{{ b.player?.full_name ?? '—' }}</span>
            <span class="text-color-secondary" style="font-size: 0.75rem;">{{ b.player?.display_positions.join(' / ') }}</span>
          </div>
        </div>

        <!-- Bullpen cards (row 5) -->
        <div v-for="(panel, i) in panels" :key="`bullpen-${i}`" class="surface-card border-round p-3">
          <div class="font-semibold text-sm mb-2">Bullpen</div>
          <div v-if="!panel.lineup.bullpen.length" class="text-color-secondary text-sm" style="font-style: italic;">Empty</div>
          <div
            v-for="(b, bi) in panel.lineup.bullpen"
            :key="bi"
            class="flex align-items-center justify-content-between py-1"
            :style="`font-size: 0.875rem;${bi > 0 ? ' border-top: 1px solid var(--p-surface-200);' : ''}`"
          >
            <span>{{ b.player?.full_name ?? '—' }}</span>
            <span class="text-color-secondary" style="font-size: 0.75rem;">
              {{ editors[i].pitcherHand(b.player) }}
              <template v-if="b.player?.obp_allowed != null">· OBP {{ b.player.obp_allowed.toFixed(3) }}</template>
            </span>
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
          class="border-round p-3 mb-1 surface-hover"
          style="cursor: pointer;"
          @click="!left.spSaving.value && left.selectSP(player)"
        >
          <div class="font-medium">{{ player.full_name }}</div>
          <div class="text-color-secondary text-sm">
            {{ player.mlb_team }} · {{ left.pitcherHand(player) }}
            <template v-if="player.obp_allowed != null">· OBP {{ player.obp_allowed.toFixed(3) }} / SLG {{ player.slg_allowed?.toFixed(3) }}</template>
          </div>
        </div>
      </Dialog>
    </template>
  </div>
</template>

<style scoped>
.sections-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 1.5rem;
  row-gap: 0.75rem;
  align-items: start;
}

/* ── Batting order rows ──────────────────────────────── */
.bo-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

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

.bo-name {
  font-size: 0.875rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bo-stats {
  font-size: 0.7rem;
  color: var(--p-surface-500);
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
