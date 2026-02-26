<template>
  <div class="space-y-2">
    <label v-if="label" class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
      {{ label }}
    </label>
    <div class="relative">
      <select
        :value="modelValue || ''"
        :disabled="disabled || loading"
        class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm disabled:opacity-60"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <option :disabled="required" value="">{{ placeholder }}</option>
        <option v-for="kb in normalizedKbs" :key="kb.id" :value="kb.id">
          {{ kb.name || kb.id }}
        </option>
      </select>
      <span v-if="loading" class="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground">
        加载中...
      </span>
    </div>
    <p v-if="showEmptyHint" class="text-[11px] text-muted-foreground">
      暂无知识库，可先在上传页创建。
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  kbs: {
    type: Array,
    default: () => [],
  },
  label: {
    type: String,
    default: '选择知识库',
  },
  placeholder: {
    type: String,
    default: '请选择',
  },
  required: {
    type: Boolean,
    default: true,
  },
  disabled: Boolean,
  loading: Boolean,
})

defineEmits(['update:modelValue'])

const normalizedKbs = computed(() => (Array.isArray(props.kbs) ? props.kbs : []))
const showEmptyHint = computed(() => !props.loading && normalizedKbs.value.length === 0)
</script>
