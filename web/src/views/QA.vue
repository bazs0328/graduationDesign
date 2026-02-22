<template>
  <div class="h-full flex flex-col max-w-6xl mx-auto">
    <!-- Learning Path Context Banner -->
    <section
      v-if="entryFocusContext"
      class="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 mb-4 space-y-1"
    >
      <p class="text-[10px] font-bold uppercase tracking-widest text-primary">学习路径上下文</p>
      <p class="text-sm text-muted-foreground">
        当前学习目标：<span class="font-semibold text-foreground">{{ entryFocusContext }}</span>
      </p>
      <p class="text-xs text-muted-foreground mt-1">
        你可以针对这个知识点提问，AI 会为你详细讲解。
      </p>
    </section>
    <div class="flex-1 flex gap-8 overflow-hidden min-h-0">
      <!-- Left: Chat Interface -->
      <section class="flex-1 flex flex-col bg-card border border-border rounded-xl shadow-sm overflow-hidden">
        <!-- Header -->
        <div class="p-4 border-b border-border flex items-center justify-between bg-card/50">
          <div class="flex items-center gap-3">
            <MessageSquare class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">AI 辅导对话</h2>
          </div>
          <button @click="clearLocalMessages" class="p-2 hover:bg-accent rounded-lg transition-colors text-muted-foreground" title="仅清空本地显示">
            <Trash2 class="w-5 h-5" />
          </button>
        </div>

        <!-- Messages -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6" ref="scrollContainer">
          <EmptyState
            v-if="qaMessages.length === 0"
            class="h-full max-w-md mx-auto"
            :icon="Sparkles"
            :title="qaEmptyTitle"
            :description="qaEmptyDescription"
            :hint="qaEmptyHint"
            size="lg"
            :primary-action="qaEmptyPrimaryAction"
            @primary="handleQaEmptyPrimary"
          />
          
          <div v-for="(msg, index) in qaMessages" :key="index" class="flex flex-col" :class="msg.role === 'question' ? 'items-end' : 'items-start'">
            <div 
              class="max-w-[85%] p-4 rounded-2xl shadow-sm"
              :class="msg.role === 'question' ? 'bg-primary text-primary-foreground rounded-tr-none' : 'bg-accent text-accent-foreground rounded-tl-none'"
            >
              <div class="flex items-center gap-2 mb-1 opacity-70 text-[10px] font-bold uppercase tracking-wider">
                <component :is="msg.role === 'question' ? 'User' : 'Bot'" class="w-3 h-3" />
                {{ msg.role === 'question' ? '你' : 'AI 辅导' }}
                <span
                  v-if="msg.role !== 'question' && msg.abilityLevel"
                  class="ml-auto px-1.5 py-0.5 rounded-full border text-[9px] font-semibold normal-case tracking-normal"
                  :class="getLevelMeta(msg.abilityLevel).badgeClass"
                >
                  {{ getLevelMeta(msg.abilityLevel).text }}
                </span>
              </div>
              <p v-if="msg.role === 'question'" class="text-sm leading-relaxed whitespace-pre-wrap">{{ msg.content }}</p>
              <div v-else class="qa-markdown markdown-content" v-html="renderMarkdown(msg.content)"></div>
              
              <!-- Sources -->
              <div v-if="msg.sources && msg.sources.length" class="mt-4 pt-3 border-t border-accent-foreground/10 space-y-2">
                <p class="text-[10px] font-bold uppercase opacity-50">参考来源：</p>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="(source, sIdx) in msg.sources"
                    :key="sIdx"
                    class="text-[10px] bg-background/50 px-2 py-1 rounded-md flex items-center gap-1.5 border border-accent-foreground/5 hover:border-primary/40 hover:text-primary transition-colors"
                    @click="openQaSource(source)"
                  >
                    <FileText class="w-3 h-3 text-primary" />
                    <span class="font-medium truncate max-w-[120px]">{{ source.source }}</span>
                    <span v-if="source.page" class="opacity-50">p.{{ source.page }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-if="busy.qa" class="flex items-start">
            <div class="bg-accent text-accent-foreground p-4 rounded-2xl rounded-tl-none shadow-sm flex items-center gap-3">
              <div class="flex gap-1">
                <div class="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style="animation-delay: 0s"></div>
                <div class="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                <div class="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style="animation-delay: 0.4s"></div>
              </div>
              <span class="text-xs font-medium opacity-70">辅导正在思考…</span>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="p-4 border-t border-border bg-card/50">
          <div class="flex gap-2">
            <textarea
              v-model="qaInput"
              @keydown.enter.prevent="askQuestion"
              :placeholder="entryFocusContext ? `关于「${entryFocusContext}」，你想了解什么？` : '在此输入你的问题…'"
              class="flex-1 bg-background border border-input rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-primary resize-none h-[52px]"
              :disabled="!selectedKbId || busy.qa"
            ></textarea>
            <button
              @click="askQuestion"
              class="bg-primary text-primary-foreground p-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center"
              :disabled="!selectedKbId || !qaInput.trim() || busy.qa"
            >
              <Send class="w-6 h-6" />
            </button>
          </div>
          <p v-if="!selectedKbId" class="text-[10px] text-destructive mt-2 text-center font-bold uppercase tracking-widest">
            请先选择知识库
          </p>
        </div>
      </section>

      <!-- Right: Knowledge Base Selection -->
      <aside class="w-72 space-y-6 flex flex-col">
        <div class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
          <div class="flex items-center gap-3">
            <Database class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">上下文</h2>
          </div>
          <template v-if="busy.init">
            <SkeletonBlock type="list" :lines="3" />
          </template>
          <template v-else>
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">选择知识库</label>
              <select v-model="selectedKbId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                <option disabled value="">请选择</option>
                <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name || kb.id }}</option>
              </select>
            </div>
            <div class="space-y-2" v-if="selectedKbId">
              <div class="flex items-center gap-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">限定文档 (可选)</label>
                <LoadingSpinner v-if="busy.docs" size="sm" />
              </div>
              <select v-model="selectedDocId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                <option value="">不限定（整库问答）</option>
                <option v-for="doc in docsInKb" :key="doc.id" :value="doc.id">{{ doc.filename }}</option>
              </select>
            </div>
          </template>
        </div>

        <div class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-3">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground">会话管理</h3>
            <button
              class="text-[10px] font-semibold px-2 py-1 rounded border border-border hover:bg-accent"
              :disabled="busy.sessionAction || !selectedKbId"
              @click="createSession"
            >
              新建会话
            </button>
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">历史会话</label>
            <select
              v-model="selectedSessionId"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
            >
              <option value="">未选择（将自动新建）</option>
              <option v-for="session in sessions" :key="session.id" :value="session.id">
                {{ sessionLabel(session) }}
              </option>
            </select>
          </div>
          <div v-if="selectedSessionId" class="space-y-2">
            <input
              v-model="sessionTitleInput"
              type="text"
              placeholder="会话名称"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
            />
            <div class="grid grid-cols-3 gap-2">
              <button
                class="text-xs py-2 rounded border border-border hover:bg-accent"
                :disabled="busy.sessionAction"
                @click="renameCurrentSession"
              >
                重命名
              </button>
              <button
                class="text-xs py-2 rounded border border-border hover:bg-accent"
                :disabled="busy.sessionAction"
                @click="clearCurrentSessionMessages"
              >
                清空消息
              </button>
              <button
                class="text-xs py-2 rounded border border-destructive/40 text-destructive hover:bg-destructive/10"
                :disabled="busy.sessionAction"
                @click="deleteCurrentSession"
              >
                删除会话
              </button>
            </div>
          </div>
          <p class="text-[10px] text-muted-foreground">
            顶部垃圾桶仅清空本地显示，不会清空服务端会话消息。
          </p>
        </div>

        <div class="flex-1 bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col min-h-0">
          <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-4">简要统计</h3>
          <div v-if="busy.init" class="mt-2">
            <SkeletonBlock type="card" :lines="5" />
          </div>
          <div v-else-if="selectedKb" class="space-y-4 overflow-y-auto pr-2">
            <div class="p-3 bg-accent/30 rounded-lg border border-border">
              <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">当前知识库</p>
              <p class="text-sm font-semibold truncate">{{ selectedKb.name || selectedKb.id }}</p>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">总文档</p>
                <p class="text-lg font-bold">{{ docsInKb.length }}</p>
              </div>
              <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">相关会话</p>
                <p class="text-lg font-bold">{{ selectedKbSessions.length }}</p>
              </div>
              <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">就绪</p>
                <p class="text-lg font-bold text-green-600">{{ docsReadyCount }}</p>
              </div>
              <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">处理中/失败</p>
                <p class="text-lg font-bold">
                  <span class="text-blue-600">{{ docsProcessingCount }}</span>/<span class="text-destructive">{{ docsErrorCount }}</span>
                </p>
              </div>
            </div>
            <div class="p-3 bg-accent/20 rounded-lg border border-border">
              <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">当前会话消息数</p>
              <p class="text-sm font-semibold">{{ qaMessages.length }} 条</p>
            </div>
            
            <!-- Doc Stats -->
            <div v-if="selectedDoc" class="space-y-4">
              <div class="p-3 bg-accent/30 rounded-lg border border-border">
                <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">当前文档</p>
                <p class="text-sm font-semibold truncate">{{ selectedDoc.filename }}</p>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                  <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">页数</p>
                  <p class="text-lg font-bold">{{ selectedDoc.num_pages }}</p>
                </div>
                <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                  <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">块数</p>
                  <p class="text-lg font-bold">{{ selectedDoc.num_chunks }}</p>
                </div>
              </div>
            </div>
            <div v-else class="p-3 bg-accent/30 rounded-lg border border-border">
              <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">用途说明</p>
              <p class="text-sm text-muted-foreground leading-relaxed">
                这里用于快速确认问答上下文：当前知识库状态、文档处理进度与会话规模。
              </p>
            </div>
          </div>
          <EmptyState
            v-else
            :icon="FileText"
            title="选择知识库后查看统计"
            description="右侧会展示当前问答上下文、文档状态和会话规模。"
            hint="先选择知识库，再开始提问或切换会话。"
            size="sm"
          />
        </div>

        <div class="bg-card border border-border rounded-xl p-4 shadow-sm">
          <p class="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">学习适应等级</p>
          <div class="mt-2 flex items-center justify-between gap-3">
            <p class="text-sm font-semibold">{{ currentLevelMeta.text }}</p>
            <span class="text-[10px] font-semibold px-2 py-1 rounded-full border" :class="currentLevelMeta.badgeClass">
              {{ currentLevelMeta.code }}
            </span>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">{{ currentLevelMeta.description }}</p>
        </div>
      </aside>
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
import { ref, onMounted, onActivated, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessageSquare, Send, Trash2, Database, FileText, Sparkles, User, Bot } from 'lucide-vue-next'
import { apiDelete, apiGet, apiPatch, apiPost } from '../api'
import { useToast } from '../composables/useToast'
import { useAppContextStore } from '../stores/appContext'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import SourcePreviewModal from '../components/ui/SourcePreviewModal.vue'
import { renderMarkdown } from '../utils/markdown'
import { parseRouteContext } from '../utils/routeContext'

