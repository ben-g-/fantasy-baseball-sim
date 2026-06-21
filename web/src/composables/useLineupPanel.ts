import { ref, computed, watch } from 'vue'
import type { Ref } from 'vue'
import { patchSP, patchBattingOrder, type Lineup, type Deadlines, type Player } from '../lib/api'

export interface DisplayEntry {
  field_position: string
  player_id: number
  full_name: string
}

export function useLineupPanel(
  lineupRef: Ref<Lineup | undefined>,
  isHome: Ref<boolean>,
  isMyTeam: Ref<boolean>,
  deadlinesRef: Ref<Deadlines | undefined>,
  onUpdated: () => void,
) {
  const spDeadlineIso = computed(() => {
    if (!deadlinesRef.value) return ''
    return isHome.value ? deadlinesRef.value.home_sp : deadlinesRef.value.road_sp
  })
  const spLocked = computed(() => spDeadlineIso.value !== '' && new Date() > new Date(spDeadlineIso.value))
  const boLocked = computed(() => {
    const bo = deadlinesRef.value?.batting_order
    return bo != null && new Date() > new Date(bo)
  })

  function deadlineText(iso: string): string {
    if (!iso) return ''
    const d = new Date(iso)
    if (d < new Date()) return 'Locked'
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  }

  function pitcherHand(p: Player | null | undefined): string {
    return p?.throws === 'L' ? 'LHP' : 'RHP'
  }

  // ── SP ──────────────────────────────────────────────────────────────────────

  const showSpDialog = ref(false)
  const spSaving = ref(false)
  const spError = ref('')

  const spCandidates = computed<Player[]>(() => {
    const lineup = lineupRef.value
    if (!lineup) return []
    const currentSpId = lineup.sp?.player?.mlb_id
    const inOrder = new Set(
      lineup.batting_order
        .map((e) => e.player?.mlb_id)
        .filter((id): id is number => id != null),
    )
    return lineup.bullpen
      .map((e) => e.player)
      .filter(
        (p): p is Player =>
          p !== null && p.mlb_id !== currentSpId && !inOrder.has(p.mlb_id),
      )
  })

  async function selectSP(player: Player) {
    if (!lineupRef.value) return
    spSaving.value = true
    spError.value = ''
    try {
      await patchSP(lineupRef.value.id, player.mlb_id)
      showSpDialog.value = false
      onUpdated()
    } catch (e: unknown) {
      spError.value = e instanceof Error ? e.message : 'Failed to set SP'
    } finally {
      spSaving.value = false
    }
  }

  // ── Batting order ────────────────────────────────────────────────────────────

  const boItems = ref<DisplayEntry[]>([])
  const hasBoChanges = ref(false)
  const boSaving = ref(false)
  const boError = ref('')

  function toDisplayEntries(lineup: Lineup): DisplayEntry[] {
    return lineup.batting_order
      .slice()
      .sort((a, b) => a.batting_position - b.batting_position)
      .map((e) => ({
        field_position: e.field_position,
        player_id: e.player?.mlb_id ?? 0,
        full_name: e.player?.full_name ?? '—',
      }))
  }

  watch(
    () => lineupRef.value?.batting_order,
    () => {
      if (!lineupRef.value) return
      boItems.value = toDisplayEntries(lineupRef.value)
      hasBoChanges.value = false
      boError.value = ''
    },
    { immediate: true },
  )

  const boDisplayItems = computed<DisplayEntry[]>(() => {
    if (isMyTeam.value && !boLocked.value) return boItems.value
    if (!lineupRef.value) return []
    return toDisplayEntries(lineupRef.value)
  })

  const dragIndex = ref<number | null>(null)
  const dragOverIndex = ref<number | null>(null)

  function onDragStart(index: number) { dragIndex.value = index }
  function onDragEnd() { dragIndex.value = null; dragOverIndex.value = null }
  function onDragOver(index: number) { dragOverIndex.value = index }

  function onDrop(targetIndex: number) {
    if (dragIndex.value === null || dragIndex.value === targetIndex) {
      dragIndex.value = null; dragOverIndex.value = null; return
    }
    const items = [...boItems.value]
    const [moved] = items.splice(dragIndex.value, 1)
    items.splice(targetIndex, 0, moved)
    boItems.value = items
    hasBoChanges.value = true
    dragIndex.value = null; dragOverIndex.value = null
  }

  function revertBattingOrder() {
    if (!lineupRef.value) return
    boItems.value = toDisplayEntries(lineupRef.value)
    hasBoChanges.value = false
    boError.value = ''
  }

  async function saveBattingOrder() {
    if (!lineupRef.value) return
    boSaving.value = true
    boError.value = ''
    try {
      const payload = boItems.value.map((item, i) => ({
        batting_position: i + 1,
        player_id: item.player_id,
        field_position: item.field_position,
      }))
      await patchBattingOrder(lineupRef.value.id, payload)
      hasBoChanges.value = false
      onUpdated()
    } catch (e: unknown) {
      boError.value = e instanceof Error ? e.message : 'Failed to save batting order'
    } finally {
      boSaving.value = false
    }
  }

  return {
    spDeadlineIso, spLocked, boLocked, deadlineText, pitcherHand,
    showSpDialog, spSaving, spError, spCandidates, selectSP,
    boDisplayItems, hasBoChanges, boSaving, boError,
    dragIndex, dragOverIndex, onDragStart, onDragEnd, onDragOver, onDrop,
    revertBattingOrder, saveBattingOrder,
  }
}
