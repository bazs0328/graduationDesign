<template>
  <div class="space-y-8 max-w-6xl mx-auto">
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <!-- Upload Card -->
      <section class="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-primary/5 space-y-6">
        <div class="flex items-center gap-3">
          <UploadIcon class="w-6 h-6 text-primary" />
          <h2 class="text-xl font-bold">上传文档</h2>
        </div>

        <div class="space-y-4">
          <div class="space-y-2">
            <label class="text-sm font-medium text-muted-foreground uppercase tracking-wider">知识库</label>
            <div v-if="busy.init">
              <SkeletonBlock type="list" :lines="2" />
            </div>
            <div v-else class="flex gap-2 flex-wrap">
              <KbSelector
                class="flex-1"
                :model-value="selectedKbId"
                :kbs="kbs"
                label=""
                placeholder="请选择"
                :loading="appContext.kbsLoading"
                @update:model-value="selectedKbId = $event"
              />
              <input
                type="text"
                v-model="kbNameInput"
                ref="kbNameInputRef"
                placeholder="新知识库名称"
                class="flex-1 min-w-[160px] bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary"
              />
              <Button
                variant="secondary"
                :disabled="!kbNameInput"
                :loading="busy.kb"
                @click="createKb"
              >
                创建
              </Button>
            </div>
            <div v-if="!busy.init && selectedKbId" class="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-2">
              <input
                type="text"
                v-model="kbRenameInput"
                placeholder="当前知识库新名称"
                class="bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary"
              />
              <Button
                variant="outline"
                :disabled="!kbRenameInput || (selectedKb && kbRenameInput.trim() === selectedKb.name)"
                :loading="busy.kbManage"
                @click="renameCurrentKb"
              >
                重命名当前库
              </Button>
              <Button
                variant="destructive"
                :loading="busy.kbDelete"
                @click="deleteCurrentKb"
              >
                删除当前库
              </Button>
            </div>
            <p v-if="selectedKbId" class="text-xs text-muted-foreground">
              删除非空知识库时会二次确认是否级联删除其下文档。
            </p>
            <p class="text-xs text-muted-foreground">
              系统级文档识别能力与解析策略由管理员维护；问答与测验常用偏好可在
              <router-link to="/settings" class="font-semibold text-primary hover:underline">设置中心</router-link>
              调整。
            </p>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium text-muted-foreground uppercase tracking-wider">选择文件</label>
            <div
              class="border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-primary/50 transition-colors cursor-pointer"
              @click="triggerFilePicker"
              @dragover.prevent="dragActive = true"
              @dragleave.prevent="dragActive = false"
              @drop.prevent="onDrop"
              :class="{ 'border-primary bg-primary/5': dragActive }"
            >
              <input type="file" ref="fileInputRef" class="hidden" accept=".pdf,.txt,.md,.docx,.pptx" @change="onFileChange" />
              <div v-if="!uploadFile" class="space-y-2">
                <UploadIcon class="w-10 h-10 mx-auto text-muted-foreground" />
                <p class="text-sm text-muted-foreground">点击或拖拽 PDF/TXT/MD/DOCX/PPTX 文件到此处</p>
              </div>
              <div v-else class="flex items-center justify-center gap-2 text-primary font-medium">
                <FileText class="w-5 h-5" />
                <span>{{ uploadFile.name }}</span>
                <button @click.stop="clearSelectedUploadFile()" class="text-muted-foreground hover:text-destructive">
                  <X class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <div class="flex gap-4 pt-2">
            <Button
              class="flex-1 shadow-lg shadow-primary/25"
              size="lg"
              :disabled="!uploadFile"
              :loading="busy.upload"
              @click="uploadDoc"
            >
              <template #icon>
                <UploadIcon class="w-5 h-5" />
              </template>
              {{ busy.upload ? '上传中…' : '上传到知识库' }}
            </Button>
            <Button
              variant="secondary"
              class="border border-border"
              :loading="busy.refresh"
              @click="refreshDocs"
            >
              <template #icon>
                <RefreshCw class="w-5 h-5" />
              </template>
              <span>刷新列表</span>
            </Button>
          </div>

          <div
            v-if="uploadProgressVisible"
            class="rounded-xl border border-border bg-background/70 px-4 py-3 space-y-2"
          >
            <div class="flex items-center justify-between gap-3 text-sm">
              <div class="min-w-0">
                <p class="font-semibold truncate">{{ uploadProgressTitle }}</p>
                <p v-if="uploadProgress.filename" class="text-xs text-muted-foreground truncate">
                  {{ uploadProgress.filename }}
                </p>
              </div>
              <span
                class="text-xs font-bold px-2 py-1 rounded-full"
                :class="uploadProgress.phase === 'uploading' ? 'bg-primary/10 text-primary' : 'bg-blue-500/10 text-blue-600 animate-pulse'"
              >
                {{ uploadProgress.phase === 'uploading' ? `${uploadProgress.percent}%` : '解析中' }}
              </span>
            </div>
            <div class="h-2 rounded-full bg-accent overflow-hidden">
              <div
                class="h-full rounded-full transition-all duration-300"
                :class="uploadProgress.phase === 'uploading' ? 'bg-primary' : 'bg-blue-500 animate-pulse'"
                :style="{ width: uploadProgressWidth }"
              ></div>
            </div>
            <p class="text-xs text-muted-foreground">
              {{ uploadProgressDetail }}
            </p>
          </div>
        </div>
      </section>

      <!-- Documents List -->
      <section class="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-primary/5 flex flex-col h-[600px]">
        <div class="flex items-center justify-between mb-6">
          <div class="flex items-center gap-3">
            <FileText class="w-6 h-6 text-primary" />
            <h2 class="text-xl font-bold">我的文档</h2>
          </div>
          <span class="text-xs font-bold bg-secondary px-2 py-1 rounded text-secondary-foreground">
            {{ busy.init ? '加载中…' : `共 ${docsTotal} 个` }}
          </span>
        </div>

        <div class="mb-4 grid grid-cols-1 md:grid-cols-2 gap-2">
          <input
            v-model="docFilters.keyword"
            type="text"
            placeholder="按文件名搜索"
            class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
          />
          <div class="grid grid-cols-2 gap-2">
            <select v-model="docFilters.fileType" class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary">
              <option value="">全部类型</option>
              <option value="pdf">PDF</option>
              <option value="txt">TXT</option>
              <option value="md">MD</option>
              <option value="docx">DOCX</option>
              <option value="pptx">PPTX</option>
            </select>
            <select v-model="docFilters.status" class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary">
              <option value="">全部状态</option>
              <option value="ready">就绪</option>
              <option value="processing">处理中</option>
              <option value="error">错误</option>
            </select>
          </div>
          <select v-model="docFilters.sortBy" class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary">
            <option value="created_at">按上传时间</option>
            <option value="filename">按文件名</option>
            <option value="file_type">按类型</option>
            <option value="status">按状态</option>
            <option value="num_pages">按页数</option>
            <option value="num_chunks">按切块数</option>
          </select>
          <button
            class="text-sm border border-border rounded-lg px-3 py-2 hover:bg-accent transition-colors"
            @click="toggleSortOrder"
          >
            {{ docFilters.sortOrder === 'desc' ? '降序 ↓' : '升序 ↑' }}
          </button>
        </div>

        <div class="flex-1 overflow-y-auto space-y-4 pr-2">
          <div v-if="busy.init" class="space-y-4">
            <SkeletonBlock type="list" :lines="5" />
          </div>
          <EmptyState
            v-else-if="docs.length === 0"
            :icon="Database"
            title="还没有文档，先开始上传"
            :description="uploadDocsEmptyDescription"
            :hint="uploadDocsEmptyHint"
            size="md"
            :primary-action="uploadDocsEmptyPrimaryAction"
            :secondary-action="uploadDocsEmptySecondaryAction"
            @primary="handleUploadDocsEmptyPrimary"
            @secondary="handleUploadDocsEmptySecondary"
          />
          <div v-for="doc in docs" :key="doc.id" class="p-4 bg-background border border-border rounded-lg hover:border-primary/30 transition-colors group">
            <div class="flex justify-between items-start mb-2">
              <strong class="text-sm font-semibold truncate max-w-[200px]">{{ doc.filename }}</strong>
              <div class="flex items-center gap-2">
                <span class="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded" :class="statusClass(doc.status)">
                  {{ statusLabel(doc.status) }}
                </span>
                <RefreshCw
                  v-if="doc.status === 'processing' && pollingIntervals.has(doc.id)"
                  class="w-3 h-3 text-blue-500 animate-spin"
                />
              </div>
            </div>
            <div class="flex flex-wrap gap-2 mb-3">
              <span class="text-[10px] bg-accent px-2 py-0.5 rounded-full">{{ kbNameById(doc.kb_id) }}</span>
              <template v-if="doc.status === 'processing'">
                <span class="text-[10px] bg-blue-500/20 text-blue-500 px-2 py-0.5 rounded-full animate-pulse">
                  正在处理中...
                </span>
              </template>
              <template v-else>
                <span v-if="doc.num_pages > 0" class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.num_pages }} 页</span>
                <span v-if="doc.num_chunks > 0" class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.num_chunks }} 块</span>
              </template>
            </div>
            <div class="flex items-center justify-between text-[10px] text-muted-foreground">
              <span>{{ new Date(doc.created_at).toLocaleDateString() }}</span>
              <span v-if="doc.error_message" class="text-destructive truncate max-w-[150px]">{{ doc.error_message }}</span>
              <span v-else-if="doc.status === 'processing'" class="text-blue-500">
                自动更新中...
              </span>
            </div>
            <div class="mt-3 pt-3 border-t border-border/70 flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                :disabled="isDocBusy(doc.id) || doc.status === 'processing'"
                @click="renameDoc(doc)"
              >
                重命名
              </Button>
              <Button
                size="sm"
                variant="ghost"
                :disabled="isDocBusy(doc.id) || doc.status === 'processing'"
                @click="moveDoc(doc)"
              >
                移动
              </Button>
              <Button
                size="sm"
                variant="outline"
                :disabled="isDocBusy(doc.id) || doc.status === 'processing'"
                @click="reprocessDoc(doc)"
              >
                重新解析
              </Button>
              <Button
                size="sm"
                variant="destructive"
                :disabled="isDocBusy(doc.id)"
                @click="deleteDocItem(doc)"
              >
                删除
              </Button>
              <span v-if="isDocBusy(doc.id)" class="text-[10px] text-muted-foreground ml-auto">
                处理中...
              </span>
            </div>
          </div>
        </div>
        <div
          v-if="!busy.init && docsTotal > 0"
          class="mt-4 pt-4 border-t border-border/70 flex items-center justify-between gap-3 text-xs"
        >
          <span class="text-muted-foreground">
            显示 {{ docsPageStart }}-{{ docsPageEnd }} / {{ docsTotal }}
          </span>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 rounded border border-border hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="busy.refresh || docsOffset <= 0"
              @click="goToPrevDocsPage"
            >
              上一页
            </button>
            <span class="text-muted-foreground">
              第 {{ docsPageNumber }} / {{ docsTotalPages }} 页
            </span>
            <button
              class="px-3 py-1.5 rounded border border-border hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="busy.refresh || !docsHasMore"
              @click="goToNextDocsPage"
            >
              下一页
            </button>
          </div>
        </div>
      </section>
    </div>

    <section class="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-primary/5 space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <RefreshCw class="w-5 h-5 text-primary" />
          <h3 class="text-lg font-bold">解析任务中心</h3>
        </div>
        <div class="flex items-center gap-2 text-xs text-muted-foreground">
          <span>处理中 {{ taskCenter.processing_count }}</span>
          <span>失败 {{ taskCenter.error_count }}</span>
        </div>
      </div>

      <div v-if="taskCenter.processing_count === 0 && taskCenter.error_count === 0" class="text-sm text-muted-foreground">
        当前没有解析中的任务或失败任务。
      </div>

      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="space-y-2">
          <div class="text-sm font-semibold">处理中</div>
          <div v-if="taskCenter.processing.length === 0" class="text-xs text-muted-foreground">暂无</div>
          <div
            v-for="task in taskCenter.processing"
            :key="`proc-${task.id}`"
            class="text-xs p-3 bg-background border border-border rounded-lg flex items-center justify-between gap-3"
          >
            <div class="min-w-0">
              <div class="truncate font-medium">{{ task.filename }}</div>
              <div class="text-muted-foreground">自动刷新中</div>
            </div>
            <RefreshCw class="w-3 h-3 text-blue-500 animate-spin shrink-0" />
          </div>
        </div>

        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <div class="text-sm font-semibold">失败</div>
            <Button
              size="sm"
              variant="outline"
              :disabled="taskCenter.error_count === 0"
              :loading="busy.retryFailed"
              @click="retryFailedTasks()"
            >
              一键重试
            </Button>
          </div>
          <div v-if="taskCenter.error.length === 0" class="text-xs text-muted-foreground">暂无</div>
          <div
            v-for="task in taskCenter.error"
            :key="`err-${task.id}`"
            class="text-xs p-3 bg-background border border-destructive/30 rounded-lg flex items-center justify-between gap-3"
          >
            <div class="min-w-0">
              <div class="truncate font-medium">{{ task.filename }}</div>
              <div class="text-destructive truncate">{{ task.error_message || '解析失败' }}</div>
              <div class="text-muted-foreground">重试次数 {{ task.retry_count || 0 }}</div>
            </div>
            <Button size="sm" variant="ghost" :loading="isDocBusy(task.id)" @click="retryFailedTasks([task.id])">
              重试
            </Button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { Upload, FileText, Database, X, RefreshCw } from 'lucide-vue-next'
