<template>
  <div class="space-y-8 max-w-6xl mx-auto">
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
            <Button
              class="w-full"
              :disabled="!selectedDocId"
              :loading="busy.summary"
              @click="generateSummary()"
            >
              {{ busy.summary ? '生成中…' : '生成摘要' }}
            </Button>
            <Button
              class="w-full"
              variant="secondary"
              :disabled="!selectedDocId"
              :loading="busy.keypoints"
              @click="generateKeypoints()"
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
              class="p-4 bg-background border border-border rounded-xl hover:border-primary/30 transition-all group"
              :class="masteryBorderClass(point)"
            >
              <div class="flex gap-4">
                <div class="flex-shrink-0 w-6 h-6 bg-primary/10 text-primary rounded-full flex items-center justify-center text-xs font-bold">
                  {{ idx + 1 }}
                </div>
                <div class="space-y-2 flex-1">
                  <p class="font-medium leading-snug">{{ typeof point === 'string' ? point : point.text }}</p>
                  <p v-if="typeof point !== 'string' && point.explanation" class="text-sm text-muted-foreground">
                    {{ point.explanation }}
                  </p>
                  <div v-if="getMasteryLevel(point) !== null" class="flex items-center gap-2">
                    <span
                      class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border"
                      :class="masteryBadgeClass(point)"
                    >
                      {{ masteryLabel(point) }}
                    </span>
                    <span class="text-[10px] text-muted-foreground">{{ masteryPercent(point) }}%</span>
                    <button
                      v-if="isWeakMastery(point)"
                      class="ml-auto text-[10px] font-bold text-destructive hover:underline"
                      @click="goToQuiz"
                    >
                      去测验
                    </button>
                  </div>
                  <div v-if="typeof point !== 'string' && (point.source || point.page || point.chunk)" class="flex items-center gap-2 pt-1">
                    <span class="text-[10px] font-bold uppercase text-primary/60">来源：</span>
                    <span class="text-[10px] bg-accent px-2 py-0.5 rounded-full text-accent-foreground">
                      {{ [point.source, point.page ? `p.${point.page}` : '', point.chunk ? `c.${point.chunk}` : ''].filter(Boolean).join(' ') }}
                    </span>
                  </div>
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
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
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

function goToQuiz() {
  router.push('/quiz')
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
    const res = await apiPost('/api/keypoints', {
      doc_id: selectedDocId.value,
      user_id: resolvedUserId.value,
      force
    })
    keypoints.value = res.keypoints || []
    keypointsCached.value = !!res.cached
    showToast('要点提取完成', 'success')
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
  } finally {
    busy.value.init = false
  }
})
</script>
