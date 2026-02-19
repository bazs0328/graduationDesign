<template>
  <div class="space-y-8 max-w-6xl mx-auto">
    <!-- Top Stats Bar -->
    <section v-if="!busy.init && progress" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <div v-for="stat in topStats" :key="stat.label" class="bg-card border border-border rounded-xl p-6 shadow-sm flex items-center gap-4">
        <div class="w-12 h-12 rounded-lg flex items-center justify-center" :class="stat.color">
          <component :is="stat.icon" class="w-6 h-6" />
        </div>
        <div>
          <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{{ stat.label }}</p>
          <p class="text-2xl font-black">{{ stat.value }}</p>
        </div>
      </div>
    </section>
    <section v-else-if="busy.init" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <div v-for="index in 4" :key="`top-skeleton-${index}`" class="bg-card border border-border rounded-xl p-6 shadow-sm">
        <SkeletonBlock type="card" :lines="3" />
      </div>
    </section>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Left: KB Breakdown & Recommendations -->
      <div class="lg:col-span-2 space-y-8">
        <section v-if="busy.init" class="bg-card border border-border rounded-xl p-6 shadow-sm">
          <SkeletonBlock type="card" :lines="6" />
        </section>
        <LearnerProfileCard v-else :profile="profile" />
        <!-- KB Selector & Stats -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-8">
          <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div class="flex items-center gap-3">
              <Database class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">知识库统计</h2>
            </div>
            <select v-model="selectedKbId" class="bg-background border border-input rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-primary text-sm min-w-[200px]">
              <option disabled value="">选择知识库…</option>
              <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
          </div>

          <div v-if="busy.init" class="py-2">
            <SkeletonBlock type="card" :lines="5" />
          </div>
          <div v-else-if="kbProgress" class="grid grid-cols-2 md:grid-cols-4 gap-6 animate-in fade-in slide-in-from-bottom-2">
            <div v-for="s in kbStatItems" :key="s.label" class="space-y-1">
              <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{{ s.label }}</p>
              <p class="text-xl font-bold">{{ s.value }}</p>
            </div>
          </div>
          <div v-else class="py-12 text-center text-muted-foreground border-2 border-dashed border-border rounded-xl">
            <p>选择知识库以查看详细统计</p>
          </div>
        </section>

        <!-- Recommendations -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Sparkles class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">智能推荐</h2>
            </div>
            <button @click="fetchRecommendations" class="p-2 hover:bg-accent rounded-lg transition-colors" :disabled="busy.recommendations">
              <RefreshCw class="w-5 h-5" :class="{ 'animate-spin': busy.recommendations }" />
            </button>
          </div>

          <div v-if="busy.init" class="space-y-4">
            <SkeletonBlock type="card" :lines="6" />
          </div>
          <div v-else-if="recommendations.length" class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div v-for="item in recommendations" :key="item.doc_id" class="p-5 bg-background border border-border rounded-xl hover:border-primary/30 transition-all group space-y-4">
              <div class="flex items-start justify-between">
                <div class="flex items-center gap-2">
                  <FileText class="w-5 h-5 text-primary" />
                  <h4 class="font-bold truncate max-w-[150px]">{{ item.doc_name || '文档' }}</h4>
                </div>
              </div>
              <div class="flex flex-wrap gap-2">
                <span v-for="action in item.actions" :key="action.type" class="px-2 py-1 bg-primary/10 text-primary text-[10px] font-bold rounded-full uppercase">
                  {{ actionLabel(action.type) }}
                </span>
              </div>
              <div class="space-y-2">
                <div v-for="action in item.actions" :key="`${item.doc_id}-${action.type}`" class="flex gap-2 text-xs">
                  <div class="mt-1 w-1 h-1 bg-primary rounded-full flex-shrink-0"></div>
                  <p class="text-muted-foreground">{{ action.reason }}</p>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="py-12 text-center text-muted-foreground bg-accent/20 rounded-xl">
            <p>该知识库暂无推荐。</p>
          </div>
        </section>

        <!-- Learning Path -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <GitBranch class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">学习路径</h2>
            </div>
            <div class="flex items-center gap-2">
              <button @click="rebuildPath" class="p-2 hover:bg-accent rounded-lg transition-colors text-xs flex items-center gap-1" :disabled="busy.pathBuild">
                <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': busy.pathBuild }" />
                <span class="hidden sm:inline">重建</span>
              </button>
            </div>
          </div>

          <div v-if="busy.init" class="space-y-4">
            <SkeletonBlock type="card" :lines="8" />
          </div>
          <div v-else-if="learningPath.length" class="space-y-4">
            <!-- ECharts graph -->
            <div class="border border-border rounded-lg bg-background p-2" style="height: 376px">
              <VChart ref="pathChartRef" class="w-full" style="height: 360px; display: block;" :option="pathChartOption" autoresize />
            </div>

            <!-- Legend -->
            <div class="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
              <div class="flex items-center gap-2">
                <span class="font-medium text-foreground">文档颜色：</span>
                <span v-for="(color, docName) in docColorLegend" :key="docName" class="inline-flex items-center gap-1">
                  <span class="w-3 h-3 rounded-full inline-block" :style="{ background: color }"></span>
                  <span class="truncate max-w-[100px]">{{ docName }}</span>
                </span>
              </div>
              <span class="text-border">|</span>
              <div class="flex items-center gap-3">
                <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-foreground inline-block"></span> 待学习</span>
                <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-foreground/40 inline-block"></span> 已掌握</span>
              </div>
            </div>

            <!-- Step list (compact) -->
            <details class="group">
              <summary class="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                <ChevronDown class="w-4 h-4 transition-transform group-open:rotate-180" />
                查看详细步骤列表（{{ learningPath.length }} 项）
              </summary>
              <div class="mt-3 space-y-2 max-h-[300px] overflow-y-auto pr-2">
                <div v-for="item in learningPath" :key="item.keypoint_id"
                  class="flex items-start gap-3 p-3 border border-border rounded-lg text-sm"
                  :class="{ 'opacity-50': item.priority === 'completed' }">
                  <span class="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                    :class="stepBadgeClass(item.priority)">
                    {{ item.step }}
                  </span>
                  <div class="flex-1 min-w-0 space-y-1">
                    <p class="font-medium leading-tight">{{ item.text }}</p>
                    <div class="flex items-center gap-2 text-xs text-muted-foreground">
                      <span class="truncate max-w-[120px]">{{ item.doc_name || '文档' }}</span>
                      <span>·</span>
                      <span>掌握度 {{ masteryPercent(item.mastery_level) }}%</span>
                    </div>
                    <div v-if="item.prerequisites.length" class="text-xs text-orange-500">
                      需先学习：{{ item.prerequisites.join('、') }}
                    </div>
                  </div>
                  <button v-if="item.priority !== 'completed'"
                    class="flex-shrink-0 px-3 py-1 bg-primary/10 text-primary rounded-md text-xs font-medium hover:bg-primary/20 transition-colors"
                    @click="goToAction(item)">
                    {{ actionBtnLabel(item.action) }}
                  </button>
                </div>
              </div>
            </details>
          </div>

          <!-- Empty state -->
          <div v-else-if="!busy.recommendations" class="py-12 text-center text-muted-foreground bg-accent/20 rounded-xl space-y-2">
            <GitBranch class="w-10 h-10 mx-auto opacity-30" />
            <p>请先为知识库内的文档生成知识点</p>
            <p class="text-xs">生成知识点后，系统将自动分析知识点间的依赖关系并规划学习路径</p>
          </div>
        </section>
      </div>

    <!-- Right: Activity Feed -->
      <section class="bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col h-[750px]">
        <div class="flex items-center gap-3 mb-6">
          <Activity class="w-6 h-6 text-primary" />
          <h2 class="text-xl font-bold">最近动态</h2>
        </div>

        <div class="flex-1 overflow-y-auto space-y-6 pr-2">
          <div v-if="busy.init" class="space-y-4">
            <SkeletonBlock type="list" :lines="6" />
          </div>
          <div v-else-if="activity.length === 0" class="h-full flex flex-col items-center justify-center text-muted-foreground opacity-30">
            <Clock class="w-12 h-12 mb-2" />
            <p>暂无最近动态</p>
          </div>
          <div v-for="(item, idx) in activity" :key="idx" class="relative pl-6 border-l-2 border-border pb-6 last:pb-0">
            <div class="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-background border-2 border-primary"></div>
            <div class="space-y-1">
              <p class="text-sm font-bold leading-none">{{ activityLabel(item) }}</p>
              <p v-if="item.doc_name" class="text-xs text-primary font-medium">{{ item.doc_name }}</p>
              <p v-if="item.detail" class="text-xs text-muted-foreground">{{ item.detail }}</p>
              <div v-if="item.score !== null" class="mt-2 inline-flex items-center gap-2 px-2 py-1 bg-secondary rounded text-[10px] font-bold">
                得分：{{ Math.round(item.score * 100) }}%（{{ item.total }} 题）
              </div>
              <p class="text-[10px] text-muted-foreground pt-1">{{ new Date(item.timestamp).toLocaleString() }}</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { 
  BarChart2, 
  FileText, 
  PenTool, 
  MessageSquare, 
  Database, 
  Activity, 
  Sparkles, 
  RefreshCw,
  Clock,
  TrendingUp,
  CheckCircle2,
  GitBranch,
  ChevronDown
} from 'lucide-vue-next'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import LearnerProfileCard from '../components/LearnerProfileCard.vue'
import { apiGet, apiPost, getProfile, buildLearningPath } from '../api'
import { useToast } from '../composables/useToast'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import { MASTERY_MASTERED, masteryPercent } from '../utils/mastery'

