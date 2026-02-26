<template>
  <div class="space-y-6 md:space-y-8 max-w-6xl mx-auto">
    <section
      v-if="hasPathContext"
      class="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 space-y-1"
    >
      <p class="text-[10px] font-bold uppercase tracking-widest text-primary">学习路径上下文</p>
      <p class="text-sm text-muted-foreground">
        <span v-if="entryKbContextId">
          当前知识库：<span class="font-semibold text-foreground">{{ entryKbContextName }}</span>
        </span>
        <span v-if="entryDocContextId">
          <span v-if="entryKbContextId"> · </span>
          当前文档：<span class="font-semibold text-foreground">{{ entryDocContextName }}</span>
        </span>
        <span v-if="entryFocusContext">
          <span v-if="entryKbContextId || entryDocContextId"> · </span>
          重点概念：<span class="font-semibold text-foreground">{{ entryFocusContext }}</span>
        </span>
      </p>
    </section>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-8">
      <!-- Left: Quiz Generation -->
      <aside class="space-y-4 md:space-y-6">
        <section class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-6">
          <div class="flex items-center gap-3">
            <PenTool class="w-6 h-6 text-primary" />
            <h2 class="text-lg sm:text-xl font-bold">测验生成</h2>
          </div>

          <div class="space-y-4">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">目标知识库</label>
              <select v-model="selectedKbId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                <option disabled value="">请选择</option>
                <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name || kb.id }}</option>
              </select>
            </div>

            <div v-if="selectedKbId" class="space-y-2">
              <div class="flex items-center gap-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">限定文档（可选）</label>
                <span v-if="busy.docs" class="text-[10px] text-muted-foreground">加载中...</span>
              </div>
              <select v-model="selectedDocId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                <option value="">不限定（整库测验）</option>
                <option v-for="doc in docsInKb" :key="doc.id" :value="doc.id">{{ doc.filename }}</option>
              </select>
            </div>

            <div v-if="selectedKbId" class="space-y-2">
              <div class="flex items-center justify-between gap-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">重点聚合知识点（可选）</label>
                <button
                  v-if="quizFocusConcepts.length"
                  type="button"
                  class="text-[10px] text-muted-foreground hover:text-foreground"
                  @click="clearQuizFocusConcepts"
                >
                  清空
                </button>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2">
                <input
                  v-model="quizFocusSearch"
                  type="text"
                  placeholder="搜索聚合知识点（如：牛顿定律）"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                  @keydown.enter.prevent="addSelectedQuizFocusCandidate"
                />
                <button
                  type="button"
                  class="px-3 py-2 rounded-lg border border-input bg-background text-sm hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="busy.focusKeypoints || !quizFocusCandidate"
                  @click="addSelectedQuizFocusCandidate"
                >
                  添加
                </button>
              </div>
              <select
                v-model="quizFocusCandidate"
                class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                :disabled="busy.focusKeypoints || !filteredQuizFocusOptions.length"
              >
                <option value="">{{ quizFocusSelectPlaceholder }}</option>
                <option v-for="item in filteredQuizFocusOptions" :key="item.id" :value="item.text">
                  {{ item.text }}
                </option>
              </select>
              <p class="text-[10px] text-muted-foreground">
                选项来自知识库聚合知识点；若已选择文档，仅显示该文档相关的聚合知识点。留空则按整库/文档自动出题。
              </p>
              <div v-if="quizFocusConcepts.length" class="flex flex-wrap gap-2">
                <span
                  v-for="(concept, idx) in quizFocusConcepts"
                  :key="`${concept}-${idx}`"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-primary/20 bg-primary/10 text-primary text-[11px] font-semibold"
                >
                  <span>{{ concept }}</span>
                  <button
                    type="button"
                    class="text-primary/80 hover:text-primary"
                    :aria-label="`移除重点知识点 ${concept}`"
                    @click="removeQuizFocusConcept(idx)"
                  >
                    ×
                  </button>
                </span>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">题目数量</label>
                <input type="number" min="1" max="20" v-model.number="quizCount" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm" />
              </div>
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">自适应模式</label>
                <button
                  class="w-full flex items-center justify-between border border-input rounded-lg px-3 py-2 text-sm transition-colors"
                  :class="autoAdapt ? 'bg-primary/10 text-primary border-primary/30' : 'bg-background text-muted-foreground'"
                  @click="autoAdapt = !autoAdapt"
                >
                  <span>{{ autoAdapt ? '开启' : '关闭' }}</span>
                  <span class="text-xs">{{ autoAdapt ? '系统自动调难度' : '手动选择难度' }}</span>
                </button>
              </div>
            </div>

            <div v-if="!autoAdapt" class="space-y-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">难度</label>
              <select v-model="quizDifficulty" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                <option value="easy">简单</option>
                <option value="medium">中等</option>
                <option value="hard">困难</option>
              </select>
            </div>

            <Button
              class="w-full"
              size="lg"
              :disabled="!selectedKbId"
              :loading="busy.quiz"
              @click="generateQuiz"
            >
              <template #icon>
                <Sparkles class="w-5 h-5" />
              </template>
              {{ busy.quiz ? '正在生成题目…' : '生成新测验' }}
            </Button>
          </div>
        </section>

        <div v-if="quizResult" class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-4 text-center">
          <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground">上次结果</h3>
          <div class="relative inline-flex items-center justify-center">
            <svg class="w-24 h-24">
              <circle class="text-muted/20" stroke-width="8" stroke="currentColor" fill="transparent" r="40" cx="48" cy="48" />
              <circle 
                class="text-primary transition-all duration-1000 ease-out" 
                stroke-width="8" 
                :stroke-dasharray="2 * Math.PI * 40" 
                :stroke-dashoffset="2 * Math.PI * 40 * (1 - quizResult.score)" 
                stroke-linecap="round" 
                stroke="currentColor" 
                fill="transparent" 
                r="40" cx="48" cy="48" 
              />
            </svg>
            <span class="absolute text-2xl font-black">{{ Math.round(quizResult.score * 100) }}%</span>
          </div>
          <p class="text-sm font-medium">
            {{ quizResult.correct }} / {{ quizResult.total }} 正确
          </p>
          <div v-if="hasProfileDelta" class="space-y-2 text-left">
            <p class="text-xs font-bold uppercase tracking-widest text-primary">能力变化</p>
            <div class="grid grid-cols-2 gap-3 text-xs font-semibold">
              <div class="bg-accent/40 rounded-lg p-3 space-y-1">
                <p class="text-muted-foreground">准确率</p>
                <p :class="profileDelta.recent_accuracy_delta >= 0 ? 'text-green-600' : 'text-red-600'">
                  <span>{{ profileDelta.recent_accuracy_delta >= 0 ? '+' : '' }}</span>
                  <AnimatedNumber :value="profileDelta.recent_accuracy_delta * 100" :decimals="1" />
                  %
                  <span class="ml-1">{{ profileDelta.recent_accuracy_delta >= 0 ? '↑' : '↓' }}</span>
                </p>
              </div>
              <div class="bg-accent/40 rounded-lg p-3 space-y-1">
                <p class="text-muted-foreground">挫败感</p>
                <p :class="profileDelta.frustration_delta <= 0 ? 'text-green-600' : 'text-red-600'">
                  <span>{{ profileDelta.frustration_delta >= 0 ? '+' : '' }}</span>
                  <AnimatedNumber :value="profileDelta.frustration_delta" :decimals="2" />
                  <span class="ml-1">{{ profileDelta.frustration_delta <= 0 ? '↓' : '↑' }}</span>
                </p>
              </div>
            </div>
            <div v-if="profileDelta.ability_level_changed" class="text-xs font-semibold text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
              能力等级更新！继续保持进步节奏。
            </div>
          </div>
          <div v-if="quizResult.feedback" class="mt-4 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg text-left space-y-2">
            <p class="text-xs font-bold uppercase tracking-widest text-amber-600">学习建议</p>
            <div
              class="quiz-feedback-markdown markdown-content"
              v-html="renderMarkdown(quizResult.feedback.message)"
            ></div>
            <div v-if="quizResult.next_quiz_recommendation" class="text-xs text-amber-700">
              下次建议：{{ quizResult.next_quiz_recommendation.difficulty }} 难度
              <span v-if="quizResult.next_quiz_recommendation.focus_concepts?.length">
                （重点：{{ quizResult.next_quiz_recommendation.focus_concepts.join('、') }}）
              </span>
            </div>
          </div>
        </div>
      </aside>

      <!-- Right: Quiz Content -->
      <section class="lg:col-span-2 space-y-4 md:space-y-6 relative">
        <LoadingOverlay :show="busy.quiz" message="正在根据知识库生成题目…" />
        <div v-if="quiz" class="space-y-6">
          <div v-for="(q, idx) in quiz.questions" :id="`question-${idx + 1}`" :key="idx" class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-4 transition-all" :class="{ 'border-primary/50 ring-1 ring-primary/20': quizResult }">
            <div class="flex items-start gap-4">
              <div class="flex-shrink-0 w-8 h-8 bg-accent text-accent-foreground rounded-lg flex items-center justify-center font-bold">
                {{ idx + 1 }}
              </div>
              <div class="space-y-4 flex-1">
                <div v-if="q._imageObjectUrl || q.image?.caption" class="space-y-2">
                  <div
                    v-if="q._imageObjectUrl"
                    class="rounded-xl border border-border bg-background p-2 overflow-hidden"
                  >
                    <button
                      type="button"
                      class="group relative block w-full rounded-lg overflow-hidden focus:outline-none focus:ring-2 focus:ring-primary/50"
                      :aria-label="`打开题目配图预览（第 ${idx + 1} 题）`"
                      @click="openQuestionImagePreview(q, idx)"
                    >
                      <img
                        :src="q._imageObjectUrl"
                        :alt="q.image?.caption || `题目配图 ${idx + 1}`"
                        class="w-full max-h-72 object-contain rounded-lg bg-muted/20"
                        loading="lazy"
                      />
                      <span
                        class="absolute inset-x-2 bottom-2 rounded-md bg-black/60 text-white text-[11px] px-2 py-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"
                      >
                        点击放大预览
                      </span>
                    </button>
                  </div>
                  <p v-if="q.image?.caption" class="text-xs text-muted-foreground">
                    图注：{{ q.image.caption }}
                  </p>
                </div>

                <div class="quiz-question-markdown markdown-content" v-html="renderMarkdown(q.question)"></div>
                
                <div class="grid grid-cols-1 gap-2">
                  <label 
                    v-for="(opt, optIdx) in q.options" 
                    :key="optIdx"
                    class="flex items-start sm:items-center gap-3 p-3 rounded-lg border border-border cursor-pointer transition-all hover:bg-accent/50"
                    :class="{ 
                      'bg-primary/10 border-primary/30': quizAnswers[idx] === optIdx && !quizResult,
                      'bg-green-500/10 border-green-500/30': quizResult && q.answer_index === optIdx,
                      'bg-destructive/10 border-destructive/30': quizResult && quizAnswers[idx] === optIdx && q.answer_index !== optIdx,
                      'opacity-50 grayscale-[0.5]': quizResult && quizAnswers[idx] !== optIdx && q.answer_index !== optIdx
                    }"
                  >
                    <input
                      type="radio"
                      :name="`q-${idx}`"
                      :value="optIdx"
                      v-model.number="quizAnswers[idx]"
                      class="hidden"
                      :disabled="!!quizResult"
                    />
                    <div class="w-5 h-5 rounded-full border-2 border-primary flex items-center justify-center flex-shrink-0">
                      <div v-if="quizAnswers[idx] === optIdx" class="w-2.5 h-2.5 bg-primary rounded-full"></div>
                    </div>
                    <span
                      class="quiz-option-markdown min-w-0 flex-1"
                      v-html="renderMarkdownInline(opt)"
                    ></span>
                    <CheckCircle2 v-if="quizResult && q.answer_index === optIdx" class="w-5 h-5 text-green-500 ml-auto" />
                    <XCircle v-if="quizResult && quizAnswers[idx] === optIdx && q.answer_index !== optIdx" class="w-5 h-5 text-destructive ml-auto" />
                  </label>
                </div>

                <div v-if="quizResult" class="mt-4 p-4 bg-accent/30 rounded-lg space-y-2">
                  <p class="text-xs font-bold uppercase tracking-widest text-primary">解析</p>
                  <div
                    class="quiz-explanation-markdown markdown-content"
                    v-html="renderMarkdown(quizResult.explanations[idx])"
                  ></div>
                  <div v-if="quizResult.results?.[idx] === false" class="pt-2 flex justify-end">
                    <button
                      class="px-3 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/15 transition-colors"
                      @click="goToQaExplainForWrongQuestion(idx)"
                    >
                      讲解此题
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-center pt-4">
            <Button
              v-if="!quizResult"
              size="lg"
              class="w-full sm:w-auto px-6 sm:px-12 text-base sm:text-lg font-black shadow-lg hover:scale-105"
              @click="submitQuiz"
              :loading="busy.submit"
              :disabled="busy.submit || !!quizResult || Object.keys(quizAnswers).length < quiz.questions.length"
            >
              {{ busy.submit ? '正在批改…' : '提交全部答案' }}
            </Button>
            <button
              v-else
              class="w-full sm:w-auto px-6 sm:px-12 py-4 bg-secondary text-secondary-foreground rounded-xl font-black text-base sm:text-lg shadow-lg hover:scale-105 active:scale-95 transition-all"
              @click="generateQuiz"
            >
              再测一次
            </button>
          </div>
          <div v-if="hasMasteryUpdates" class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
            <h3 class="text-lg font-bold">知识点掌握度变化</h3>
            <p v-if="isKbQuizResultContext" class="text-xs text-muted-foreground">
              以下知识点反馈已按知识库口径去重合并统计。
            </p>
            <div class="grid grid-cols-1 gap-3">
              <div v-for="mu in masteryUpdates" :key="mu.keypoint_id"
                class="flex items-center gap-3 p-3 border rounded-lg"
                :class="masteryBorderClass(mu.new_level)">
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium truncate">{{ mu.text }}</p>
                  <div class="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                    <span>{{ masteryPercent(mu.old_level) }}%</span>
                    <span>→</span>
                    <span class="font-semibold" :class="mu.new_level > mu.old_level ? 'text-green-600' : 'text-red-500'">
                      {{ masteryPercent(mu.new_level) }}%
                    </span>
                  </div>
                </div>
                <span class="px-2 py-1 text-[10px] font-bold rounded-full border" :class="masteryBadgeClass(mu.new_level)">
                  {{ masteryLabel(mu.new_level) }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="hasWrongGroups" class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-lg font-bold">错题知识点归类</h3>
                <p class="text-xs text-muted-foreground">点击题号可跳转到对应题目</p>
                <p v-if="isKbQuizResultContext" class="text-xs text-muted-foreground">
                  概念名称可能与单文档表述不同，但会映射到同一知识点。
                </p>
              </div>
              <button
                class="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity"
                @click="generateTargetedQuiz"
              >
                针对薄弱点再练
              </button>
            </div>
            <div class="grid grid-cols-1 gap-3">
              <div v-for="group in wrongQuestionGroups" :key="group.concept" class="border border-border rounded-lg p-4 bg-accent/20">
                <div
                  class="quiz-concept-markdown text-primary"
                  v-html="renderMarkdownInline(group.concept)"
                ></div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <button
                    v-for="index in group.question_indices"
                    :key="index"
                    class="px-3 py-1 text-xs font-semibold rounded-full bg-background border border-input hover:border-primary hover:text-primary transition-colors"
                    @click="scrollToQuestion(index)"
                  >
                    第 {{ index }} 题
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="bg-card border border-border rounded-xl p-4 sm:p-6 lg:p-8 min-h-[420px] flex items-center justify-center">
          <EmptyState
            :icon="PenTool"
            :title="quizEmptyTitle"
            :description="quizEmptyDescription"
            :hint="quizEmptyHint"
            size="lg"
            :primary-action="quizEmptyPrimaryAction"
            @primary="handleQuizEmptyPrimary"
          />
        </div>
      </section>
    </div>
    <ImageLightboxModal
      :open="imagePreviewState.open"
      :src="imagePreviewState.src"
      :alt="imagePreviewState.alt"
      :caption="imagePreviewState.caption"
      :title="imagePreviewState.title"
      @close="closeQuestionImagePreview"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PenTool, Sparkles, CheckCircle2, XCircle } from 'lucide-vue-next'
