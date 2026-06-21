<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { patchSP, patchBattingOrder, type Lineup, type Player, type Deadlines } from '../lib/api'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'

const props = defineProps<{
  lineup: Lineup
  teamName: string
  isHome: boolean
  isMyTeam: boolean
  deadlines: Deadlines
}>()

const emit = defineEmits<{ updated: [] }>()

// ── Deadline helpers ──────────────────────────────────────────────────────────

const spDeadlineIso = computed(() =>
  props.isHome ? props.deadlines.home_sp : props.deadlines.road_sp,
)
const spLocked = computed(() => new Date() > new Date(spDeadlineIso.value))
const boLocked = computed(() => new Date() > new Date(props.deadlines.batting_order))

function deadlineText(iso: string): string {
  const d = new Date(iso)
  if (d < new Date()) return 'Locked'
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

// ── SP dialog ─────────────────────────────────────────────────────────────────

const showSpDialog = ref(false)
const spSaving = ref(false)
const spError = ref('')

const spCandidates = computed<Player[]>(() => {
  const currentSpId = props.lineup.sp?.player?.mlb_id
  const inOrder = new Set(
    props.lineup.batting_order
      .map((e) => e.player?.mlb_id)
      .filter((id): id is number => id != null),
  )
  return props.lineup.bullpen
    .map((e) => e.player)
    .filter(
      (p): p is Player =>
        p !== null && p.mlb_id !== currentSpId && !inOrder.has(p.mlb_id),
    )
})

async function selectSP(player: Player) {
  spSaving.value = true
  spError.value = ''
  try {
    await patchSP(props.lineup.id, player.mlb_id)
    showSpDialog.value = false
    emit('updated')
  } catch (e: unknown) {
    spError.value = e instanceof Error ? e.message : 'Failed to set SP'
  } finally {
    spSaving.value = false
  }
}

// ── Batting order editing ─────────────────────────────────────────────────────

interface DisplayEntry {
  field_position: string
  player_id: number
  full_name: string
}

const boItems = ref<DisplayEntry[]>([])
const hasBoChanges = ref(false)
const boSaving = ref(false)
const boError = ref('')

watch(
  () => props.lineup.batting_order,
  (entries) => {
    boItems.value = entries
      .slice()
      .sort((a, b) => a.batting_position - b.batting_position)
      .map((e) => ({
        field_position: e.field_position,
        player_id: e.player?.mlb_id ?? 0,
        full_name: e.player?.full_name ?? '—',
      }))
    hasBoChanges.value = false
    boError.value = ''
  },
  { immediate: true },
)

// Unified display list — editable uses boItems, read-only converts from lineup prop
const boDisplayItems = computed<DisplayEntry[]>(() => {
  if (props.isMyTeam && !boLocked.value) return boItems.value
  return props.lineup.batting_order
    .slice()
    .sort((a, b) => a.batting_position - b.batting_position)
    .map((e) => ({
      field_position: e.field_position,
      player_id: e.player?.mlb_id ?? 0,
      full_name: e.player?.full_name ?? '—',
    }))
})

// HTML5 drag-and-drop for the editable column
const dragIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)

function onDragStart(index: number) {
  dragIndex.value = index
}

function onDragEnd() {
  dragIndex.value = null
  dragOverIndex.value = null
}

function onDragOver(index: number) {
  dragOverIndex.value = index
}

function onDrop(targetIndex: number) {
  if (dragIndex.value === null || dragIndex.value === targetIndex) {
    dragIndex.value = null
    dragOverIndex.value = null
    return
  }
  const items = [...boItems.value]
  const [moved] = items.splice(dragIndex.value, 1)
  items.splice(targetIndex, 0, moved)
  boItems.value = items
  hasBoChanges.value = true
  dragIndex.value = null
  dragOverIndex.value = null
}

