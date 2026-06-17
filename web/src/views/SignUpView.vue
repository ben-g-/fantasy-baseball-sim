<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Message from 'primevue/message'

const router = useRouter()
const email = ref('')
const password = ref('')
const username = ref('')
const displayName = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function signUp() {
  loading.value = true
  errorMsg.value = ''
  const { error } = await supabase.auth.signUp({
    email: email.value,
    password: password.value,
    options: {
      data: {
        username: username.value,
        display_name: displayName.value,
      },
    },
  })
  loading.value = false
  if (error) {
    const msg = typeof error.message === 'string' ? error.message : ''
    errorMsg.value = msg && msg !== '{}' ? msg : 'An unexpected error occurred.'
  } else {
    router.push('/login')
  }
}
</script>

<template>
  <div class="flex align-items-center justify-content-center min-h-screen">
    <div class="surface-card p-5 border-round shadow-2 w-full" style="max-width: 400px">
      <h1 class="text-2xl font-bold mt-0 mb-5">Create account</h1>
      <Message v-if="errorMsg" severity="error" class="mb-4">{{ errorMsg }}</Message>
      <div class="flex flex-column gap-3">
        <div class="flex flex-column gap-1">
          <label class="font-medium">Display name</label>
          <InputText v-model="displayName" />
        </div>
        <div class="flex flex-column gap-1">
          <label class="font-medium">Username</label>
          <InputText v-model="username" />
        </div>
        <div class="flex flex-column gap-1">
          <label class="font-medium">Email</label>
          <InputText v-model="email" type="email" />
        </div>
        <div class="flex flex-column gap-1">
          <label class="font-medium">Password</label>
          <Password v-model="password" toggle-mask input-class="w-full" />
        </div>
        <Button label="Create account" :loading="loading" @click="signUp" />
        <p class="text-center m-0 text-sm">
          Already have an account? <RouterLink to="/login">Sign in</RouterLink>
        </p>
      </div>
    </div>
  </div>
</template>
