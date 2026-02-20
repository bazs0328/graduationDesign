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
          <button @click="qaMessages = []" class="p-2 hover:bg-accent rounded-lg transition-colors text-muted-foreground" title="清空对话">
            <Trash2 class="w-5 h-5" />
          </button>
        </div>

        <!-- Messages -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6" ref="scrollContainer">
          <div v-if="qaMessages.length === 0" class="h-full flex flex-col items-center justify-center text-muted-foreground space-y-4 text-center max-w-sm mx-auto">
            <div class="w-16 h-16 bg-primary/10 text-primary rounded-full flex items-center justify-center">
              <Sparkles class="w-8 h-8" />
            </div>
            <p>在右侧选择知识库后，即可针对该知识库提问。</p>
          </div>
          
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
              <p class="text-sm leading-relaxed whitespace-pre-wrap">{{ msg.content }}</p>
              
              <!-- Sources -->
              <div v-if="msg.sources && msg.sources.length" class="mt-4 pt-3 border-t border-accent-foreground/10 space-y-2">
                <p class="text-[10px] font-bold uppercase opacity-50">参考来源：</p>
                <div class="flex flex-wrap gap-2">
                  <div v-for="(source, sIdx) in msg.sources" :key="sIdx" class="text-[10px] bg-background/50 px-2 py-1 rounded-md flex items-center gap-1.5 border border-accent-foreground/5">
                    <FileText class="w-3 h-3 text-primary" />
                    <span class="font-medium truncate max-w-[120px]">{{ source.source }}</span>
                    <span v-if="source.page" class="opacity-50">p.{{ source.page }}</span>
                  </div>
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
              <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">文档数量</p>
              <p class="text-sm font-semibold">{{ docsInKb.length }} 篇</p>
            </div>
          </div>
          <div v-else class="flex-1 flex flex-col items-center justify-center text-muted-foreground text-xs text-center opacity-50">
            <FileText class="w-12 h-12 mb-2" />
            <p>选择知识库以开始提问</p>
          </div>
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
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { MessageSquare, Send, Trash2, Database, FileText, Sparkles, User, Bot } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'
import { useToast } from '../composables/useToast'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'

const { showToast } = useToast()
const route = useRoute()

const userId = ref(localStorage.getItem('gradtutor_user') || 'default')
const resolvedUserId = computed(() => userId.value || 'default')
const kbs = ref([])
const docsInKb = ref([])
const selectedKbId = ref('')
const selectedDocId = ref('')
const qaInput = ref('')
const qaMessages = ref([])
const qaAbilityLevel = ref('intermediate')
const busy = ref({
  qa: false,
  init: false,
  docs: false
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

const currentLevelMeta = computed(() => getLevelMeta(qaAbilityLevel.value))
const entryFocusContext = computed(() => normalizeQueryString(route.query.focus).trim())
const entryDocContextId = computed(() => normalizeQueryString(route.query.doc_id))

function normalizeQueryString(value) {
  if (Array.isArray(value)) {
    return value[0] || ''
  }
  return typeof value === 'string' ? value : ''
}

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

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(resolvedUserId.value)}`)
  } catch {
    // error toast handled globally
  }
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

function applyDocContextSelection() {
  if (!entryDocContextId.value) return
  if (docsInKb.value.some((doc) => doc.id === entryDocContextId.value)) {
    selectedDocId.value = entryDocContextId.value
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
    const payload = {
      question,
      user_id: resolvedUserId.value
    }
    if (selectedDocId.value) {
      payload.doc_id = selectedDocId.value
    } else {
      payload.kb_id = selectedKbId.value
    }
    // 如果从学习路径跳转过来，传递目标知识点
    if (entryFocusContext.value) {
      payload.focus = entryFocusContext.value
    }

    const res = await apiPost('/api/qa', payload)
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
    await Promise.all([refreshKbs(), refreshAbilityLevel()])
    const queryKbId = normalizeQueryString(route.query.kb_id)
    if (queryKbId && kbs.value.some((kb) => kb.id === queryKbId)) {
      selectedKbId.value = queryKbId
    }
    if (selectedKbId.value) {
      await refreshDocsInKb()
      applyDocContextSelection()
    }
  } finally {
    busy.value.init = false
  }
})

watch(selectedKbId, async () => {
  selectedDocId.value = ''
  await refreshDocsInKb()
  applyDocContextSelection()
})

watch(qaMessages, () => scrollToBottom(), { deep: true })

</script>
