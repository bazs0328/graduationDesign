<template>
  <button
    :class="[
      'inline-flex items-center justify-center rounded-lg font-bold transition-all active:scale-95 disabled:opacity-50 disabled:pointer-events-none',
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
  primary: 'bg-primary text-primary-foreground hover:opacity-90 shadow-sm',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
  outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
  ghost: 'hover:bg-accent hover:text-accent-foreground',
  destructive: 'bg-destructive text-destructive-foreground hover:opacity-90'
}

const sizeClasses = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 py-2 text-sm',
  lg: 'h-12 px-8 text-base',
  icon: 'h-10 w-10'
}

defineEmits(['click'])
</script>
