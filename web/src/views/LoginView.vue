<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Message from 'primevue/message'
import Divider from 'primevue/divider'

const router = useRouter()
const email = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function signIn() {
  loading.value = true
  errorMsg.value = ''
  const { error } = await supabase.auth.signInWithPassword({
    email: email.value,
    password: password.value,
  })
  loading.value = false
  if (error) {
    errorMsg.value = error.message
  } else {
    router.push('/')
  }
}

async function signInWithGoogle() {
  await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin },
  })
}
</script>

<template>
  <div class="flex align-items-center justify-content-center min-h-screen">
    <div class="surface-card p-5 border-round shadow-2 w-full" style="max-width: 400px">
      <h1 class="text-2xl font-bold mt-0 mb-5">Sign in</h1>
      <Message v-if="errorMsg" severity="error" class="mb-4">{{ errorMsg }}</Message>
      <div class="flex flex-column gap-3">
        <div class="flex flex-column gap-1">
          <label class="font-medium">Email</label>
          <InputText v-model="email" type="email" @keyup.enter="signIn" />
        </div>
        <div class="flex flex-column gap-1">
          <label class="font-medium">Password</label>
          <Password
            v-model="password"
            :feedback="false"
            toggle-mask
            input-class="w-full"
            @keyup.enter="signIn"
          />
        </div>
        <Button label="Sign in" :loading="loading" @click="signIn" />
        <Divider align="center">or</Divider>
        <Button
          label="Sign in with Google"
          icon="pi pi-google"
          severity="secondary"
          outlined
          @click="signInWithGoogle"
        />
        <p class="text-center m-0 text-sm">
          No account? <RouterLink to="/signup">Sign up</RouterLink>
        </p>
      </div>
    </div>
  </div>
</template>
