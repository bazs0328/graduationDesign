<template>
  <div class="h-full flex flex-col max-w-6xl mx-auto space-y-0">
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
    <div class="flex-1 flex flex-col lg:flex-row gap-4 lg:gap-8 overflow-hidden min-h-0">
      <!-- Left: Chat Interface -->
      <section class="flex-1 flex flex-col bg-card border border-border rounded-xl shadow-sm overflow-hidden">
        <!-- Header -->
        <div class="p-3 sm:p-4 border-b border-border flex items-center justify-between gap-3 bg-card/50">
          <div class="flex items-center gap-3">
            <MessageSquare class="w-6 h-6 text-primary" />
            <h2 class="text-lg sm:text-xl font-bold">AI 辅导对话</h2>
          </div>
          <div class="flex items-center gap-1 sm:gap-2">
            <button
              class="lg:hidden px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-border hover:bg-accent transition-colors"
              @click="qaSidebarOpen = !qaSidebarOpen"
            >
              {{ qaSidebarOpen ? '收起面板' : '上下文面板' }}
            </button>
            <button @click="clearLocalMessages" class="p-2 hover:bg-accent rounded-lg transition-colors text-muted-foreground" title="仅清空本地显示">
              <Trash2 class="w-5 h-5" />
            </button>
          </div>
        </div>
        <div class="px-4 py-3 border-b border-border/80 bg-gradient-to-r from-accent/40 via-background to-background">
          <div class="flex flex-wrap items-center gap-2">
            <span
              v-for="stage in qaFlowStages"
              :key="stage.key"
              class="px-2 py-1 rounded-full border text-[10px] font-semibold tracking-wide"
              :class="qaFlowPhaseChipClass(stage.key)"
            >
              {{ stage.label }}
            </span>
            <span
              v-if="qaFlow.usedFallback"
              class="px-2 py-1 rounded-full border border-amber-300 bg-amber-50 text-amber-700 text-[10px] font-semibold tracking-wide"
            >
              已回退非流式
            </span>
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <p class="text-muted-foreground">
              {{ qaFlow.message || '等待提问…' }}
            </p>
            <p v-if="qaFlow.retrievedCount > 0" class="text-muted-foreground">
              检索到 {{ qaFlow.retrievedCount }} 个片段
            </p>
            <p v-if="qaFlow.timings.total_ms" class="text-muted-foreground">
              总耗时 {{ qaFlow.timings.total_ms }} ms
            </p>
          </div>
        </div>

        <!-- Messages -->
        <div class="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 sm:space-y-6" ref="scrollContainer">
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
              class="max-w-[92%] sm:max-w-[85%] p-3 sm:p-4 rounded-2xl shadow-sm"
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
              <div v-else>
                <div
                  v-if="msg.status && msg.status !== 'done'"
                  class="mb-2 flex flex-wrap items-center gap-2 text-[10px]"
                >
                  <span
                    class="px-1.5 py-0.5 rounded-full border font-semibold normal-case tracking-normal"
                    :class="qaMessageStatusBadgeClass(msg)"
                  >
                    {{ qaMessageStatusText(msg) }}
                  </span>
                  <span v-if="msg.errorCode" class="opacity-60">{{ msg.errorCode }}</span>
                </div>
                <div
                  v-if="shouldRenderExplainCards(msg)"
                  class="space-y-3"
                >
                  <div class="flex flex-wrap items-center gap-2 text-[10px]">
                    <span class="px-1.5 py-0.5 rounded-full border border-primary/30 bg-primary/10 text-primary font-semibold">
                      讲解模式
                    </span>
                    <span
                      v-if="msg.explainIncomplete"
                      class="px-1.5 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700 font-semibold"
                    >
                      结构容错展示
                    </span>
                  </div>
                  <section
                    v-for="section in msg.explainSections"
                    :key="section.key"
                    class="rounded-xl border border-accent-foreground/10 bg-background/35 p-3"
                  >
                    <p class="text-[10px] font-bold uppercase tracking-widest opacity-60">
                      {{ section.title }}
                    </p>
                    <div
                      class="mt-2 qa-markdown markdown-content"
                      v-html="renderMarkdown(section.content || '（该部分暂无可解析内容）')"
                    ></div>
                  </section>
                  <p
                    v-if="msg.streaming"
                    class="mt-1 text-sm leading-relaxed"
                  >
                    <span class="qa-stream-cursor" aria-hidden="true"></span>
                  </p>
                </div>
                <div
                  v-else-if="msg.content && msg.content.trim()"
                  class="qa-markdown markdown-content"
                  v-html="renderMarkdown(msg.content)"
                ></div>
                <p
                  v-else
                  class="text-sm leading-relaxed opacity-70 italic flex items-center gap-1"
                >
                  {{ msg.streaming ? '正在生成回答…' : '暂无回答内容' }}
                  <span v-if="msg.streaming" class="qa-stream-cursor" aria-hidden="true"></span>
                </p>
                <p
                  v-if="msg.streaming && msg.content && msg.content.trim()"
                  class="mt-1 text-sm leading-relaxed"
                >
                  <span class="qa-stream-cursor" aria-hidden="true"></span>
                </p>
              </div>
              
              <!-- Sources -->
              <div v-if="msg.sources && msg.sources.length" class="mt-4 pt-3 border-t border-accent-foreground/10 space-y-2">
                <p class="text-[10px] font-bold uppercase opacity-50">参考来源（{{ msg.sources.length }}）</p>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="(source, sIdx) in msg.sources"
                    :key="sIdx"
                    class="text-[10px] bg-background/50 px-2 py-1 rounded-md flex items-center gap-1.5 border border-accent-foreground/5 hover:border-primary/40 hover:text-primary transition-colors"
                    @click="openQaSource(source)"
                  >
                    <FileText class="w-3 h-3 text-primary" />
                    <span class="font-medium truncate max-w-[120px]">{{ source.source }}</span>
                    <span v-if="source.page" class="opacity-50 px-1 py-0.5 rounded border border-accent-foreground/10">p.{{ source.page }}</span>
                    <span v-if="source.chunk !== undefined && source.chunk !== null" class="opacity-50 px-1 py-0.5 rounded border border-accent-foreground/10">c.{{ source.chunk }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="p-3 sm:p-4 border-t border-border bg-card/50">
          <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              <Sparkles class="w-3.5 h-3.5 text-primary" />
              回答模式
            </div>
            <div class="inline-flex rounded-lg border border-border bg-background p-1">
              <button
                class="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
                :class="qaMode === 'normal' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'"
                :disabled="busy.qa"
                @click="qaMode = 'normal'"
              >
                普通问答
              </button>
              <button
                class="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
                :class="qaMode === 'explain' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'"
                :disabled="busy.qa"
                @click="qaMode = 'explain'"
              >
                讲解模式
              </button>
            </div>
          </div>
          <div class="flex flex-col sm:flex-row gap-2">
            <textarea
              v-model="qaInput"
              @keydown.enter.prevent="askQuestion"
              :placeholder="entryFocusContext ? `关于「${entryFocusContext}」，你想了解什么？` : '在此输入你的问题…'"
              class="flex-1 bg-background border border-input rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-primary resize-none h-[88px] sm:h-[52px]"
              :disabled="!selectedKbId || busy.qa"
            ></textarea>
            <button
              @click="askQuestion"
              class="bg-primary text-primary-foreground p-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center sm:w-auto w-full"
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
      <aside
        class="w-full lg:w-72 space-y-4 lg:space-y-6 flex-col"
        :class="qaSidebarOpen ? 'flex' : 'hidden lg:flex'"
      >
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

        <div class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground">本次回答来源</h3>
            <span
              class="text-[10px] font-semibold px-2 py-1 rounded-full border"
              :class="qaFlowPanelBadgeClass"
            >
              {{ qaFlowPanelBadgeText }}
            </span>
          </div>
          <div class="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
            <span v-if="qaFlow.retrievedCount > 0" class="px-2 py-1 rounded border border-border bg-accent/20">
              检索片段 {{ qaFlow.retrievedCount }}
            </span>
            <span v-if="qaFlow.timings.retrieve_ms" class="px-2 py-1 rounded border border-border bg-accent/20">
              检索 {{ qaFlow.timings.retrieve_ms }} ms
            </span>
            <span v-if="qaFlow.timings.generate_ms" class="px-2 py-1 rounded border border-border bg-accent/20">
              生成 {{ qaFlow.timings.generate_ms }} ms
            </span>
          </div>

          <div v-if="busy.qa && qaSourcePanelSources.length === 0" class="space-y-2">
            <SkeletonBlock type="list" :lines="3" />
            <p class="text-xs text-muted-foreground">正在收集检索来源...</p>
          </div>

          <div v-else-if="qaSourcePanelSources.length" class="space-y-2 max-h-56 overflow-y-auto pr-1">
            <button
              v-for="(source, index) in qaSourcePanelSources"
              :key="`${source.doc_id || 'doc'}-${source.page ?? 'x'}-${source.chunk ?? index}`"
              class="w-full text-left p-2 rounded-lg border border-border hover:border-primary/40 hover:bg-accent/20 transition-colors"
              @click="openQaSource(source)"
            >
              <div class="flex items-start gap-2">
                <FileText class="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <div class="min-w-0 flex-1">
                  <p class="text-xs font-semibold truncate">{{ source.source || `来源 ${index + 1}` }}</p>
                  <div class="mt-1 flex flex-wrap gap-1">
                    <span
                      v-if="source.page !== undefined && source.page !== null"
                      class="text-[10px] px-1.5 py-0.5 rounded border border-border bg-background"
                    >
                      页码 p.{{ source.page }}
                    </span>
                    <span
                      v-if="source.chunk !== undefined && source.chunk !== null"
                      class="text-[10px] px-1.5 py-0.5 rounded border border-border bg-background"
                    >
                      Chunk c.{{ source.chunk }}
                    </span>
                  </div>
                  <p class="mt-1 text-[11px] text-muted-foreground line-clamp-2">{{ source.snippet || '点击查看原文片段' }}</p>
                </div>
              </div>
            </button>
          </div>

          <EmptyState
            v-else
            :icon="FileText"
            title="暂无来源"
            description="提问后会在这里显示本次回答引用的文档片段。"
            :hint="busy.qa ? '正在等待检索结果...' : '点击来源项可查看原文片段。'"
            size="sm"
          />
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
import { apiDelete, apiGet, apiPatch, apiPost, apiSsePost } from '../api'
import { useToast } from '../composables/useToast'
import { useAppContextStore } from '../stores/appContext'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import SourcePreviewModal from '../components/ui/SourcePreviewModal.vue'
import { parseExplainMarkdownSections } from '../utils/qaExplain'
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
const qaMode = ref('normal')
const qaSidebarOpen = ref(false)
const qaFlow = ref(createQaFlowState())
const syncingFromSession = ref(false)
const preserveQaFlowOnNextSessionLoad = ref(false)
const lastAutoQaRouteKey = ref('')
const autoQaMissingContextToastKey = ref('')
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
const lastQaSubmitFingerprint = ref('')
const lastQaSubmitAt = ref(0)

const QA_FLOW_STAGES = [
  { key: 'retrieving', label: '检索中' },
  { key: 'generating', label: '生成中' },
  { key: 'saving', label: '保存中' },
  { key: 'done', label: '完成' },
  { key: 'failed', label: '失败' },
]

const STREAM_NON_FALLBACK_CODES = new Set(['validation_error', 'not_found', 'no_results'])
const QA_EXPLAIN_DISPLAY_THRESHOLD = 3
const QA_SUBMIT_DEDUPE_WINDOW_MS = 1200

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
const qaFlowStages = QA_FLOW_STAGES
const latestAssistantMessage = computed(() => {
  for (let i = qaMessages.value.length - 1; i >= 0; i -= 1) {
    const msg = qaMessages.value[i]
    if (msg?.role === 'answer') return msg
  }
  return null
})
const qaStreamingMessage = computed(() => {
  for (let i = qaMessages.value.length - 1; i >= 0; i -= 1) {
    const msg = qaMessages.value[i]
    if (msg?.role === 'answer' && msg.streaming) return msg
  }
  return null
})
const qaSourcePanelMessage = computed(() => qaStreamingMessage.value || latestAssistantMessage.value || null)
const qaSourcePanelSources = computed(() => {
  const sources = qaSourcePanelMessage.value?.sources
  return Array.isArray(sources) ? sources : []
})
const qaFlowPanelBadgeText = computed(() => {
  const phase = qaFlow.value.phase
  if (phase === 'retrieving') return '检索中'
  if (phase === 'generating') return '生成中'
  if (phase === 'saving') return '保存中'
  if (phase === 'done' && qaFlow.value.result === 'no_results') return '无结果'
  if (phase === 'done') return '完成'
  if (phase === 'failed') return '失败'
  return '就绪'
})
const qaFlowPanelBadgeClass = computed(() => {
  const phase = qaFlow.value.phase
  if (phase === 'retrieving' || phase === 'generating' || phase === 'saving') {
    return 'border-blue-200 bg-blue-50 text-blue-700'
  }
  if (phase === 'done' && qaFlow.value.result === 'no_results') {
    return 'border-amber-200 bg-amber-50 text-amber-700'
  }
  if (phase === 'done') {
    return 'border-green-200 bg-green-50 text-green-700'
  }
  if (phase === 'failed') {
    return 'border-red-200 bg-red-50 text-red-700'
  }
  return 'border-border text-muted-foreground'
})

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

function normalizeQaMode(mode) {
  const normalized = String(mode || '').trim().toLowerCase()
  return normalized === 'explain' ? 'explain' : 'normal'
}

function createQaFlowState() {
  return {
    phase: 'idle',
    message: '',
    result: null,
    retrievedCount: 0,
    timings: {},
    usedFallback: false,
    errorCode: null,
  }
}

function resetQaFlow() {
  qaFlow.value = createQaFlowState()
}

function updateQaFlow(patch = {}) {
  qaFlow.value = {
    ...qaFlow.value,
    ...patch,
    timings: {
      ...(qaFlow.value?.timings || {}),
      ...(patch.timings || {}),
    },
  }
}

function qaFlowPhaseChipClass(stageKey) {
  const phase = qaFlow.value.phase
  const isCurrent = phase === stageKey
  const isDone = phase === 'done' && (stageKey === 'retrieving' || stageKey === 'generating' || stageKey === 'saving' || stageKey === 'done')

  if (phase === 'failed' && stageKey === 'failed') return 'border-red-300 bg-red-50 text-red-700'
  if (qaFlow.value.result === 'no_results' && stageKey === 'done') return 'border-amber-300 bg-amber-50 text-amber-700'
  if (isCurrent || isDone) return 'border-primary/30 bg-primary/10 text-primary'
  return 'border-border text-muted-foreground'
}

function qaMessageStatusText(msg) {
  if (!msg || msg.role === 'question') return ''
  if (msg.status === 'pending') return '排队中'
  if (msg.status === 'streaming') return msg.content?.trim() ? '生成中' : '准备生成'
  if (msg.status === 'fallback') return '已回退非流式'
  if (msg.status === 'error') return '生成失败'
  return '已完成'
}

function qaMessageStatusBadgeClass(msg) {
  if (!msg) return 'border-border text-muted-foreground'
  if (msg.status === 'fallback') return 'border-amber-300 bg-amber-50 text-amber-700'
  if (msg.status === 'error') return 'border-red-300 bg-red-50 text-red-700'
  if (msg.status === 'streaming' || msg.status === 'pending') return 'border-blue-300 bg-blue-50 text-blue-700'
  return 'border-green-300 bg-green-50 text-green-700'
}

function normalizeQaSource(raw) {
  if (!raw || typeof raw !== 'object') return null
  const rawSource = typeof raw.source === 'string' ? raw.source.trim() : ''
  let friendlySource = rawSource
  if (!friendlySource) {
    friendlySource = raw.doc_id ? `文档片段 (${String(raw.doc_id).slice(0, 8)})` : '文档片段'
  } else if (/^document(\b|[\s._-])/i.test(friendlySource) || /^document$/i.test(friendlySource)) {
    friendlySource = friendlySource.replace(/^document/i, '文档片段')
  }
  return {
    source: friendlySource,
    snippet: raw.snippet || '',
    doc_id: raw.doc_id ?? null,
    kb_id: raw.kb_id ?? null,
    page: raw.page ?? null,
    chunk: raw.chunk ?? null,
  }
}

function applyExplainStateToAssistantMessage(msg) {
  if (!msg || msg.role !== 'answer') return msg
  const parsed = parseExplainMarkdownSections(msg.content || '')
  const requestedMode = normalizeQaMode(msg.requestedMode)
  const resolvedMode = normalizeQaMode(msg.resolvedMode || msg.mode || requestedMode)
  const explicitExplain = requestedMode === 'explain' || resolvedMode === 'explain'
  const canRenderExplain = parsed.sections.length >= QA_EXPLAIN_DISPLAY_THRESHOLD && parsed.isExplainLike

  msg.requestedMode = requestedMode
  msg.resolvedMode = resolvedMode
  msg.explainSections = parsed.sections
  msg.explainMissing = parsed.missing
  msg.explainIncomplete = explicitExplain && parsed.missing.length > 0
  msg.displayMode = (explicitExplain || parsed.isExplainLike) && canRenderExplain ? 'explain' : 'normal'
  return msg
}

function makeAssistantPlaceholder() {
  return applyExplainStateToAssistantMessage({
    role: 'answer',
    content: '',
    sources: [],
    abilityLevel: qaAbilityLevel.value,
    streaming: true,
    status: 'pending',
    errorCode: null,
    requestedMode: qaMode.value,
    resolvedMode: qaMode.value,
    displayMode: qaMode.value === 'explain' ? 'explain' : 'normal',
    explainSections: [],
    explainMissing: [],
    explainIncomplete: false,
  })
}

function shouldRenderExplainCards(msg) {
  return (
    msg?.role === 'answer'
    && msg?.displayMode === 'explain'
    && Array.isArray(msg?.explainSections)
    && msg.explainSections.length > 0
  )
}

function streamPayloadError(payload = {}) {
  const err = new Error(payload.message || '流式回答失败')
  err.qaStream = {
    code: payload.code || 'unknown',
    stage: payload.stage || 'generating',
    retryable: payload.retryable !== false,
    message: payload.message || '流式回答失败',
  }
  return err
}

function isStreamErrorRetryable(err) {
  const code = err?.qaStream?.code
  if (code && STREAM_NON_FALLBACK_CODES.has(code)) return false
  if (typeof err?.qaStream?.retryable === 'boolean') return err.qaStream.retryable
  return true
}

function buildQaPayload(question, activeSessionId) {
  const payload = {
    question,
    user_id: resolvedUserId.value,
    mode: normalizeQaMode(qaMode.value),
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
  if (entryFocusContext.value) {
    payload.focus = entryFocusContext.value
  }
  return payload
}

function buildQaSubmitFingerprint(question) {
  const normalizedQuestion = (question || '').trim()
  if (!normalizedQuestion) return ''
  return [
    selectedKbId.value || '',
    selectedDocId.value || '',
    selectedSessionId.value || '',
    normalizeQaMode(qaMode.value),
    normalizedQuestion,
  ].join('::')
}

function isDuplicateQaSubmit(fingerprint) {
  if (!fingerprint) return false
  const now = Date.now()
  const isDuplicate = (
    lastQaSubmitFingerprint.value === fingerprint
    && (now - lastQaSubmitAt.value) < QA_SUBMIT_DEDUPE_WINDOW_MS
  )
  if (!isDuplicate) {
    lastQaSubmitFingerprint.value = fingerprint
    lastQaSubmitAt.value = now
  }
  return isDuplicate
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
  return applyExplainStateToAssistantMessage({
    role: 'answer',
    content: message.content,
    sources: Array.isArray(message.sources) ? message.sources.map(normalizeQaSource).filter(Boolean) : [],
    streaming: false,
    status: 'done',
    errorCode: null,
    requestedMode: 'normal',
    resolvedMode: 'normal',
    displayMode: 'normal',
    explainSections: [],
    explainMissing: [],
    explainIncomplete: false,
  })
}

async function loadSessionMessages(sessionId) {
  if (!sessionId) {
    qaMessages.value = []
    resetQaFlow()
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
      resetQaFlow()
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
    resetQaFlow()
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
    resetQaFlow()
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
  resetQaFlow()
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
    if (source.page !== undefined && source.page !== null) params.set('page', String(source.page))
    if (source.chunk !== undefined && source.chunk !== null) params.set('chunk', String(source.chunk))
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

function buildAutoQaRouteKey(parsed) {
  return [
    parsed.qaFrom || '',
    parsed.qaMode || '',
    parsed.qaQuestion || '',
    parsed.kbId || '',
    parsed.docId || '',
  ].join('|')
}

async function clearTransientQaRouteParams() {
  const nextQuery = { ...(route.query || {}) }
  let changed = false
  for (const key of ['qa_mode', 'qa_autosend', 'qa_question', 'qa_from']) {
    if (Object.prototype.hasOwnProperty.call(nextQuery, key)) {
      delete nextQuery[key]
      changed = true
    }
  }
  if (!changed) return
  await router.replace({ path: route.path, query: nextQuery })
}

async function maybeAutoAskFromRoute() {
  const parsed = parseRouteContext(route.query)
  if (parsed.qaMode) {
    qaMode.value = normalizeQaMode(parsed.qaMode)
  }
  if (parsed.qaQuestion) {
    qaInput.value = parsed.qaQuestion
  }
  const shouldAutoSend = parsed.qaMode === 'explain' && parsed.qaAutoSend === '1' && !!parsed.qaQuestion
  if (!shouldAutoSend || busy.value.qa) return

  const routeKey = buildAutoQaRouteKey(parsed)
  if (lastAutoQaRouteKey.value === routeKey) return

  if (!selectedKbId.value && !selectedSessionId.value) {
    if (autoQaMissingContextToastKey.value !== routeKey) {
      autoQaMissingContextToastKey.value = routeKey
      showToast('请先选择知识库后再发送', 'error')
    }
    return
  }

  lastAutoQaRouteKey.value = routeKey
  try {
    await askQuestion()
  } finally {
    await clearTransientQaRouteParams()
  }
}

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
    await maybeAutoAskFromRoute()
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
  const submitFingerprint = buildQaSubmitFingerprint(question)
  if (isDuplicateQaSubmit(submitFingerprint)) return
  qaInput.value = ''
  qaMessages.value.push({ role: 'question', content: question })
  const placeholderIndex = qaMessages.value.push(makeAssistantPlaceholder()) - 1
  
  resetQaFlow()
  updateQaFlow({
    phase: 'retrieving',
    message: '正在检索相关片段...',
  })
  busy.value.qa = true
  scrollToBottom()
  let activeSessionId = selectedSessionId.value
  
  try {
    if (!activeSessionId) {
      activeSessionId = await createSession({ silent: true, activate: false })
    }
    const payload = buildQaPayload(question, activeSessionId)

    let streamDone = false
    await apiSsePost('/api/qa/stream', payload, {
      onStatus(data = {}) {
        const nextPhase = data.stage || qaFlow.value.phase
        updateQaFlow({
          phase: nextPhase,
          message: data.message || qaFlow.value.message,
          result: data.result ?? qaFlow.value.result,
          retrievedCount: Number.isFinite(Number(data.retrieved_count))
            ? Number(data.retrieved_count)
            : qaFlow.value.retrievedCount,
          timings: data.timings || {},
          errorCode: nextPhase === 'failed' ? (qaFlow.value.errorCode || 'unknown') : qaFlow.value.errorCode,
        })
        const msg = qaMessages.value[placeholderIndex]
        if (!msg || msg.role !== 'answer') return
        if (nextPhase === 'retrieving') {
          msg.status = 'pending'
          msg.streaming = true
        } else if (nextPhase === 'generating') {
          msg.status = 'streaming'
          msg.streaming = true
        } else if (nextPhase === 'saving') {
          msg.status = 'streaming'
          msg.streaming = true
        } else if (nextPhase === 'done') {
          msg.streaming = false
          if (qaFlow.value.usedFallback) {
            msg.status = 'fallback'
          } else if (data.result === 'no_results') {
            msg.status = 'done'
          } else {
            msg.status = 'done'
          }
        } else if (nextPhase === 'failed') {
          msg.status = 'error'
          msg.streaming = false
        }
      },
      onChunk(data = {}) {
        const msg = qaMessages.value[placeholderIndex]
        if (!msg || msg.role !== 'answer') return
        msg.streaming = true
        msg.status = 'streaming'
        msg.content = `${msg.content || ''}${data.delta || ''}`
        applyExplainStateToAssistantMessage(msg)
      },
      onSources(data = {}) {
        const msg = qaMessages.value[placeholderIndex]
        if (!msg || msg.role !== 'answer') return
        msg.sources = Array.isArray(data.sources) ? data.sources.map(normalizeQaSource).filter(Boolean) : []
        if (Number.isFinite(Number(data.retrieved_count))) {
          updateQaFlow({ retrievedCount: Number(data.retrieved_count) })
        }
      },
      onDone(data = {}) {
        streamDone = true
        const responseLevel = normalizeAbilityLevel(data.ability_level || qaAbilityLevel.value)
        qaAbilityLevel.value = responseLevel
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.abilityLevel = responseLevel
          msg.streaming = false
          msg.resolvedMode = normalizeQaMode(data.mode || msg.resolvedMode || msg.requestedMode)
          if ((!msg.content || !msg.content.trim()) && data.result === 'no_results') {
            msg.content = '无法找到与该问题相关的内容。'
          }
          applyExplainStateToAssistantMessage(msg)
          msg.status = qaFlow.value.usedFallback ? 'fallback' : 'done'
        }
        updateQaFlow({
          phase: 'done',
          message: data.result === 'no_results' ? '未检索到相关内容' : '回答生成完成',
          result: data.result || 'ok',
          retrievedCount: Number.isFinite(Number(data.retrieved_count))
            ? Number(data.retrieved_count)
            : qaFlow.value.retrievedCount,
          timings: data.timings || {},
          errorCode: null,
        })
        if (!selectedSessionId.value && activeSessionId) {
          preserveQaFlowOnNextSessionLoad.value = true
          selectedSessionId.value = activeSessionId
        }
      },
      onError(data = {}) {
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.streaming = false
          msg.status = 'error'
          msg.errorCode = data.code || 'unknown'
        }
        updateQaFlow({
          phase: 'failed',
          message: data.message || '流式回答失败',
          errorCode: data.code || 'unknown',
        })
        throw streamPayloadError(data)
      },
    })

    if (streamDone) {
      await refreshSessions()
      if (!selectedSessionId.value && activeSessionId) {
        preserveQaFlowOnNextSessionLoad.value = true
        selectedSessionId.value = activeSessionId
      }
    }
  } catch (err) {
    const canFallback = isStreamErrorRetryable(err)
    if (canFallback) {
      updateQaFlow({
        phase: 'failed',
        message: '流式连接中断，正在回退到非流式请求...',
      })
      try {
        const payload = buildQaPayload(question, activeSessionId)
        const res = await apiPost('/api/qa', payload)
        const responseLevel = normalizeAbilityLevel(res?.ability_level || qaAbilityLevel.value)
        qaAbilityLevel.value = responseLevel
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.content = res?.answer || ''
          msg.sources = Array.isArray(res?.sources) ? res.sources.map(normalizeQaSource).filter(Boolean) : []
          msg.abilityLevel = responseLevel
          msg.resolvedMode = normalizeQaMode(res?.mode || msg.resolvedMode || msg.requestedMode)
          msg.streaming = false
          applyExplainStateToAssistantMessage(msg)
          msg.status = 'fallback'
          msg.errorCode = null
        }
        updateQaFlow({
          phase: 'done',
          message: '流式中断，已自动回退为非流式回答',
          usedFallback: true,
          result: res?.answer ? 'ok' : qaFlow.value.result,
          errorCode: null,
        })
        await refreshSessions()
        if (!selectedSessionId.value && (res?.session_id || activeSessionId)) {
          preserveQaFlowOnNextSessionLoad.value = true
          selectedSessionId.value = res?.session_id || activeSessionId
        }
      } catch (fallbackErr) {
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.content = `错误：${fallbackErr.message}`
          msg.streaming = false
          msg.status = 'error'
          msg.errorCode = fallbackErr?.qaStream?.code || 'fallback_failed'
        }
        updateQaFlow({
          phase: 'failed',
          message: fallbackErr?.message || '问答请求失败',
          errorCode: fallbackErr?.qaStream?.code || 'fallback_failed',
        })
      }
    } else {
      const msg = qaMessages.value[placeholderIndex]
      if (msg && msg.role === 'answer') {
        msg.content = `错误：${err.message}`
        msg.streaming = false
        msg.status = 'error'
        msg.errorCode = err?.qaStream?.code || 'request_failed'
      } else {
        qaMessages.value.push({ role: 'answer', content: '错误：' + err.message, status: 'error' })
      }
      updateQaFlow({
        phase: 'failed',
        message: err?.message || '问答请求失败',
        errorCode: err?.qaStream?.code || 'request_failed',
      })
    }
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
    resetQaFlow()
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
    resetQaFlow()
  }
})

watch(selectedSessionId, async (sessionId) => {
  if (!sessionId) {
    sessionTitleInput.value = ''
    qaMessages.value = []
    resetQaFlow()
    return
  }
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    preserveQaFlowOnNextSessionLoad.value = false
    return
  }
  const skipFlowReset = preserveQaFlowOnNextSessionLoad.value
  preserveQaFlowOnNextSessionLoad.value = false

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
  if (!busy.value.qa && !skipFlowReset) {
    resetQaFlow()
  }
  await loadSessionMessages(sessionId)
})

watch(qaMessages, () => scrollToBottom(), { deep: true })

</script>

<style scoped>
.qa-stream-cursor {
  display: inline-block;
  width: 0.45rem;
  height: 1em;
  vertical-align: text-bottom;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.8;
  animation: qaCursorBlink 1s steps(2, start) infinite;
}

@keyframes qaCursorBlink {
  0%,
  49% {
    opacity: 0.8;
  }
  50%,
  100% {
    opacity: 0.15;
  }
}
</style>
