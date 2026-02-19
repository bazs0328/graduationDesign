<template>
  <div class="min-h-screen flex items-center justify-center bg-background p-4">
    <div class="w-full max-w-md space-y-8">
      <div class="text-center">
        <div class="inline-flex w-12 h-12 bg-primary rounded-xl items-center justify-center text-primary-foreground font-bold text-xl mb-4">G</div>
        <h1 class="text-2xl font-bold tracking-tight">GradTutor</h1>
        <p class="text-muted-foreground mt-1">登录或注册以继续</p>
      </div>

      <div class="bg-card border border-border rounded-2xl p-8 shadow-sm">
        <div class="flex rounded-lg bg-muted p-1 mb-6">
          <button
            type="button"
            class="flex-1 py-2 text-sm font-medium rounded-md transition-colors"
            :class="isLogin ? 'bg-background text-foreground shadow' : 'text-muted-foreground hover:text-foreground'"
            @click="isLogin = true"
          >
            登录
          </button>
          <button
            type="button"
            class="flex-1 py-2 text-sm font-medium rounded-md transition-colors"
            :class="!isLogin ? 'bg-background text-foreground shadow' : 'text-muted-foreground hover:text-foreground'"
            @click="isLogin = false"
          >
            注册
          </button>
        </div>

        <form @submit.prevent="submit" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-foreground mb-1">用户名</label>
            <input
              v-model="username"
              type="text"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
              placeholder="3–32 个字符"
              autocomplete="username"
            />
            <p v-if="errors.username" class="mt-1 text-sm text-destructive">{{ errors.username }}</p>
          </div>

          <div>
            <label class="block text-sm font-medium text-foreground mb-1">密码</label>
            <input
              v-model="password"
              type="password"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
              placeholder="至少 6 个字符"
              autocomplete="current-password"
            />
            <p v-if="errors.password" class="mt-1 text-sm text-destructive">{{ errors.password }}</p>
          </div>

          <div v-if="!isLogin">
            <label class="block text-sm font-medium text-foreground mb-1">确认密码</label>
            <input
              v-model="passwordConfirm"
              type="password"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
              placeholder="再次输入密码"
              autocomplete="new-password"
            />
            <p v-if="errors.passwordConfirm" class="mt-1 text-sm text-destructive">{{ errors.passwordConfirm }}</p>
          </div>

          <div v-if="!isLogin">
            <label class="block text-sm font-medium text-foreground mb-1">昵称（可选）</label>
            <input
              v-model="name"
              type="text"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
              placeholder="显示名称"
            />
          </div>

          <p v-if="errorMessage" class="text-sm text-destructive">{{ errorMessage }}</p>

          <Button
            type="submit"
            size="lg"
            class="w-full"
            :loading="loading"
          >
            {{ loading ? '处理中…' : (isLogin ? '登录' : '注册') }}
          </Button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { authRegister, authLogin } from '../api'
import Button from '../components/ui/Button.vue'

const router = useRouter()
const isLogin = ref(true)
const username = ref('')
const password = ref('')
const passwordConfirm = ref('')
const name = ref('')
const loading = ref(false)
const errorMessage = ref('')
const errors = reactive({ username: '', password: '', passwordConfirm: '' })

function validate() {
  errors.username = ''
  errors.password = ''
  errors.passwordConfirm = ''
  const u = username.value.trim()
  if (!u) {
    errors.username = '请输入用户名'
    return false
  }
  if (u.length < 3 || u.length > 32) {
    errors.username = '用户名需 3–32 个字符'
    return false
  }
  if (password.value.length < 6) {
    errors.password = '密码至少 6 个字符'
    return false
  }
  if (!isLogin.value && password.value !== passwordConfirm.value) {
    errors.passwordConfirm = '两次密码不一致'
    return false
  }
  return true
}

async function submit() {
  errorMessage.value = ''
  if (!validate()) return
  loading.value = true
  try {
    const res = isLogin.value
      ? await authLogin(username.value.trim(), password.value)
      : await authRegister(username.value.trim(), password.value, name.value.trim() || null)
    localStorage.setItem('gradtutor_user_id', res.user_id)
    localStorage.setItem('gradtutor_username', res.username)
    localStorage.setItem('gradtutor_name', res.name || '')
    localStorage.setItem('gradtutor_user', res.user_id)
    router.push('/')
  } catch (err) {
    if (err?.name === 'AbortError') {
      errorMessage.value = '连接超时，请检查后端服务是否已启动（默认 http://localhost:8000）'
    } else if (err?.message === 'Failed to fetch' || err?.name === 'TypeError') {
      errorMessage.value = '无法连接后端，请检查服务是否已启动'
    } else {
      errorMessage.value = err?.message || '操作失败，请重试'
    }
  } finally {
    loading.value = false
  }
}
</script>