const { showToast } = useToast()
const appContext = useAppContextStore()
appContext.hydrate()
const router = useRouter()
const route = useRoute()

const resolvedUserId = computed(() => appContext.resolvedUserId || 'default')
const kbs = computed(() => appContext.kbs)
const docsInKb = ref([])
const sessions = ref([])
const selectedKbId = computed({
  get: () => appContext.selectedKbId,
  set: (value) => appContext.setSelectedKbId(value),
})
const selectedDocId = computed({
  get: () => appContext.selectedDocId,
  set: (value) => appContext.setSelectedDocId(value),
})
const selectedSessionId = ref('')
const sessionTitleInput = ref('')
const qaInput = ref('')
const qaMessages = ref([])
const qaAbilityLevel = ref('intermediate')
const syncingFromSession = ref(false)
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
  qa: false,
  init: false,
  docs: false,
  sessions: false,
  sessionAction: false
})
const scrollContainer = ref(null)

const LEVEL_LABELS = {
  beginner: {
    text: '基础模式',
    code: 'BEGINNER',
    badgeClass: 'text-green-700 bg-green-100 border-green-200',
    description: '回答会更通俗、分步骤，并尽量减少术语。',
  },
  intermediate: {
    text: '进阶模式',
    code: 'INTERMEDIATE',
    badgeClass: 'text-blue-700 bg-blue-100 border-blue-200',
    description: '回答兼顾清晰度与专业度，适合有一定基础的学习者。',
  },
  advanced: {
    text: '专家模式',
    code: 'ADVANCED',
    badgeClass: 'text-purple-700 bg-purple-100 border-purple-200',
    description: '回答会更深入，包含更多术语、原理和扩展思路。',
  },
}

