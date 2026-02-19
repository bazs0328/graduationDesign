<template>
  <Teleport v-if="fullscreen" to="body">
    <div
      v-if="show"
      class="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm"
    >
      <LoadingSpinner size="lg" :message="message" vertical />
    </div>
  </Teleport>

  <div
    v-else-if="show"
    class="absolute inset-0 z-10 flex items-center justify-center bg-background/80 backdrop-blur-sm rounded-xl"
  >
    <LoadingSpinner size="lg" :message="message" vertical />
  </div>
</template>

<script setup>
import LoadingSpinner from './LoadingSpinner.vue'

defineProps({
  show: {
    type: Boolean,
    default: false
  },
  message: {
    type: String,
    default: ''
  },
  fullscreen: {
    type: Boolean,
    default: false
  }
})
</script>
