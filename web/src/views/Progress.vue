<template>
  <div class="space-y-8 max-w-6xl mx-auto">
    <!-- Top Stats Bar -->
    <section v-if="progress" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
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

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Left: KB Breakdown & Recommendations -->
      <div class="lg:col-span-2 space-y-8">
        <!-- KB Selector & Stats -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-8">
          <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div class="flex items-center gap-3">
              <Database class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">Knowledge Base Stats</h2>
            </div>
            <select v-model="selectedKbId" class="bg-background border border-input rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-primary text-sm min-w-[200px]">
              <option disabled value="">Select a Knowledge Base...</option>
              <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
          </div>

          <div v-if="kbProgress" class="grid grid-cols-2 md:grid-cols-4 gap-6 animate-in fade-in slide-in-from-bottom-2">
            <div v-for="s in kbStatItems" :key="s.label" class="space-y-1">
              <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{{ s.label }}</p>
              <p class="text-xl font-bold">{{ s.value }}</p>
            </div>
          </div>
          <div v-else class="py-12 text-center text-muted-foreground border-2 border-dashed border-border rounded-xl">
            <p>Select a knowledge base to see detailed statistics</p>
          </div>
        </section>

        <!-- Recommendations -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Sparkles class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">Smart Recommendations</h2>
            </div>
            <button @click="fetchRecommendations" class="p-2 hover:bg-accent rounded-lg transition-colors" :disabled="busy.recommendations">
              <RefreshCw class="w-5 h-5" :class="{ 'animate-spin': busy.recommendations }" />
            </button>
          </div>

          <div v-if="recommendations.length" class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div v-for="item in recommendations" :key="item.doc_id" class="p-5 bg-background border border-border rounded-xl hover:border-primary/30 transition-all group space-y-4">
              <div class="flex items-start justify-between">
                <div class="flex items-center gap-2">
                  <FileText class="w-5 h-5 text-primary" />
                  <h4 class="font-bold truncate max-w-[150px]">{{ item.doc_name || 'Document' }}</h4>
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
            <p>No recommendations available for this knowledge base.</p>
          </div>
        </section>
      </div>

      <!-- Right: Activity Feed -->
      <section class="bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col h-[750px]">
        <div class="flex items-center gap-3 mb-6">
          <Activity class="w-6 h-6 text-primary" />
          <h2 class="text-xl font-bold">Recent Activity</h2>
        </div>

        <div class="flex-1 overflow-y-auto space-y-6 pr-2">
          <div v-if="activity.length === 0" class="h-full flex flex-col items-center justify-center text-muted-foreground opacity-30">
            <Clock class="w-12 h-12 mb-2" />
            <p>No recent activity</p>
          </div>
          <div v-for="(item, idx) in activity" :key="idx" class="relative pl-6 border-l-2 border-border pb-6 last:pb-0">
            <div class="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-background border-2 border-primary"></div>
            <div class="space-y-1">
              <p class="text-sm font-bold leading-none">{{ activityLabel(item) }}</p>
              <p v-if="item.doc_name" class="text-xs text-primary font-medium">{{ item.doc_name }}</p>
              <p v-if="item.detail" class="text-xs text-muted-foreground">{{ item.detail }}</p>
              <div v-if="item.score !== null" class="mt-2 inline-flex items-center gap-2 px-2 py-1 bg-secondary rounded text-[10px] font-bold">
                SCORE: {{ Math.round(item.score * 100) }}% ({{ item.total }} Qs)
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
  CheckCircle2
} from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'

const userId = ref(localStorage.getItem('gradtutor_user') || '')
const progress = ref(null)
const activity = ref([])
const recommendations = ref([])
const kbs = ref([])
const selectedKbId = ref('')
const busy = ref({
  recommendations: false
})

const topStats = computed(() => {
  if (!progress.value) return []
  return [
    { label: 'Documents', value: progress.value.total_docs, icon: FileText, color: 'bg-blue-500/10 text-blue-500' },
    { label: 'Quizzes', value: progress.value.total_attempts, icon: PenTool, color: 'bg-orange-500/10 text-orange-500' },
    { label: 'Questions', value: progress.value.total_questions, icon: MessageSquare, color: 'bg-green-500/10 text-green-500' },
    { label: 'Avg Score', value: `${Math.round(progress.value.avg_score * 100)}%`, icon: TrendingUp, color: 'bg-purple-500/10 text-purple-500' }
  ]
})

const kbProgress = computed(() => {
  if (!progress.value || !selectedKbId.value) return null
  return progress.value.by_kb.find(k => k.kb_id === selectedKbId.value) || null
})

const kbStatItems = computed(() => {
  if (!kbProgress.value) return []
  return [
    { label: 'Docs', value: kbProgress.value.total_docs },
    { label: 'Quizzes', value: kbProgress.value.total_attempts },
    { label: 'Questions', value: kbProgress.value.total_questions },
    { label: 'Avg Score', value: `${Math.round(kbProgress.value.avg_score * 100)}%` }
  ]
})

async function fetchProgress() {
  try {
    progress.value = await apiGet(`/api/progress?user_id=${encodeURIComponent(userId.value)}`)
  } catch (err) {
    console.error(err)
  }
}

async function fetchActivity() {
  try {
    const res = await apiGet(`/api/activity?user_id=${encodeURIComponent(userId.value)}`)
    activity.value = res.items || []
  } catch (err) {
    console.error(err)
  }
}

async function fetchRecommendations() {
  if (!selectedKbId.value) return
  busy.value.recommendations = true
  try {
    const res = await apiGet(`/api/recommendations?user_id=${encodeURIComponent(userId.value)}&kb_id=${encodeURIComponent(selectedKbId.value)}&limit=6`)
    recommendations.value = res.items || []
  } catch (err) {
    console.error(err)
  } finally {
    busy.value.recommendations = false
  }
}

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(userId.value)}`)
  } catch (err) {
    console.error(err)
  }
}

function activityLabel(item) {
  switch (item.type) {
    case 'document_upload': return 'Uploaded document'
    case 'summary_generated': return 'Summary generated'
    case 'keypoints_generated': return 'Keypoints generated'
    case 'question_asked': return 'Question asked'
    case 'quiz_attempt': return 'Quiz attempt'
    default: return item.type
  }
}

function actionLabel(type) {
  switch (type) {
    case 'summary': return 'Summary'
    case 'keypoints': return 'Keypoints'
    case 'quiz': return 'Quiz'
    case 'qa': return 'Q&A'
    default: return type
  }
}

onMounted(async () => {
  if (userId.value) {
    await fetchProgress()
    await fetchActivity()
    await refreshKbs()
  }
})

watch(selectedKbId, () => {
  fetchRecommendations()
})
</script>