import { apiGet, apiGetBlob, apiPost } from '../api'
import AnimatedNumber from '../components/ui/AnimatedNumber.vue'
import { useToast } from '../composables/useToast'
import { useAppContextStore } from '../stores/appContext'
import Button from '../components/ui/Button.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ImageLightboxModal from '../components/ui/ImageLightboxModal.vue'
import LoadingOverlay from '../components/ui/LoadingOverlay.vue'
import { masteryLabel, masteryPercent, masteryBadgeClass, masteryBorderClass } from '../utils/mastery'
import { renderMarkdown, renderMarkdownInline } from '../utils/markdown'
import { buildRouteContextQuery, normalizeDifficulty, parseRouteContext } from '../utils/routeContext'

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
const docsInKb = ref([])
const quiz = ref(null)
const quizAnswers = ref({})
const quizResult = ref(null)
const quizCount = ref(5)
const quizDifficulty = ref('medium')
const autoAdapt = ref(true)
const quizFocusConcepts = ref([])
const quizFocusSearch = ref('')
const quizFocusCandidate = ref('')
const quizFocusOptions = ref([])
const busy = ref({
  quiz: false,
  submit: false,
  docs: false,
  focusKeypoints: false,
})

const profileDelta = computed(() => quizResult.value?.profile_delta || null)
const hasProfileDelta = computed(() => !!profileDelta.value)
const wrongQuestionGroups = computed(() => quizResult.value?.wrong_questions_by_concept || [])
const hasWrongGroups = computed(() => wrongQuestionGroups.value.length > 0)
const masteryUpdates = computed(() => quizResult.value?.mastery_updates || [])
const hasMasteryUpdates = computed(() => masteryUpdates.value.length > 0)
const isKbQuizResultContext = computed(() => Boolean(selectedKbId.value && quizResult.value))
const entryKbContextId = computed(() => parseRouteContext(route.query).kbId)
const entryDocContextId = computed(() => parseRouteContext(route.query).docId)
const entryFocusContext = computed(() => appContext.routeContext.focus)
const hasPathContext = computed(() => Boolean(entryKbContextId.value || entryDocContextId.value || entryFocusContext.value))
const entryKbContextName = computed(() => {
  if (!entryKbContextId.value) return ''
  const kb = kbs.value.find((item) => item.id === entryKbContextId.value)
  if (kb?.name) return kb.name
  return `${entryKbContextId.value.slice(0, 8)}...`
})
const entryDocContextName = computed(() => {
  if (!entryDocContextId.value) return ''
  const doc = docsInKb.value.find((item) => item.id === entryDocContextId.value)
  if (doc?.filename) return doc.filename
  return `${entryDocContextId.value.slice(0, 8)}...`
})
const hasAnyKb = computed(() => kbs.value.length > 0)
const quizEmptyTitle = computed(() => {
  if (!hasAnyKb.value) return '先上传文档再开始测验'
  if (!selectedKbId.value) return '先选择知识库'
  return '准备好检验掌握程度了吗？'
})
const quizEmptyDescription = computed(() => {
  if (!hasAnyKb.value) return '当前还没有知识库，上传并解析文档后才能生成测验。'
  if (!selectedKbId.value) return '在左侧选择目标知识库，并按需设置题量与难度。'
  return '已选知识库后可直接生成专属测验，系统会根据配置生成题目。'
})
const quizEmptyHint = computed(() => {
  if (!hasAnyKb.value) return '上传完成后返回本页即可一键生成题目。'
  if (!selectedKbId.value) return '开启自适应模式后，系统会自动调整题目难度。'
  return '生成后可提交批改，并查看错题归类与能力变化。'
})
const quizEmptyPrimaryAction = computed(() => {
  if (!hasAnyKb.value) return { label: '去上传文档' }
  if (!selectedKbId.value) return null
  return { label: '生成新测验', loading: busy.value.quiz }
})
const scopedQuizFocusOptions = computed(() => {
  const options = Array.isArray(quizFocusOptions.value) ? quizFocusOptions.value : []
  const docId = String(selectedDocId.value || '').trim()
  if (!docId) return options
  return options.filter((item) => {
    const sourceDocIds = Array.isArray(item?.sourceDocIds) ? item.sourceDocIds : []
    return sourceDocIds.includes(docId)
  })
})
const filteredQuizFocusOptions = computed(() => {
  const keyword = String(quizFocusSearch.value || '').trim().toLowerCase()
  const selected = new Set((quizFocusConcepts.value || []).map((item) => String(item || '').trim().toLowerCase()))
  const options = Array.isArray(scopedQuizFocusOptions.value) ? scopedQuizFocusOptions.value : []
  return options
    .filter((item) => {
      const text = String(item?.text || '').trim()
      if (!text) return false
      if (selected.has(text.toLowerCase())) return false
      if (!keyword) return true
      return text.toLowerCase().includes(keyword)
    })
    .slice(0, 80)
})
const quizFocusSelectPlaceholder = computed(() => {
  if (busy.value.focusKeypoints) return '正在加载知识点...'
  if (filteredQuizFocusOptions.value.length) return '请选择知识点'
  return selectedDocId.value ? '该文档暂无可选聚合知识点' : '暂无可选聚合知识点'
})
const OPTION_LABELS = ['A', 'B', 'C', 'D']
let quizImageLoadSeq = 0
const imagePreviewState = ref({
  open: false,
  src: '',
  alt: '',
  caption: '',
  title: '图片预览',
})

