<template>
  <div
    data-empty-state
    :class="[
      'w-full flex flex-col',
      alignClasses.container,
      sizeClasses.container,
    ]"
  >
    <div
      v-if="resolvedIcon"
      :class="[
        'rounded-full border border-border bg-accent/40 flex items-center justify-center text-primary',
        sizeClasses.iconWrap,
      ]"
    >
      <component :is="resolvedIcon" :class="sizeClasses.icon" />
    </div>

    <div :class="['space-y-2', alignClasses.text]">
      <h3 :class="['font-bold text-foreground', sizeClasses.title]">
        {{ title }}
      </h3>
      <p v-if="description" :class="['text-muted-foreground', sizeClasses.description]">
        {{ description }}
      </p>
      <p v-if="hint" class="text-xs text-muted-foreground/90">
        {{ hint }}
      </p>
      <div v-if="$slots.default" class="text-xs text-muted-foreground">
        <slot />
      </div>
    </div>

    <div v-if="primaryAction || secondaryAction" :class="['flex flex-wrap gap-2', alignClasses.actions]">
      <Button
        v-if="primaryAction"
        :variant="primaryAction.variant || 'primary'"
        :disabled="primaryAction.disabled"
        :loading="primaryAction.loading"
        @click="$emit('primary')"
      >
        {{ primaryAction.label }}
      </Button>
      <Button
        v-if="secondaryAction"
        :variant="secondaryAction.variant || 'outline'"
        :disabled="secondaryAction.disabled"
        :loading="secondaryAction.loading"
        @click="$emit('secondary')"
      >
        {{ secondaryAction.label }}
      </Button>
    </div>
  </div>
</template>

<script setup>
import { computed, markRaw, toRaw } from 'vue'
import Button from './Button.vue'

const props = defineProps({
  icon: {
    type: [Object, Function],
    default: null,
  },
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
  hint: {
    type: String,
    default: '',
  },
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['sm', 'md', 'lg'].includes(value),
  },
  align: {
    type: String,
    default: 'center',
    validator: (value) => ['center', 'left'].includes(value),
  },
  primaryAction: {
    type: Object,
    default: null,
  },
  secondaryAction: {
    type: Object,
    default: null,
  },
})

defineEmits(['primary', 'secondary'])

const resolvedIcon = computed(() => {
  if (!props.icon) return null
  if (typeof props.icon === 'object') {
    return markRaw(toRaw(props.icon))
  }
  return props.icon
})

const alignClasses = computed(() => {
  if (props.align === 'left') {
    return {
      container: 'items-start text-left',
      text: 'text-left',
      actions: 'justify-start',
    }
  }
  return {
    container: 'items-center text-center',
    text: 'text-center',
    actions: 'justify-center',
  }
})

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return {
        container: 'gap-3 py-6',
        iconWrap: 'w-12 h-12',
        icon: 'w-6 h-6',
        title: 'text-base',
        description: 'text-sm',
      }
    case 'lg':
      return {
        container: 'gap-5 py-12',
        iconWrap: 'w-20 h-20',
        icon: 'w-10 h-10',
        title: 'text-2xl',
        description: 'text-base max-w-xl',
      }
    default:
      return {
        container: 'gap-4 py-8',
        iconWrap: 'w-16 h-16',
        icon: 'w-8 h-8',
        title: 'text-lg',
        description: 'text-sm max-w-md',
      }
  }
})
</script>
