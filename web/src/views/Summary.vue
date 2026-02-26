<template>
  <div class="space-y-8 max-w-6xl mx-auto">
    <section
      v-if="entryDocContextId || entryKeypointText"
      class="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 space-y-1"
    >
      <p class="text-[10px] font-bold uppercase tracking-widest text-primary">学习路径上下文</p>
      <p class="text-sm text-muted-foreground">
        <span v-if="entryDocContextId">
          当前目标文档：<span class="font-semibold text-foreground">{{ entryDocContextName }}</span>
        </span>
        <span v-if="entryKeypointText">
          <span v-if="entryDocContextId"> · </span>
          学习目标：<span class="font-semibold text-foreground">{{ entryKeypointText }}</span>
        </span>
      </p>
    </section>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Sidebar: Doc Selection -->
      <aside class="space-y-6">
        <div class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
          <div class="flex items-center gap-3">
            <FileText class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">选择范围</h2>
          </div>
          <SkeletonBlock v-if="busy.init" type="list" :lines="4" />
          <KnowledgeScopePicker
            v-else
            :kb-id="selectedKbId"
            :doc-id="selectedDocId"
            :kbs="kbs"
            :docs="docs"
            :kb-loading="appContext.kbsLoading"
            :docs-loading="busy.docs"
            mode="kb-and-required-doc"
            kb-label="目标知识库"
            doc-label="目标文档"
            @update:kb-id="selectedKbId = $event"
            @update:doc-id="selectedDocId = $event"
          >
            <p class="text-[11px] text-muted-foreground">
              摘要与要点生成作用于单文档；你可以先选知识库，再选具体文档。
            </p>
          </KnowledgeScopePicker>
          <div class="flex flex-col gap-2 pt-2">
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input
                v-model="forceRefresh"
                type="checkbox"
                class="w-4 h-4 rounded border-input text-primary focus:ring-primary"
              />
              <span class="text-muted-foreground">强制刷新（绕过缓存）</span>
            </label>
            <Button
              class="w-full"
              :disabled="!selectedDocId"
              :loading="busy.summary"
              @click="generateSummary(forceRefresh)"
            >
              {{ busy.summary ? '生成中…' : '生成摘要' }}
            </Button>
            <Button
              class="w-full"
              variant="secondary"
              :disabled="!selectedDocId"
              :loading="busy.keypoints"
              @click="generateKeypoints(forceRefresh)"
            >
              {{ busy.keypoints ? '提取中…' : '提取要点' }}
            </Button>
          </div>
        </div>

        <div v-if="selectedDocId" class="bg-card border border-border rounded-xl p-4 text-xs space-y-2">
          <div class="flex justify-between">
            <span class="text-muted-foreground">文档 ID：</span>
            <span class="font-mono">{{ selectedDocId.slice(0, 8) }}...</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted-foreground">知识库：</span>
            <span>{{ selectedKbName }}</span>
          </div>
        </div>
      </aside>

      <!-- Main Content: Summary & Keypoints -->
      <div class="lg:col-span-2 space-y-8">
        <!-- Summary Card -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6 min-h-[300px]">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Sparkles class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">内容摘要</h2>
            </div>
            <span v-if="summaryCached" class="text-[10px] font-bold bg-green-500/10 text-green-500 px-2 py-1 rounded-full uppercase tracking-tighter">
              已缓存
            </span>
          </div>

          <div v-if="busy.summary" class="flex flex-col items-center justify-center py-20 space-y-4">
            <LoadingSpinner size="lg" message="正在分析文档内容…" vertical />
          </div>
          <div
            v-else-if="summary"
            class="summary-markdown markdown-content max-w-none"
            v-html="renderedSummary"
          ></div>
          <EmptyState
            v-else
            :icon="FileText"
            title="开始生成文档摘要"
            :description="summaryEmptyDescription"
            :hint="summaryEmptyHint"
            size="lg"
            :primary-action="summaryEmptyPrimaryAction"
            :secondary-action="summaryEmptySecondaryAction"
            @primary="handleSummaryEmptyPrimary"
            @secondary="goToUpload"
          />
        </section>

        <!-- Keypoints Card -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-3 flex-wrap">
              <Layers class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">核心知识点</h2>
              <span class="text-[10px] font-bold px-2 py-1 rounded-full border border-primary/20 bg-primary/10 text-primary uppercase tracking-tighter">
                单文档视图
              </span>
            </div>
            <span v-if="keypointsCached" class="text-[10px] font-bold bg-green-500/10 text-green-500 px-2 py-1 rounded-full uppercase tracking-tighter">
              已缓存
            </span>
          </div>

          <div v-if="busy.keypoints" class="flex flex-col items-center justify-center py-12 space-y-4">
            <LoadingSpinner size="md" message="正在提取核心概念…" vertical />
          </div>
          <p v-else-if="keypointsError" class="text-sm text-destructive">{{ keypointsError }}</p>
          <div v-else-if="keypoints.length" class="grid grid-cols-1 gap-4">
            <div
              v-if="hasSelectedDocKb"
              class="rounded-lg border border-border bg-background px-4 py-3 space-y-3"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="space-y-1">
                  <p class="text-xs font-bold uppercase tracking-widest text-primary">知识库聚合视图</p>
                  <p class="text-xs text-muted-foreground">
                    跨文档去重后的知识点视图，便于统整复习与对照不同文档表述。
                  </p>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    class="text-xs font-semibold px-3 py-1.5 rounded-md border border-input hover:bg-accent transition-colors"
                    :disabled="kbGroupedBusy"
                    @click="toggleKbGroupedPanel"
                  >
                    {{ kbGroupedPanelOpen ? '收起聚合知识点' : '查看知识库聚合知识点' }}
                  </button>
                  <button
                    v-if="kbGroupedPanelOpen"
                    class="text-xs font-semibold px-3 py-1.5 rounded-md border border-input hover:bg-accent transition-colors disabled:opacity-50"
                    :disabled="kbGroupedBusy"
                    @click="refreshKbGroupedKeypoints"
                  >
                    {{ kbGroupedBusy ? '加载中…' : '刷新' }}
                  </button>
                </div>
              </div>

              <div v-if="kbGroupedPanelOpen" class="space-y-3">
                <div v-if="kbGroupedBusy" class="py-6">
                  <LoadingSpinner size="sm" message="正在加载 KB 聚合知识点…" vertical />
                </div>
                <p v-else-if="kbGroupedError" class="text-sm text-destructive">{{ kbGroupedError }}</p>
                <div v-else-if="kbGroupedKeypoints.length" class="space-y-2">
                  <div class="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                    <span class="px-2 py-1 rounded-full border border-primary/15 bg-primary/5 text-primary font-semibold">
                      知识库聚合
                    </span>
                    <span v-if="kbGroupedGroupCount !== null">聚合后 {{ kbGroupedGroupCount }} 项</span>
                    <span v-if="kbGroupedRawCount !== null">原始 {{ kbGroupedRawCount }} 项</span>
                  </div>
                  <div class="max-h-[360px] overflow-y-auto pr-1 space-y-2">
                    <div
                      v-for="(point, idx) in kbGroupedKeypoints"
                      :key="point.id || idx"
                      class="rounded-lg border border-border p-3 bg-card space-y-2"
                    >
                      <div class="flex items-start gap-3">
                        <span class="w-6 h-6 shrink-0 rounded-full bg-primary/10 text-primary text-[11px] font-bold flex items-center justify-center">
                          {{ idx + 1 }}
                        </span>
                        <div class="flex-1 min-w-0 space-y-1.5">
                          <p class="text-sm font-medium leading-snug">{{ point.text }}</p>
                          <p v-if="point.explanation" class="text-xs text-muted-foreground leading-relaxed">
                            {{ point.explanation }}
                          </p>
                          <div class="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                            <span class="px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-primary font-semibold">KB聚合</span>
                            <span>来自 {{ ((point.source_doc_ids && point.source_doc_ids.length) || point.member_count || 1) }} 个文档</span>
                            <span v-if="Number(point.member_count || 1) > 1">合并 {{ point.member_count }} 个条目</span>
                          </div>
                          <div
                            v-if="point.source_doc_names && point.source_doc_names.length"
                            class="text-[10px] text-muted-foreground"
                            :title="point.source_doc_names.join('、')"
                          >
                            文档：{{ point.source_doc_names.slice(0, 3).join('、') }}<span v-if="point.source_doc_names.length > 3"> 等 {{ point.source_doc_names.length }} 个</span>
                          </div>
                          <details v-if="point.source_refs && point.source_refs.length" class="text-xs">
                            <summary class="cursor-pointer text-primary hover:underline select-none">
                              查看来源定位（{{ point.source_refs.length }}）
                            </summary>
                            <div class="mt-2 space-y-1.5">
                              <div
                                v-for="(ref, refIdx) in point.source_refs"
                                :key="`${ref.keypoint_id || point.id}-${refIdx}`"
                                class="rounded border border-border/70 bg-background px-2 py-1.5 text-[11px] text-muted-foreground"
                              >
                                <span class="font-medium text-foreground">{{ ref.doc_name || ref.doc_id }}</span>
                                <span v-if="ref.source"> · {{ ref.source }}</span>
                              </div>
                            </div>
                          </details>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div v-else class="rounded-lg border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">
                  当前知识库暂无可展示的聚合知识点。
                </div>
              </div>
            </div>
            <div class="rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-sm">
              <p class="text-muted-foreground leading-relaxed">
                当前展示的是该文档提取结果（单文档视图）；跨文档去重后的知识点请在进度页查看学习路径。
              </p>
              <button
                v-if="hasSelectedDocKb"
                class="mt-2 text-xs font-semibold text-primary hover:underline"
                @click="goToKbProgressFromKeypointsCard"
              >
                查看 KB 学习路径
              </button>
            </div>
            <div
              v-for="(point, idx) in keypoints"
              :key="point?.id || idx"
              :data-target-keypoint="isTargetKeypoint(point) ? 'true' : undefined"
              class="p-5 bg-background border rounded-xl hover:border-primary/30 transition-all group"
              :class="isTargetKeypoint(point) ? 'border-primary ring-2 ring-primary/30 bg-primary/5' : ''"
            >
              <div class="space-y-4">
                <!-- Header: Number + Title -->
                <div class="flex gap-3 items-start">
                  <div class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold"
                    :class="isTargetKeypoint(point) ? 'bg-primary text-primary-foreground ring-2 ring-primary/50' : 'bg-primary/10 text-primary'">
                    {{ idx + 1 }}
                  </div>
                  <div class="flex-1 space-y-2">
                    <p class="font-medium leading-snug text-base" :class="isTargetKeypoint(point) ? 'text-primary' : ''">
                      {{ typeof point === 'string' ? point : point.text }}
                    </p>
                    <div v-if="isTargetKeypoint(point)" class="text-xs font-semibold text-primary bg-primary/10 px-2 py-1 rounded-full inline-block">
                      当前学习目标
                    </div>
                  </div>
                </div>

                <!-- Explanation -->
                <p v-if="typeof point !== 'string' && point.explanation" class="text-sm text-muted-foreground pl-11">
                  {{ point.explanation }}
                </p>

                <!-- Source Info -->
                <div v-if="typeof point !== 'string' && (point.source || point.page || point.chunk)" class="flex items-center gap-2 pt-2 pl-11 border-t border-border/50">
                  <span class="text-[10px] font-bold uppercase text-primary/60">来源：</span>
                  <span class="text-[10px] bg-accent px-2 py-0.5 rounded-full text-accent-foreground">
                    {{ point.source || '文档片段' }}
                  </span>
                  <button
                    class="text-[10px] font-semibold text-primary hover:underline"
                    @click="openKeypointSource(point)"
                  >
                    查看原文
                  </button>
                </div>

                <!-- View Details Link -->
                <div v-if="hasSelectedDocKb" class="pt-2 pl-11 border-t border-border/50">
                  <button
                    class="text-xs text-primary hover:underline font-medium"
                    @click="goToProgress(point)"
                  >
                    查看学习路径 →
                  </button>
                </div>
              </div>
            </div>
          </div>
          <EmptyState
            v-else
            :icon="Layers"
            title="提取核心知识点"
            :description="keypointsEmptyDescription"
            :hint="keypointsEmptyHint"
            :primary-action="keypointsEmptyPrimaryAction"
            :secondary-action="keypointsEmptySecondaryAction"
            @primary="handleKeypointsEmptyPrimary"
            @secondary="goToUpload"
          />
        </section>
      </div>
    </div>
    <SourcePreviewModal
      :open="sourcePreview.open"
      :loading="sourcePreview.loading"
      :title="sourcePreview.title"
      :source-label="sourcePreview.sourceLabel"
      :page="sourcePreview.page"
      :chunk="sourcePreview.chunk"
      :snippet="sourcePreview.snippet"
      :error="sourcePreview.error"
      @close="closeSourcePreview"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, watch, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { FileText, Sparkles, Layers } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'