function closeQuestionImagePreview() {
  imagePreviewState.value = {
    open: false,
    src: '',
    alt: '',
    caption: '',
    title: '图片预览',
  }
}

function openQuestionImagePreview(question, questionIndex) {
  const src = typeof question?._imageObjectUrl === 'string' ? question._imageObjectUrl.trim() : ''
  if (!src) return
  const caption = typeof question?.image?.caption === 'string' ? question.image.caption.trim() : ''
  imagePreviewState.value = {
    open: true,
    src,
    alt: caption || `题目配图 ${questionIndex + 1}`,
    caption,
    title: `第 ${questionIndex + 1} 题配图`,
  }
}

function revokeQuizImageObjectUrls(quizPayload) {
  if (imagePreviewState.value.open) {
    const openSrc = imagePreviewState.value.src
    const questions = Array.isArray(quizPayload?.questions) ? quizPayload.questions : []
    if (questions.some((q) => q && q._imageObjectUrl === openSrc)) {
      closeQuestionImagePreview()
    }
  }
  const questions = Array.isArray(quizPayload?.questions) ? quizPayload.questions : []
  for (const q of questions) {
    if (q && q._imageObjectUrl) {
      try {
        URL.revokeObjectURL(q._imageObjectUrl)
      } catch {
        // ignore revoke failures
      }
      q._imageObjectUrl = ''
    }
  }
}