import { apiDelete, apiGet, apiPatch, apiPost, apiUploadWithProgress } from '../api'
import { useToast } from '../composables/useToast'
import { useAppContextStore } from '../stores/appContext'
import Button from '../components/ui/Button.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import KbSelector from '../components/context/KbSelector.vue'

const { showToast } = useToast()
const appContext = useAppContextStore()
appContext.hydrate()

const UPLOAD_ALLOWED_EXTENSIONS = new Set(['.pdf', '.txt', '.md', '.docx', '.pptx'])
const UPLOAD_MAX_FILE_BYTES = 50 * 1024 * 1024

const resolvedUserId = computed(() => appContext.resolvedUserId || 'default')
const docs = ref([])
const docsTotal = ref(0)
const docsOffset = ref(0)
const docsLimit = ref(20)
const docsHasMore = ref(false)
const kbs = computed(() => appContext.kbs)
const selectedKbId = computed({
  get: () => appContext.selectedKbId,
  set: (value) => appContext.setSelectedKbId(value),
})
const kbNameInput = ref('')
const kbRenameInput = ref('')
const kbNameInputRef = ref(null)
const docFilters = ref({
  keyword: '',
  fileType: '',
  status: '',
  sortBy: 'created_at',
  sortOrder: 'desc'
})
const uploadFile = ref(null)
const fileInputRef = ref(null)
const dragActive = ref(false)
const uploadProgress = ref({
  phase: 'idle',
  percent: 0,
  loaded: 0,
  total: 0,
  filename: '',
  docId: null,
})
const docBusyMap = ref({})
const taskCenter = ref({
  processing: [],
  error: [],
  processing_count: 0,
  error_count: 0,
  auto_refresh_ms: 2000
})
const busy = ref({
  upload: false,
  kb: false,
  kbManage: false,
  kbDelete: false,
  retryFailed: false,
  refresh: false,
  init: false
})
const pollingIntervals = ref(new Map()) // 存储每个文档的轮询定时器
let taskCenterInterval = null
let docsFilterDebounce = null
let uploadProgressResetTimer = null
const selectedKb = computed(() => kbs.value.find((item) => item.id === selectedKbId.value) || null)
const hasAnyKb = computed(() => kbs.value.length > 0)
const isDocFilterActive = computed(() => {
  return Boolean(
    (docFilters.value.keyword && docFilters.value.keyword.trim())
    || docFilters.value.fileType
    || docFilters.value.status
  )
})
const uploadDocsEmptyDescription = computed(() => {
  if (!hasAnyKb.value) {
    return '先创建一个知识库，再上传 PDF/TXT/MD/DOCX/PPTX 文档进行解析。'
  }
  if (isDocFilterActive.value) {
    return '当前筛选条件下没有匹配文档，可以清空筛选后查看全部结果。'
  }
  return '选择文件后上传到当前知识库，系统会自动解析并建立索引。'
})
const uploadDocsEmptyHint = computed(() => {
  if (!hasAnyKb.value) {
    return '创建完成后即可在左侧选择文件并上传。'
  }
  if (isDocFilterActive.value) {
    return '清空筛选不会影响已上传文档。'
  }
  return '支持拖拽上传，处理中的文档会自动刷新状态。'
})
const uploadDocsEmptyPrimaryAction = computed(() => {
  if (!hasAnyKb.value) {
    return { label: '创建知识库' }
  }
  if (isDocFilterActive.value) {
    return { label: '清空筛选', variant: 'secondary' }
  }
  return { label: '选择文件上传' }
})
const uploadDocsEmptySecondaryAction = computed(() => {
  if (hasAnyKb.value && isDocFilterActive.value) {
    return { label: '选择文件上传', variant: 'outline' }
  }
  return null
})
const uploadProgressVisible = computed(() => uploadProgress.value.phase !== 'idle')
const uploadProgressTitle = computed(() => {
  if (uploadProgress.value.phase === 'uploading') return '正在上传文件'
  if (uploadProgress.value.phase === 'processing') return '上传完成，正在解析'
  return ''
})
const uploadProgressDetail = computed(() => {
  if (!uploadProgressVisible.value) return ''
  if (uploadProgress.value.phase === 'uploading') {
    const loaded = formatFileSize(uploadProgress.value.loaded)
    const total = uploadProgress.value.total > 0 ? formatFileSize(uploadProgress.value.total) : '未知大小'
    return `${loaded} / ${total}`
  }
  return '文档已提交到后端，正在建立索引，可在右侧任务中心查看状态。'
})
const uploadProgressWidth = computed(() => {
  if (uploadProgress.value.phase === 'processing') return '100%'
  return `${Math.max(0, Math.min(100, uploadProgress.value.percent || 0))}%`
})
const docsTotalPages = computed(() => {
  if (docsTotal.value <= 0) return 1
  return Math.max(1, Math.ceil(docsTotal.value / docsLimit.value))
})
const docsPageNumber = computed(() => Math.floor(docsOffset.value / docsLimit.value) + 1)
const docsPageStart = computed(() => {
  if (docsTotal.value <= 0 || docs.value.length === 0) return 0
  return docsOffset.value + 1
})
const docsPageEnd = computed(() => {
  if (docsTotal.value <= 0 || docs.value.length === 0) return 0
  return Math.min(docsOffset.value + docs.value.length, docsTotal.value)
})

