<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'
import { getTeamMatchups, type MatchupSummary } from '../lib/api'
import Button from 'primevue/button'
import Tag from 'primevue/tag'

const router = useRouter()

interface TeamRow {
  id: string
  name: string
  league_name: string
  matchups: MatchupSummary[]
}

const teams = ref<TeamRow[]>([])
const loading = ref(true)
const errorMsg = ref('')

async function signOut() {
  await supabase.auth.signOut()
  router.push('/login')
}

function formatSimDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function statusSeverity(status: string): 'info' | 'success' | 'warn' | 'danger' | 'secondary' {
  if (status === 'scheduled') return 'info'
  if (status === 'sim_pending') return 'warn'
  if (status === 'sim_complete') return 'success'
  if (status === 'sim_error') return 'danger'
  return 'secondary'
}

function statusLabel(status: string) {
  if (status === 'scheduled') return 'Upcoming'
  if (status === 'sim_pending') return 'Simulating'
  if (status === 'sim_complete') return 'Final'
  if (status === 'sim_error') return 'Error'
  return status
}

function matchupLabel(m: MatchupSummary, myTeamId: string) {
  const isHome = m.home_team?.id === myTeamId
  const opp = isHome ? m.road_team?.name : m.home_team?.name
  const side = isHome ? 'H' : 'R'
  return `vs. ${opp ?? '—'} (${side})`
}

onMounted(async () => {
  try {
    const {
      data: { user },
    } = await supabase.auth.getUser()
    if (!user) return

    const { data: userTeams } = await supabase
      .from('teams')
      .select('id, name, leagues(name)')
      .eq('manager_id', user.id)

    if (!userTeams?.length) {
      loading.value = false
      return
    }

    const rows = await Promise.all(
      userTeams.map(async (t) => {
        const matchups = await getTeamMatchups(t.id).catch(() => [] as MatchupSummary[])
        return {
          id: t.id,
          name: t.name,
          league_name: (t.leagues as any)?.name ?? '',
          matchups,
        }
      }),
    )
    teams.value = rows
  } catch {
    errorMsg.value = 'Failed to load data.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div style="max-width: 800px; margin: 0 auto; padding: 1.5rem;">
    <div class="flex align-items-center justify-content-between mb-5">
      <h1 class="m-0 text-2xl font-bold">Fantasy Baseball</h1>
      <Button label="Sign out" severity="secondary" outlined size="small" @click="signOut" />
    </div>

    <div v-if="loading" class="text-color-secondary">Loading…</div>
    <div v-else-if="errorMsg" style="color: var(--red-500);">{{ errorMsg }}</div>
    <div v-else-if="!teams.length" class="text-color-secondary">
      You are not in any leagues yet.
    </div>

    <div v-for="team in teams" :key="team.id" class="mb-5">
      <p class="m-0 text-color-secondary text-sm">{{ team.league_name }}</p>
      <h2 class="mt-1 mb-3 text-xl font-semibold">{{ team.name }}</h2>

      <div v-if="!team.matchups.length" class="text-color-secondary text-sm">
        No matchups scheduled.
      </div>

      <div
        v-for="m in team.matchups"
        :key="m.id"
        class="surface-card border-round p-3 mb-2 flex align-items-center justify-content-between"
        style="cursor: pointer;"
        @click="router.push(`/matchups/${m.id}`)"
      >
        <div>
          <span class="font-medium">Week {{ m.week_number }}</span>
          <span class="text-color-secondary text-sm ml-2">{{ matchupLabel(m, team.id) }}</span>
        </div>
        <div class="flex align-items-center gap-2">
          <span class="text-color-secondary text-sm">{{ formatSimDate(m.sim_scheduled_at) }}</span>
          <Tag
            :severity="statusSeverity(m.sim_status)"
            :value="statusLabel(m.sim_status)"
            style="font-size: 0.75rem;"
          />
        </div>
      </div>
    </div>
  </div>
</template>
