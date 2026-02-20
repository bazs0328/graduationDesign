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
              <span v-if="recommendationsUpdatedLabel && !busy.init" class="text-xs text-muted-foreground">
                更新于 {{ recommendationsUpdatedLabel }}
              </span>
              <span v-if="busy.recommendations && !busy.init" class="text-sm text-muted-foreground flex items-center gap-2">
                <RefreshCw class="w-4 h-4 animate-spin" />
                <span>正在加载推荐...</span>
              </span>
            </div>
            <button @click="fetchRecommendations" class="p-2 hover:bg-accent rounded-lg transition-colors" :disabled="busy.recommendations">
              <RefreshCw class="w-5 h-5" :class="{ 'animate-spin': busy.recommendations }" />
            </button>
          </div>

          <div v-if="busy.init" class="space-y-4">
            <SkeletonBlock type="card" :lines="6" />
          </div>
          <template v-else>
            <div v-if="nextRecommendation" class="rounded-xl border border-primary/25 bg-primary/5 p-4 space-y-3">
              <p class="text-[10px] font-bold uppercase tracking-widest text-primary">下一步建议</p>
              <div class="flex items-start justify-between gap-3">
                <div class="space-y-1 min-w-0">
                  <p class="text-sm font-semibold truncate">
                    {{ nextRecommendation.doc_name || '文档' }} · {{ actionLabel(nextRecommendation.action?.type) }}
                  </p>
                  <p v-if="nextRecommendation.reason" class="text-xs text-muted-foreground">{{ nextRecommendation.reason }}</p>
                </div>
                <button
                  class="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition-opacity whitespace-nowrap"
                  @click="runRecommendation(nextRecommendation, nextRecommendation.action)"
                >
                  {{ recommendationActionBtnLabel(nextRecommendation.action) }}
                </button>
              </div>
            </div>
            <div v-if="recommendations.length" class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div v-for="item in recommendations" :key="item.doc_id" class="p-5 bg-background border border-border rounded-xl hover:border-primary/30 transition-all group space-y-4">
                <div class="flex items-start justify-between gap-3">
                  <div class="flex items-center gap-2 min-w-0">
                    <FileText class="w-5 h-5 text-primary flex-shrink-0" />
                    <h4 class="font-bold truncate max-w-[180px]">{{ item.doc_name || '文档' }}</h4>
                  </div>
                  <div class="flex flex-col items-end gap-2">
                    <span class="text-[10px] px-2 py-0.5 rounded-full border font-semibold" :class="recommendationStatusClass(item.status)">
                      {{ recommendationStatusLabel(item.status) }}
                    </span>
                    <button
                      v-if="primaryRecommendationAction(item)"
                      class="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-[11px] font-semibold hover:opacity-90 transition-opacity whitespace-nowrap"
                      @click="runRecommendation(item, primaryRecommendationAction(item))"
                    >
                      {{ recommendationActionBtnLabel(primaryRecommendationAction(item)) }}
                    </button>
                  </div>
                </div>
                <p v-if="item.summary" class="text-xs text-muted-foreground">{{ item.summary }}</p>
                <div class="grid grid-cols-2 gap-3 text-[11px]">
                  <div class="rounded-md border border-border bg-accent/30 px-2 py-1.5">
                    <p class="text-muted-foreground">完成度</p>
                    <p class="font-semibold">{{ Math.round(item.completion_score || 0) }}%</p>
                  </div>
                  <div class="rounded-md border border-border bg-accent/30 px-2 py-1.5">
                    <p class="text-muted-foreground">紧急度</p>
                    <p class="font-semibold">{{ Math.round(item.urgency_score || 0) }}</p>
                  </div>
                </div>
                <div class="h-1.5 rounded-full bg-accent overflow-hidden">
                  <div class="h-full bg-primary/80 transition-all duration-500" :style="{ width: `${Math.round(item.completion_score || 0)}%` }"></div>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="action in item.actions"
                    :key="`${item.doc_id}-${action.type}-tag`"
                    class="px-2 py-1 bg-primary/10 text-primary text-[10px] font-bold rounded-full uppercase hover:bg-primary/20 transition-colors"
                    @click="runRecommendation(item, action)"
                  >
                    {{ actionLabel(action.type) }}
                  </button>
                </div>
                <div class="space-y-2">
                  <div v-for="action in item.actions" :key="`${item.doc_id}-${action.type}-reason`" class="flex gap-2 text-xs">
                    <div class="mt-1 w-1 h-1 bg-primary rounded-full flex-shrink-0"></div>
                    <div class="space-y-1">
                      <p class="text-muted-foreground">{{ action.reason }}</p>
                      <p v-if="recommendationActionHint(action)" class="text-[11px] text-primary">{{ recommendationActionHint(action) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="py-12 text-center text-muted-foreground bg-accent/20 rounded-xl">
              <p>该知识库暂无推荐。</p>
            </div>
          </template>
        </section>

        <!-- Learning Path -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <GitBranch class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">学习路径</h2>
              <span v-if="busy.pathLoad && !busy.init" class="text-sm text-muted-foreground flex items-center gap-2">
                <RefreshCw class="w-4 h-4 animate-spin" />
                <span>正在加载学习路径...</span>
              </span>
              <span v-else-if="busy.pathBuild" class="text-sm text-muted-foreground flex items-center gap-2">
                <RefreshCw class="w-4 h-4 animate-spin" />
                <span>正在重建学习路径...</span>
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button @click="rebuildPath" class="p-2 hover:bg-accent rounded-lg transition-colors text-xs flex items-center gap-1" :disabled="busy.pathBuild || busy.pathLoad">
                <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': busy.pathBuild || busy.pathLoad }" />
                <span class="hidden sm:inline">重建</span>
              </button>
            </div>
          </div>

          <div v-if="busy.init || busy.pathLoad || busy.pathBuild" class="space-y-4">
            <SkeletonBlock type="card" :lines="8" />
          </div>
          <div v-else-if="learningPath.length" class="space-y-6">
            <!-- Path summary -->
            <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div v-for="stat in pathSummaryCards" :key="stat.label" class="rounded-lg border border-border bg-background p-3 space-y-1">
                <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{{ stat.label }}</p>
                <p class="text-lg font-extrabold">{{ stat.value }}</p>
              </div>
            </div>

            <!-- Stage & module views -->
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div class="rounded-lg border border-border p-4 space-y-3">
                <h3 class="text-sm font-bold">阶段视图</h3>
                <div class="space-y-3 max-h-[260px] overflow-y-auto pr-1">
                  <div v-for="stage in displayStages" :key="stage.stage_id" class="rounded-lg border border-border bg-background p-3 space-y-2">
                    <div class="flex items-center justify-between gap-2">
                      <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full" :style="{ background: stageColor(stage.stage_id) }"></span>
                        <p class="font-semibold text-sm">{{ stage.name }}</p>
                      </div>
                      <span class="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                        {{ formatMinutes(stage.estimated_time || 0) }}
                      </span>
                    </div>
                    <p class="text-xs text-muted-foreground">{{ stage.description }}</p>
                    <div class="h-2 rounded-full bg-accent overflow-hidden">
                      <div class="h-full bg-primary transition-all duration-500" :style="{ width: `${stageProgress(stage)}%` }"></div>
                    </div>
                    <div class="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>进度 {{ stageProgress(stage) }}%</span>
                      <span>知识点 {{ stage.keypoint_ids.length }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="rounded-lg border border-border p-4 space-y-3">
                <h3 class="text-sm font-bold">模块视图</h3>
                <div class="space-y-3 max-h-[260px] overflow-y-auto pr-1">
                  <div v-for="module in displayModules" :key="module.module_id" class="rounded-lg border border-border bg-background p-3 space-y-2">
                    <div class="flex items-center justify-between gap-2">
                      <p class="font-semibold text-sm truncate">{{ module.name }}</p>
                      <span class="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                        {{ formatMinutes(module.estimated_time || 0) }}
                      </span>
                    </div>
                    <p class="text-xs text-muted-foreground">{{ module.description }}</p>
                    <div class="h-2 rounded-full bg-accent overflow-hidden">
                      <div class="h-full bg-emerald-500 transition-all duration-500" :style="{ width: `${moduleProgress(module)}%` }"></div>
                    </div>
                    <div class="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>进度 {{ moduleProgress(module) }}%</span>
                      <span>知识点 {{ module.keypoint_ids.length }}</span>
                    </div>
                    <p v-if="module.prerequisite_modules?.length" class="text-[11px] text-orange-500">
                      前置模块：{{ modulePrereqLabels(module).join('、') }}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <!-- ECharts graph -->
            <div class="border border-border rounded-lg bg-background p-2" style="height: 396px">
              <VChart ref="pathChartRef" class="w-full" style="height: 380px; display: block;" :option="pathChartOption" autoresize />
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
              <div class="flex items-center gap-2">
                <span class="font-medium text-foreground">阶段：</span>
                <span v-for="stage in displayStages" :key="stage.stage_id" class="inline-flex items-center gap-1">
                  <span class="w-2.5 h-2.5 rounded-full inline-block" :style="{ background: stageColor(stage.stage_id) }"></span>
                  <span>{{ stage.name }}</span>
                </span>
              </div>
              <span class="text-border">|</span>
              <div class="flex items-center gap-3">
                <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-foreground inline-block"></span> 待学习</span>
                <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-foreground/40 inline-block"></span> 已掌握</span>
                <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rotate-45 bg-primary/40 inline-block"></span> 里程碑</span>
              </div>
            </div>

            <!-- Step list -->
            <details class="group">
              <summary class="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                <ChevronDown class="w-4 h-4 transition-transform group-open:rotate-180" />
                查看详细步骤列表（{{ learningPath.length }} 项）
              </summary>
              <div class="mt-3 space-y-2 max-h-[320px] overflow-y-auto pr-2">
                <div v-for="item in learningPath" :key="item.keypoint_id"
                  class="flex items-start gap-3 p-3 border border-border rounded-lg text-sm"
                  :class="{ 'opacity-50': item.priority === 'completed' }">
                  <span class="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                    :class="stepBadgeClass(item.priority)">
                    {{ item.step }}
                  </span>
                  <div class="flex-1 min-w-0 space-y-1">
                    <div class="flex items-center gap-2 flex-wrap">
                      <p class="font-medium leading-tight">{{ item.text }}</p>
                      <span v-if="item.milestone" class="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-semibold">里程碑</span>
                    </div>
                    <div class="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                      <span class="truncate max-w-[120px]">{{ item.doc_name || '文档' }}</span>
                      <span>·</span>
                      <span>{{ stageLabel(item.stage) }}</span>
                      <span>·</span>
                      <span>掌握度 {{ masteryPercent(item.mastery_level) }}%</span>
                      <span>·</span>
                      <span>难度 {{ Math.round((item.difficulty || 0) * 100) }}</span>
                      <span>·</span>
                      <span>约 {{ item.estimated_time || 0 }} 分钟</span>
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
          <div v-else-if="!busy.pathLoad && !busy.pathBuild" class="py-12 text-center text-muted-foreground bg-accent/20 rounded-xl space-y-2">
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
import { useRoute, useRouter } from 'vue-router'
import {
  FileText,
  PenTool,
  MessageSquare,
  Database,
  Activity,
  Sparkles,
  RefreshCw,
  Clock,
  TrendingUp,
  GitBranch,
  ChevronDown,
} from 'lucide-vue-next'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import LearnerProfileCard from '../components/LearnerProfileCard.vue'
import { apiGet, getProfile, buildLearningPath } from '../api'
import { useToast } from '../composables/useToast'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import { MASTERY_MASTERED, masteryPercent } from '../utils/mastery'

const { showToast } = useToast()

use([CanvasRenderer, GraphChart, TooltipComponent, LegendComponent, GraphicComponent])

const STAGE_ORDER = ['foundation', 'intermediate', 'advanced', 'application']
const STAGE_META = {
  foundation: { name: '基础阶段', description: '先建立核心概念与术语理解。' },
  intermediate: { name: '进阶阶段', description: '连接概念并形成系统化理解。' },
  advanced: { name: '高级阶段', description: '攻克复杂推理与综合分析问题。' },
  application: { name: '应用阶段', description: '迁移到实战场景并完成综合应用。' },
}
const STAGE_COLOR_MAP = {
  foundation: '#3b82f6',
  intermediate: '#10b981',
  advanced: '#f59e0b',
  application: '#ef4444',
}

const router = useRouter()
const route = useRoute()
const userId = ref(localStorage.getItem('gradtutor_user') || 'default')
const resolvedUserId = computed(() => userId.value || 'default')
const progress = ref(null)
const profile = ref(null)
const activity = ref([])
const recommendations = ref([])
const nextRecommendation = ref(null)
const recommendationsUpdatedAt = ref('')
const learningPath = ref([])
const learningPathEdges = ref([])
const learningPathStages = ref([])
const learningPathModules = ref([])
const learningPathSummary = ref({})
const kbs = ref([])
const selectedKbId = ref('')
const pathChartRef = ref(null)
const busy = ref({
  init: false,
  recommendations: false,
  pathLoad: false,
  pathBuild: false,
})

const topStats = computed(() => {
  if (!progress.value) return []
  return [
    { label: '文档数', value: progress.value.total_docs, icon: FileText, color: 'bg-blue-500/10 text-blue-500' },
    { label: '测验数', value: progress.value.total_attempts, icon: PenTool, color: 'bg-orange-500/10 text-orange-500' },
    { label: '问答数', value: progress.value.total_questions, icon: MessageSquare, color: 'bg-green-500/10 text-green-500' },
    { label: '平均分', value: `${Math.round(progress.value.avg_score * 100)}%`, icon: TrendingUp, color: 'bg-purple-500/10 text-purple-500' },
  ]
})

const kbProgress = computed(() => {
  if (!progress.value || !selectedKbId.value) return null
  return progress.value.by_kb.find((kb) => kb.kb_id === selectedKbId.value) || null
})

const kbStatItems = computed(() => {
  if (!kbProgress.value) return []
  return [
    { label: '文档', value: kbProgress.value.total_docs },
    { label: '测验', value: kbProgress.value.total_attempts },
    { label: '问答', value: kbProgress.value.total_questions },
    { label: '平均分', value: `${Math.round(kbProgress.value.avg_score * 100)}%` },
  ]
})

const itemById = computed(() => {
  const map = {}
  for (const item of learningPath.value) {
    map[item.keypoint_id] = item
  }
  return map
})

const displayStages = computed(() => {
  if (learningPathStages.value.length) return learningPathStages.value
  if (!learningPath.value.length) return []
  const grouped = {}
  for (const item of learningPath.value) {
    const stageId = item.stage || 'foundation'
    if (!grouped[stageId]) grouped[stageId] = []
    grouped[stageId].push(item)
  }
  return STAGE_ORDER
    .filter((stageId) => grouped[stageId]?.length)
    .map((stageId) => ({
      stage_id: stageId,
      name: stageLabel(stageId),
      description: STAGE_META[stageId]?.description || '',
      keypoint_ids: grouped[stageId].map((item) => item.keypoint_id),
      estimated_time: grouped[stageId].reduce((sum, item) => sum + (item.estimated_time || 0), 0),
      milestone_keypoint_id: grouped[stageId].find((item) => item.milestone)?.keypoint_id || grouped[stageId][grouped[stageId].length - 1]?.keypoint_id,
    }))
})

const displayModules = computed(() => {
  if (learningPathModules.value.length) return learningPathModules.value
  if (!learningPath.value.length) return []
  const grouped = {}
  for (const item of learningPath.value) {
    const moduleId = item.module || `doc-${item.doc_id}`
    if (!grouped[moduleId]) {
      grouped[moduleId] = {
        module_id: moduleId,
        name: item.doc_name ? `${item.doc_name}模块` : `模块 ${Object.keys(grouped).length + 1}`,
        description: '按文档自动分组的学习模块。',
        keypoint_ids: [],
        prerequisite_modules: [],
        estimated_time: 0,
      }
    }
    grouped[moduleId].keypoint_ids.push(item.keypoint_id)
    grouped[moduleId].estimated_time += item.estimated_time || 0
  }
  return Object.values(grouped)
})

const moduleNameMap = computed(() => {
  const map = {}
  for (const module of displayModules.value) {
    map[module.module_id] = module.name
  }
  return map
})

const summaryResolved = computed(() => {
  if (learningPathSummary.value && Object.keys(learningPathSummary.value).length) {
    return learningPathSummary.value
  }
  const totalItems = learningPath.value.length
  const completedItems = learningPath.value.filter((item) => item.priority === 'completed').length
  const totalEstimatedTime = learningPath.value.reduce((sum, item) => sum + (item.estimated_time || 0), 0)
  let currentStage = 'completed'
  for (const stage of displayStages.value) {
    const unfinished = stage.keypoint_ids.some((keypointId) => itemById.value[keypointId]?.priority !== 'completed')
    if (unfinished) {
      currentStage = stage.stage_id
      break
    }
  }
  return {
    total_items: totalItems,
    completed_items: completedItems,
    completion_rate: totalItems ? completedItems / totalItems : 0,
    total_estimated_time: totalEstimatedTime,
    stages_count: displayStages.value.length,
    modules_count: displayModules.value.length,
    current_stage: currentStage,
    current_stage_label: currentStage === 'completed' ? '全部完成' : stageLabel(currentStage),
  }
})

const pathSummaryCards = computed(() => {
  const summary = summaryResolved.value
  return [
    { label: '总时长', value: formatMinutes(summary.total_estimated_time || 0) },
    { label: '阶段数', value: summary.stages_count || 0 },
    { label: '模块数', value: summary.modules_count || 0 },
    { label: '完成度', value: `${Math.round((summary.completion_rate || 0) * 100)}%` },
    { label: '当前阶段', value: summary.current_stage_label || stageLabel(summary.current_stage) },
  ]
})

const recommendationsUpdatedLabel = computed(() => {
  if (!recommendationsUpdatedAt.value) return ''
  const dt = new Date(recommendationsUpdatedAt.value)
  if (Number.isNaN(dt.getTime())) return ''
  return dt.toLocaleString()
})

function normalizeRecommendationAction(action) {
  if (!action || typeof action !== 'object') return null
  const fallbackPriorityMap = {
    summary: 100,
    keypoints: 95,
    review: 85,
    quiz: 80,
    qa: 65,
    challenge: 55,
  }
  return {
    ...action,
    priority: Number(action.priority) || fallbackPriorityMap[action.type] || 50,
  }
}

function normalizeRecommendationItems(items) {
  if (!Array.isArray(items)) return []
  return items.map((item) => ({
    ...item,
    completion_score: Number(item.completion_score) || 0,
    urgency_score: Number(item.urgency_score) || 0,
    actions: (item.actions || [])
      .map((action) => normalizeRecommendationAction(action))
      .filter(Boolean)
      .sort((a, b) => (b.priority || 0) - (a.priority || 0)),
  }))
}

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
  nextRecommendation.value = null
  recommendationsUpdatedAt.value = ''
  try {
    const res = await apiGet(`/api/recommendations?user_id=${encodeURIComponent(resolvedUserId.value)}&kb_id=${encodeURIComponent(selectedKbId.value)}&limit=6`)
    recommendations.value = normalizeRecommendationItems(res.items || [])
    nextRecommendation.value = res.next_step || null
    recommendationsUpdatedAt.value = res.generated_at || ''
  } catch {
    recommendations.value = []
    // error toast handled globally
  } finally {
    busy.value.recommendations = false
  }
}

async function fetchLearningPath() {
  if (!selectedKbId.value) return
  busy.value.pathLoad = true
  try {
    const res = await apiGet(`/api/learning-path?user_id=${encodeURIComponent(resolvedUserId.value)}&kb_id=${encodeURIComponent(selectedKbId.value)}&limit=20`)
    learningPath.value = res.items || []
    learningPathEdges.value = res.edges || []
    learningPathStages.value = res.stages || []
    learningPathModules.value = res.modules || []
    learningPathSummary.value = res.path_summary || {}
  } catch {
    // error toast handled globally
  } finally {
    busy.value.pathLoad = false
  }
}

async function rebuildPath() {
  if (!selectedKbId.value) return
  busy.value.pathBuild = true
  try {
    await buildLearningPath(resolvedUserId.value, selectedKbId.value, true)
    showToast('学习路径已重建', 'success')
    await fetchLearningPath()
  } catch {
    // error toast handled globally
  } finally {
    busy.value.pathBuild = false
  }
}

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    const queryKbId = normalizeQueryString(route.query.kb_id)
    const hasSelected = !!selectedKbId.value && kbs.value.some((kb) => kb.id === selectedKbId.value)
    if (queryKbId && kbs.value.some((kb) => kb.id === queryKbId)) {
      selectedKbId.value = queryKbId
    } else if (!hasSelected && kbs.value.length > 0) {
      selectedKbId.value = kbs.value[0].id
    }
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

function normalizeQueryString(value) {
  if (Array.isArray(value)) {
    return value[0] || ''
  }
  return typeof value === 'string' ? value : ''
}

function normalizeDifficulty(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'easy' || normalized === 'medium' || normalized === 'hard') {
    return normalized
  }
  return ''
}

function difficultyLabel(value) {
  const normalized = normalizeDifficulty(value)
  if (normalized === 'easy') return '简单'
  if (normalized === 'medium') return '中等'
  if (normalized === 'hard') return '困难'
  return ''
}

function recommendationFocusConcept(action) {
  const concepts = action?.params?.focus_concepts
  if (!Array.isArray(concepts)) return ''
  const first = concepts.find((item) => typeof item === 'string' && item.trim())
  return first ? first.trim() : ''
}

function recommendationActionHint(action) {
  if (!action) return ''
  if (action.type === 'quiz') {
    const label = difficultyLabel(action?.params?.difficulty)
    if (label) {
      return `推荐难度：${label}`
    }
  }
  if (action.type === 'review') {
    const concepts = action?.params?.focus_concepts
    if (Array.isArray(concepts) && concepts.length) {
      return `重点：${concepts.slice(0, 3).join('、')}`
    }
  }
  if (action.type === 'challenge') {
    const label = difficultyLabel(action?.params?.difficulty)
    if (label) {
      return `建议难度：${label}`
    }
  }
  return ''
}

function primaryRecommendationAction(item) {
  const actions = item?.actions || []
  if (!actions.length) return null
  return [...actions].sort((a, b) => (b.priority || 0) - (a.priority || 0))[0]
}

function recommendationActionBtnLabel(action) {
  if (action?.cta) return action.cta
  switch (action?.type) {
    case 'summary': return '去生成摘要'
    case 'keypoints': return '去提取要点'
    case 'quiz': return '去测验'
    case 'qa': return '去问答'
    case 'review': return '去复习'
    case 'challenge': return '去挑战'
    default: return '去执行'
  }
}

function recommendationStatusLabel(status) {
  switch (status) {
    case 'blocked': return '待准备'
    case 'ready_for_practice': return '待练习'
    case 'needs_practice': return '需巩固'
    case 'ready_for_challenge': return '可挑战'
    case 'on_track': return '进行中'
    default: return '待处理'
  }
}

function recommendationStatusClass(status) {
  switch (status) {
    case 'blocked': return 'text-red-700 bg-red-50 border-red-200'
    case 'ready_for_practice': return 'text-amber-700 bg-amber-50 border-amber-200'
    case 'needs_practice': return 'text-orange-700 bg-orange-50 border-orange-200'
    case 'ready_for_challenge': return 'text-emerald-700 bg-emerald-50 border-emerald-200'
    case 'on_track': return 'text-blue-700 bg-blue-50 border-blue-200'
    default: return 'text-muted-foreground bg-accent border-border'
  }
}

function runRecommendation(item, action) {
  if (!action) return
  const focusConcept = recommendationFocusConcept(action)
  switch (action.type) {
    case 'summary':
    case 'keypoints': {
      if (!item?.doc_id) return
      router.push({
        path: '/summary',
        query: { doc_id: item.doc_id },
      })
      return
    }
    case 'quiz':
    case 'challenge': {
      const query = {}
      if (selectedKbId.value) query.kb_id = selectedKbId.value
      if (focusConcept) query.focus = focusConcept
      const difficulty = normalizeDifficulty(action?.params?.difficulty)
      if (difficulty) query.difficulty = difficulty
      router.push({ path: '/quiz', query })
      return
    }
    case 'qa':
    case 'review': {
      const query = {}
      if (selectedKbId.value) query.kb_id = selectedKbId.value
      if (item?.doc_id) query.doc_id = item.doc_id
      if (focusConcept) query.focus = focusConcept
      router.push({ path: '/qa', query })
      return
    }
    default:
      return
  }
}

function stageLabel(stageId) {
  return STAGE_META[stageId]?.name || stageId || '阶段'
}

function stageColor(stageId) {
  return STAGE_COLOR_MAP[stageId] || '#64748b'
}

function formatMinutes(minutes) {
  const m = Number(minutes) || 0
  if (m >= 60) {
    const h = Math.floor(m / 60)
    const r = m % 60
    return r ? `${h}h${r}m` : `${h}h`
  }
  return `${m}m`
}

function stageProgress(stage) {
  if (!stage?.keypoint_ids?.length) return 0
  const completed = stage.keypoint_ids.filter((keypointId) => itemById.value[keypointId]?.priority === 'completed').length
  return Math.round((completed / stage.keypoint_ids.length) * 100)
}

function moduleProgress(module) {
  if (!module?.keypoint_ids?.length) return 0
  const completed = module.keypoint_ids.filter((keypointId) => itemById.value[keypointId]?.priority === 'completed').length
  return Math.round((completed / module.keypoint_ids.length) * 100)
}

function modulePrereqLabels(module) {
  return (module.prerequisite_modules || []).map((moduleId) => moduleNameMap.value[moduleId] || moduleId)
}

// -- Learning path chart --
const DOC_PALETTE = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

const docColorMap = computed(() => {
  const map = {}
  const docIds = [...new Set(learningPath.value.map((item) => item.doc_id))]
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
  const stageIds = displayStages.value.length
    ? displayStages.value.map((stage) => stage.stage_id)
    : [...new Set(learningPath.value.map((item) => item.stage || 'foundation'))]
  const stageIndexMap = {}
  stageIds.forEach((stageId, idx) => { stageIndexMap[stageId] = idx })

  const stageCounts = {}
  const nodes = learningPath.value.map((item) => {
    const stageId = item.stage || 'foundation'
    const rowIdx = stageCounts[stageId] || 0
    stageCounts[stageId] = rowIdx + 1
    const stageIdx = stageIndexMap[stageId] ?? 0
    const isMastered = item.mastery_level >= MASTERY_MASTERED
    const baseSize = 24 + Math.round((item.importance || 0.5) * 18)
    return {
      id: item.keypoint_id,
      name: item.text.length > 20 ? `${item.text.slice(0, 20)}…` : item.text,
      x: 80 + stageIdx * 240 + (item.milestone ? 12 : 0),
      y: 60 + rowIdx * 86,
      symbol: item.milestone ? 'diamond' : 'circle',
      symbolSize: item.milestone ? baseSize + 6 : baseSize,
      itemStyle: {
        color: colors[item.doc_id] || '#666',
        opacity: isMastered ? 0.35 : 1,
        borderColor: stageColor(stageId),
        borderWidth: item.milestone ? 3 : 2,
      },
      label: {
        show: true,
        position: 'bottom',
        fontSize: 10,
        color: 'inherit',
        overflow: 'truncate',
        width: 120,
      },
      tooltip: {
        formatter: () => {
          const prereqs = item.prerequisites.length ? `<br/><span style="color:#f59e0b">前置：${item.prerequisites.join('、')}</span>` : ''
          return `<b>${item.text}</b><br/>阶段：${stageLabel(stageId)}<br/>模块：${item.module || '—'}<br/>掌握度：${masteryPercent(item.mastery_level)}%<br/>难度：${Math.round((item.difficulty || 0) * 100)}<br/>重要性：${Math.round((item.importance || 0) * 100)}<br/>预计时长：${item.estimated_time || 0} 分钟${prereqs}`
        },
      },
    }
  })

  const nodeIdSet = new Set(nodes.map((node) => node.id))
  const links = learningPathEdges.value
    .filter((edge) => nodeIdSet.has(edge.from_id) && nodeIdSet.has(edge.to_id))
    .map((edge) => {
      const targetStage = itemById.value[edge.to_id]?.stage
      return {
        source: edge.from_id,
        target: edge.to_id,
        lineStyle: { color: stageColor(targetStage), width: 1.4, curveness: 0.06, opacity: 0.65 },
        symbol: ['none', 'arrow'],
        symbolSize: [0, 8],
      }
    })

  const graphics = stageIds.map((stageId, idx) => ({
    type: 'text',
    left: 55 + idx * 240,
    top: 8,
    style: {
      text: stageLabel(stageId),
      fill: '#94a3b8',
      fontSize: 12,
      fontWeight: 600,
    },
  }))

  return {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.75)', textStyle: { color: '#fff', fontSize: 12 } },
    graphic: graphics,
    series: [{
      type: 'graph',
      layout: 'none',
      roam: true,
      draggable: true,
      data: nodes,
      links,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 8],
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 2.5 },
      },
      lineStyle: { opacity: 0.65 },
    }],
    animationDuration: 650,
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
    router.push({
      path: '/quiz',
      query: {
        kb_id: selectedKbId.value || '',
        focus: item.text || '',
      },
    })
    return
  }
  router.push({
    path: '/qa',
    query: {
      kb_id: selectedKbId.value || '',
      focus: item.text || '',
    },
  })
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
  if (selectedKbId.value) {
    fetchRecommendations()
    fetchLearningPath()
  }
})

watch(
  () => normalizeQueryString(route.query.kb_id),
  (queryKbId) => {
    if (!queryKbId) return
    if (kbs.value.some((kb) => kb.id === queryKbId)) {
      selectedKbId.value = queryKbId
    }
  }
)
</script>
