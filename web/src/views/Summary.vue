<template>
  <div class="space-y-8 max-w-6xl mx-auto">
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Sidebar: Doc Selection -->
      <aside class="space-y-6">
        <div class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
          <div class="flex items-center gap-3">
            <FileText class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">Select Document</h2>
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Choose a document</label>
            <select v-model="selectedDocId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary">
              <option disabled value="">Select...</option>
              <option v-for="doc in docs" :key="doc.id" :value="doc.id">{{ doc.filename }}</option>
            </select>
          </div>
          <div class="flex flex-col gap-2 pt-2">
            <button
              class="w-full bg-primary text-primary-foreground rounded-lg py-2 font-bold hover:opacity-90 transition-opacity disabled:opacity-50"
              :disabled="!selectedDocId || busy.summary"
              @click="generateSummary()"
            >
              {{ busy.summary ? 'Summarizing...' : 'Generate Summary' }}
            </button>
            <button
              class="w-full bg-secondary text-secondary-foreground rounded-lg py-2 font-bold hover:bg-secondary/80 transition-colors disabled:opacity-50"
              :disabled="!selectedDocId || busy.keypoints"
              @click="generateKeypoints()"
            >
              {{ busy.keypoints ? 'Extracting...' : 'Extract Keypoints' }}
            </button>
          </div>
        </div>

        <div v-if="selectedDocId" class="bg-card border border-border rounded-xl p-4 text-xs space-y-2">
          <div class="flex justify-between">
            <span class="text-muted-foreground">Document ID:</span>
            <span class="font-mono">{{ selectedDocId.slice(0, 8) }}...</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted-foreground">KB:</span>
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
              <h2 class="text-2xl font-bold">Executive Summary</h2>
            </div>
            <span v-if="summaryCached" class="text-[10px] font-bold bg-green-500/10 text-green-500 px-2 py-1 rounded-full uppercase tracking-tighter">
              Cached
            </span>
          </div>

          <div v-if="busy.summary" class="flex flex-col items-center justify-center py-20 space-y-4">
            <div class="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p class="text-muted-foreground animate-pulse">Analyzing document content...</p>
          </div>
          <div v-else-if="summary" class="prose prose-invert max-w-none">
            <p class="text-lg leading-relaxed whitespace-pre-wrap">{{ summary }}</p>
          </div>
          <div v-else class="flex flex-col items-center justify-center py-20 text-muted-foreground space-y-4">
            <FileText class="w-16 h-16 opacity-10" />
            <p>Select a document and click "Generate Summary" to begin.</p>
          </div>
        </section>

        <!-- Keypoints Card -->
        <section class="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Layers class="w-6 h-6 text-primary" />
              <h2 class="text-2xl font-bold">Key Knowledge Points</h2>
            </div>
            <span v-if="keypointsCached" class="text-[10px] font-bold bg-green-500/10 text-green-500 px-2 py-1 rounded-full uppercase tracking-tighter">
              Cached
            </span>
          </div>

          <div v-if="busy.keypoints" class="flex flex-col items-center justify-center py-12 space-y-4">
            <div class="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p class="text-muted-foreground animate-pulse">Extracting key concepts...</p>
          </div>
          <div v-else-if="keypoints.length" class="grid grid-cols-1 gap-4">
            <div v-for="(point, idx) in keypoints" :key="idx" class="p-4 bg-background border border-border rounded-xl hover:border-primary/30 transition-all group">
              <div class="flex gap-4">
                <div class="flex-shrink-0 w-6 h-6 bg-primary/10 text-primary rounded-full flex items-center justify-center text-xs font-bold">
                  {{ idx + 1 }}
                </div>
                <div class="space-y-2 flex-1">
                  <p class="font-medium leading-snug">{{ typeof point === 'string' ? point : point.text }}</p>
                  <p v-if="typeof point !== 'string' && point.explanation" class="text-sm text-muted-foreground">
                    {{ point.explanation }}
                  </p>
                  <div v-if="typeof point !== 'string' && (point.source || point.page || point.chunk)" class="flex items-center gap-2 pt-1">
                    <span class="text-[10px] font-bold uppercase text-primary/60">Source:</span>
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
            <p>No keypoints extracted yet.</p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { FileText, Sparkles, Layers, RefreshCw } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'

const userId = ref(localStorage.getItem('gradtutor_user') || '')
const docs = ref([])
const kbs = ref([])
const selectedDocId = ref('')
const summary = ref('')
const summaryCached = ref(false)
const keypoints = ref([])
const keypointsCached = ref(false)
const busy = ref({
  summary: false,
  keypoints: false
})

const selectedKbName = computed(() => {
  const doc = docs.value.find(d => d.id === selectedDocId.value)
  if (!doc) return 'N/A'
  const kb = kbs.value.find(k => k.id === doc.kb_id)
  return kb ? kb.name : 'Unknown'
})

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(userId.value)}`)
  } catch (err) {
    console.error(err)
  }
}

async function refreshDocs() {
  try {
    docs.value = await apiGet(`/api/docs?user_id=${encodeURIComponent(userId.value)}`)
  } catch (err) {
    console.error(err)
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
      user_id: userId.value,
      force
    })
    summary.value = res.summary
    summaryCached.value = !!res.cached
  } catch (err) {
    summary.value = 'Error: ' + err.message
  } finally {
    busy.value.summary = false
  }
}

async function generateKeypoints(force = false) {
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
  } catch (err) {
    console.error(err)
  } finally {
    busy.value.keypoints = false
  }
}

onMounted(async () => {
  if (userId.value) {
    await refreshKbs()
    await refreshDocs()
  }
})
</script>