const selectedKb = computed(() => {
  return kbs.value.find(k => k.id === selectedKbId.value) || null
})

const selectedDoc = computed(() => {
  return docsInKb.value.find(d => d.id === selectedDocId.value) || null
})
const selectedSession = computed(() => {
  return sessions.value.find((session) => session.id === selectedSessionId.value) || null
})
const selectedKbSessions = computed(() =>
  sessions.value.filter((session) => session.kb_id === selectedKbId.value)
)
const docsReadyCount = computed(() =>
  docsInKb.value.filter((doc) => doc.status === 'ready').length
)
const docsProcessingCount = computed(() =>
  docsInKb.value.filter((doc) => doc.status === 'processing').length
)
const docsErrorCount = computed(() =>
  docsInKb.value.filter((doc) => doc.status === 'error').length
)
const hasAnyKb = computed(() => kbs.value.length > 0)
const qaEmptyTitle = computed(() => {
  if (!hasAnyKb.value) return '先上传文档再开始问答'
  if (!selectedKbId.value) return '先选择一个知识库'
  return '开始你的第一次提问'
})
const qaEmptyDescription = computed(() => {
  if (!hasAnyKb.value) return '当前还没有知识库，上传文档后即可基于知识库进行 RAG 问答。'
  if (!selectedKbId.value) return '在右侧上下文面板选择知识库后，输入框会自动解锁。'
  return '可以提问概念解释、公式推导、对比分析，AI 会结合知识库内容回答。'
})
const qaEmptyHint = computed(() => {
  if (!hasAnyKb.value) return '上传并解析完成后，可按知识库或文档范围提问。'
  if (!selectedKbId.value) return '如需限定范围，可继续选择某个文档进行问答。'
  return entryFocusContext.value
    ? `已带入学习目标「${entryFocusContext.value}」，可直接围绕该知识点提问。`
    : '点击下方按钮可自动填入一个示例问题。'
})
const qaEmptyPrimaryAction = computed(() => {
  if (!hasAnyKb.value) return { label: '去上传文档' }
  if (!selectedKbId.value) return null
  return { label: '填入示例问题', variant: 'secondary' }
})

