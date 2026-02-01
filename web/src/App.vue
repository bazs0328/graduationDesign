<template>
  <div class="app-shell">
    <section class="hero">
      <h1>GradTutor</h1>
      <p>Upload learning materials, generate summaries and quizzes, and chat with a tutor.</p>
      <div class="user-row">
        <span class="muted">User ID</span>
        <input class="user-input" type="text" v-model="userIdInput" />
        <button class="secondary" @click="applyUserId">Apply</button>
      </div>
    </section>

    <section class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="tab"
        :class="{ active: activeTab === tab }"
        @click="activeTab = tab"
      >
        {{ tab }}
      </button>
    </section>
    <p v-if="statusMessage" class="status">{{ statusMessage }}</p>

    <section v-if="activeTab === 'Upload'" class="grid">
      <div class="card">
        <h2>Upload Document</h2>
        <label>Knowledge Base</label>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
          <select v-model="selectedKbId">
            <option disabled value="">Select...</option>
            <option v-for="kb in kbs" :key="kb.id" :value="kb.id">
              {{ kb.name }}
            </option>
          </select>
          <input
            class="user-input"
            style="flex: 1; min-width: 160px"
            type="text"
            v-model="kbNameInput"
            placeholder="New knowledge base name"
          />
          <button class="secondary" :disabled="!kbNameInput || busy.kb" @click="createKb">
            {{ busy.kb ? 'Creating...' : 'Create KB' }}
          </button>
        </div>
        <label>Select PDF or text file</label>
        <input type="file" @change="onFileChange" />
        <div style="margin-top: 12px; display: flex; gap: 10px;">
          <button :disabled="!uploadFile || busy.upload" @click="uploadDoc">
            {{ busy.upload ? 'Uploading...' : 'Upload' }}
          </button>
          <button class="secondary" @click="refreshDocs">Refresh List</button>
        </div>
        <p v-if="statusMessage" class="status">{{ statusMessage }}</p>
      </div>

      <div class="card">
        <h2>Documents</h2>
        <div class="list">
          <div v-for="doc in docs" :key="doc.id" class="list-item">
            <strong>{{ doc.filename }}</strong>
            <span v-if="doc.kb_id" class="badge">{{ kbNameById(doc.kb_id) }}</span>
            <span v-if="doc.status" class="badge">{{ doc.status }}</span>
            <span class="badge">{{ doc.num_chunks }} chunks</span>
            <span class="badge">{{ doc.num_pages }} pages</span>
            <span class="badge">{{ doc.char_count }} chars</span>
            <p class="muted">{{ new Date(doc.created_at).toLocaleString() }}</p>
            <p v-if="doc.error_message" class="muted">Error: {{ doc.error_message }}</p>
          </div>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'Summary'" class="grid">
      <div class="card">
        <h2>Generate Summary</h2>
        <label>Choose a document</label>
        <select v-model="selectedDocId">
          <option disabled value="">Select...</option>
          <option v-for="doc in docs" :key="doc.id" :value="doc.id">
            {{ doc.filename }}
          </option>
        </select>
        <button style="margin-top: 12px" :disabled="!selectedDocId || busy.summary" @click="generateSummary()">
          {{ busy.summary ? 'Working...' : 'Summarize' }}
        </button>
        <button
          style="margin-top: 12px; margin-left: 8px"
          class="secondary"
          :disabled="!selectedDocId || busy.summary"
          @click="generateSummary(true)"
        >
          Regenerate
        </button>
        <p v-if="summary" class="muted" style="margin-top: 12px; white-space: pre-wrap;">
          {{ summary }} <span v-if="summaryCached"> (cached)</span>
        </p>
      </div>

      <div class="card">
        <h2>Keypoints</h2>
        <p class="muted">Extract concise knowledge points for review.</p>
        <button style="margin-top: 12px" :disabled="!selectedDocId || busy.keypoints" @click="generateKeypoints()">
          {{ busy.keypoints ? 'Extracting...' : 'Extract Keypoints' }}
        </button>
        <button
          style="margin-top: 12px; margin-left: 8px"
          class="secondary"
          :disabled="!selectedDocId || busy.keypoints"
          @click="generateKeypoints(true)"
        >
          Regenerate
        </button>
        <div v-if="keypoints.length" class="list" style="margin-top: 12px">
          <div v-for="(point, idx) in keypoints" :key="idx" class="list-item">
            {{ point }}
          </div>
          <p v-if="keypointsCached" class="muted">Cached result.</p>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'Q&A'" class="grid">
      <div class="card">
        <h2>Ask a Question</h2>
        <label>Choose a document</label>
        <select v-model="selectedDocId">
          <option disabled value="">Select...</option>
          <option v-for="doc in docs" :key="doc.id" :value="doc.id">
            {{ doc.filename }}
          </option>
        </select>
        <label style="margin-top: 12px">Question</label>
        <textarea v-model="qaInput" placeholder="e.g., Explain the main theorem"></textarea>
        <button style="margin-top: 12px" :disabled="!selectedDocId || !qaInput || busy.qa" @click="askQuestion">
          {{ busy.qa ? 'Thinking...' : 'Ask' }}
        </button>
      </div>

      <div class="card">
        <h2>Conversation</h2>
        <div class="qa-log">
          <div v-for="(msg, index) in qaMessages" :key="index" class="qa-bubble" :class="msg.role">
            <strong>{{ msg.role === 'answer' ? 'Tutor' : 'You' }}</strong>
            <p>{{ msg.content }}</p>
            <p v-if="msg.sources && msg.sources.length" class="muted">
              Sources: {{ msg.sources.map((s) => s.source).join(', ') }}
            </p>
          </div>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'Quiz'" class="grid">
      <div class="card">
        <h2>Generate Quiz</h2>
        <label>Choose a document</label>
        <select v-model="selectedDocId">
          <option disabled value="">Select...</option>
          <option v-for="doc in docs" :key="doc.id" :value="doc.id">
            {{ doc.filename }}
          </option>
        </select>
        <label style="margin-top: 12px">Question count</label>
        <input type="number" min="1" max="20" v-model.number="quizCount" />
        <label style="margin-top: 12px">Difficulty</label>
        <select v-model="quizDifficulty">
          <option value="easy">easy</option>
          <option value="medium">medium</option>
          <option value="hard">hard</option>
        </select>
        <button style="margin-top: 12px" :disabled="!selectedDocId || busy.quiz" @click="generateQuiz">
          {{ busy.quiz ? 'Building...' : 'Generate Quiz' }}
        </button>
      </div>

      <div class="card">
        <h2>Quiz</h2>
        <div v-if="quiz" class="list">
          <p v-if="quizResult" class="muted">
            Score: {{ quizResult.correct }} / {{ quizResult.total }}
            ({{ Math.round(quizResult.score * 100) }}%)
          </p>
          <div v-for="(q, idx) in quiz.questions" :key="idx" class="list-item">
            <strong>Q{{ idx + 1 }}. {{ q.question }}</strong>
            <div class="quiz-option" v-for="(opt, optIdx) in q.options" :key="optIdx">
              <input
                type="radio"
                :name="`q-${idx}`"
                :value="optIdx"
                v-model.number="quizAnswers[idx]"
              />
              <span>{{ opt }}</span>
            </div>
            <p v-if="quizResult" class="muted">
              {{ quizResult.results[idx] ? 'Correct' : 'Wrong' }} — {{ quizResult.explanations[idx] }}
            </p>
          </div>
          <button style="margin-top: 12px" class="secondary" @click="submitQuiz" :disabled="busy.submit">
            {{ busy.submit ? 'Scoring...' : 'Submit Answers' }}
          </button>
        </div>
        <p v-else class="muted">Generate a quiz to begin.</p>
      </div>
    </section>

    <section v-if="activeTab === 'Progress'" class="grid">
      <div class="card">
        <h2>Progress Overview</h2>
        <div v-if="progress" class="list">
          <div class="list-item">Documents: {{ progress.total_docs }}</div>
          <div class="list-item">Quizzes: {{ progress.total_quizzes }}</div>
          <div class="list-item">Attempts: {{ progress.total_attempts }}</div>
          <div class="list-item">Questions asked: {{ progress.total_questions }}</div>
          <div class="list-item">Summaries: {{ progress.total_summaries }}</div>
          <div class="list-item">Keypoints: {{ progress.total_keypoints }}</div>
          <div class="list-item">Average score: {{ progress.avg_score }}</div>
          <div class="list-item">
            Last activity: {{ progress.last_activity ? new Date(progress.last_activity).toLocaleString() : 'N/A' }}
          </div>
        </div>
        <button style="margin-top: 12px" class="secondary" @click="fetchProgress">Refresh</button>
      </div>

      <div class="card">
        <h2>Knowledge Base Breakdown</h2>
        <label>Choose a knowledge base</label>
        <select v-model="selectedKbId">
          <option disabled value="">Select...</option>
          <option v-for="kb in kbs" :key="kb.id" :value="kb.id">
            {{ kb.name }}
          </option>
        </select>
        <div v-if="kbProgress" class="list" style="margin-top: 12px">
          <div class="list-item">Documents: {{ kbProgress.total_docs }}</div>
          <div class="list-item">Quizzes: {{ kbProgress.total_quizzes }}</div>
          <div class="list-item">Attempts: {{ kbProgress.total_attempts }}</div>
          <div class="list-item">Questions asked: {{ kbProgress.total_questions }}</div>
          <div class="list-item">Summaries: {{ kbProgress.total_summaries }}</div>
          <div class="list-item">Keypoints: {{ kbProgress.total_keypoints }}</div>
          <div class="list-item">Average score: {{ kbProgress.avg_score }}</div>
          <div class="list-item">
            Last activity:
            {{ kbProgress.last_activity ? new Date(kbProgress.last_activity).toLocaleString() : 'N/A' }}
          </div>
        </div>
        <p v-else class="muted" style="margin-top: 12px">No KB stats yet.</p>
        <div v-if="progress && progress.by_kb && progress.by_kb.length" class="list" style="margin-top: 16px">
          <div v-for="kbStat in progress.by_kb" :key="kbStat.kb_id" class="list-item">
            <strong>{{ kbStat.kb_name || kbStat.kb_id }}</strong>
            <p class="muted">
              Docs: {{ kbStat.total_docs }} | Quizzes: {{ kbStat.total_quizzes }} | Attempts:
              {{ kbStat.total_attempts }} | Questions: {{ kbStat.total_questions }}
            </p>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>Recommendations</h2>
        <p class="muted">Personalized next steps for the selected knowledge base.</p>
        <button
          style="margin-top: 8px"
          class="secondary"
          :disabled="busy.recommendations"
          @click="fetchRecommendations"
        >
          {{ busy.recommendations ? 'Loading...' : 'Refresh' }}
        </button>
        <div v-if="recommendations.length" class="list" style="margin-top: 12px">
          <div v-for="item in recommendations" :key="item.doc_id" class="list-item">
            <strong>{{ item.doc_name || item.doc_id }}</strong>
            <p class="muted" v-if="item.doc_id">Doc ID: {{ item.doc_id }}</p>
            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px">
              <span v-for="action in item.actions" :key="action.type" class="badge">
                {{ actionLabel(action.type) }}
              </span>
            </div>
            <p v-for="action in item.actions" :key="`${item.doc_id}-${action.type}`" class="muted">
              {{ actionLabel(action.type) }}: {{ action.reason }}
            </p>
          </div>
        </div>
        <p v-else class="muted" style="margin-top: 12px">No recommendations yet.</p>
      </div>

      <div class="card">
        <h2>Recent Activity</h2>
        <div v-if="activity.length" class="list">
          <div v-for="(item, idx) in activity" :key="idx" class="list-item">
            <strong>{{ activityLabel(item) }}</strong>
            <p class="muted" v-if="item.doc_name">Doc: {{ item.doc_name }}</p>
            <p class="muted" v-if="item.detail">{{ item.detail }}</p>
            <p class="muted" v-if="item.score !== null && item.total !== null">
              Score: {{ Math.round(item.score * 100) }}% ({{ item.total }} questions)
            </p>
            <p class="muted">{{ new Date(item.timestamp).toLocaleString() }}</p>
          </div>
        </div>
        <p v-else class="muted">No activity yet.</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { apiGet, apiPost } from './api'

