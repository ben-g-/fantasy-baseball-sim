<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMatchup, type Matchup } from '../lib/api'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import LineupPanel from '../components/LineupPanel.vue'

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
  } catch (e: any) {
    errorMsg.value = e.message ?? 'Failed to load matchup'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const deadlineItems = computed(() => {
  if (!matchup.value) return []
  const { deadlines } = matchup.value
  return [
    { label: 'Road SP', iso: deadlines.road_sp },
    { label: 'Home SP', iso: deadlines.home_sp },
    { label: 'Batting order', iso: deadlines.batting_order },
  ]
})

function deadlineText(iso: string): string {
  const d = new Date(iso)
  if (d < new Date()) return 'Locked'
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function deadlinePast(iso: string): boolean {
  return new Date(iso) < new Date()
}

function formatSimDate(iso: string) {
  return new Date(iso).toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
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
</script>

<template>
  <div style="max-width: 1100px; margin: 0 auto; padding: 1.5rem;">
    <Button
      icon="pi pi-arrow-left"
      label="Home"
      text
      severity="secondary"
      class="mb-3"
      @click="router.push('/')"
    />

    <div v-if="loading" class="text-color-secondary">Loading…</div>
    <div v-else-if="errorMsg" style="color: var(--red-500);">{{ errorMsg }}</div>

    <template v-else-if="matchup">
      <!-- Header -->
      <div
        class="flex align-items-start justify-content-between mb-2 gap-3"
        style="flex-wrap: wrap;"
      >
        <div>
          <h1 class="m-0 text-2xl font-bold">
            {{ matchup.home_team?.name }} vs. {{ matchup.road_team?.name }}
          </h1>
          <p class="mt-1 mb-0 text-color-secondary text-sm">
            Week {{ matchup.week_number }} · {{ formatSimDate(matchup.sim_scheduled_at) }}
          </p>
        </div>
        <Tag
          :severity="statusSeverity(matchup.sim_status)"
          :value="statusLabel(matchup.sim_status)"
        />
      </div>

      <!-- Deadlines -->
      <div class="flex gap-4 mb-5" style="flex-wrap: wrap;">
        <div v-for="d in deadlineItems" :key="d.label" class="text-sm">
          <span class="text-color-secondary">{{ d.label }}: </span>
          <span
            :style="
              deadlinePast(d.iso) ? 'color: var(--red-400);' : 'color: var(--green-500);'
            "
          >
            {{ deadlineText(d.iso) }}
          </span>
        </div>
      </div>

      <!-- Two-column lineup grid -->
      <div
        style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem;"
      >
        <LineupPanel
          v-if="matchup.home_lineup && matchup.home_team"
          :lineup="matchup.home_lineup"
          :team-name="matchup.home_team.name"
          :is-home="true"
          :is-my-team="matchup.my_team_id === matchup.home_team.id"
          :deadlines="matchup.deadlines"
          @updated="load"
        />

        <LineupPanel
          v-if="matchup.road_lineup && matchup.road_team"
          :lineup="matchup.road_lineup"
          :team-name="matchup.road_team.name"
          :is-home="false"
          :is-my-team="matchup.my_team_id === matchup.road_team.id"
          :deadlines="matchup.deadlines"
          @updated="load"
        />
      </div>
    </template>
  </div>
</template>
