<template>
  <div class="space-y-8 max-w-6xl mx-auto">
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <!-- Upload Card -->
      <section class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-6">
        <div class="flex items-center gap-3">
          <Upload class="w-6 h-6 text-primary" />
          <h2 class="text-xl font-bold">Upload Document</h2>
        </div>

        <div class="space-y-4">
          <div class="space-y-2">
            <label class="text-sm font-medium text-muted-foreground uppercase tracking-wider">Knowledge Base</label>
            <div class="flex gap-2 flex-wrap">
              <select v-model="selectedKbId" class="flex-1 bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary">
                <option disabled value="">Select...</option>
                <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
              </select>
              <input
                type="text"
                v-model="kbNameInput"
                placeholder="New KB name"
                class="flex-1 min-w-[160px] bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                class="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg font-medium hover:bg-secondary/80 transition-colors disabled:opacity-50"
                :disabled="!kbNameInput || busy.kb"
                @click="createKb"
              >
                {{ busy.kb ? '...' : 'Create' }}
              </button>
            </div>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium text-muted-foreground uppercase tracking-wider">Select File</label>
            <div
              class="border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-primary/50 transition-colors cursor-pointer"
              @click="$refs.fileInput.click()"
              @dragover.prevent="dragActive = true"
              @dragleave.prevent="dragActive = false"
              @drop.prevent="onDrop"
              :class="{ 'border-primary bg-primary/5': dragActive }"
            >
              <input type="file" ref="fileInput" class="hidden" @change="onFileChange" />
              <div v-if="!uploadFile" class="space-y-2">
                <Upload class="w-10 h-10 mx-auto text-muted-foreground" />
                <p class="text-sm text-muted-foreground">Click or drag PDF/text file here</p>
              </div>
              <div v-else class="flex items-center justify-center gap-2 text-primary font-medium">
                <FileText class="w-5 h-5" />
                <span>{{ uploadFile.name }}</span>
                <button @click.stop="uploadFile = null" class="text-muted-foreground hover:text-destructive">
                  <X class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <div class="flex gap-4 pt-2">
            <button
              class="flex-1 bg-primary text-primary-foreground rounded-lg py-2.5 font-bold hover:opacity-90 transition-opacity disabled:opacity-50"
              :disabled="!uploadFile || busy.upload"
              @click="uploadDoc"
            >
              {{ busy.upload ? 'Uploading...' : 'Upload to Knowledge Base' }}
            </button>
            <button
              class="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg font-medium hover:bg-secondary/80 transition-colors"
              @click="refreshDocs"
            >
              <RefreshCw class="w-5 h-5" :class="{ 'animate-spin': busy.refresh }" />
            </button>
          </div>
          <p v-if="statusMessage" class="text-sm text-center" :class="statusMessage.includes('Error') ? 'text-destructive' : 'text-green-500'">
            {{ statusMessage }}
          </p>
        </div>
      </section>

      <!-- Documents List -->
      <section class="bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col h-[600px]">
        <div class="flex items-center justify-between mb-6">
          <div class="flex items-center gap-3">
            <FileText class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">Your Documents</h2>
          </div>
          <span class="text-xs font-bold bg-secondary px-2 py-1 rounded text-secondary-foreground">
            {{ docs.length }} Total
          </span>
        </div>

        <div class="flex-1 overflow-y-auto space-y-4 pr-2">
          <div v-if="docs.length === 0" class="h-full flex flex-col items-center justify-center text-muted-foreground space-y-2">
            <Database class="w-12 h-12 opacity-20" />
            <p>No documents found</p>
          </div>
          <div v-for="doc in docs" :key="doc.id" class="p-4 bg-background border border-border rounded-lg hover:border-primary/30 transition-colors group">
            <div class="flex justify-between items-start mb-2">
              <strong class="text-sm font-semibold truncate max-w-[200px]">{{ doc.filename }}</strong>
              <span class="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded" :class="statusClass(doc.status)">
                {{ doc.status }}
              </span>
            </div>
            <div class="flex flex-wrap gap-2 mb-3">
              <span class="text-[10px] bg-accent px-2 py-0.5 rounded-full">{{ kbNameById(doc.kb_id) }}</span>
              <span class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.num_pages }} pages</span>
              <span class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.num_chunks }} chunks</span>
            </div>
            <div class="flex items-center justify-between text-[10px] text-muted-foreground">
              <span>{{ new Date(doc.created_at).toLocaleDateString() }}</span>
              <span v-if="doc.error_message" class="text-destructive truncate max-w-[150px]">{{ doc.error_message }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Upload, FileText, Database, X, RefreshCw } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'

const userId = ref(localStorage.getItem('gradtutor_user') || '')
const docs = ref([])
const kbs = ref([])
const selectedKbId = ref('')
const kbNameInput = ref('')
const uploadFile = ref(null)
const dragActive = ref(false)
const statusMessage = ref('')
const busy = ref({
  upload: false,
  kb: false,
  refresh: false
})

function onFileChange(event) {
  uploadFile.value = event.target.files[0]
}

function onDrop(event) {
  dragActive.value = false
  uploadFile.value = event.dataTransfer.files[0]
}

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(userId.value)}`)
    if (!kbs.value.find((kb) => kb.id === selectedKbId.value)) {
      selectedKbId.value = kbs.value.length ? kbs.value[0].id : ''
    }
  } catch (err) {
    statusMessage.value = 'Error loading KBs: ' + err.message
  }
}

async function refreshDocs() {
  busy.value.refresh = true
  try {
    const kbParam = selectedKbId.value ? `&kb_id=${encodeURIComponent(selectedKbId.value)}` : ''
    docs.value = await apiGet(`/api/docs?user_id=${encodeURIComponent(userId.value)}${kbParam}`)
  } catch (err) {
    statusMessage.value = 'Error loading docs: ' + err.message
  } finally {
    busy.value.refresh = false
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
  } catch (err) {
    statusMessage.value = 'Error: ' + err.message
  } finally {
    busy.value.upload = false
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
    statusMessage.value = 'Error: ' + err.message
  } finally {
    busy.value.kb = false
  }
}

function kbNameById(kbId) {
  const kb = kbs.value.find((item) => item.id === kbId)
  return kb ? kb.name : 'Unknown KB'
}

function statusClass(status) {
  switch (status) {
    case 'ready': return 'bg-green-500/20 text-green-500'
    case 'processing': return 'bg-blue-500/20 text-blue-500 animate-pulse'
    case 'error': return 'bg-destructive/20 text-destructive'
    default: return 'bg-muted/20 text-muted-foreground'
  }
}

onMounted(async () => {
  if (userId.value) {
    await refreshKbs()
    await refreshDocs()
  }
})

watch(selectedKbId, async () => {
  await refreshDocs()
})
</script>
