<template>
  <div class="space-y-8 max-w-6xl mx-auto">
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Left: Quiz Generation -->
      <aside class="space-y-6">
        <section class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-6">
          <div class="flex items-center gap-3">
            <PenTool class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">测验生成</h2>
          </div>

          <div class="space-y-4">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">目标文档</label>
              <select v-model="selectedDocId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                <option disabled value="">请选择</option>
                <option v-for="doc in docs" :key="doc.id" :value="doc.id">{{ doc.filename }}</option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">题目数量</label>
                <input type="number" min="1" max="20" v-model.number="quizCount" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm" />
              </div>
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">难度</label>
                <select v-model="quizDifficulty" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                  <option value="easy">简单</option>
                  <option value="medium">中等</option>
                  <option value="hard">困难</option>
                </select>
              </div>
            </div>

            <button
              class="w-full bg-primary text-primary-foreground rounded-lg py-3 font-bold hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
              :disabled="!selectedDocId || busy.quiz"
              @click="generateQuiz"
            >
              <Sparkles v-if="!busy.quiz" class="w-5 h-5" />
              <RefreshCw v-else class="w-5 h-5 animate-spin" />
              {{ busy.quiz ? '正在生成题目…' : '生成新测验' }}
            </button>
          </div>
        </section>

        <div v-if="quizResult" class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4 text-center">
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
        </div>
      </aside>

      <!-- Right: Quiz Content -->
      <section class="lg:col-span-2 space-y-6">
        <div v-if="busy.quiz" class="bg-card border border-border rounded-xl p-12 flex flex-col items-center justify-center space-y-4">
          <div class="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          <p class="text-muted-foreground animate-pulse font-medium">正在根据文档生成题目…</p>
        </div>

        <div v-else-if="quiz" class="space-y-6">
          <div v-for="(q, idx) in quiz.questions" :key="idx" class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4 transition-all" :class="{ 'border-primary/50 ring-1 ring-primary/20': quizResult }">
            <div class="flex items-start gap-4">
              <div class="flex-shrink-0 w-8 h-8 bg-accent text-accent-foreground rounded-lg flex items-center justify-center font-bold">
                {{ idx + 1 }}
              </div>
              <div class="space-y-4 flex-1">
                <h3 class="text-lg font-bold leading-tight">{{ q.question }}</h3>
                
                <div class="grid grid-cols-1 gap-2">
                  <label 
                    v-for="(opt, optIdx) in q.options" 
                    :key="optIdx"
                    class="flex items-center gap-3 p-3 rounded-lg border border-border cursor-pointer transition-all hover:bg-accent/50"
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
                    <span class="text-sm font-medium">{{ opt }}</span>
                    <CheckCircle2 v-if="quizResult && q.answer_index === optIdx" class="w-5 h-5 text-green-500 ml-auto" />
                    <XCircle v-if="quizResult && quizAnswers[idx] === optIdx && q.answer_index !== optIdx" class="w-5 h-5 text-destructive ml-auto" />
                  </label>
                </div>

                <div v-if="quizResult" class="mt-4 p-4 bg-accent/30 rounded-lg space-y-2">
                  <p class="text-xs font-bold uppercase tracking-widest text-primary">解析</p>
                  <p class="text-sm leading-relaxed text-muted-foreground">{{ quizResult.explanations[idx] }}</p>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-center pt-4">
            <button
              v-if="!quizResult"
              class="px-12 py-4 bg-primary text-primary-foreground rounded-xl font-black text-lg shadow-lg hover:scale-105 active:scale-95 transition-all disabled:opacity-50"
              @click="submitQuiz"
              :disabled="busy.submit || Object.keys(quizAnswers).length < quiz.questions.length"
            >
              {{ busy.submit ? '正在批改…' : '提交全部答案' }}
            </button>
            <button
              v-else
              class="px-12 py-4 bg-secondary text-secondary-foreground rounded-xl font-black text-lg shadow-lg hover:scale-105 active:scale-95 transition-all"
              @click="generateQuiz"
            >
              再测一次
            </button>
          </div>
        </div>

        <div v-else class="bg-card border border-border rounded-xl p-20 flex flex-col items-center justify-center text-center space-y-6">
          <div class="w-24 h-24 bg-accent rounded-full flex items-center justify-center">
            <PenTool class="w-12 h-12 text-primary opacity-50" />
          </div>
          <div class="space-y-2">
            <h2 class="text-2xl font-bold">准备好检验掌握程度了吗？</h2>
            <p class="text-muted-foreground max-w-sm mx-auto">选择文档并设置偏好，即可生成专属测验。</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { PenTool, Sparkles, RefreshCw, CheckCircle2, XCircle } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'

const userId = ref(localStorage.getItem('gradtutor_user') || 'default')
const resolvedUserId = computed(() => userId.value || 'default')
const docs = ref([])
const selectedDocId = ref('')
const quiz = ref(null)
const quizAnswers = ref({})
const quizResult = ref(null)
const quizCount = ref(5)
const quizDifficulty = ref('medium')
const busy = ref({
  quiz: false,
  submit: false
})

async function refreshDocs() {
  try {
    docs.value = await apiGet(`/api/docs?user_id=${encodeURIComponent(resolvedUserId.value)}`)
  } catch (err) {
    console.error(err)
  }
}

async function generateQuiz() {
  if (!selectedDocId.value) return
  busy.value.quiz = true
  quiz.value = null
  quizAnswers.value = {}
  quizResult.value = null
  try {
    const res = await apiPost('/api/quiz/generate', {
      doc_id: selectedDocId.value,
      count: quizCount.value,
      difficulty: quizDifficulty.value,
      user_id: resolvedUserId.value
    })
    quiz.value = res
  } catch (err) {
    console.error(err)
  } finally {
    busy.value.quiz = false
  }
}

async function submitQuiz() {
  if (!quiz.value) return
  busy.value.submit = true
  try {
    const answers = quiz.value.questions.map((_, idx) => quizAnswers.value[idx] ?? null)
    const res = await apiPost('/api/quiz/submit', {
      quiz_id: quiz.value.quiz_id,
      answers,
      user_id: resolvedUserId.value
    })
    quizResult.value = res
  } catch (err) {
    console.error(err)
  } finally {
    busy.value.submit = false
  }
}

onMounted(async () => {
  await refreshDocs()
})
</script>