import { useKbDocuments } from '../composables/useKbDocuments'
import { useToast } from '../composables/useToast'
import { useAppContextStore } from '../stores/appContext'
import KnowledgeScopePicker from '../components/context/KnowledgeScopePicker.vue'
import Button from '../components/ui/Button.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import SourcePreviewModal from '../components/ui/SourcePreviewModal.vue'
import { renderMarkdown } from '../utils/markdown'
import { buildRouteContextQuery, parseRouteContext } from '../utils/routeContext'

const { showToast } = useToast()
const appContext = useAppContextStore()
appContext.hydrate()

const router = useRouter()
const route = useRoute()
const resolvedUserId = computed(() => appContext.resolvedUserId || 'default')
const kbs = computed(() => appContext.kbs)
const selectedKbId = computed({
  get: () => appContext.selectedKbId,
  set: (value) => appContext.setSelectedKbId(value),
})
const selectedDocId = computed({
  get: () => appContext.selectedDocId,
  set: (value) => appContext.setSelectedDocId(value),
})
const kbDocs = useKbDocuments({ userId: resolvedUserId, kbId: selectedKbId })
const docs = kbDocs.docs
const summary = ref('')
const summaryCached = ref(false)
const keypoints = ref([])
const keypointsCached = ref(false)
const keypointsError = ref('')
const kbGroupedPanelOpen = ref(false)
const kbGroupedBusy = ref(false)
const kbGroupedError = ref('')
const kbGroupedKeypoints = ref([])
const kbGroupedRawCount = ref(null)
const kbGroupedGroupCount = ref(null)
const kbGroupedLoadedKbId = ref('')
const forceRefresh = ref(false)
const sourcePreview = ref({
  open: false,
  loading: false,
  title: '',
  sourceLabel: '',
  page: null,
  chunk: null,
  snippet: '',
  error: '',
})
const busy = ref({
  summary: false,
  keypoints: false,
  init: false,
  docs: false,
})

