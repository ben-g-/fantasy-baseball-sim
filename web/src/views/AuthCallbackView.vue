<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'

const router = useRouter()

onMounted(async () => {
  console.log('AuthCallbackView mounted, URL:', window.location.href)
  const { data: { session }, error } = await supabase.auth.getSession()
  console.log('getSession result:', { session, error })
  router.replace(session ? '/' : '/login')
})
</script>

<template>
  <div class="flex align-items-center justify-content-center min-h-screen">
    Signing in…
  </div>
</template>
