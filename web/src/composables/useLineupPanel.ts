import { ref, computed, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { patchSP, patchBattingOrder, type Lineup, type Deadlines, type Player, type BatterSplits } from '../lib/api'

export interface DisplayEntry {
  field_position: string
  eligible_positions: string[] // non-pitcher positions available in the field position picker
  player_id: number
  full_name: string
  mlb_team: string
  bats: string
  obp: number | null
  slg: number | null
}

const FIELD_POSITION_ORDER = ['C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF', 'DH']

export function splitsStats(s: BatterSplits): { obp: number; slg: number } {
  const h = s.singles + s.doubles + s.triples + s.hr
  const ab = s.pa - s.bb - s.hbp
  const tb = s.singles + 2 * s.doubles + 3 * s.triples + 4 * s.hr
  return {
    obp: s.pa > 0 ? (h + s.bb + s.hbp) / s.pa : 0,
    slg: ab > 0 ? tb / ab : 0,
  }
}

function playerOBPSLG(player: Player | null | undefined): { obp: number | null; slg: number | null } {
  const splits = player?.vs_rhp ?? player?.vs_lhp ?? null
  if (!splits) return { obp: null, slg: null }
  const { obp, slg } = splitsStats(splits)
  return { obp, slg }
}

function sortedEligiblePositions(player: Player | null | undefined): string[] {
  const raw = (player?.eligible_positions ?? []).filter((p) => p !== 'P')
  return [...raw].sort((a, b) => {
    const ai = FIELD_POSITION_ORDER.indexOf(a)
    const bi = FIELD_POSITION_ORDER.indexOf(b)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
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
  const now = ref(Date.now())
  const spLocked = computed(() => spDeadlineIso.value !== '' && now.value > new Date(spDeadlineIso.value).getTime())
  const boLocked = computed(() => {
    const bo = deadlinesRef.value?.batting_order
    return bo != null && now.value > new Date(bo).getTime()
  })

  const deadlineTimers: ReturnType<typeof setTimeout>[] = []
  function scheduleTick(isoString: string | undefined) {
    if (!isoString) return
    const ms = new Date(isoString).getTime() - Date.now()
    if (ms <= 0) return
    deadlineTimers.push(setTimeout(() => { now.value = Date.now() }, ms))
  }
  watch(
    [spDeadlineIso, () => deadlinesRef.value?.batting_order],
    ([spIso, boIso]) => {
      deadlineTimers.forEach(clearTimeout)
      deadlineTimers.length = 0
      scheduleTick(spIso)
      scheduleTick(boIso)
    },
    { immediate: true },
  )

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
    const fromBullpen = lineup.bullpen
      .map((e) => e.player)
      .filter((p): p is Player => p !== null && p.mlb_id !== currentSpId)
    const fromOrder = lineup.batting_order
      .map((e) => e.player)
      .filter(
        (p): p is Player =>
          p !== null &&
          p.mlb_id !== currentSpId &&
          (p.eligible_positions ?? []).includes('P'),
      )
    return [...fromBullpen, ...fromOrder]
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
  const savedBoItems = ref<DisplayEntry[]>([])
  const hasBoChanges = ref(false)
  const boSaving = ref(false)
  const boError = ref('')

  function toDisplayEntries(lineup: Lineup): DisplayEntry[] {
    return lineup.batting_order
      .slice()
      .sort((a, b) => a.batting_position - b.batting_position)
      .map((e) => {
        const { obp, slg } = playerOBPSLG(e.player)
        return {
          field_position: e.field_position,
          eligible_positions: sortedEligiblePositions(e.player),
          player_id: e.player?.mlb_id ?? 0,
          full_name: e.player?.full_name ?? '—',
          mlb_team: e.player?.mlb_team ?? '',
          bats: e.player?.bats ?? '',
          obp,
          slg,
        }
      })
  }

  watch(
    () => lineupRef.value?.batting_order,
    () => {
      if (!lineupRef.value) return
      const entries = toDisplayEntries(lineupRef.value)
      boItems.value = entries
      savedBoItems.value = entries.map((e) => ({ ...e }))
      hasBoChanges.value = false
      boError.value = ''
    },
    { immediate: true },
  )

  const spInOrder = computed(() => {
    const spId = lineupRef.value?.sp?.player?.mlb_id
    if (spId == null) return false
    return boItems.value.some((e) => e.player_id === spId)
  })

  const boDisplayItems = computed<DisplayEntry[]>(() => {
    if (isMyTeam.value && !boLocked.value) return boItems.value
    if (!lineupRef.value) return []
    return toDisplayEntries(lineupRef.value)
  })

  const displayPitchingStaff = computed(() => {
    const lineup = lineupRef.value
    if (!lineup) return []
    const spId = lineup.sp?.player?.mlb_id
    const booPitchers = lineup.batting_order
      .filter((e) => e.player?.mlb_id !== spId && (e.player?.eligible_positions ?? []).includes('P'))
      .map((e) => ({ player: e.player }))
    return [...lineup.bullpen, ...booPitchers]
  })

  const boConflicts = computed<string[][]>(() => {
    if (!isMyTeam.value || boLocked.value) return boItems.value.map(() => [])
    const items = boItems.value
    const result: string[][] = items.map(() => [])

    const FIELDING_POSITIONS = ['C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF']
    const assignedSet = new Set(items.map((item) => item.field_position))
    const hasP = assignedSet.has('P')
    const expected = [...FIELDING_POSITIONS, hasP ? 'P' : 'DH']
    const missing = expected.filter((p) => !assignedSet.has(p))
    const missingSuffix = missing.map((p) => `missing ${p}`).join(' · ')

    const posIndices = new Map<string, number[]>()
    items.forEach((item, idx) => {
      if (item.field_position && item.field_position !== 'P') {
        const list = posIndices.get(item.field_position) ?? []
        list.push(idx)
        posIndices.set(item.field_position, list)
      }
    })
    posIndices.forEach((indices, pos) => {
      if (indices.length > 1) indices.forEach((idx) => result[idx].push(`Duplicate ${pos}`))
    })

    items.forEach((item, idx) => {
      if (
        item.field_position &&
        item.field_position !== 'P' &&
        item.eligible_positions.length > 0 &&
        !item.eligible_positions.includes(item.field_position)
      ) {
        result[idx].push(`${item.full_name} cannot play ${item.field_position}`)
      }
    })

    // P and DH cannot coexist
    if (hasP && assignedSet.has('DH')) {
      items.forEach((item, idx) => {
        if (item.field_position === 'DH') {
          result[idx].push('A DH cannot be used when the pitcher is batting for himself')
        }
      })
    }

    // Append missing positions once as a separate · -separated entry on each conflicted slot
    if (missingSuffix) {
      result.forEach((slotConflicts) => {
        if (slotConflicts.length > 0) slotConflicts.push(missingSuffix)
      })
    }

    return result
  })

  const boIsValid = computed(() => boConflicts.value.every((c) => c.length === 0))

  const displayBench = computed(() => {
    const lineup = lineupRef.value
    if (!lineup) return []
    if (!isMyTeam.value || boLocked.value) return lineup.bench
    const inOrder = new Set(boItems.value.map((e) => e.player_id))
    const spId = lineup.sp?.player?.mlb_id
    const serverBench = lineup.bench.filter((b) => !b.player || !inOrder.has(b.player.mlb_id))
    const displaced = lineup.batting_order
      .filter((e) => {
        const id = e.player?.mlb_id
        return id != null && !inOrder.has(id) && id !== spId
      })
      .map((e) => ({ player: e.player }))
    return [...serverBench, ...displaced]
  })

  const dragIndex = ref<number | null>(null)
  const dragOverIndex = ref<number | null>(null)
  const benchDragPlayerId = ref<number | null>(null)

  function onDragStart(index: number) {
    dragIndex.value = index
    benchDragPlayerId.value = null
  }

  function onBenchDragStart(playerId: number) {
    benchDragPlayerId.value = playerId
    dragIndex.value = null
  }

  function onDragEnd() {
    dragIndex.value = null
    dragOverIndex.value = null
    benchDragPlayerId.value = null
  }

  function onDragOver(index: number) { dragOverIndex.value = index }

  function dropBenchPlayer(targetIndex: number, playerId: number) {
    const lineup = lineupRef.value
    if (!lineup) return
    const player =
      lineup.bench.find((b) => b.player?.mlb_id === playerId)?.player ??
      lineup.batting_order.find((e) => e.player?.mlb_id === playerId)?.player
    if (!player) return
    const currentFieldPos = boItems.value[targetIndex].field_position
    const { obp, slg } = playerOBPSLG(player)
    boItems.value[targetIndex] = {
      field_position: currentFieldPos === 'P' ? 'DH' : currentFieldPos,
      eligible_positions: sortedEligiblePositions(player),
      player_id: player.mlb_id,
      full_name: player.full_name,
      mlb_team: player.mlb_team,
      bats: player.bats,
      obp,
      slg,
    }
    hasBoChanges.value = true
  }

  function onDrop(targetIndex: number) {
    if (benchDragPlayerId.value !== null) {
      dropBenchPlayer(targetIndex, benchDragPlayerId.value)
      benchDragPlayerId.value = null
      dragOverIndex.value = null
      return
    }
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

  function useSpInstead(idx: number) {
    const lineup = lineupRef.value
    if (!lineup?.sp?.player) return
    const sp = lineup.sp.player
    const { obp, slg } = playerOBPSLG(sp)
    boItems.value[idx] = {
      field_position: 'P',
      eligible_positions: sortedEligiblePositions(sp),
      player_id: sp.mlb_id,
      full_name: sp.full_name,
      mlb_team: sp.mlb_team,
      bats: sp.bats,
      obp,
      slg,
    }
    hasBoChanges.value = true
  }

  function setFieldPosition(idx: number, pos: string) {
    boItems.value[idx].field_position = pos
    hasBoChanges.value = true
  }

  function revertBattingOrder() {
    boItems.value = savedBoItems.value.map((e) => ({ ...e }))
    hasBoChanges.value = false
    boError.value = ''
  }

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  watch([hasBoChanges, boIsValid], ([changes, valid]) => {
    if (saveTimer !== null) clearTimeout(saveTimer)
    if (changes && valid && isMyTeam.value && !boLocked.value) {
      saveTimer = setTimeout(() => {
        saveTimer = null
        if (hasBoChanges.value && boIsValid.value && !boSaving.value) void saveBattingOrder()
      }, 500)
    }
  })
  onUnmounted(() => {
    if (saveTimer !== null) clearTimeout(saveTimer)
    deadlineTimers.forEach(clearTimeout)
  })

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
      savedBoItems.value = boItems.value.map((e) => ({ ...e }))
      hasBoChanges.value = false
    } catch (e: unknown) {
      boError.value = e instanceof Error ? e.message : 'Failed to save batting order'
    } finally {
      boSaving.value = false
    }
  }

  return {
    spDeadlineIso, spLocked, boLocked, deadlineText, pitcherHand,
    showSpDialog, spSaving, spError, spCandidates, selectSP,
    boDisplayItems, displayPitchingStaff, displayBench, spInOrder,
    boConflicts, boIsValid, hasBoChanges, boSaving, boError,
    dragIndex, dragOverIndex, onDragStart, onBenchDragStart, onDragEnd, onDragOver, onDrop,
    useSpInstead, setFieldPosition, revertBattingOrder, saveBattingOrder,
  }
}