async function hydrateQuizQuestionImages(quizPayload) {
  const currentSeq = ++quizImageLoadSeq
  const questions = Array.isArray(quizPayload?.questions) ? quizPayload.questions : []
  for (const q of questions) {
    if (!q || !q.image || typeof q.image !== 'object') continue
    const imageUrl = typeof q.image.url === 'string' ? q.image.url.trim() : ''
    if (!imageUrl) continue
    try {
      const blob = await apiGetBlob(imageUrl)
      if (currentSeq !== quizImageLoadSeq) return
      if (!(blob instanceof Blob)) continue
      q._imageObjectUrl = URL.createObjectURL(blob)
    } catch {
      // Image is optional; keep question usable even if preview image fails.
      q._imageObjectUrl = ''
    }
  }
}

function goToUpload() {
  router.push({ path: '/upload' })
}

function handleQuizEmptyPrimary() {
  if (!hasAnyKb.value) {
    goToUpload()
    return
  }
  if (!selectedKbId.value) return
  generateQuiz()
}

function normalizeQuizFocusConcepts(values = []) {
  const seen = new Set()
  const out = []
  for (const raw of values) {
    const text = String(raw ?? '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(text)
    if (out.length >= 8) break
  }
  return out
}

function addQuizFocusConcept(concept) {
  const next = normalizeQuizFocusConcepts([...(quizFocusConcepts.value || []), concept])
  quizFocusConcepts.value = next
}

function addSelectedQuizFocusCandidate() {
  const text = String(quizFocusCandidate.value || '').trim()
  if (!text) return
  addQuizFocusConcept(text)
  quizFocusCandidate.value = ''
}

function clearQuizFocusConcepts() {
  quizFocusConcepts.value = []
  quizFocusSearch.value = ''
  quizFocusCandidate.value = ''
}

function removeQuizFocusConcept(index) {
  if (!Number.isInteger(index) || index < 0 || index >= quizFocusConcepts.value.length) return
  quizFocusConcepts.value = quizFocusConcepts.value.filter((_, idx) => idx !== index)
}

function normalizeQuizFocusOptions(items = []) {
  const seenIndex = new Map()
  const out = []
  for (const item of items) {
    const id = String(item?.id || '').trim()
    const text = String(item?.text || '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    const sourceDocIds = [
      ...new Set(
        (Array.isArray(item?.source_doc_ids) ? item.source_doc_ids : [])
          .map((docId) => String(docId || '').trim())
          .filter(Boolean)
      )
    ]
    if (seenIndex.has(key)) {
      const existingIndex = seenIndex.get(key)
      const existing = out[existingIndex]
      const mergedSourceDocIds = [
        ...new Set([...(existing.sourceDocIds || []), ...sourceDocIds])
      ]
      existing.sourceDocIds = mergedSourceDocIds
      existing.sourceDocCount = mergedSourceDocIds.length
      existing.memberCount = Math.max(
        Number(existing.memberCount || 1),
        Number(item?.member_count || 1),
      )
      continue
    }
    seenIndex.set(key, out.length)
    out.push({
      id: id || text,
      text,
      memberCount: Number(item?.member_count || 1),
      sourceDocCount: sourceDocIds.length,
      sourceDocIds,
    })
  }
  return out
}

function syncQuizFocusCandidateSelection() {
  if (
    quizFocusCandidate.value
    && !filteredQuizFocusOptions.value.some((item) => item.text === quizFocusCandidate.value)
  ) {
    quizFocusCandidate.value = ''
  }
}

function pruneQuizFocusConceptsToCurrentDocScope() {
  if (!selectedDocId.value) return
  if (!Array.isArray(quizFocusOptions.value)) return
  if (!quizFocusOptions.value.length && busy.value.focusKeypoints) return
  const allowedTexts = new Set(
    (Array.isArray(scopedQuizFocusOptions.value) ? scopedQuizFocusOptions.value : [])
      .map((item) => String(item?.text || '').trim())
      .filter(Boolean)
  )
  const next = (Array.isArray(quizFocusConcepts.value) ? quizFocusConcepts.value : [])
    .map((item) => String(item || '').trim())
    .filter((text) => text && allowedTexts.has(text))
  const prev = Array.isArray(quizFocusConcepts.value) ? quizFocusConcepts.value : []
  if (next.length === prev.length && next.every((item, idx) => item === prev[idx])) {
    return
  }
  quizFocusConcepts.value = next
}

async function refreshQuizFocusOptions() {
  if (!selectedKbId.value) {
    quizFocusOptions.value = []
    quizFocusCandidate.value = ''
    busy.value.focusKeypoints = false
    return
  }
  busy.value.focusKeypoints = true
  const requestKbId = selectedKbId.value
  try {
    const params = new URLSearchParams()
    params.set('user_id', resolvedUserId.value)
    params.set('grouped', 'true')
    const res = await apiGet(`/api/keypoints/kb/${encodeURIComponent(requestKbId)}?${params.toString()}`)
    if (selectedKbId.value !== requestKbId) return
    quizFocusOptions.value = normalizeQuizFocusOptions(Array.isArray(res?.keypoints) ? res.keypoints : [])
  } catch {
    if (selectedKbId.value !== requestKbId) return
    quizFocusOptions.value = []
    // error toast handled globally
  } finally {
    if (selectedKbId.value === requestKbId) {
      busy.value.focusKeypoints = false
    }
  }
  pruneQuizFocusConceptsToCurrentDocScope()
  syncQuizFocusCandidateSelection()
}

function maybeAdoptRouteFocusConcept(focusText) {
  const raw = String(focusText || '').trim()
  if (!raw || quizFocusConcepts.value.length) return ''
  const scopedOptions = Array.isArray(scopedQuizFocusOptions.value) ? scopedQuizFocusOptions.value : []
  const exact = scopedOptions.find((item) => String(item?.text || '').trim() === raw)
  if (exact) {
    addQuizFocusConcept(exact.text)
    return exact.text
  }
  const normalized = raw.toLowerCase()
  const partial = scopedOptions.find((item) => String(item?.text || '').toLowerCase().includes(normalized))
  if (partial) {
    addQuizFocusConcept(partial.text)
    return partial.text
  }
  if (selectedDocId.value) return ''
  // Route-provided focus originates from internal recommendation/learning-path flows; allow as fallback.
  addQuizFocusConcept(raw)
  return raw
}

async function refreshDocsInKb() {
  if (!selectedKbId.value) {
    docsInKb.value = []
    busy.value.docs = false
    if (selectedDocId.value) selectedDocId.value = ''
    return
  }
  busy.value.docs = true
  try {
    const rows = await apiGet(
      `/api/docs?user_id=${encodeURIComponent(resolvedUserId.value)}&kb_id=${encodeURIComponent(selectedKbId.value)}`
    )
    docsInKb.value = Array.isArray(rows) ? rows : []
  } catch {
    docsInKb.value = []
    // error toast handled globally
  } finally {
    busy.value.docs = false
  }
  if (selectedDocId.value && !docsInKb.value.some((doc) => doc.id === selectedDocId.value)) {
    selectedDocId.value = ''
  }
}

async function generateQuiz(options = {}) {
  if (!selectedKbId.value) return
  busy.value.quiz = true
  closeQuestionImagePreview()
  revokeQuizImageObjectUrls(quiz.value)
  quiz.value = null
  quizAnswers.value = {}
  quizResult.value = null
  try {
    const payload = {
      kb_id: selectedKbId.value,
      count: quizCount.value,
      user_id: resolvedUserId.value,
      auto_adapt: autoAdapt.value
    }
    if (selectedDocId.value) {
      payload.doc_id = selectedDocId.value
    }
    const explicitFocusConcepts = normalizeQuizFocusConcepts(options.focusConcepts || quizFocusConcepts.value)
    if (explicitFocusConcepts.length) {
      payload.focus_concepts = explicitFocusConcepts
    }
    if (!autoAdapt.value) {
      payload.difficulty = quizDifficulty.value
    }
    const res = await apiPost('/api/quiz/generate', payload)
    quiz.value = res
    void hydrateQuizQuestionImages(quiz.value)
    showToast(`已生成 ${res.questions?.length || 0} 道题目`, 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.quiz = false
  }
}

async function submitQuiz() {
  if (!quiz.value || quizResult.value) return
  busy.value.submit = true
  try {
    const answers = quiz.value.questions.map((_, idx) => quizAnswers.value[idx] ?? null)
    const res = await apiPost('/api/quiz/submit', {
      quiz_id: quiz.value.quiz_id,
      answers,
      user_id: resolvedUserId.value
    })
    quizResult.value = res
    showToast(`测验已批改，得分 ${Math.round(res.score * 100)}%`, 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.submit = false
  }
}

function generateTargetedQuiz() {
  const concepts = [
    ...new Set(
      wrongQuestionGroups.value
        .map((group) => group.concept)
        .filter((concept) => concept && String(concept).trim())
    )
  ]
  if (!concepts.length) {
    generateQuiz()
    return
  }
  generateQuiz({ focusConcepts: concepts })
}

function formatQuizOptionLabel(optionIndex, options) {
  if (!Number.isInteger(optionIndex) || optionIndex < 0 || optionIndex >= OPTION_LABELS.length) {
    return '未作答'
  }
  const label = OPTION_LABELS[optionIndex] || `选项${optionIndex + 1}`
  const text = Array.isArray(options) ? String(options[optionIndex] ?? '').trim() : ''
  return text ? `${label}. ${text}` : label
}

function buildWrongQuestionExplainPrompt(questionIndex) {
  const q = quiz.value?.questions?.[questionIndex]
  if (!q) return ''
  const selectedIndex = Number.isInteger(quizAnswers.value?.[questionIndex])
    ? quizAnswers.value[questionIndex]
    : null
  const answerIndex = Number.isInteger(q.answer_index) ? q.answer_index : null
  const optionLines = Array.isArray(q.options)
    ? q.options.map((opt, idx) => `${OPTION_LABELS[idx] || `选项${idx + 1}`}. ${String(opt ?? '').trim()}`).join('\n')
    : ''

  return [
    '请用讲解模式解析这道选择题，并重点解释我为什么会错、如何避免再次出错。',
    '',
    `题干：${String(q.question || '').trim()}`,
    '选项：',
    optionLines,
    `我的答案：${formatQuizOptionLabel(selectedIndex, q.options)}`,
    `正确答案：${formatQuizOptionLabel(answerIndex, q.options)}`,
    '额外要求：请总结易错点，并给出 1-2 个自测变式问题。',
  ].join('\n')
}

function goToQaExplainForWrongQuestion(questionIndex) {
  const q = quiz.value?.questions?.[questionIndex]
  if (!q || !selectedKbId.value) return
  const explainPrompt = buildWrongQuestionExplainPrompt(questionIndex)
  if (!explainPrompt) return

  const focusConcept = Array.isArray(q.concepts)
    ? q.concepts.find((concept) => concept && String(concept).trim())
    : ''

  const query = buildRouteContextQuery(
    {
      kbId: selectedKbId.value,
      focus: focusConcept ? String(focusConcept).trim() : '',
    },
    {
      qa_mode: 'explain',
      qa_autosend: '1',
      qa_question: explainPrompt,
      qa_from: 'quiz_wrong',
    }
  )

  router.push({ path: '/qa', query })
}

function scrollToQuestion(index) {
  const target = document.getElementById(`question-${index}`)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
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

    const queryDifficulty = appContext.routeContext.difficulty
    if (queryDifficulty) {
      autoAdapt.value = false
      quizDifficulty.value = queryDifficulty
    }

    const queryFocus = entryFocusContext.value
    const queryDocId = entryDocContextId.value
    if (!options.autoGenerate) return
    if ((!queryFocus && !queryDifficulty) || !selectedKbId.value) return

    const contextKey = `${selectedKbId.value}|${queryDocId}|${queryFocus}|${queryDifficulty}`
    if (lastAutoContextKey.value === contextKey) return
    lastAutoContextKey.value = contextKey

    const generateOptions = {}
    let adoptedFocus = ''
    if (queryFocus) {
      adoptedFocus = maybeAdoptRouteFocusConcept(queryFocus)
    }
    if (adoptedFocus) {
      generateOptions.focusConcepts = [adoptedFocus]
    }
    await generateQuiz(generateOptions)
  } finally {
    syncingRouteContext.value = false
  }
}

onMounted(async () => {
  try {
    await appContext.loadKbs()
  } catch {
    // error toast handled globally
  }
  await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions()])
  await syncFromRoute({ autoGenerate: true })
})

onActivated(async () => {
  await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions()])
  await syncFromRoute({
    ensureKbs: !appContext.kbs.length,
    autoGenerate: true,
  })
})

onBeforeUnmount(() => {
  closeQuestionImagePreview()
  quizImageLoadSeq += 1
  revokeQuizImageObjectUrls(quiz.value)
})

watch(
  () => route.fullPath,
  async () => {
    await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions()])
    await syncFromRoute({ autoGenerate: true })
  }
)

watch(selectedKbId, async () => {
  clearQuizFocusConcepts()
  quizFocusOptions.value = []
  quizFocusSearch.value = ''
  quizFocusCandidate.value = ''
  await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions()])
})

watch(selectedDocId, () => {
  pruneQuizFocusConceptsToCurrentDocScope()
  syncQuizFocusCandidateSelection()
})

watch(quizFocusOptions, () => {
  pruneQuizFocusConceptsToCurrentDocScope()
  syncQuizFocusCandidateSelection()
})

watch(quizFocusSearch, () => {
  syncQuizFocusCandidateSelection()
})

watch(quizFocusConcepts, () => {
  syncQuizFocusCandidateSelection()
})
</script>
