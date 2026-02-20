<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4"
      @click.self="$emit('close')"
    >
      <section class="w-full max-w-4xl bg-card border border-border rounded-2xl shadow-xl overflow-hidden">
        <header class="px-5 py-4 border-b border-border flex items-start justify-between gap-4">
          <div class="space-y-1">
            <h3 class="text-lg font-bold text-foreground">文档诊断</h3>
            <p class="text-xs text-muted-foreground">{{ filename || '未命名文档' }}</p>
          </div>
          <button
            class="shrink-0 text-sm px-3 py-1.5 rounded-lg border border-border hover:bg-accent"
            @click="$emit('close')"
          >
            关闭
          </button>
        </header>

        <div class="px-5 py-5 max-h-[70vh] overflow-auto space-y-4">
          <div v-if="loading" class="text-sm text-muted-foreground">正在加载诊断数据...</div>
          <div v-else-if="error" class="text-sm text-destructive">{{ error }}</div>
          <template v-else>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="text-muted-foreground">RAG Backend</p>
                <p class="font-semibold mt-1">{{ data.rag_backend || '-' }}</p>
              </div>
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="text-muted-foreground">解析引擎</p>
                <p class="font-semibold mt-1">{{ data.parser_engine || '-' }}</p>
              </div>
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="text-muted-foreground">解析器</p>
                <p class="font-semibold mt-1">{{ data.parser_provider || '-' }}</p>
              </div>
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="text-muted-foreground">提取方式</p>
                <p class="font-semibold mt-1">{{ data.extract_method || '-' }}</p>
              </div>
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="text-muted-foreground">策略</p>
                <p class="font-semibold mt-1">{{ data.strategy || '-' }}</p>
              </div>
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="text-muted-foreground">质量分</p>
                <p class="font-semibold mt-1">{{ formatScore(data.quality_score) }}</p>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="font-semibold">低质量页</p>
                <p class="mt-1 text-muted-foreground">{{ listOrDash(data.low_quality_pages) }}</p>
              </div>
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="font-semibold">OCR 页</p>
                <p class="mt-1 text-muted-foreground">{{ listOrDash(data.ocr_pages) }}</p>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="font-semibold">回退链路</p>
                <p class="mt-1 text-muted-foreground">{{ listOrDash(data.fallback_chain) }}</p>
              </div>
              <div class="p-3 rounded-lg bg-background border border-border">
                <p class="font-semibold">资产统计</p>
                <p class="mt-1 text-muted-foreground">
                  {{ formatAssetStats(data.asset_stats) }}
                </p>
              </div>
            </div>

            <div class="p-3 rounded-lg bg-background border border-border text-xs">
              <p class="font-semibold">阶段耗时 (ms)</p>
              <div class="mt-2 space-y-1">
                <div v-for="(value, key) in data.stage_timings_ms || {}" :key="key" class="flex items-center justify-between">
                  <span class="text-muted-foreground">{{ key }}</span>
                  <span class="font-medium">{{ Number(value).toFixed(2) }}</span>
                </div>
                <p v-if="!Object.keys(data.stage_timings_ms || {}).length" class="text-muted-foreground">-</p>
              </div>
            </div>

            <div class="p-3 rounded-lg bg-background border border-border text-xs">
              <p class="font-semibold mb-2">页级质量</p>
              <div class="space-y-1 max-h-56 overflow-auto pr-1">
                <div
                  v-for="row in data.page_scores || []"
                  :key="`${row.page}-${row.method}`"
                  class="grid grid-cols-[56px_80px_1fr] gap-2 items-center border border-border rounded px-2 py-1"
                >
                  <span>p.{{ row.page }}</span>
                  <span>{{ Number(row.quality_score || 0).toFixed(1) }}</span>
                  <span class="truncate text-muted-foreground">{{ row.method }} · {{ listOrDash(row.flags) }}</span>
                </div>
                <p v-if="!(data.page_scores || []).length" class="text-muted-foreground">暂无页级评分</p>
              </div>
            </div>
          </template>
        </div>
      </section>
    </div>
  </teleport>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  filename: { type: String, default: '' },
  data: { type: Object, default: () => ({}) },
  error: { type: String, default: '' },
})

defineEmits(['close'])

function listOrDash(value) {
  if (Array.isArray(value) && value.length) return value.join(', ')
  return '-'
}

function formatScore(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return num.toFixed(1)
}

function formatAssetStats(value) {
  if (!value || typeof value !== 'object') return '-'
  const total = Number(value.total || 0)
  const byType = value.by_type && typeof value.by_type === 'object'
    ? Object.entries(value.by_type).map(([k, v]) => `${k}:${v}`).join(', ')
    : ''
  if (!byType) return `total=${total}`
  return `total=${total}; ${byType}`
}
</script>