const currentLevelMeta = computed(() => getLevelMeta(qaAbilityLevel.value))
const entryFocusContext = computed(() => appContext.routeContext.focus)
const entryDocContextId = computed(() => parseRouteContext(route.query).docId)

function normalizeAbilityLevel(level) {
  const normalized = (level || '').toString().trim().toLowerCase()
  if (normalized === 'beginner' || normalized === 'intermediate' || normalized === 'advanced') {
    return normalized
  }
  return 'intermediate'
}

function getLevelMeta(level) {
  return LEVEL_LABELS[normalizeAbilityLevel(level)] || LEVEL_LABELS.intermediate
}

function goToUpload() {
  router.push({ path: '/upload' })
}

function fillSampleQuestion() {
  if (entryFocusContext.value) {
    qaInput.value = `请用通俗的方式讲解「${entryFocusContext.value}」，并给出一个简单例子。`
    return
  }
  qaInput.value = '请先概括这个知识库中最重要的3个概念，并说明它们之间的关系。'
}

function handleQaEmptyPrimary() {
  if (!hasAnyKb.value) {
    goToUpload()
    return
  }
  if (!selectedKbId.value) return
  fillSampleQuestion()
}

async function refreshDocsInKb() {
  if (!selectedKbId.value) {
    docsInKb.value = []
    busy.value.docs = false
    return
  }
  busy.value.docs = true
  try {
    docsInKb.value = await apiGet(`/api/docs?user_id=${encodeURIComponent(resolvedUserId.value)}&kb_id=${encodeURIComponent(selectedKbId.value)}`)
  } catch {
    // error toast handled globally
  } finally {
    busy.value.docs = false
  }
}