const { showToast } = useToast()

use([CanvasRenderer, GraphChart, TooltipComponent, LegendComponent])

const router = useRouter()
const userId = ref(localStorage.getItem('gradtutor_user') || 'default')
const resolvedUserId = computed(() => userId.value || 'default')
const progress = ref(null)
const profile = ref(null)
const activity = ref([])
const recommendations = ref([])
const learningPath = ref([])
const learningPathEdges = ref([])
const kbs = ref([])
const selectedKbId = ref('')
const pathChartRef = ref(null)
const busy = ref({
  init: false,
  recommendations: false,
  pathBuild: false,
})

const topStats = computed(() => {
  if (!progress.value) return []
  return [
    { label: '文档数', value: progress.value.total_docs, icon: FileText, color: 'bg-blue-500/10 text-blue-500' },
    { label: '测验数', value: progress.value.total_attempts, icon: PenTool, color: 'bg-orange-500/10 text-orange-500' },
    { label: '问答数', value: progress.value.total_questions, icon: MessageSquare, color: 'bg-green-500/10 text-green-500' },
    { label: '平均分', value: `${Math.round(progress.value.avg_score * 100)}%`, icon: TrendingUp, color: 'bg-purple-500/10 text-purple-500' }
  ]
})

const kbProgress = computed(() => {
  if (!progress.value || !selectedKbId.value) return null
  return progress.value.by_kb.find(k => k.kb_id === selectedKbId.value) || null
})

