<template>
  <div class="h-full flex flex-col max-w-6xl mx-auto">
    <div class="flex-1 flex gap-8 overflow-hidden min-h-0">
      <!-- Left: Chat Interface -->
      <section class="flex-1 flex flex-col bg-card border border-border rounded-xl shadow-sm overflow-hidden">
        <!-- Header -->
        <div class="p-4 border-b border-border flex items-center justify-between bg-card/50">
          <div class="flex items-center gap-3">
            <MessageSquare class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">AI Tutor Chat</h2>
          </div>
          <button @click="qaMessages = []" class="p-2 hover:bg-accent rounded-lg transition-colors text-muted-foreground" title="Clear chat">
            <Trash2 class="w-5 h-5" />
          </button>
        </div>

        <!-- Messages -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6" ref="scrollContainer">
          <div v-if="qaMessages.length === 0" class="h-full flex flex-col items-center justify-center text-muted-foreground space-y-4 text-center max-w-sm mx-auto">
            <div class="w-16 h-16 bg-primary/10 text-primary rounded-full flex items-center justify-center">
              <Sparkles class="w-8 h-8" />
            </div>
            <p>Select a document on the right and ask anything about its content.</p>
          </div>
          
          <div v-for="(msg, index) in qaMessages" :key="index" class="flex flex-col" :class="msg.role === 'question' ? 'items-end' : 'items-start'">
            <div 
              class="max-w-[85%] p-4 rounded-2xl shadow-sm"
              :class="msg.role === 'question' ? 'bg-primary text-primary-foreground rounded-tr-none' : 'bg-accent text-accent-foreground rounded-tl-none'"
            >
              <div class="flex items-center gap-2 mb-1 opacity-70 text-[10px] font-bold uppercase tracking-wider">
                <component :is="msg.role === 'question' ? 'User' : 'Bot'" class="w-3 h-3" />
                {{ msg.role === 'question' ? 'You' : 'AI Tutor' }}
              </div>
              <p class="text-sm leading-relaxed whitespace-pre-wrap">{{ msg.content }}</p>
              
              <!-- Sources -->
              <div v-if="msg.sources && msg.sources.length" class="mt-4 pt-3 border-t border-accent-foreground/10 space-y-2">
                <p class="text-[10px] font-bold uppercase opacity-50">References:</p>
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
              <span class="text-xs font-medium opacity-70">Tutor is thinking...</span>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="p-4 border-t border-border bg-card/50">
          <div class="flex gap-2">
            <textarea
              v-model="qaInput"
              @keydown.enter.prevent="askQuestion"
              placeholder="Type your question here..."
              class="flex-1 bg-background border border-input rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-primary resize-none h-[52px]"
              :disabled="!selectedDocId || busy.qa"
            ></textarea>
            <button
              @click="askQuestion"
              class="bg-primary text-primary-foreground p-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center"
              :disabled="!selectedDocId || !qaInput.trim() || busy.qa"
            >
              <Send class="w-6 h-6" />
            </button>
          </div>
          <p v-if="!selectedDocId" class="text-[10px] text-destructive mt-2 text-center font-bold uppercase tracking-widest">
            Please select a document first
          </p>
        </div>
      </section>

      <!-- Right: Doc Selection -->
      <aside class="w-72 space-y-6 flex flex-col">
        <div class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
          <div class="flex items-center gap-3">
            <Database class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">Context</h2>
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Target Document</label>
            <select v-model="selectedDocId" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
              <option disabled value="">Select...</option>
              <option v-for="doc in docs" :key="doc.id" :value="doc.id">{{ doc.filename }}</option>
            </select>
          </div>
        </div>

        <div class="flex-1 bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col min-h-0">
          <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-4">Quick Stats</h3>
          <div v-if="selectedDoc" class="space-y-4 overflow-y-auto pr-2">
            <div class="p-3 bg-accent/30 rounded-lg border border-border">
              <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">Knowledge Base</p>
              <p class="text-sm font-semibold truncate">{{ kbNameById(selectedDoc.kb_id) }}</p>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">Pages</p>
                <p class="text-lg font-bold">{{ selectedDoc.num_pages }}</p>
              </div>
              <div class="p-3 bg-accent/30 rounded-lg border border-border text-center">
                <p class="text-[10px] uppercase font-bold text-muted-foreground mb-1">Chunks</p>
                <p class="text-lg font-bold">{{ selectedDoc.num_chunks }}</p>
              </div>
            </div>
          </div>
          <div v-else class="flex-1 flex flex-col items-center justify-center text-muted-foreground text-xs text-center opacity-50">
            <FileText class="w-12 h-12 mb-2" />
            <p>Select a document to see details</p>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { MessageSquare, Send, Trash2, Database, FileText, Sparkles, User, Bot } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'

const userId = ref(localStorage.getItem('gradtutor_user') || '')
const docs = ref([])
const kbs = ref([])
const selectedDocId = ref('')
const qaInput = ref('')
const qaMessages = ref([])
const busy = ref({
  qa: false
})
const scrollContainer = ref(null)

const selectedDoc = computed(() => {
  return docs.value.find(d => d.id === selectedDocId.value) || null
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

async function askQuestion() {
  if (!selectedDocId.value || !qaInput.value.trim() || busy.value.qa) return
  
  const question = qaInput.value.trim()
  qaInput.value = ''
  qaMessages.value.push({ role: 'question', content: question })
  
  busy.value.qa = true
  scrollToBottom()
  
  try {
    const res = await apiPost('/api/qa', {
      doc_id: selectedDocId.value,
      question,
      user_id: userId.value
    })
    qaMessages.value.push({ role: 'answer', content: res.answer, sources: res.sources })
  } catch (err) {
    qaMessages.value.push({ role: 'answer', content: 'Error: ' + err.message })
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

function kbNameById(kbId) {
  const kb = kbs.value.find((item) => item.id === kbId)
  return kb ? kb.name : 'Unknown KB'
}

onMounted(async () => {
  if (userId.value) {
    await refreshKbs()
    await refreshDocs()
  }
})

watch(qaMessages, () => scrollToBottom(), { deep: true })
</script>