function revertBattingOrder() {
  boItems.value = props.lineup.batting_order
    .slice()
    .sort((a, b) => a.batting_position - b.batting_position)
    .map((e) => ({
      field_position: e.field_position,
      player_id: e.player?.mlb_id ?? 0,
      full_name: e.player?.full_name ?? '—',
    }))
  hasBoChanges.value = false
  boError.value = ''
}

async function saveBattingOrder() {
  boSaving.value = true
  boError.value = ''
  try {
    const payload = boItems.value.map((item, i) => ({
      batting_position: i + 1,
      player_id: item.player_id,
      field_position: item.field_position,
    }))
    await patchBattingOrder(props.lineup.id, payload)
    hasBoChanges.value = false
    emit('updated')
  } catch (e: unknown) {
    boError.value = e instanceof Error ? e.message : 'Failed to save batting order'
  } finally {
    boSaving.value = false
  }
}

// ── Misc helpers ──────────────────────────────────────────────────────────────

function pitcherHand(p: Player | null): string {
  return p?.throws === 'L' ? 'LHP' : 'RHP'
}
</script>

<template>
  <div>
    <!-- Column header -->
    <div class="flex align-items-center gap-2 mb-3">
      <h2 class="m-0 text-lg font-semibold">{{ teamName }}</h2>
      <Tag :value="isHome ? 'Home' : 'Road'" severity="secondary" style="font-size: 0.7rem;" />
      <Tag v-if="isMyTeam" value="You" severity="info" style="font-size: 0.7rem;" />
    </div>

    <!-- SP card -->
    <div class="surface-card border-round p-3 mb-3">
      <div class="flex align-items-center justify-content-between mb-2">
        <span class="font-semibold text-sm">Starting Pitcher</span>
        <div class="flex align-items-center gap-2">
          <span
            class="text-xs"
            :style="spLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'"
          >
            {{ deadlineText(spDeadlineIso) }}
          </span>
          <Button
            v-if="isMyTeam && !spLocked"
            label="Change"
            size="small"
            text
            @click="showSpDialog = true"
          />
        </div>
      </div>
      <div v-if="lineup.sp?.player">
        <span class="font-medium">{{ lineup.sp.player.full_name }}</span>
        <span class="text-color-secondary text-sm ml-2">{{ lineup.sp.player.mlb_team }}</span>
        <span class="text-color-secondary text-sm ml-1">· {{ pitcherHand(lineup.sp.player) }}</span>
        <template v-if="lineup.sp.player.obp_allowed != null">
          <span class="text-color-secondary text-sm ml-1">
            · OBP {{ lineup.sp.player.obp_allowed.toFixed(3) }}
            / SLG {{ lineup.sp.player.slg_allowed?.toFixed(3) }}
          </span>
        </template>
      </div>
      <div v-else class="text-color-secondary text-sm" style="font-style: italic;">
        No SP set
      </div>
    </div>

    <!-- Batting order -->
    <div class="surface-card border-round p-3 mb-3">
      <div class="flex align-items-center justify-content-between mb-2">
        <span class="font-semibold text-sm">Batting Order</span>
        <span
          class="text-xs"
          :style="boLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'"
        >
          {{ deadlineText(deadlines.batting_order) }}
        </span>
      </div>

      <div class="bo-list">
        <div
          v-for="(item, index) in boDisplayItems"
          :key="item.player_id"
          class="bo-row"
          :class="{ 'bo-drag-over': dragOverIndex === index && dragIndex !== index }"
          :draggable="isMyTeam && !boLocked"
          @dragstart="isMyTeam && !boLocked ? onDragStart(index) : undefined"
          @dragend="onDragEnd"
          @dragover.prevent="isMyTeam && !boLocked ? onDragOver(index) : undefined"
          @drop.prevent="isMyTeam && !boLocked ? onDrop(index) : undefined"
        >
          <span class="bo-grip" :style="isMyTeam && !boLocked ? '' : 'visibility: hidden'">⠿</span>
          <span class="bo-num">{{ index + 1 }}</span>
          <span class="bo-name">{{ item.full_name }}</span>
          <span class="bo-pos">{{ item.field_position }}</span>
        </div>
      </div>

      <!-- Save / Revert bar -->
      <div
        v-if="isMyTeam && !boLocked && hasBoChanges"
        class="flex align-items-center justify-content-between mt-3"
      >
        <span v-if="boError" class="text-sm" style="color: var(--red-500);">{{ boError }}</span>
        <div class="flex gap-2 ml-auto">
          <Button
            label="Revert"
            severity="secondary"
            outlined
            size="small"
            :disabled="boSaving"
            @click="revertBattingOrder"
          />
          <Button label="Save order" size="small" :loading="boSaving" @click="saveBattingOrder" />
        </div>
      </div>
    </div>

    <!-- Bench -->
    <div class="surface-card border-round p-3 mb-3">
      <div class="font-semibold text-sm mb-2">Bench</div>
      <div v-if="!lineup.bench.length" class="text-color-secondary text-sm" style="font-style: italic;">
        Empty
      </div>
      <div
        v-for="(b, i) in lineup.bench"
        :key="i"
        class="flex align-items-center justify-content-between py-1"
        :style="`font-size: 0.875rem;${i > 0 ? ' border-top: 1px solid var(--p-surface-200);' : ''}`"
      >
        <span>{{ b.player?.full_name ?? '—' }}</span>
        <span class="text-color-secondary" style="font-size: 0.75rem;">
          {{ b.player?.display_positions.join(' / ') }}
        </span>
      </div>
    </div>

    <!-- Bullpen -->
    <div class="surface-card border-round p-3">
      <div class="font-semibold text-sm mb-2">Bullpen</div>
      <div v-if="!lineup.bullpen.length" class="text-color-secondary text-sm" style="font-style: italic;">
        Empty
      </div>
      <div
        v-for="(b, i) in lineup.bullpen"
        :key="i"
        class="flex align-items-center justify-content-between py-1"
        :style="`font-size: 0.875rem;${i > 0 ? ' border-top: 1px solid var(--p-surface-200);' : ''}`"
      >
        <span>{{ b.player?.full_name ?? '—' }}</span>
        <span class="text-color-secondary" style="font-size: 0.75rem;">
          {{ pitcherHand(b.player) }}
          <template v-if="b.player?.obp_allowed != null">
            · OBP {{ b.player.obp_allowed.toFixed(3) }}
          </template>
        </span>
      </div>
    </div>

    <!-- SP selection dialog -->
    <Dialog
      v-model:visible="showSpDialog"
      header="Select Starting Pitcher"
      :style="{ width: '360px' }"
      modal
    >
      <p v-if="spError" class="mt-0 text-sm" style="color: var(--red-500);">{{ spError }}</p>
      <p v-if="!spCandidates.length" class="text-color-secondary text-sm mt-0">
        No pitcher-eligible players available.
      </p>
      <div
        v-for="player in spCandidates"
        :key="player.mlb_id"
        class="border-round p-3 mb-1 surface-hover"
        style="cursor: pointer;"
        @click="!spSaving && selectSP(player)"
      >
        <div class="font-medium">{{ player.full_name }}</div>
        <div class="text-color-secondary text-sm">
          {{ player.mlb_team }} · {{ pitcherHand(player) }}
          <template v-if="player.obp_allowed != null">
            · OBP {{ player.obp_allowed.toFixed(3) }} / SLG {{ player.slg_allowed?.toFixed(3) }}
          </template>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<style scoped>
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

.bo-row[draggable='true'] {
  cursor: grab;
}

.bo-row[draggable='true']:active {
  cursor: grabbing;
}

.bo-drag-over {
  border-color: var(--p-primary-color, #6366f1) !important;
}

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

.bo-name {
  flex: 1;
  font-size: 0.875rem;
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