const kbStatItems = computed(() => {
  if (!kbProgress.value) return []
  return [
    { label: '文档', value: kbProgress.value.total_docs },
    { label: '测验', value: kbProgress.value.total_attempts },
    { label: '问答', value: kbProgress.value.total_questions },
    { label: '平均分', value: `${Math.round(kbProgress.value.avg_score * 100)}%` }
  ]
})

async function fetchProgress() {
  try {
    progress.value = await apiGet(`/api/progress?user_id=${encodeURIComponent(resolvedUserId.value)}`)
  } catch {
    // error toast handled globally
  }
}

async function fetchProfile() {
  try {
    profile.value = await getProfile(resolvedUserId.value)
  } catch {
    // error toast handled globally
  }
}

async function fetchActivity() {
  try {
    const res = await apiGet(`/api/activity?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    activity.value = res.items || []
  } catch {
    // error toast handled globally
  }
}

async function fetchRecommendations() {
  if (!selectedKbId.value) return
  busy.value.recommendations = true
  try {
    const res = await apiGet(`/api/recommendations?user_id=${encodeURIComponent(resolvedUserId.value)}&kb_id=${encodeURIComponent(selectedKbId.value)}&limit=6`)
    recommendations.value = res.items || []
    learningPath.value = res.learning_path || []
    learningPathEdges.value = res.learning_path_edges || []
  } catch {
    // error toast handled globally
  } finally {
    busy.value.recommendations = false
  }
}

async function rebuildPath() {
  if (!selectedKbId.value) return
  busy.value.pathBuild = true
  try {
    await buildLearningPath(resolvedUserId.value, selectedKbId.value, true)
    showToast('学习路径已重建', 'success')
    await fetchRecommendations()
  } catch {
    // error toast handled globally
  } finally {
    busy.value.pathBuild = false
  }
}

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(resolvedUserId.value)}`)
  } catch {
    // error toast handled globally
  }
}