async function refreshSessions() {
  busy.value.sessions = true
  try {
    const result = await apiGet(`/api/chat/sessions?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    sessions.value = Array.isArray(result) ? result : []
    if (selectedSessionId.value && !sessions.value.some((session) => session.id === selectedSessionId.value)) {
      selectedSessionId.value = ''
      sessionTitleInput.value = ''
    }
  } catch {
    // error toast handled globally
    sessions.value = []
  } finally {
    busy.value.sessions = false
  }
}

function mapServerMessage(message) {
  if (message.role === 'user') {
    return { role: 'question', content: message.content }
  }
  return {
    role: 'answer',
    content: message.content,
    sources: Array.isArray(message.sources) ? message.sources : []
  }
}

async function loadSessionMessages(sessionId) {
  if (!sessionId) {
    qaMessages.value = []
    return
  }
  try {
    const rows = await apiGet(`/api/chat/sessions/${sessionId}/messages?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    qaMessages.value = Array.isArray(rows) ? rows.map(mapServerMessage) : []
  } catch {
    qaMessages.value = []
  }
}

function sessionLabel(session) {
  const title = session.title || '未命名会话'
  const kbText = session.kb_id ? `KB:${session.kb_id}` : '无KB'
  return `${title} (${kbText})`
}

async function createSession(options = {}) {
  const { silent = false, activate = true } = options
  if (!selectedKbId.value) {
    if (!silent) {
      showToast('请先选择知识库', 'error')
    }
    return null
  }
  busy.value.sessionAction = true
  try {
    const payload = {
      user_id: resolvedUserId.value,
      kb_id: selectedKbId.value
    }
    if (selectedDocId.value) {
      payload.doc_id = selectedDocId.value
    }
    const session = await apiPost('/api/chat/sessions', payload)
    const sessionId = session?.id || null
    await refreshSessions()
    if (activate && sessionId) {
      selectedSessionId.value = sessionId
      sessionTitleInput.value = session.title || ''
      qaMessages.value = []
    }
    if (!silent) {
      showToast('已创建新会话', 'success')
    }
    return sessionId
  } catch {
    return null
  } finally {
    busy.value.sessionAction = false
  }
}

async function renameCurrentSession() {
  if (!selectedSessionId.value) return
  busy.value.sessionAction = true
  try {
    await apiPatch(`/api/chat/sessions/${selectedSessionId.value}`, {
      user_id: resolvedUserId.value,
      name: sessionTitleInput.value
    })
    await refreshSessions()
    showToast('会话已重命名', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.sessionAction = false
  }
}

async function clearCurrentSessionMessages() {
  if (!selectedSessionId.value) return
  const confirmed = window.confirm('确认清空当前会话在服务端保存的所有消息？')
  if (!confirmed) return
  busy.value.sessionAction = true
  try {
    await apiDelete(`/api/chat/sessions/${selectedSessionId.value}/messages?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    qaMessages.value = []
    showToast('会话消息已清空', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.sessionAction = false
  }
}

async function deleteCurrentSession() {
  if (!selectedSessionId.value) return
  const confirmed = window.confirm('确认删除当前会话？删除后不可恢复。')
  if (!confirmed) return
  busy.value.sessionAction = true
  try {
    const deletingSessionId = selectedSessionId.value
    await apiDelete(`/api/chat/sessions/${deletingSessionId}?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    selectedSessionId.value = ''
    sessionTitleInput.value = ''
    qaMessages.value = []
    await refreshSessions()
    showToast('会话已删除', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.sessionAction = false
  }
}

function clearLocalMessages() {
  qaMessages.value = []
}

function closeSourcePreview() {
  sourcePreview.value.open = false
}

async function openQaSource(source) {
  if (!source || typeof source !== 'object') return
  const docId = source.doc_id || selectedDocId.value || selectedSession.value?.doc_id || ''
  if (!docId) {
    showToast('该来源缺少文档定位信息', 'error')
    return
  }
  sourcePreview.value = {
    open: true,
    loading: true,
    title: '问答来源预览',
    sourceLabel: source.source || '',
    page: Number.isFinite(Number(source.page)) ? Number(source.page) : null,
    chunk: Number.isFinite(Number(source.chunk)) ? Number(source.chunk) : null,
    snippet: '',
    error: '',
  }
  try {
    const params = new URLSearchParams()
    params.set('user_id', resolvedUserId.value)
    if (source.page) params.set('page', String(source.page))
    if (source.chunk) params.set('chunk', String(source.chunk))
    if (source.snippet) params.set('q', String(source.snippet).slice(0, 120))
    const res = await apiGet(`/api/docs/${docId}/preview?${params.toString()}`)
    sourcePreview.value = {
      open: true,
      loading: false,
      title: `${res.filename || '文档'} 原文片段`,
      sourceLabel: res.source || source.source || res.filename || '',
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

function applyDocContextSelection() {
  if (!entryDocContextId.value) return
  if (docsInKb.value.some((doc) => doc.id === entryDocContextId.value)) {
    selectedDocId.value = entryDocContextId.value
  }
}

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
    if (options.refreshDocs && selectedKbId.value) {
      await refreshDocsInKb()
    }
    applyDocContextSelection()
  } finally {
    syncingRouteContext.value = false
  }
}

async function refreshAbilityLevel() {
  try {
    const profile = await apiGet(`/api/profile?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    qaAbilityLevel.value = normalizeAbilityLevel(profile?.ability_level)
  } catch {
    qaAbilityLevel.value = 'intermediate'
  }
}

async function askQuestion() {
  if (!selectedKbId.value || !qaInput.value.trim() || busy.value.qa) return
  
  const question = qaInput.value.trim()
  qaInput.value = ''
  qaMessages.value.push({ role: 'question', content: question })
  
  busy.value.qa = true
  scrollToBottom()
  
  try {
    let activeSessionId = selectedSessionId.value
    if (!activeSessionId) {
      activeSessionId = await createSession({ silent: true, activate: false })
    }

    const payload = {
      question,
      user_id: resolvedUserId.value
    }
    if (activeSessionId) {
      payload.session_id = activeSessionId
    }
    if (selectedSession.value?.doc_id) {
      payload.doc_id = selectedSession.value.doc_id
    } else if (selectedSession.value?.kb_id) {
      payload.kb_id = selectedSession.value.kb_id
    } else if (selectedDocId.value) {
      payload.doc_id = selectedDocId.value
    } else {
      payload.kb_id = selectedKbId.value
    }
    // 如果从学习路径跳转过来，传递目标知识点
    if (entryFocusContext.value) {
      payload.focus = entryFocusContext.value
    }

    const res = await apiPost('/api/qa', payload)
    await refreshSessions()
    if (!selectedSessionId.value && activeSessionId) {
      selectedSessionId.value = activeSessionId
    }
    const responseLevel = normalizeAbilityLevel(res?.ability_level || qaAbilityLevel.value)
    qaAbilityLevel.value = responseLevel
    qaMessages.value.push({
      role: 'answer',
      content: res.answer,
      sources: res.sources,
      abilityLevel: responseLevel,
    })
  } catch (err) {
    qaMessages.value.push({ role: 'answer', content: '错误：' + err.message })
  } finally {
    busy.value.qa = false
    scrollToBottom()
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  })
}

onMounted(async () => {
  busy.value.init = true
  try {
    try {
      await appContext.loadKbs()
    } catch {
      // error toast handled globally
    }
    await Promise.all([refreshAbilityLevel(), refreshSessions()])
    await syncFromRoute({ refreshDocs: false })
    if (selectedKbId.value) {
      await refreshDocsInKb()
      applyDocContextSelection()
    } else {
      docsInKb.value = []
    }
  } finally {
    busy.value.init = false
  }
})

onActivated(async () => {
  await syncFromRoute({
    ensureKbs: !appContext.kbs.length,
    refreshDocs: false,
  })
})

watch(
  () => route.fullPath,
  async () => {
    if (busy.value.init) return
    await syncFromRoute({ refreshDocs: false })
  }
)

watch(selectedKbId, async () => {
  if (!syncingFromSession.value && selectedSessionId.value) {
    selectedSessionId.value = ''
    sessionTitleInput.value = ''
    qaMessages.value = []
  }
  selectedDocId.value = ''
  await refreshDocsInKb()
  applyDocContextSelection()
})

watch(selectedDocId, () => {
  if (!syncingFromSession.value && selectedSessionId.value) {
    selectedSessionId.value = ''
    sessionTitleInput.value = ''
    qaMessages.value = []
  }
})

watch(selectedSessionId, async (sessionId) => {
  if (!sessionId) {
    sessionTitleInput.value = ''
    qaMessages.value = []
    return
  }
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) return

  sessionTitleInput.value = session.title || ''
  syncingFromSession.value = true
  try {
    if (session.kb_id && selectedKbId.value !== session.kb_id) {
      selectedKbId.value = session.kb_id
    }
    await refreshDocsInKb()
    selectedDocId.value = session.doc_id || ''
  } finally {
    syncingFromSession.value = false
  }
  await loadSessionMessages(sessionId)
})

watch(qaMessages, () => scrollToBottom(), { deep: true })

</script>