const tabs = ['Upload', 'Summary', 'Q&A', 'Quiz', 'Progress']
const activeTab = ref('Upload')

const storedUser = localStorage.getItem('gradtutor_user')
const userId = ref(storedUser || `user_${Math.random().toString(36).slice(2, 10)}`)
const userIdInput = ref(userId.value)
localStorage.setItem('gradtutor_user', userId.value)

const docs = ref([])
const kbs = ref([])
const selectedKbId = ref('')
const kbNameInput = ref('')
const selectedDocId = ref('')
const uploadFile = ref(null)
const summary = ref('')
const summaryCached = ref(false)
const keypoints = ref([])
const keypointsCached = ref(false)
const qaInput = ref('')
const qaMessages = ref([])
const quiz = ref(null)
const quizAnswers = ref({})
const quizResult = ref(null)
const quizCount = ref(5)
const quizDifficulty = ref('medium')
const progress = ref(null)
const activity = ref([])
const recommendations = ref([])
const statusMessage = ref('')

const kbProgress = computed(() => {
  if (!progress.value || !Array.isArray(progress.value.by_kb)) return null
  if (!selectedKbId.value) return null
  return progress.value.by_kb.find((item) => item.kb_id === selectedKbId.value) || null
})

const busy = ref({
  upload: false,
  summary: false,
  keypoints: false,
  qa: false,
  quiz: false,
  submit: false,
  kb: false,
  recommendations: false
})

