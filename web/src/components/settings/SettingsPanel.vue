<template>
  <section class="bg-card border border-border rounded-2xl p-5 sm:p-6 shadow-sm space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="space-y-1">
        <h3 class="text-base sm:text-lg font-bold tracking-tight">{{ title }}</h3>
        <p v-if="description" class="text-sm text-muted-foreground leading-relaxed">
          {{ description }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <button
          v-if="hasAdvanced"
          type="button"
          class="px-3 py-1.5 rounded-lg border border-input text-xs font-semibold hover:bg-accent transition-colors"
          @click="$emit('update:advancedOpen', !advancedOpen)"
        >
          {{ advancedOpen ? '收起高级' : advancedLabel }}
        </button>
      </div>
    </div>

    <div class="space-y-4">
      <slot />
      <div v-if="hasAdvanced && advancedOpen" class="rounded-xl border border-border/70 bg-background/40 p-4 space-y-3">
        <div class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">高级设置</div>
        <slot name="advanced" />
      </div>
    </div>

    <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

    <div class="flex flex-wrap items-center justify-between gap-3 pt-2">
      <p class="text-xs text-muted-foreground">
        <span v-if="dirty">有未保存更改</span>
        <span v-else>当前已与服务器保存状态一致</span>
      </p>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent disabled:opacity-50"
          :disabled="saving"
          @click="$emit('reset')"
        >
          重置
        </button>
        <button
          type="button"
          class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          :disabled="saving || !dirty"
          @click="$emit('save')"
        >
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, useSlots } from 'vue'

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
  dirty: Boolean,
  saving: Boolean,
  error: {
    type: String,
    default: '',
  },
  advancedOpen: Boolean,
  advancedLabel: {
    type: String,
    default: '高级选项',
  },
})

defineEmits(['save', 'reset', 'update:advancedOpen'])
const slots = useSlots()
const hasAdvanced = computed(() => Boolean(slots.advanced))
</script>
