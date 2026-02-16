<template>
  <div class="bg-card text-card-foreground rounded-xl border border-border shadow-sm overflow-hidden" :class="customClass">
    <div v-if="$slots.header" class="px-6 py-4 border-b border-border bg-card/50">
      <slot name="header"></slot>
    </div>
    <div class="p-6">
      <slot></slot>
    </div>
    <div v-if="$slots.footer" class="px-6 py-4 border-t border-border bg-card/50">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  class: String
})
const customClass = props.class
</script>
