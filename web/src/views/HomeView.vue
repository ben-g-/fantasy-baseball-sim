<script setup lang="ts">
import { useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'
import Button from 'primevue/button'

const router = useRouter()

async function signOut() {
  await supabase.auth.signOut()
  router.push('/login')
}
</script>

<template>
  <div class="p-4">
    <div class="flex align-items-center justify-content-between mb-4">
      <h1 class="m-0">Home</h1>
      <Button label="Sign out" severity="secondary" outlined @click="signOut" />
    </div>
    <p class="text-color-secondary">League and matchup views coming in a later phase.</p>
  </div>
</template>
