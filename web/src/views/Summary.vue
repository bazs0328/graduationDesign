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
            <h2 class="text-xl font-bold">选择文档</h2>
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">选择文档</label>
            <SkeletonBlock v-if="busy.init" type="list" :lines="3" />
            <select v-else v-model="selectedDocId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary">
              <option disabled value="">请选择</option>
              <option v-for="doc in docs" :key="doc.id" :value="doc.id">{{ doc.filename }}</option>
            </select>
          </div>
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
          <div v-else-if="summary" class="prose prose-invert max-w-none">
            <p class="text-lg leading-relaxed whitespace-pre-wrap">{{ summary }}</p>
          </div>
          <div v-else class="flex flex-col items-center justify-center py-20 text-muted-foreground space-y-4">
            <FileText class="w-16 h-16 opacity-10" />
            <p>选择文档并点击「生成摘要」开始。</p>
          </div>
        </section>

        <!-- Keypoints Card -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Layers class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">核心知识点</h2>
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
              v-for="(point, idx) in keypoints"
              :key="point?.id || idx"
              :data-target-keypoint="isTargetKeypoint(point) ? 'true' : undefined"
              class="p-5 bg-background border rounded-xl hover:border-primary/30 transition-all group"
              :class="isTargetKeypoint(point) ? 'border-primary ring-2 ring-primary/30 bg-primary/5' : masteryBorderClass(point)"
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

                <!-- Mastery Progress -->
                <div v-if="getMasteryLevel(point) !== null" class="space-y-2 pl-11">
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs font-semibold text-muted-foreground">掌握度</span>
                    <span class="text-xs font-bold" :class="masteryBadgeClass(point).includes('bg-green') ? 'text-green-500' : masteryBadgeClass(point).includes('bg-yellow') ? 'text-yellow-500' : 'text-red-500'">
                      {{ masteryPercent(point) }}%
                    </span>
                  </div>
                  <div class="w-full h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      class="h-full transition-all duration-500"
                      :class="masteryBadgeClass(point).includes('bg-green') ? 'bg-green-500' : masteryBadgeClass(point).includes('bg-yellow') ? 'bg-yellow-500' : 'bg-red-500'"
                      :style="{ width: `${masteryPercent(point)}%` }"
                    ></div>
                  </div>
                  <div class="flex items-center gap-2">
                    <span
                      class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border"
                      :class="masteryBadgeClass(point)"
                    >
                      {{ masteryLabel(point) }}
                    </span>
                    <span v-if="typeof point !== 'string' && point.attempt_count > 0" class="text-[10px] text-muted-foreground">
                      已尝试 {{ point.attempt_count }} 次
                    </span>
                  </div>
                </div>

                <!-- Source Info -->
                <div v-if="typeof point !== 'string' && (point.source || point.page || point.chunk)" class="flex items-center gap-2 pt-2 pl-11 border-t border-border/50">
                  <span class="text-[10px] font-bold uppercase text-primary/60">来源：</span>
                  <span class="text-[10px] bg-accent px-2 py-0.5 rounded-full text-accent-foreground">
                    {{ [point.source, point.page ? `p.${point.page}` : '', point.chunk ? `c.${point.chunk}` : ''].filter(Boolean).join(' ') }}
                  </span>
                </div>

                <!-- View Details Link -->
                <div v-if="getMasteryLevel(point) !== null" class="pt-2 pl-11 border-t border-border/50">
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
          <div v-else class="flex flex-col items-center justify-center py-12 text-muted-foreground space-y-4">
            <Layers class="w-12 h-12 opacity-10" />
            <p>尚未提取要点。</p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { FileText, Sparkles, Layers } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'
import { useToast } from '../composables/useToast'
import Button from '../components/ui/Button.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import {
  masteryLabel as _masteryLabel,
  masteryPercent as _masteryPercent,
  masteryBadgeClass as _masteryBadgeClass,
  masteryBorderClass as _masteryBorderClass,
  isWeakMastery as _isWeakMastery,
} from '../utils/mastery'

const { showToast } = useToast()

const router = useRouter()
const route = useRoute()
const userId = ref(localStorage.getItem('gradtutor_user') || 'default')
const resolvedUserId = computed(() => userId.value || 'default')
const docs = ref([])
const kbs = ref([])
const selectedDocId = ref('')
const summary = ref('')
const summaryCached = ref(false)
const keypoints = ref([])
const keypointsCached = ref(false)
const keypointsError = ref('')
const forceRefresh = ref(false)
const busy = ref({
  summary: false,
  keypoints: false,
  init: false
})

const selectedKbName = computed(() => {
  const doc = docs.value.find(d => d.id === selectedDocId.value)
  if (!doc) return '未知'
  const kb = kbs.value.find(k => k.id === doc.kb_id)
  return kb ? kb.name : '未知'
})
const entryDocContextId = computed(() => normalizeQueryString(route.query.doc_id))
const entryKeypointText = computed(() => normalizeQueryString(route.query.keypoint_text).trim())
const entryDocContextName = computed(() => {
  if (!entryDocContextId.value) return ''
  const doc = docs.value.find((d) => d.id === entryDocContextId.value)
  if (doc?.filename) return doc.filename
  return `${entryDocContextId.value.slice(0, 8)}...`
})

function isTargetKeypoint(point) {
  if (!entryKeypointText.value) return false
  const pointText = typeof point === 'string' ? point : point.text || ''
  return pointText.trim() === entryKeypointText.value.trim()
}

function scrollToTargetKeypoint() {
  nextTick(() => {
    const targetEl = document.querySelector('[data-target-keypoint="true"]')
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

function getMasteryLevel(point) {
  if (!point || typeof point !== 'object') return null
  const level = Number(point.mastery_level)
  return Number.isFinite(level) ? Math.max(0, Math.min(level, 1)) : null
}

function masteryLabel(point) {
  const lv = getMasteryLevel(point)
  return lv === null ? '' : _masteryLabel(lv)
}
function masteryPercent(point) {
  const lv = getMasteryLevel(point)
  return lv === null ? 0 : _masteryPercent(lv)
}
function masteryBadgeClass(point) {
  const lv = getMasteryLevel(point)
  return lv === null ? '' : _masteryBadgeClass(lv)
}
function masteryBorderClass(point) {
  const lv = getMasteryLevel(point)
  return lv === null ? '' : _masteryBorderClass(lv)
}
function isWeakMastery(point) {
  const lv = getMasteryLevel(point)
  return lv !== null && _isWeakMastery(lv)
}

function goToProgress(point) {
  const doc = docs.value.find((d) => d.id === selectedDocId.value)
  const kbId = doc?.kb_id || ''
  router.push({
    path: '/progress',
    query: kbId ? { kb_id: kbId } : {},
  })
}

function normalizeQueryString(value) {
  if (Array.isArray(value)) {
    return value[0] || ''
  }
  return typeof value === 'string' ? value : ''
}

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(resolvedUserId.value)}`)
  } catch {
    // error toast handled globally
  }
}

async function refreshDocs() {
  try {
    docs.value = await apiGet(`/api/docs?user_id=${encodeURIComponent(resolvedUserId.value)}`)
  } catch {
    // error toast handled globally
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

onMounted(async () => {
  busy.value.init = true
  try {
    await Promise.all([refreshKbs(), refreshDocs()])
    const queryDocId = normalizeQueryString(route.query.doc_id)
    if (queryDocId && docs.value.some((d) => d.id === queryDocId)) {
      selectedDocId.value = queryDocId
      await Promise.all([generateSummary(), generateKeypoints()])
    }
  } finally {
    busy.value.init = false
  }
})
</script>
