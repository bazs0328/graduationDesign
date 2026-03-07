<template>
  <button
    :class="[
      'inline-flex items-center justify-center rounded-xl font-semibold transition-all duration-200 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30',
      variantClasses[variant],
      sizeClasses[size],
      customClass
    ]"
    :disabled="disabled || loading"
    @click="$emit('click', $event)"
  >
    <div v-if="loading" class="mr-2 h-4 w-4 animate-spin border-2 border-current border-t-transparent rounded-full"></div>
    <slot v-else name="icon"></slot>
    <slot></slot>
  </button>
</template>

<script setup>
const props = defineProps({
  variant: {
    type: String,
    default: 'primary'
  },
  size: {
    type: String,
    default: 'md'
  },
  disabled: Boolean,
  loading: Boolean,
  class: String
})

const customClass = props.class

const variantClasses = {
  primary: 'bg-primary text-primary-foreground hover:-translate-y-0.5 shadow-[0_16px_30px_-18px_rgba(37,99,235,0.6)]',
  secondary: 'border border-border bg-secondary/90 text-secondary-foreground hover:bg-secondary',
  outline: 'border border-input bg-background/90 text-foreground hover:bg-accent hover:border-border/90',
  ghost: 'text-muted-foreground hover:bg-accent hover:text-foreground',
  destructive: 'bg-destructive text-destructive-foreground hover:-translate-y-0.5 shadow-[0_16px_30px_-18px_rgba(220,38,38,0.45)]'
}

const sizeClasses = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 py-2 text-sm',
  lg: 'h-12 px-7 text-base',
  icon: 'h-10 w-10'
}

defineEmits(['click'])
</script>
