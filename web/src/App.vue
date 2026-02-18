<template>
  <router-view v-if="isLoginPage" />
  <AppLayout v-else />
  <ToastContainer />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from './layout/AppLayout.vue'
import ToastContainer from './components/ui/ToastContainer.vue'

const route = useRoute()
const isLoginPage = computed(() => route.path === '/login')
</script>
