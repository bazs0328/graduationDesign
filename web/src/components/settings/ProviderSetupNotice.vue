<template>
  <section
    class="rounded-2xl border shadow-sm"
    :class="compact ? 'border-amber-200 bg-amber-50/90 p-4' : 'border-amber-200 bg-[linear-gradient(135deg,rgba(251,191,36,0.14),rgba(255,255,255,0.94))] p-5 sm:p-6'"
  >
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2 max-w-3xl">
        <div class="inline-flex items-center gap-2 rounded-full border border-amber-300 bg-white/80 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.24em] text-amber-700">
          <Settings2 class="w-3.5 h-3.5" />
          模型接入未完成
        </div>
        <div class="space-y-1">
          <h3 class="text-base sm:text-lg font-bold tracking-tight text-slate-900">{{ title }}</h3>
          <p class="text-sm text-slate-700 leading-relaxed">
            {{ description }}
          </p>
        </div>
        <p v-if="missingSummary" class="text-xs text-slate-600">
          缺少项：{{ missingSummary }}
        </p>
      </div>

      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-xl border border-slate-900/10 bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition-opacity"
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
  'deepseek.api_key': 'DeepSeek API Key',
  'deepseek.base_url': 'DeepSeek Base URL',
  'deepseek.model': 'DeepSeek 对话模型',
  'deepseek.embedding_model': 'DeepSeek 向量模型',
  'qwen.api_key': 'Qwen API Key',
  'qwen.base_url': 'Qwen Base URL',
  'qwen.model': 'Qwen 对话模型',
  'qwen.embedding_model': 'Qwen 向量模型',
  'dashscope.base_url': 'DashScope Base URL',
  'dashscope.embedding_model': 'DashScope 向量模型',
  'openai.api_key': 'OpenAI API Key',
  'gemini.api_key': 'Gemini API Key',
}

const props = defineProps({
  title: {
    type: String,
    default: '先完成模型接入配置',
  },
  description: {
    type: String,
    default: '填写 API Key 和基础地址后，摘要、问答与测验功能才能正常使用。',
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