const renderedSummary = computed(() => {
  return renderMarkdown(summary.value)
})
const hasDocs = computed(() => docs.value.length > 0)
const selectedDoc = computed(() => docs.value.find(d => d.id === selectedDocId.value) || null)
const hasSelectedDocKb = computed(() => Boolean(selectedDoc.value?.kb_id))
const selectedDocKbId = computed(() => selectedDoc.value?.kb_id || '')

const selectedKbName = computed(() => {
  const kbId = selectedDoc.value?.kb_id || selectedKbId.value
  if (!kbId) return '未知'
  const kb = kbs.value.find(k => k.id === kbId)
  return kb ? kb.name : '未知'
})
const entryDocContextId = computed(() => parseRouteContext(route.query).docId)
const entryKeypointText = computed(() => appContext.routeContext.keypointText)
const entryDocContextName = computed(() => {
  if (!entryDocContextId.value) return ''
  const doc = docs.value.find((d) => d.id === entryDocContextId.value)
  if (doc?.filename) return doc.filename
  return `${entryDocContextId.value.slice(0, 8)}...`
})
const hasSelectedDoc = computed(() => Boolean(selectedDocId.value))
const summaryEmptyDescription = computed(() => {
  if (!hasDocs.value) {
    return '还没有可分析的文档，请先上传并完成解析。'
  }
  if (!hasSelectedDoc.value) {
    return '左侧文档列表已有内容，请先选择一个目标文档。'
  }
  return '系统会基于当前文档生成结构化内容摘要。'
})
const summaryEmptyHint = computed(() => {
  if (!hasDocs.value) {
    return '上传后返回本页即可生成摘要与要点。'
  }
  if (!hasSelectedDoc.value) {
    return '选择文档后可直接点击生成摘要，支持强制刷新缓存。'
  }
  return '生成结果会缓存，重复查看更快。'
})
const summaryEmptyPrimaryAction = computed(() => {
  if (!hasDocs.value) return { label: '去上传文档' }
  if (!hasSelectedDoc.value) return null
  return { label: '生成摘要', loading: busy.value.summary }
})
const summaryEmptySecondaryAction = computed(() => {
  if (!hasDocs.value) return null
  if (!hasSelectedDoc.value) return { label: '去上传页', variant: 'outline' }
  return null
})
const keypointsEmptyDescription = computed(() => {
  if (!hasDocs.value) {
    return '当前还没有文档，无法提取知识点。'
  }
  if (!hasSelectedDoc.value) {
    return '先在左侧选择文档，再提取核心知识点。'
  }
  return '提取后会展示知识点、讲解与来源定位信息。'
})
const keypointsEmptyHint = computed(() => {
  if (!hasDocs.value) {
    return '建议先上传课程讲义、笔记或教材片段。'
  }
  if (!hasSelectedDoc.value) {
    return '提取结果可用于后续学习路径与测验推荐。'
  }
  return '生成完成后可直接跳转到学习路径查看后续建议。'
})
const keypointsEmptyPrimaryAction = computed(() => {
  if (!hasDocs.value) return { label: '去上传文档' }
  if (!hasSelectedDoc.value) return null
  return { label: '提取要点', variant: 'secondary', loading: busy.value.keypoints }
})
const keypointsEmptySecondaryAction = computed(() => {
  if (!hasDocs.value) return null
  if (!hasSelectedDoc.value) return { label: '去上传页', variant: 'outline' }
  return null
})

