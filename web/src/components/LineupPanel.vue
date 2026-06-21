<script setup lang="ts">
import { ref, computed } from 'vue'
import { patchSP, patchBattingOrder, type Lineup, type Player, type Deadlines } from '../lib/api'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import OrderList from 'primevue/orderlist'

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
  } catch (e: any) {
    spError.value = e.message ?? 'Failed to set SP'
  } finally {
    spSaving.value = false
  }
}

// ── Batting order dialog ──────────────────────────────────────────────────────

interface EditEntry {
  field_position: string
  player_id: number
  full_name: string
}

const showBoDialog = ref(false)
const boItems = ref<EditEntry[]>([])
const boSaving = ref(false)
const boError = ref('')

function openBoDialog() {
  boItems.value = props.lineup.batting_order
    .slice()
    .sort((a, b) => a.batting_position - b.batting_position)
    .map((e) => ({
      field_position: e.field_position,
      player_id: e.player?.mlb_id ?? 0,
      full_name: e.player?.full_name ?? '—',
    }))
  boError.value = ''
  showBoDialog.value = true
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
    showBoDialog.value = false
    emit('updated')
  } catch (e: any) {
    boError.value = e.message ?? 'Failed to save batting order'
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
        <div class="flex align-items-center gap-2">
          <span
            class="text-xs"
            :style="boLocked ? 'color: var(--red-400);' : 'color: var(--green-500);'"
          >
            {{ deadlineText(deadlines.batting_order) }}
          </span>
          <Button
            v-if="isMyTeam && !boLocked"
            label="Edit"
            size="small"
            text
            @click="openBoDialog"
          />
        </div>
      </div>
      <table style="width: 100%; border-collapse: collapse; font-size: 0.875rem;">
        <thead>
          <tr style="color: var(--text-color-secondary); font-size: 0.75rem;">
            <th style="text-align: left; padding: 0.25rem 0.5rem 0.25rem 0; width: 2rem;">#</th>
            <th style="text-align: left; padding: 0.25rem 0.5rem; width: 3rem;">Pos</th>
            <th style="text-align: left; padding: 0.25rem 0;">Player</th>
            <th style="text-align: right; padding: 0.25rem 0; color: var(--text-color-secondary);">AVG</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in lineup.batting_order.slice().sort((a, b) => a.batting_position - b.batting_position)"
            :key="entry.batting_position"
          >
            <td style="padding: 0.25rem 0.5rem 0.25rem 0; color: var(--text-color-secondary);">
              {{ entry.batting_position }}
            </td>
            <td style="padding: 0.25rem 0.5rem; font-family: monospace; font-size: 0.75rem;">
              {{ entry.field_position }}
            </td>
            <td style="padding: 0.25rem 0;">{{ entry.player?.full_name ?? '—' }}</td>
            <td style="padding: 0.25rem 0; text-align: right; color: var(--text-color-secondary); font-size: 0.8rem;">
              <template v-if="entry.player?.vs_rhp">
                {{ ((entry.player.vs_rhp.singles + entry.player.vs_rhp.doubles + entry.player.vs_rhp.triples + entry.player.vs_rhp.hr) / (entry.player.vs_rhp.pa - entry.player.vs_rhp.bb - entry.player.vs_rhp.hbp)).toFixed(3) }}
              </template>
            </td>
          </tr>
        </tbody>
      </table>
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
        style="font-size: 0.875rem; border-bottom: 1px solid var(--surface-border);"
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
        style="font-size: 0.875rem; border-bottom: 1px solid var(--surface-border);"
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

    <!-- Batting order edit dialog -->
    <Dialog
      v-model:visible="showBoDialog"
      header="Edit Batting Order"
      :style="{ width: '400px' }"
      modal
    >
      <p class="mt-0 mb-3 text-color-secondary text-sm">
        Drag rows to reorder. Field positions move with each player.
      </p>
      <p v-if="boError" class="mt-0 text-sm" style="color: var(--red-500);">{{ boError }}</p>

      <OrderList v-model="boItems" :pt="{ container: { style: 'height: auto; border: none; padding: 0' } }">
        <template #item="{ item, index }">
          <div class="flex align-items-center gap-3 py-1">
            <span class="text-color-secondary text-sm" style="width: 1.5rem; text-align: right;">
              {{ index + 1 }}
            </span>
            <span
              style="
                font-family: monospace;
                font-size: 0.75rem;
                min-width: 2.5rem;
                text-align: center;
                background: var(--surface-200);
                border-radius: 4px;
                padding: 2px 6px;
              "
            >
              {{ item.field_position }}
            </span>
            <span class="text-sm">{{ item.full_name }}</span>
          </div>
        </template>
      </OrderList>

      <div class="flex justify-content-end gap-2 mt-4">
        <Button
          label="Cancel"
          severity="secondary"
          outlined
          size="small"
          @click="showBoDialog = false"
        />
        <Button label="Save" size="small" :loading="boSaving" @click="saveBattingOrder" />
      </div>
    </Dialog>
  </div>
</template>
