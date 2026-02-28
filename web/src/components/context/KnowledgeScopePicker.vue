<template>
  <div class="space-y-3">
    <KbSelector
      :model-value="kbId"
      :kbs="kbs"
      :label="kbLabel"
      :placeholder="kbPlaceholder"
      :required="true"
      :loading="kbLoading"
      :disabled="disabled"
      @update:model-value="$emit('update:kbId', $event)"
    />

    <DocSelector
      :visible="showDocSelector"
      :model-value="docId"
      :docs="docs"
      :label="docLabel"
      :placeholder="docPlaceholder"
      :required="docRequired"
      :loading="docsLoading"
      :disabled="disabled || !kbId"
      @update:model-value="$emit('update:docId', $event)"
    />

    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import KbSelector from './KbSelector.vue'
import DocSelector from './DocSelector.vue'

const props = defineProps({
  kbId: {
    type: String,
    default: '',
  },
  docId: {
    type: String,
    default: '',
  },
  kbs: {
    type: Array,
    default: () => [],
  },
  docs: {
    type: Array,
    default: () => [],
  },
  mode: {
    type: String,
    default: 'kb-and-optional-doc',
    validator: (value) => ['kb-only', 'kb-and-optional-doc', 'kb-and-required-doc'].includes(value),
  },
  kbLabel: {
    type: String,
    default: '选择知识库',
  },
  kbPlaceholder: {
    type: String,
    default: '请选择',
  },
  docLabel: {
    type: String,
    default: '限定文档（可选）',
  },
  kbLoading: Boolean,
  docsLoading: Boolean,
  disabled: Boolean,
})

defineEmits(['update:kbId', 'update:docId'])

const docRequired = computed(() => props.mode === 'kb-and-required-doc')
const showDocSelector = computed(() => props.mode !== 'kb-only' && Boolean(props.kbId))
const docPlaceholder = computed(() => {
  if (docRequired.value) return '请选择文档'
  return props.mode === 'kb-and-optional-doc' ? '不限定（当前知识库范围）' : '不限定'
})
</script>
