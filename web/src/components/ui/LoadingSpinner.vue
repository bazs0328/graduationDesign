<template>
  <div
    class="flex items-center gap-2"
    :class="{ 'flex-col justify-center': vertical }"
    role="status"
    aria-live="polite"
  >
    <div
      class="rounded-full animate-spin border-current border-t-transparent"
      :class="sizeClasses[size]"
      :aria-label="message || '加载中'"
    ></div>
    <span v-if="message" class="text-muted-foreground text-sm animate-pulse">
      {{ message }}
    </span>
  </div>
</template>

<script setup>
defineProps({
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['sm', 'md', 'lg'].includes(value)
  },
  message: {
    type: String,
    default: ''
  },
  vertical: {
    type: Boolean,
    default: false
  }
})

const sizeClasses = {
  sm: 'h-4 w-4 border-2',
  md: 'h-8 w-8 border-[3px]',
  lg: 'h-12 w-12 border-4'
}
</script>
