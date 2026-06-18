<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'

const router = useRouter()

onMounted(async () => {
  const { data: { session } } = await supabase.auth.getSession()
  router.replace(session ? '/' : '/login')
})
</script>

<template>
  <div class="flex align-items-center justify-content-center min-h-screen">
    Signing in…
  </div>
</template>