function isTargetKeypoint(point) {
  if (!entryKeypointText.value) return false
  const pointText = typeof point === 'string' ? point : point.text || ''
  return pointText.trim() === entryKeypointText.value.trim()
}

function goToUpload() {
  router.push({ path: '/upload' })
}

function handleSummaryEmptyPrimary() {
  if (!hasDocs.value) {
    goToUpload()
    return
  }
  if (!hasSelectedDoc.value) return
  generateSummary(forceRefresh.value)
}

function handleKeypointsEmptyPrimary() {
  if (!hasDocs.value) {
    goToUpload()
    return
  }
  if (!hasSelectedDoc.value) return
  generateKeypoints(forceRefresh.value)
}

function scrollToTargetKeypoint() {
  nextTick(() => {
    const targetEl = document.querySelector('[data-target-keypoint="true"]')
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

function closeSourcePreview() {
  sourcePreview.value.open = false
}

async function openKeypointSource(point) {
  if (!selectedDocId.value || !point || typeof point === 'string') return
  sourcePreview.value = {
    open: true,
    loading: true,
    title: '知识点来源预览',
    sourceLabel: point.source || '',
    page: Number.isFinite(Number(point.page)) ? Number(point.page) : null,
    chunk: Number.isFinite(Number(point.chunk)) ? Number(point.chunk) : null,
    snippet: '',
    error: '',
  }
  try {
    const params = new URLSearchParams()
    params.set('user_id', resolvedUserId.value)
    if (point.page) params.set('page', String(point.page))
    if (point.chunk) params.set('chunk', String(point.chunk))
    if (point.text) params.set('q', String(point.text))
    const res = await apiGet(`/api/docs/${selectedDocId.value}/preview?${params.toString()}`)
    sourcePreview.value = {
      open: true,
      loading: false,
      title: `${res.filename || '文档'} 原文片段`,
      sourceLabel: res.source || point.source || res.filename || '',
      page: res.page ?? null,
      chunk: res.chunk ?? null,
      snippet: res.snippet || '',
      error: '',
    }
  } catch (err) {
    sourcePreview.value.loading = false
    sourcePreview.value.error = err?.message || '无法加载来源片段'
  }
}

function goToProgress(point) {
  const doc = docs.value.find((d) => d.id === selectedDocId.value)
  const kbId = doc?.kb_id || ''
  router.push({
    path: '/progress',
    query: buildRouteContextQuery({ kbId }),
  })
}

function goToKbProgressFromKeypointsCard() {
  if (!selectedDoc.value?.kb_id) return
  router.push({
    path: '/progress',
    query: buildRouteContextQuery({ kbId: selectedDoc.value.kb_id }),
  })
}

function resetKbGroupedPanelState() {
  kbGroupedPanelOpen.value = false
  kbGroupedBusy.value = false
  kbGroupedError.value = ''
  kbGroupedKeypoints.value = []
  kbGroupedRawCount.value = null
  kbGroupedGroupCount.value = null
  kbGroupedLoadedKbId.value = ''
}

async function loadKbGroupedKeypoints(options = {}) {
  const kbId = selectedDocKbId.value
  if (!kbId) return
  const { force = false } = options
  if (!force && kbGroupedLoadedKbId.value === kbId && !kbGroupedError.value) return

  kbGroupedBusy.value = true
  kbGroupedError.value = ''
  const requestKbId = kbId
  try {
    const params = new URLSearchParams()
    params.set('user_id', resolvedUserId.value)
    params.set('grouped', 'true')
    const res = await apiGet(`/api/keypoints/kb/${encodeURIComponent(requestKbId)}?${params.toString()}`)
    if (selectedDocKbId.value !== requestKbId) return
    kbGroupedKeypoints.value = Array.isArray(res?.keypoints) ? res.keypoints : []
    kbGroupedRawCount.value = Number.isFinite(Number(res?.raw_count)) ? Number(res.raw_count) : null
    kbGroupedGroupCount.value = Number.isFinite(Number(res?.group_count)) ? Number(res.group_count) : null
    kbGroupedLoadedKbId.value = requestKbId
  } catch (err) {
    if (selectedDocKbId.value !== requestKbId) return
    kbGroupedError.value = err?.message || '加载 KB 聚合知识点失败，请稍后重试'
  } finally {
    if (selectedDocKbId.value === requestKbId) {
      kbGroupedBusy.value = false
    }
  }
}

async function toggleKbGroupedPanel() {
  if (!hasSelectedDocKb.value) return
  kbGroupedPanelOpen.value = !kbGroupedPanelOpen.value
  if (kbGroupedPanelOpen.value) {
    await loadKbGroupedKeypoints()
  }
}

async function refreshKbGroupedKeypoints() {
  if (!hasSelectedDocKb.value) return
  if (!kbGroupedPanelOpen.value) kbGroupedPanelOpen.value = true
  await loadKbGroupedKeypoints({ force: true })
}

async function refreshDocsInKb(options = {}) {
  try {
    await kbDocs.refresh(options)
  } catch {
    // error toast handled globally
  }
}

async function resolveDocKbIdByDocId(docId) {
  const queryDocId = String(docId || '').trim()
  if (!queryDocId) return ''
  try {
    const rows = await apiGet(`/api/docs?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    const found = Array.isArray(rows) ? rows.find((row) => row?.id === queryDocId) : null
    return found?.kb_id || ''
  } catch {
    return ''
  }
}

async function generateSummary(force = false) {
  if (!selectedDocId.value) return
  busy.value.summary = true
  summary.value = ''
  summaryCached.value = false
  try {
    const res = await apiPost('/api/summary', {
      doc_id: selectedDocId.value,
      user_id: resolvedUserId.value,
      force
    })
    summary.value = res.summary
    summaryCached.value = !!res.cached
    showToast('摘要生成完成', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.summary = false
  }
}

async function generateKeypoints(force = false) {
  if (!selectedDocId.value) return
  busy.value.keypoints = true
  keypoints.value = []
  keypointsCached.value = false
  keypointsError.value = ''
  try {
    const payload = {
      doc_id: selectedDocId.value,
      user_id: resolvedUserId.value,
      force
    }
    // 如果是从学习路径跳转过来的，传递目标知识点文本以记录学习行为
    if (entryKeypointText.value) {
      payload.study_keypoint_text = entryKeypointText.value
    }
    const res = await apiPost('/api/keypoints', payload)
    keypoints.value = res.keypoints || []
    keypointsCached.value = !!res.cached
    showToast('要点提取完成', 'success')
    if (entryKeypointText.value) {
      // 等待 DOM 更新完成后再滚动
      await nextTick()
      setTimeout(() => {
        scrollToTargetKeypoint()
      }, 100)
    }
  } catch {
    keypointsError.value = '提取失败，请重试'
  } finally {
    busy.value.keypoints = false
  }
}

function normalizeDocSelection() {
  if (selectedDocId.value && !docs.value.some((doc) => doc.id === selectedDocId.value)) {
    selectedDocId.value = ''
  }
}

const lastAutoContextKey = ref('')
const syncingRouteContext = ref(false)

async function syncFromRoute(options = {}) {
  if (syncingRouteContext.value) return
  syncingRouteContext.value = true
  try {
    try {
      await appContext.applyRouteContext(route.query, {
        ensureKbs: options.ensureKbs === true,
        fallbackToFirstKb: true,
      })
    } catch {
      // error toast handled globally
    }

    if (selectedKbId.value) {
      await refreshDocsInKb({ force: options.refreshDocs === true })
    } else if (options.refreshDocs === true) {
      docs.value = []
    }
    normalizeDocSelection()

    const queryDocId = entryDocContextId.value
    if (!queryDocId) return
    if (!docs.value.some((doc) => doc.id === queryDocId)) {
      const routeDocKbId = await resolveDocKbIdByDocId(queryDocId)
      if (routeDocKbId && routeDocKbId !== selectedKbId.value) {
        selectedKbId.value = routeDocKbId
        await refreshDocsInKb({ force: true })
        normalizeDocSelection()
      }
    }
    if (!docs.value.some((doc) => doc.id === queryDocId)) return

    if (selectedDocId.value !== queryDocId) {
      selectedDocId.value = queryDocId
    }

    const contextKey = `${queryDocId}|${entryKeypointText.value}`
    if (lastAutoContextKey.value === contextKey) return
    lastAutoContextKey.value = contextKey
    await Promise.all([generateSummary(), generateKeypoints()])
  } finally {
    syncingRouteContext.value = false
  }
}

onMounted(async () => {
  busy.value.init = true
  try {
    try {
      await appContext.loadKbs()
    } catch {
      // error toast handled globally
    }
    await syncFromRoute({ refreshDocs: true })
  } finally {
    busy.value.init = false
  }
})

onActivated(async () => {
  await syncFromRoute({ ensureKbs: !appContext.kbs.length, refreshDocs: true })
})

watch(
  () => route.fullPath,
  async () => {
    if (busy.value.init) return
    await syncFromRoute({ refreshDocs: true })
  }
)

watch(selectedKbId, async (nextKbId, prevKbId) => {
  if (nextKbId === prevKbId) return
  if (syncingRouteContext.value) return
  await refreshDocsInKb({ force: true })
  normalizeDocSelection()
})

watch(kbDocs.loading, (loading) => {
  busy.value.docs = !!loading
}, { immediate: true })

watch(selectedDocKbId, (nextKbId, prevKbId) => {
  if (nextKbId === prevKbId) return
  resetKbGroupedPanelState()
})
</script>
