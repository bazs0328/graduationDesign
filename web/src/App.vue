<template>
  <router-view v-if="isLoginPage" />
  <AppLayout v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from './layout/AppLayout.vue'

const route = useRoute()
const isLoginPage = computed(() => route.path === '/login')
</script>

<style>
/* Global styles can go here if needed, but we use index.css */
</style>
