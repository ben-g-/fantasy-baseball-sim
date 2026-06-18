import { createRouter, createWebHistory } from 'vue-router'
import { supabase } from '../lib/supabase'
import LoginView from '../views/LoginView.vue'
import SignUpView from '../views/SignUpView.vue'
import HomeView from '../views/HomeView.vue'
import AuthCallbackView from '../views/AuthCallbackView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: HomeView, meta: { requiresAuth: true } },
    { path: '/login', component: LoginView },
    { path: '/signup', component: SignUpView },
    { path: '/auth/callback', component: AuthCallbackView },
  ],
})

router.beforeEach(async (to) => {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  const isAuthenticated = !!session

  if (to.meta.requiresAuth && !isAuthenticated) {
    return '/login'
  }
  if ((to.path === '/login' || to.path === '/signup') && isAuthenticated) {
    return '/'
  }
})

export default router
