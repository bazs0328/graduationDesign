<template>
  <section
    class="workspace-alert workspace-alert-warning shadow-sm"
    :class="compact ? 'p-4' : 'p-5 sm:p-6'"
  >
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2 max-w-3xl">
        <div class="inline-flex items-center gap-2 rounded-full border workspace-badge-warning px-3 py-1 text-[11px] font-bold uppercase tracking-[0.24em]">
          <Settings2 class="w-3.5 h-3.5" />
          模型接入未完成
        </div>
        <div class="space-y-1">
          <h3 class="text-base sm:text-lg font-bold tracking-tight">{{ title }}</h3>
          <p class="text-sm leading-relaxed text-current/80">
            {{ description }}
          </p>
        </div>
        <p v-if="missingSummary" class="text-xs text-current/70">
          缺少项：{{ missingSummary }}
        </p>
      </div>

      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-xl border border-amber-900/10 bg-amber-950 px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition-opacity dark:border-amber-200/10 dark:bg-amber-100 dark:text-amber-950"
        @click="router.push('/settings')"
      >
        去设置中心
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Settings2 } from 'lucide-vue-next'

const FIELD_LABEL_MAP = {
  'deepseek.api_key': 'DeepSeek API 密钥',
  'deepseek.base_url': 'DeepSeek 服务地址',
  'deepseek.model': 'DeepSeek 对话模型',
  'qwen.api_key': 'Qwen API 密钥',
  'qwen.base_url': 'Qwen 服务地址',
  'qwen.model': 'Qwen 对话模型',
  'qwen.embedding_model': 'Qwen 向量模型',
  'dashscope.base_url': 'DashScope 服务地址',
  'dashscope.embedding_model': 'DashScope 向量模型',
}

const props = defineProps({
  title: {
    type: String,
    default: '先完成模型接入配置',
  },
  description: {
    type: String,
    default: '填写 API 密钥和服务地址后，摘要、问答与测验功能才能正常使用。',
  },
  missing: {
    type: Array,
    default: () => [],
  },
  compact: {
    type: Boolean,
    default: false,
  },
})

const router = useRouter()

const missingSummary = computed(() => {
  const labels = (Array.isArray(props.missing) ? props.missing : [])
    .map((item) => FIELD_LABEL_MAP[item] || String(item || '').trim())
    .filter(Boolean)
  return labels.join('、')
})
</script>