function onFileChange(event) {
  uploadFile.value = event.target.files[0]
}

function applyUserId() {
  const next = userIdInput.value.trim()
  if (!next) return
  userId.value = next
  localStorage.setItem('gradtutor_user', next)
  refreshKbs()
  refreshDocs()
  fetchProgress()
}

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(userId.value)}`)
    if (!kbs.value.find((kb) => kb.id === selectedKbId.value)) {
      selectedKbId.value = kbs.value.length ? kbs.value[0].id : ''
    }
  } catch (err) {
    statusMessage.value = err.message
  }
}

async function refreshDocs() {
  try {
    const kbParam = selectedKbId.value ? `&kb_id=${encodeURIComponent(selectedKbId.value)}` : ''
    docs.value = await apiGet(`/api/docs?user_id=${encodeURIComponent(userId.value)}${kbParam}`)
    if (!docs.value.find((doc) => doc.id === selectedDocId.value)) {
      selectedDocId.value = docs.value.length ? docs.value[0].id : ''
    }
  } catch (err) {
    statusMessage.value = err.message
  }
}

async function uploadDoc() {
  if (!uploadFile.value) return
  busy.value.upload = true
  statusMessage.value = ''
  try {
    const form = new FormData()
    form.append('file', uploadFile.value)
    form.append('user_id', userId.value)
    if (selectedKbId.value) {
      form.append('kb_id', selectedKbId.value)
    }
    await apiPost('/api/docs/upload', form, true)
    statusMessage.value = 'Upload complete.'
    uploadFile.value = null
    await refreshDocs()
    await fetchProgress()
  } catch (err) {
    statusMessage.value = err.message
  } finally {
    busy.value.upload = false
  }
}

async function generateSummary(force = false) {
  if (typeof force !== 'boolean') force = false
  if (!selectedDocId.value) return
  busy.value.summary = true
  summary.value = ''
  summaryCached.value = false
  try {
    const res = await apiPost('/api/summary', {
      doc_id: selectedDocId.value,
      user_id: userId.value,
      force
    })
    summary.value = res.summary
    summaryCached.value = !!res.cached
    await fetchProgress()
  } catch (err) {
    summary.value = err.message
  } finally {
    busy.value.summary = false
  }
}

async function generateKeypoints(force = false) {
  if (typeof force !== 'boolean') force = false
  if (!selectedDocId.value) return
  busy.value.keypoints = true
  keypoints.value = []
  keypointsCached.value = false
  try {
    const res = await apiPost('/api/keypoints', {
      doc_id: selectedDocId.value,
      user_id: userId.value,
      force
    })
    keypoints.value = res.keypoints || []
    keypointsCached.value = !!res.cached
    await fetchProgress()
  } catch (err) {
    statusMessage.value = err.message
  } finally {
    busy.value.keypoints = false
  }
}

async function askQuestion() {
  if (!selectedDocId.value || !qaInput.value) return
  busy.value.qa = true
  const question = qaInput.value
  qaInput.value = ''
  qaMessages.value.push({ role: 'question', content: question })
  try {
    const res = await apiPost('/api/qa', {
      doc_id: selectedDocId.value,
      question,
      user_id: userId.value
    })
    qaMessages.value.push({ role: 'answer', content: res.answer, sources: res.sources })
    await fetchProgress()
  } catch (err) {
    qaMessages.value.push({ role: 'answer', content: err.message })
  } finally {
    busy.value.qa = false
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
      user_id: userId.value
    })
    quiz.value = res
    await fetchProgress()
  } catch (err) {
    statusMessage.value = err.message
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
      user_id: userId.value
    })
    quizResult.value = res
    await fetchProgress()
  } catch (err) {
    statusMessage.value = err.message
  } finally {
    busy.value.submit = false
  }
}

async function fetchProgress() {
  try {
    progress.value = await apiGet(`/api/progress?user_id=${encodeURIComponent(userId.value)}`)
    await fetchActivity()
    await fetchRecommendations()
  } catch (err) {
    statusMessage.value = err.message
  }
}

async function fetchActivity() {
  try {
    const res = await apiGet(`/api/activity?user_id=${encodeURIComponent(userId.value)}`)
    activity.value = res.items || []
  } catch (err) {
    statusMessage.value = err.message
  }
}

async function fetchRecommendations() {
  if (!selectedKbId.value) {
    recommendations.value = []
    return
  }
  busy.value.recommendations = true
  try {
    const res = await apiGet(
      `/api/recommendations?user_id=${encodeURIComponent(userId.value)}&kb_id=${encodeURIComponent(
        selectedKbId.value
      )}&limit=6`
    )
    recommendations.value = res.items || []
  } catch (err) {
    statusMessage.value = err.message
  } finally {
    busy.value.recommendations = false
  }
}

function activityLabel(item) {
  switch (item.type) {
    case 'document_upload':
      return 'Uploaded document'
    case 'summary_generated':
      return 'Summary generated'
    case 'keypoints_generated':
      return 'Keypoints generated'
    case 'question_asked':
      return 'Question asked'
    case 'quiz_attempt':
      return 'Quiz attempt'
    default:
      return item.type
  }
}

function actionLabel(type) {
  switch (type) {
    case 'summary':
      return 'Summary'
    case 'keypoints':
      return 'Keypoints'
    case 'quiz':
      return 'Quiz'
    case 'qa':
      return 'Q&A'
    default:
      return type
  }
}

async function createKb() {
  if (!kbNameInput.value) return
  busy.value.kb = true
  statusMessage.value = ''
  try {
    const res = await apiPost('/api/kb', {
      name: kbNameInput.value,
      user_id: userId.value
    })
    kbNameInput.value = ''
    await refreshKbs()
    if (res?.id) {
      selectedKbId.value = res.id
    }
    await refreshDocs()
  } catch (err) {
    statusMessage.value = err.message
  } finally {
    busy.value.kb = false
  }
}

function kbNameById(kbId) {
  const kb = kbs.value.find((item) => item.id === kbId)
  return kb ? kb.name : 'Unknown KB'
}

onMounted(async () => {
  await refreshKbs()
  await refreshDocs()
  await fetchProgress()
})

watch(selectedKbId, async () => {
  await refreshDocs()
  await fetchRecommendations()
})
</script>
