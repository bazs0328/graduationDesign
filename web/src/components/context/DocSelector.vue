<template>
  <div class="space-y-2" v-if="visible">
    <div class="flex items-center gap-2">
      <label v-if="label" class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {{ label }}
      </label>
      <span v-if="loading" class="text-[10px] text-muted-foreground">加载中...</span>
    </div>
    <select
      :value="modelValue || ''"
      :disabled="disabled || loading"
      class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm disabled:opacity-60"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option :disabled="required" value="">{{ placeholder }}</option>
      <option v-for="doc in normalizedDocs" :key="doc.id" :value="doc.id">
        {{ doc.filename || doc.id }}
      </option>
    </select>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  docs: {
    type: Array,
    default: () => [],
  },
  visible: {
    type: Boolean,
    default: true,
  },
  label: {
    type: String,
    default: '限定文档（可选）',
  },
  placeholder: {
    type: String,
    default: '不限定（整库）',
  },
  required: {
    type: Boolean,
    default: false,
  },
  disabled: Boolean,
  loading: Boolean,
})

defineEmits(['update:modelValue'])

const normalizedDocs = computed(() => (Array.isArray(props.docs) ? props.docs : []))
</script>