function normalizeUploadFileSelection(file) {
  if (!file) return null
  const filename = (file.name || '').trim()
  const dotIndex = filename.lastIndexOf('.')
  const ext = dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : ''
  if (!UPLOAD_ALLOWED_EXTENSIONS.has(ext)) {
    showToast(`不支持的文件类型：${ext || '无扩展名'}`, 'error')
    return null
  }
  if (file.size > UPLOAD_MAX_FILE_BYTES) {
    showToast('文件过大，单个文件请控制在 50MB 以内', 'error')
    return null
  }
  return file
}

function clearSelectedUploadFile() {
  uploadFile.value = null
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function onFileChange(event) {
  const selected = normalizeUploadFileSelection(event.target.files?.[0] || null)
  if (!selected) {
    if (event.target) {
      event.target.value = ''
    }
    return
  }
  uploadFile.value = selected
}

function onDrop(event) {
  dragActive.value = false
  const selected = normalizeUploadFileSelection(event.dataTransfer.files?.[0] || null)
  if (!selected) return
  uploadFile.value = selected
}

function clearUploadProgress(delayMs = 0) {
  if (uploadProgressResetTimer) {
    clearTimeout(uploadProgressResetTimer)
    uploadProgressResetTimer = null
  }
  const reset = () => {
    uploadProgressResetTimer = null
    uploadProgress.value = {
      phase: 'idle',
      percent: 0,
      loaded: 0,
      total: 0,
      filename: '',
      docId: null,
    }
  }
  if (delayMs > 0) {
    uploadProgressResetTimer = setTimeout(reset, delayMs)
    return
  }
  reset()
}

function setUploadProgress(next) {
  uploadProgress.value = { ...uploadProgress.value, ...next }
}

function formatFileSize(bytes) {
  const value = Number(bytes) || 0
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function triggerFilePicker() {
  fileInputRef.value?.click()
}

function focusKbNameInput() {
  kbNameInputRef.value?.focus?.()
  kbNameInputRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
}

function resetDocFilters() {
  docFilters.value = {
    keyword: '',
    fileType: '',
    status: '',
    sortBy: 'created_at',
    sortOrder: 'desc',
  }
}

function handleUploadDocsEmptyPrimary() {
  if (!hasAnyKb.value) {
    if (kbNameInput.value && kbNameInput.value.trim()) {
      createKb()
      return
    }
    focusKbNameInput()
    return
  }
  if (isDocFilterActive.value) {
    resetDocFilters()
    return
  }
  triggerFilePicker()
}

function handleUploadDocsEmptySecondary() {
  if (hasAnyKb.value && isDocFilterActive.value) {
    triggerFilePicker()
  }
}

async function refreshKbs(force = false) {
  try {
    await appContext.loadKbs(force)
    const active = kbs.value.find((kb) => kb.id === selectedKbId.value)
    kbRenameInput.value = active ? active.name : ''
  } catch {
    // error toast handled globally
  }
}

function stopTaskCenterAutoRefresh() {
  if (taskCenterInterval) {
    clearInterval(taskCenterInterval)
    taskCenterInterval = null
  }
}

function scheduleTaskCenterAutoRefresh() {
  stopTaskCenterAutoRefresh()
  if (!taskCenter.value.processing_count) return
  const interval = Math.max(1000, taskCenter.value.auto_refresh_ms || 2000)
  taskCenterInterval = setInterval(async () => {
    await refreshTaskCenter()
    if (!taskCenter.value.processing_count) {
      await refreshDocs()
      stopTaskCenterAutoRefresh()
    }
  }, interval)
}

async function refreshTaskCenter() {
  try {
    const kbParam = selectedKbId.value ? `&kb_id=${encodeURIComponent(selectedKbId.value)}` : ''
    taskCenter.value = await apiGet(`/api/docs/tasks?user_id=${encodeURIComponent(resolvedUserId.value)}${kbParam}`)
    scheduleTaskCenterAutoRefresh()
  } catch {
    stopTaskCenterAutoRefresh()
  }
}

function buildDocsQueryParams(options = {}) {
  const {
    includePaging = false,
    offset = docsOffset.value,
    limit = docsLimit.value,
  } = options
  const params = new URLSearchParams()
  params.set('user_id', resolvedUserId.value)
  if (selectedKbId.value) params.set('kb_id', selectedKbId.value)
  if (docFilters.value.keyword && docFilters.value.keyword.trim()) {
    params.set('keyword', docFilters.value.keyword.trim())
  }
  if (docFilters.value.fileType) params.set('file_type', docFilters.value.fileType)
  if (docFilters.value.status) params.set('status', docFilters.value.status)
  if (docFilters.value.sortBy) params.set('sort_by', docFilters.value.sortBy)
  if (docFilters.value.sortOrder) params.set('sort_order', docFilters.value.sortOrder)
  if (includePaging) {
    params.set('offset', String(Math.max(0, Number(offset) || 0)))
    params.set('limit', String(Math.max(1, Math.min(100, Number(limit) || docsLimit.value || 20))))
  }
  return params
}

function toggleSortOrder() {
  docFilters.value.sortOrder = docFilters.value.sortOrder === 'desc' ? 'asc' : 'desc'
}

async function goToPrevDocsPage() {
  if (docsOffset.value <= 0 || busy.value.refresh) return
  const nextOffset = Math.max(0, docsOffset.value - docsLimit.value)
  await refreshDocs({ offset: nextOffset })
}

async function goToNextDocsPage() {
  if (!docsHasMore.value || busy.value.refresh) return
  const nextOffset = docsOffset.value + docsLimit.value
  await refreshDocs({ offset: nextOffset })
}

async function refreshDocs(options = {}) {
  const { resetPage = false, offset = null } = options
  if (resetPage) {
    docsOffset.value = 0
  } else if (Number.isFinite(Number(offset))) {
    docsOffset.value = Math.max(0, Number(offset))
  }
  busy.value.refresh = true
  try {
    while (true) {
      const query = buildDocsQueryParams({ includePaging: true }).toString()
      const result = await apiGet(`/api/docs/page?${query}`)
      const items = Array.isArray(result?.items) ? result.items : []
      const total = Math.max(0, Number(result?.total) || 0)
      docs.value = items
      docsTotal.value = total
      docsOffset.value = Math.max(0, Number(result?.offset) || 0)
      docsLimit.value = Math.max(1, Number(result?.limit) || docsLimit.value || 20)
      docsHasMore.value = Boolean(result?.has_more)

      if (total > 0 && items.length === 0 && docsOffset.value > 0) {
        const lastPageOffset = Math.max(0, (Math.ceil(total / docsLimit.value) - 1) * docsLimit.value)
        if (lastPageOffset !== docsOffset.value) {
          docsOffset.value = lastPageOffset
          continue
        }
      }
      break
    }
    await refreshTaskCenter()

    // 刷新后检查是否有处理中的文档需要轮询
    checkAndStartPolling()
  } catch {
    // error toast handled globally
  } finally {
    busy.value.refresh = false
  }
}

async function uploadDoc() {
  if (!uploadFile.value) return
  const file = uploadFile.value
  busy.value.upload = true
  clearUploadProgress()
  setUploadProgress({
    phase: 'uploading',
    percent: 0,
    loaded: 0,
    total: file.size || 0,
    filename: file.name || '',
    docId: null,
  })
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('user_id', resolvedUserId.value)
    if (selectedKbId.value) {
      form.append('kb_id', selectedKbId.value)
    }
    const uploadedDoc = await apiUploadWithProgress('/api/docs/upload', form, {
      onProgress({ percent, loaded, total }) {
        setUploadProgress({
          phase: 'uploading',
          percent,
          loaded,
          total: total || file.size || 0,
        })
      }
    })
    setUploadProgress({
      phase: 'processing',
      percent: 100,
      loaded: file.size || uploadProgress.value.loaded,
      total: file.size || uploadProgress.value.total,
      docId: uploadedDoc?.id || null,
    })
    showToast('文档上传成功，正在处理中...', 'success')
    clearSelectedUploadFile()
    await refreshDocs({ resetPage: true })

    // 如果文档状态是 processing，开始轮询
    if (uploadedDoc.status === 'processing') {
      startPolling(uploadedDoc.id)
    } else {
      clearUploadProgress(1200)
    }
  } catch {
    clearUploadProgress()
    // error toast handled globally
  } finally {
    busy.value.upload = false
  }
}

function startPolling(docId) {
  // 如果已经在轮询，先清除旧的定时器
  if (pollingIntervals.value.has(docId)) {
    clearInterval(pollingIntervals.value.get(docId))
  }

  // 立即检查一次
  checkDocStatus(docId)

  // 每 2 秒轮询一次
  const interval = setInterval(() => {
    checkDocStatus(docId)
  }, 2000)

  pollingIntervals.value.set(docId, interval)
}

async function checkDocStatus(docId) {
  try {
    const doc = await apiGet(`/api/docs/${encodeURIComponent(docId)}?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    const docIndex = docs.value.findIndex((item) => item.id === docId)
    if (docIndex >= 0) {
      const nextDocs = docs.value.slice()
      nextDocs.splice(docIndex, 1, doc)
      docs.value = nextDocs
    }

    // 如果状态不再是 processing，停止轮询
    if (doc.status !== 'processing') {
      if (uploadProgress.value.docId === docId) {
        clearUploadProgress(800)
      }
      stopPolling(docId)
      await refreshTaskCenter()
      await refreshDocs()
      if (doc.status === 'ready') {
        showToast('文档处理完成', 'success')
      } else if (doc.status === 'error') {
        showToast(`文档处理失败: ${doc.error_message || '未知错误'}`, 'error')
      }
    }
  } catch (error) {
    console.error('检查文档状态失败:', error)
    if (uploadProgress.value.docId === docId) {
      clearUploadProgress(800)
    }
    // 出错时也停止轮询，避免无限重试
    stopPolling(docId)
  }
}

function stopPolling(docId) {
  if (pollingIntervals.value.has(docId)) {
    clearInterval(pollingIntervals.value.get(docId))
    pollingIntervals.value.delete(docId)
  }
}

// 检查是否有处理中的文档，如果有则开始轮询
function checkAndStartPolling() {
  const processingDocs = docs.value.filter(doc => doc.status === 'processing')
  processingDocs.forEach(doc => {
    if (!pollingIntervals.value.has(doc.id)) {
      startPolling(doc.id)
    }
  })
}

function setDocBusy(docId, busyState) {
  docBusyMap.value = { ...docBusyMap.value, [docId]: busyState }
}

function isDocBusy(docId) {
  return !!docBusyMap.value[docId]
}

async function createKb() {
  if (!kbNameInput.value) return
  busy.value.kb = true
  try {
    const res = await apiPost('/api/kb', {
      name: kbNameInput.value,
      user_id: resolvedUserId.value
    })
    showToast('知识库创建成功', 'success')
    kbNameInput.value = ''
    await refreshKbs(true)
    if (res?.id) {
      selectedKbId.value = res.id
    }
    await refreshDocs()
  } catch {
    // error toast handled globally
  } finally {
    busy.value.kb = false
  }
}

async function renameCurrentKb() {
  if (!selectedKbId.value) return
  const targetName = kbRenameInput.value.trim()
  if (!targetName) return
  if (selectedKb.value && targetName === selectedKb.value.name) return
  busy.value.kbManage = true
  try {
    await apiPatch(`/api/kb/${selectedKbId.value}`, {
      user_id: resolvedUserId.value,
      name: targetName
    })
    showToast('知识库重命名成功', 'success')
    await refreshKbs(true)
  } catch {
    // error toast handled globally
  } finally {
    busy.value.kbManage = false
  }
}

async function deleteCurrentKb() {
  if (!selectedKbId.value) return
  const docCount = docsTotal.value
  let cascade = false
  if (docCount > 0) {
    cascade = window.confirm(`当前知识库包含 ${docCount} 个文档，是否级联删除该知识库及其全部文档？`)
    if (!cascade) return
  } else {
    const confirmed = window.confirm('确认删除当前空知识库？')
    if (!confirmed) return
  }
  busy.value.kbDelete = true
  try {
    await apiDelete(`/api/kb/${selectedKbId.value}?user_id=${encodeURIComponent(resolvedUserId.value)}&cascade=${cascade}`)
    showToast('知识库已删除', 'success')
    await refreshKbs(true)
    await refreshDocs({ resetPage: true })
  } catch {
    // error toast handled globally
  } finally {
    busy.value.kbDelete = false
  }
}

function resolveTargetKb(inputText, currentKbId) {
  const normalized = (inputText || '').trim().toLowerCase()
  if (!normalized) return null
  return (
    kbs.value.find((kb) => kb.id.toLowerCase() === normalized && kb.id !== currentKbId)
    || kbs.value.find((kb) => kb.name.toLowerCase() === normalized && kb.id !== currentKbId)
    || null
  )
}

async function renameDoc(doc) {
  if (isDocBusy(doc.id) || doc.status === 'processing') return
  const nextName = window.prompt('输入新的文档名称（扩展名保持不变）', doc.filename)
  if (!nextName || !nextName.trim() || nextName.trim() === doc.filename) return
  setDocBusy(doc.id, true)
  try {
    await apiPatch(`/api/docs/${doc.id}`, {
      user_id: resolvedUserId.value,
      filename: nextName.trim()
    })
    showToast('文档已重命名', 'success')
    await refreshDocs()
  } catch {
    // error toast handled globally
  } finally {
    setDocBusy(doc.id, false)
  }
}

async function moveDoc(doc) {
  if (isDocBusy(doc.id) || doc.status === 'processing') return
  const options = kbs.value
    .filter((kb) => kb.id !== doc.kb_id)
    .map((kb) => `${kb.name} (${kb.id})`)
  if (options.length === 0) {
    showToast('没有可移动的目标知识库', 'error')
    return
  }
  const input = window.prompt(`输入目标知识库名称或ID：\n${options.join('\n')}`)
  const target = resolveTargetKb(input, doc.kb_id)
  if (!target) return

  setDocBusy(doc.id, true)
  try {
    await apiPatch(`/api/docs/${doc.id}`, {
      user_id: resolvedUserId.value,
      kb_id: target.id
    })
    showToast(`文档已移动到「${target.name}」`, 'success')
    await refreshDocs()
  } catch {
    // error toast handled globally
  } finally {
    setDocBusy(doc.id, false)
  }
}

async function reprocessDoc(doc) {
  if (isDocBusy(doc.id) || doc.status === 'processing') return
  const confirmed = window.confirm('确认重新解析该文档？这会重建该文档索引。')
  if (!confirmed) return
  setDocBusy(doc.id, true)
  try {
    await apiPost(`/api/docs/${doc.id}/reprocess?user_id=${encodeURIComponent(resolvedUserId.value)}`, {})
    showToast('已触发重新解析', 'success')
    await refreshDocs()
    startPolling(doc.id)
  } catch {
    // error toast handled globally
  } finally {
    setDocBusy(doc.id, false)
  }
}

async function retryFailedTasks(targetDocIds = null) {
  const docIds = Array.isArray(targetDocIds) ? targetDocIds.filter(Boolean) : null
  if (docIds && docIds.length === 1) {
    setDocBusy(docIds[0], true)
  } else {
    busy.value.retryFailed = true
  }
  try {
    const payload = {
      user_id: resolvedUserId.value,
      doc_ids: docIds && docIds.length ? docIds : undefined
    }
    const res = await apiPost('/api/docs/retry-failed', payload)
    const queued = Array.isArray(res?.queued) ? res.queued : []
    const skipped = Array.isArray(res?.skipped) ? res.skipped : []
    if (queued.length > 0) {
      showToast(`已重试 ${queued.length} 个失败任务`, 'success')
      queued.forEach((docId) => startPolling(docId))
    } else if (skipped.length > 0) {
      showToast('未找到可重试的失败任务', 'error')
    }
    await refreshDocs()
  } catch {
    // error toast handled globally
  } finally {
    if (docIds && docIds.length === 1) {
      setDocBusy(docIds[0], false)
    } else {
      busy.value.retryFailed = false
    }
  }
}

async function deleteDocItem(doc) {
  if (isDocBusy(doc.id)) return
  const confirmed = window.confirm(`确认删除文档「${doc.filename}」？该操作不可恢复。`)
  if (!confirmed) return
  setDocBusy(doc.id, true)
  try {
    await apiDelete(`/api/docs/${doc.id}?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    stopPolling(doc.id)
    showToast('文档已删除', 'success')
    await refreshDocs()
  } catch {
    // error toast handled globally
  } finally {
    setDocBusy(doc.id, false)
  }
}

function kbNameById(kbId) {
  const kb = kbs.value.find((item) => item.id === kbId)
  return kb ? kb.name : '未知知识库'
}

function statusLabel(status) {
  switch (status) {
    case 'ready': return '就绪'
    case 'processing': return '处理中'
    case 'error': return '错误'
    default: return status
  }
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
  busy.value.init = true
  try {
    await refreshKbs()
    await refreshDocs()
  } finally {
    busy.value.init = false
  }
})

watch(selectedKbId, async () => {
  // 切换知识库时，停止所有轮询
  pollingIntervals.value.forEach((interval) => clearInterval(interval))
  pollingIntervals.value.clear()
  stopTaskCenterAutoRefresh()
  if (docsFilterDebounce) {
    clearTimeout(docsFilterDebounce)
    docsFilterDebounce = null
  }
  kbRenameInput.value = selectedKb.value ? selectedKb.value.name : ''
  await refreshDocs({ resetPage: true })
})

watch(
  () => [
    docFilters.value.keyword,
    docFilters.value.fileType,
    docFilters.value.status,
    docFilters.value.sortBy,
    docFilters.value.sortOrder,
  ],
  () => {
    if (docsFilterDebounce) {
      clearTimeout(docsFilterDebounce)
    }
    docsFilterDebounce = setTimeout(() => {
      refreshDocs({ resetPage: true })
    }, 300)
  }
)

// 组件卸载时清理所有轮询
onUnmounted(() => {
  pollingIntervals.value.forEach((interval) => clearInterval(interval))
  pollingIntervals.value.clear()
  stopTaskCenterAutoRefresh()
  if (docsFilterDebounce) {
    clearTimeout(docsFilterDebounce)
    docsFilterDebounce = null
  }
  if (uploadProgressResetTimer) {
    clearTimeout(uploadProgressResetTimer)
    uploadProgressResetTimer = null
  }
})
</script>