function activityLabel(item) {
  switch (item.type) {
    case 'document_upload': return '上传了文档'
    case 'summary_generated': return '生成了摘要'
    case 'keypoints_generated': return '生成了要点'
    case 'question_asked': return '进行了提问'
    case 'quiz_attempt': return '完成了测验'
    default: return item.type
  }
}

function actionLabel(type) {
  switch (type) {
    case 'summary': return '摘要'
    case 'keypoints': return '要点'
    case 'quiz': return '测验'
    case 'qa': return '问答'
    case 'review': return '复习'
    case 'challenge': return '挑战'
    default: return type
  }
}

// -- Learning path chart --
const DOC_PALETTE = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

const docColorMap = computed(() => {
  const map = {}
  const docIds = [...new Set(learningPath.value.map(i => i.doc_id))]
  docIds.forEach((id, idx) => { map[id] = DOC_PALETTE[idx % DOC_PALETTE.length] })
  return map
})

const docColorLegend = computed(() => {
  const legend = {}
  for (const item of learningPath.value) {
    const name = item.doc_name || item.doc_id
    if (!legend[name]) legend[name] = docColorMap.value[item.doc_id]
  }
  return legend
})

const pathChartOption = computed(() => {
  if (!learningPath.value.length) return {}

  const colors = docColorMap.value
  const nodes = learningPath.value.map((item) => {
    const isMastered = item.mastery_level >= MASTERY_MASTERED
    const sizeMap = { high: 50, medium: 40, low: 30, completed: 25 }
    return {
      id: item.keypoint_id,
      name: item.text.length > 18 ? item.text.slice(0, 18) + '…' : item.text,
      symbolSize: sizeMap[item.priority] || 35,
      itemStyle: {
        color: colors[item.doc_id] || '#666',
        opacity: isMastered ? 0.35 : 1,
        borderColor: isMastered ? '#888' : colors[item.doc_id] || '#666',
        borderWidth: 2,
      },
      label: {
        show: true,
        position: 'bottom',
        fontSize: 10,
        color: 'inherit',
        overflow: 'truncate',
        width: 100,
      },
      tooltip: {
        formatter: () => {
          const prereqs = item.prerequisites.length ? `<br/><span style="color:#f59e0b">前置：${item.prerequisites.join('、')}</span>` : ''
          return `<b>${item.text}</b><br/>文档：${item.doc_name || '—'}<br/>掌握度：${masteryPercent(item.mastery_level)}%<br/>优先级：${item.priority}${prereqs}`
        }
      },
      _raw: item,
    }
  })

  const links = learningPathEdges.value
    .filter(e => nodes.some(n => n.id === e.from_id) && nodes.some(n => n.id === e.to_id))
    .map(e => ({
      source: e.from_id,
      target: e.to_id,
      lineStyle: { color: '#999', width: 1.5, curveness: 0.2 },
      symbol: ['none', 'arrow'],
      symbolSize: [0, 8],
    }))

  return {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.75)', textStyle: { color: '#fff', fontSize: 12 } },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      force: { repulsion: 200, gravity: 0.05, edgeLength: [80, 200] },
      data: nodes,
      links,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 8],
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3 },
      },
      lineStyle: { opacity: 0.6 },
    }],
    animationDuration: 800,
  }
})

function stepBadgeClass(priority) {
  const map = {
    high: 'bg-red-500/15 text-red-600 border border-red-500/30',
    medium: 'bg-yellow-500/15 text-yellow-600 border border-yellow-500/30',
    low: 'bg-green-500/15 text-green-600 border border-green-500/30',
    completed: 'bg-muted text-muted-foreground border border-border',
  }
  return map[priority] || map.medium
}

function actionBtnLabel(action) {
  const map = { study: '去学习', quiz: '去测验', review: '去复习' }
  return map[action] || '去学习'
}

function goToAction(item) {
  if (item.action === 'quiz') {
    router.push('/quiz')
  } else if (item.action === 'study') {
    router.push('/summary')
  } else {
    router.push('/qa')
  }
}

onMounted(async () => {
  busy.value.init = true
  try {
    await Promise.all([fetchProfile(), fetchProgress(), fetchActivity(), refreshKbs()])
  } finally {
    busy.value.init = false
  }
})

watch(selectedKbId, () => {
  fetchRecommendations()
})
</script>
