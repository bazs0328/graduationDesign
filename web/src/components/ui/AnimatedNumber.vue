<template>
  <span>{{ formattedValue }}</span>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  value: {
    type: Number,
    required: true
  },
  duration: {
    type: Number,
    default: 1200
  },
  decimals: {
    type: Number,
    default: 2
  }
})

const displayValue = ref(Number.isFinite(props.value) ? props.value : 0)
let rafId = null

const formattedValue = computed(() => {
  const safeValue = Number.isFinite(displayValue.value) ? displayValue.value : 0
  return safeValue.toFixed(props.decimals)
})

function animate(fromValue, toValue) {
  if (rafId) {
    cancelAnimationFrame(rafId)
  }

  const start = performance.now()
  const duration = Math.max(0, props.duration)

  const step = (now) => {
    const progress = duration === 0 ? 1 : Math.min((now - start) / duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3)
    displayValue.value = fromValue + (toValue - fromValue) * eased

    if (progress < 1) {
      rafId = requestAnimationFrame(step)
    }
  }

  rafId = requestAnimationFrame(step)
}

watch(
  () => props.value,
  (next, prev) => {
    const fromValue = Number.isFinite(prev) ? prev : 0
    const toValue = Number.isFinite(next) ? next : 0
    animate(fromValue, toValue)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (rafId) {
    cancelAnimationFrame(rafId)
  }
})
</script>
