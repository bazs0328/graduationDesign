<template>
  <div class="animate-pulse space-y-3" role="status" aria-live="polite" aria-busy="true">
    <template v-if="type === 'card'">
      <div class="h-5 w-1/3 rounded bg-accent"></div>
      <div class="space-y-2">
        <div
          v-for="index in normalizedLines"
          :key="`card-line-${index}`"
          class="h-4 rounded bg-accent/70"
          :class="index === normalizedLines ? 'w-2/3' : 'w-full'"
        ></div>
      </div>
      <div class="h-9 w-24 rounded bg-accent/60"></div>
    </template>

    <template v-else-if="type === 'list'">
      <div
        v-for="index in normalizedLines"
        :key="`list-line-${index}`"
        class="flex items-center gap-3"
      >
        <div class="h-9 w-9 rounded-lg bg-accent/70"></div>
        <div class="flex-1 space-y-2">
          <div class="h-3.5 w-2/3 rounded bg-accent/80"></div>
          <div class="h-3 w-1/3 rounded bg-accent/60"></div>
        </div>
      </div>
    </template>

    <template v-else>
      <div
        v-for="index in normalizedLines"
        :key="`text-line-${index}`"
        class="h-3.5 rounded bg-accent/70"
        :class="index === normalizedLines ? 'w-3/4' : 'w-full'"
      ></div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  lines: {
    type: Number,
    default: 3
  },
  type: {
    type: String,
    default: 'text',
    validator: (value) => ['text', 'card', 'list'].includes(value)
  }
})

const normalizedLines = computed(() => Math.max(1, Math.floor(props.lines)))
</script>
