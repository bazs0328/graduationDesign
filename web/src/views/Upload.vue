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
              <select v-model="selectedKbId" class="flex-1 bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary">
                <option disabled value="">请选择</option>
                <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
              </select>
              <input
                type="text"
                v-model="kbNameInput"
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
            <div v-if="selectedKbId" class="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-2 pt-1">
              <select
                v-model="kbSettings.parse_policy"
                class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="stable">解析策略: 稳定</option>
                <option value="balanced">解析策略: 平衡</option>
                <option value="aggressive">解析策略: 激进</option>
              </select>
              <select
                v-model="kbSettings.preferred_parser"
                class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="auto">Parser: 自动</option>
                <option value="native">Parser: Native</option>
                <option value="docling">Parser: Docling</option>
              </select>
              <Button
                variant="outline"
                :loading="busy.kbSettings"
                @click="saveKbSettings"
              >
                保存策略
              </Button>
            </div>
            <div v-if="selectedKbId" class="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_auto] gap-2">
              <select
                v-model="kbRagSettings.rag_backend"
                class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="raganything_mineru">RAG: RAGAnything MinerU</option>
                <option value="raganything_docling">RAG: RAGAnything Docling</option>
                <option value="legacy">RAG: Legacy</option>
              </select>
              <select
                v-model="kbRagSettings.query_mode"
                class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="hybrid">查询: Hybrid</option>
                <option value="local">查询: Local</option>
                <option value="global">查询: Global</option>
                <option value="naive">查询: Naive</option>
              </select>
              <select
                v-model="kbRagSettings.parser_preference"
                class="bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="mineru">解析引擎: MinerU</option>
                <option value="docling">解析引擎: Docling</option>
                <option value="auto">解析引擎: Auto</option>
              </select>
              <Button
                variant="outline"
                :loading="busy.kbRagSettings"
                @click="saveKbRagSettings"
              >
                保存RAG
              </Button>
            </div>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-medium text-muted-foreground uppercase tracking-wider">选择文件</label>
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
                <UploadIcon class="w-10 h-10 mx-auto text-muted-foreground" />
                <p class="text-sm text-muted-foreground">点击或拖拽 PDF/文本文件到此处</p>
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
            {{ busy.init ? '加载中…' : `共 ${docs.length} 个` }}
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
            <option value="stage">按阶段</option>
            <option value="progress_percent">按进度</option>
            <option value="quality_score">按质量分</option>
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
          <div v-else-if="docs.length === 0" class="h-full flex flex-col items-center justify-center text-muted-foreground space-y-2">
            <Database class="w-12 h-12 opacity-20" />
            <p>暂无文档</p>
          </div>
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
              <span v-if="doc.parser_provider" class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.parser_provider }}</span>
              <span v-if="doc.extract_method" class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.extract_method }}</span>
              <span
                v-if="Number.isFinite(Number(doc.quality_score))"
                class="text-[10px] px-2 py-0.5 rounded-full"
                :class="Number(doc.quality_score) < 45 ? 'bg-destructive/20 text-destructive' : 'bg-green-500/20 text-green-600'"
              >
                质量 {{ Number(doc.quality_score).toFixed(1) }}
              </span>
              <template v-if="doc.status === 'processing'">
                <span class="text-[10px] bg-blue-500/20 text-blue-500 px-2 py-0.5 rounded-full animate-pulse">
                  {{ stageLabel(doc.stage) }}
                </span>
              </template>
              <template v-else>
                <span v-if="doc.num_pages > 0" class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.num_pages }} 页</span>
                <span v-if="doc.num_chunks > 0" class="text-[10px] bg-secondary px-2 py-0.5 rounded-full">{{ doc.num_chunks }} 块</span>
              </template>
            </div>
            <div v-if="doc.status === 'processing'" class="mb-3">
              <div class="h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  class="h-full bg-primary transition-all duration-300"
                  :style="{ width: `${clampProgress(doc.progress_percent)}%` }"
                ></div>
              </div>
              <p class="mt-1 text-[10px] text-muted-foreground">
                {{ stageLabel(doc.stage) }} · {{ clampProgress(doc.progress_percent) }}%
              </p>
            </div>
            <div class="flex items-center justify-between text-[10px] text-muted-foreground">
              <span>{{ new Date(doc.created_at).toLocaleDateString() }}</span>
              <span v-if="doc.error_message" class="text-destructive truncate max-w-[150px]">{{ doc.error_message }}</span>
              <span v-else-if="doc.status === 'processing'" class="text-blue-500">
                {{ stageLabel(doc.stage) }} · 自动更新中...
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
                variant="ghost"
                :disabled="isDocBusy(doc.id)"
                data-testid="doc-diagnostics-btn"
                @click="openDiagnostics(doc)"
              >
                诊断
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
      </section>
    </div>

    <section class="bg-card border border-border rounded-2xl p-6 shadow-lg shadow-primary/5 space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <RefreshCw class="w-5 h-5 text-primary" />
          <h3 class="text-lg font-bold">解析任务中心</h3>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>处理中 {{ taskCenter.processing_count }}</span>
          <span>失败 {{ taskCenter.error_count }}</span>
          <span>运行中 {{ taskCenter.running_workers }}</span>
          <span>排队 {{ taskCenter.queued_jobs }}</span>
          <span>平均进度 {{ Number(taskCenter.avg_progress_percent || 0).toFixed(1) }}%</span>
        </div>
      </div>
      <div
        v-if="Object.keys(taskCenter.stage_counts || {}).length"
        class="flex flex-wrap items-center gap-2 text-xs"
      >
        <span
          v-for="(count, stage) in taskCenter.stage_counts"
          :key="stage"
          class="px-2 py-1 rounded-full bg-secondary text-secondary-foreground"
        >
          {{ stageLabel(stage) }}: {{ count }}
        </span>
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
            class="text-xs p-3 bg-background border border-border rounded-lg space-y-2"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate font-medium">{{ task.filename }}</div>
                <div class="text-muted-foreground">{{ stageLabel(task.stage) }} · {{ clampProgress(task.progress_percent) }}%</div>
              </div>
              <RefreshCw class="w-3 h-3 text-blue-500 animate-spin shrink-0" />
            </div>
            <div class="h-1.5 bg-muted rounded-full overflow-hidden">
              <div class="h-full bg-primary transition-all duration-300" :style="{ width: `${clampProgress(task.progress_percent)}%` }"></div>
            </div>
          </div>
        </div>

        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <div class="text-sm font-semibold">失败</div>
            <div class="flex items-center gap-2">
              <select
                v-model="processMode"
                data-testid="process-mode-select"
                class="bg-background border border-input rounded-lg px-2 py-1 text-xs outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="auto">Auto</option>
                <option value="force_ocr">强制 OCR</option>
                <option value="text_layer">文本层</option>
                <option value="parser_auto">ParserAuto</option>
              </select>
              <Button
                size="sm"
                variant="outline"
                data-testid="retry-failed-btn"
                :disabled="taskCenter.error_count === 0"
                :loading="busy.retryFailed"
                @click="retryFailedTasks()"
              >
                一键重试
              </Button>
            </div>
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
              按当前模式重试
            </Button>
          </div>
        </div>
      </div>
    </section>
    <DocumentDiagnosticsModal
      :open="diagnosticsModal.open"
      :loading="diagnosticsModal.loading"
      :filename="diagnosticsModal.filename"
      :data="diagnosticsModal.data"
      :error="diagnosticsModal.error"
      @close="closeDiagnostics"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { Upload as UploadIcon, FileText, Database, X, RefreshCw } from 'lucide-vue-next'
import { apiDelete, apiGet, apiPatch, apiPost } from '../api'
import { useToast } from '../composables/useToast'
import Button from '../components/ui/Button.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import DocumentDiagnosticsModal from '../components/ui/DocumentDiagnosticsModal.vue'

const { showToast } = useToast()

const userId = ref(localStorage.getItem('gradtutor_user') || 'default')
const resolvedUserId = computed(() => userId.value || 'default')
const docs = ref([])
const kbs = ref([])
const selectedKbId = ref('')
const kbNameInput = ref('')
const kbRenameInput = ref('')
const kbSettings = ref({
  parse_policy: 'balanced',
  preferred_parser: 'auto'
})
const kbRagSettings = ref({
  rag_backend: 'raganything_mineru',
  query_mode: 'hybrid',
  parser_preference: 'mineru'
})
const processMode = ref('auto')
const docFilters = ref({
  keyword: '',
  fileType: '',
  status: '',
  sortBy: 'created_at',
  sortOrder: 'desc'
})
const uploadFile = ref(null)
const dragActive = ref(false)
const docBusyMap = ref({})
const taskCenter = ref({
  processing: [],
  error: [],
  processing_count: 0,
  error_count: 0,
  stage_counts: {},
  avg_progress_percent: 0,
  running_workers: 0,
  queued_jobs: 0,
  auto_refresh_ms: 2000
})
const busy = ref({
  upload: false,
  kb: false,
  kbManage: false,
  kbDelete: false,
  kbSettings: false,
  kbRagSettings: false,
  retryFailed: false,
  refresh: false,
  init: false
})
const diagnosticsModal = ref({
  open: false,
  loading: false,
  filename: '',
  error: '',
  data: {}
})
const pollingIntervals = ref(new Map()) // 存储每个文档的轮询定时器
let taskCenterInterval = null
let docsFilterDebounce = null
const selectedKb = computed(() => kbs.value.find((item) => item.id === selectedKbId.value) || null)

function onFileChange(event) {
  uploadFile.value = event.target.files[0]
}

function onDrop(event) {
  dragActive.value = false
  uploadFile.value = event.dataTransfer.files[0]
}

async function refreshKbs() {
  try {
    kbs.value = await apiGet(`/api/kb?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    const found = kbs.value.find((kb) => kb.id === selectedKbId.value)
    if (!found) {
      selectedKbId.value = kbs.value.length ? kbs.value[0].id : ''
    }
    const active = kbs.value.find((kb) => kb.id === selectedKbId.value)
    kbRenameInput.value = active ? active.name : ''
  } catch {
    // error toast handled globally
  }
}

async function refreshKbSettings() {
  if (!selectedKbId.value) {
    kbSettings.value = {
      parse_policy: 'balanced',
      preferred_parser: 'auto'
    }
    return
  }
  try {
    const res = await apiGet(`/api/kb/${selectedKbId.value}/settings?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    kbSettings.value = {
      parse_policy: res?.parse_policy || 'balanced',
      preferred_parser: res?.preferred_parser || 'auto'
    }
  } catch {
    kbSettings.value = {
      parse_policy: 'balanced',
      preferred_parser: 'auto'
    }
  }
}

async function refreshKbRagSettings() {
  if (!selectedKbId.value) {
    kbRagSettings.value = {
      rag_backend: 'raganything_mineru',
      query_mode: 'hybrid',
      parser_preference: 'mineru'
    }
    return
  }
  try {
    const res = await apiGet(`/api/kb/${selectedKbId.value}/rag-settings?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    kbRagSettings.value = {
      rag_backend: res?.rag_backend || 'raganything_mineru',
      query_mode: res?.query_mode || 'hybrid',
      parser_preference: res?.parser_preference || 'mineru'
    }
  } catch {
    kbRagSettings.value = {
      rag_backend: 'raganything_mineru',
      query_mode: 'hybrid',
      parser_preference: 'mineru'
    }
  }
}

async function saveKbSettings() {
  if (!selectedKbId.value) return
  busy.value.kbSettings = true
  try {
    const res = await apiPatch(`/api/kb/${selectedKbId.value}/settings`, {
      user_id: resolvedUserId.value,
      parse_policy: kbSettings.value.parse_policy,
      preferred_parser: kbSettings.value.preferred_parser
    })
    kbSettings.value = {
      parse_policy: res?.parse_policy || 'balanced',
      preferred_parser: res?.preferred_parser || 'auto'
    }
    showToast('解析策略已保存', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.kbSettings = false
  }
}

async function saveKbRagSettings() {
  if (!selectedKbId.value) return
  busy.value.kbRagSettings = true
  try {
    const res = await apiPatch(`/api/kb/${selectedKbId.value}/rag-settings`, {
      user_id: resolvedUserId.value,
      rag_backend: kbRagSettings.value.rag_backend,
      query_mode: kbRagSettings.value.query_mode,
      parser_preference: kbRagSettings.value.parser_preference
    })
    kbRagSettings.value = {
      rag_backend: res?.rag_backend || 'raganything_mineru',
      query_mode: res?.query_mode || 'hybrid',
      parser_preference: res?.parser_preference || 'mineru'
    }
    showToast('RAG 设置已保存', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.kbRagSettings = false
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
  if (!taskCenter.value.processing_count && !taskCenter.value.queued_jobs) return
  const interval = Math.max(1000, taskCenter.value.auto_refresh_ms || 2000)
  taskCenterInterval = setInterval(async () => {
    await refreshTaskCenter()
    if (!taskCenter.value.processing_count && !taskCenter.value.queued_jobs) {
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

function buildDocsQueryParams() {
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
  return params.toString()
}

function toggleSortOrder() {
  docFilters.value.sortOrder = docFilters.value.sortOrder === 'desc' ? 'asc' : 'desc'
}

async function refreshDocs() {
  busy.value.refresh = true
  try {
    const query = buildDocsQueryParams()
    const result = await apiGet(`/api/docs?${query}`)
    docs.value = result
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
  busy.value.upload = true
  try {
    const form = new FormData()
    form.append('file', uploadFile.value)
    form.append('user_id', resolvedUserId.value)
    if (selectedKbId.value) {
      form.append('kb_id', selectedKbId.value)
    }
    const uploadedDoc = await apiPost('/api/docs/upload', form, true)
    showToast('文档上传成功，正在处理中...', 'success')
    uploadFile.value = null
    await refreshDocs()
    
    // 如果文档状态是 processing，开始轮询
    if (uploadedDoc.status === 'processing') {
      startPolling(uploadedDoc.id)
    }
  } catch {
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
    const query = buildDocsQueryParams()
    const result = await apiGet(`/api/docs?${query}`)
    
    // 更新文档列表
    docs.value = result
    
    // 查找当前文档
    const doc = result.find(d => d.id === docId)
    if (!doc) {
      // 文档不存在，停止轮询
      stopPolling(docId)
      return
    }
    
    // 如果状态不再是 processing，停止轮询
    if (doc.status !== 'processing') {
      stopPolling(docId)
      await refreshTaskCenter()
      if (doc.status === 'ready') {
        showToast('文档处理完成', 'success')
      } else if (doc.status === 'error') {
        showToast(`文档处理失败: ${doc.error_message || '未知错误'}`, 'error')
      }
    }
  } catch (error) {
    console.error('检查文档状态失败:', error)
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
    await refreshKbs()
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
    await refreshKbs()
  } catch {
    // error toast handled globally
  } finally {
    busy.value.kbManage = false
  }
}

async function deleteCurrentKb() {
  if (!selectedKbId.value) return
  const docCount = docs.value.length
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
    await refreshKbs()
    await refreshDocs()
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
  const confirmed = window.confirm(`确认重新解析该文档？模式: ${processMode.value}`)
  if (!confirmed) return
  setDocBusy(doc.id, true)
  try {
    await apiPost(`/api/docs/${doc.id}/reprocess`, {
      user_id: resolvedUserId.value,
      mode: processMode.value
    })
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
      doc_ids: docIds && docIds.length ? docIds : undefined,
      mode: processMode.value
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

async function openDiagnostics(doc) {
  diagnosticsModal.value = {
    open: true,
    loading: true,
    filename: doc.filename,
    error: '',
    data: {}
  }
  try {
    const res = await apiGet(`/api/docs/${doc.id}/diagnostics?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    diagnosticsModal.value = {
      ...diagnosticsModal.value,
      loading: false,
      data: res || {}
    }
  } catch {
    diagnosticsModal.value = {
      ...diagnosticsModal.value,
      loading: false,
      error: '加载诊断失败'
    }
  }
}

function closeDiagnostics() {
  diagnosticsModal.value = {
    open: false,
    loading: false,
    filename: '',
    error: '',
    data: {}
  }
}

function kbNameById(kbId) {
  const kb = kbs.value.find((item) => item.id === kbId)
  return kb ? kb.name : '未知知识库'
}

function clampProgress(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return 0
  return Math.max(0, Math.min(Math.round(num), 100))
}

function stageLabel(stage) {
  const normalized = String(stage || '').trim().toLowerCase()
  switch (normalized) {
    case 'queued': return '排队中'
    case 'preflight': return '预检'
    case 'extract': return '提取'
    case 'ocr': return 'OCR'
    case 'chunk': return '切块'
    case 'index_dense': return '向量索引'
    case 'index_lexical': return '词法索引'
    case 'done': return '完成'
    case 'error': return '失败'
    default: return normalized ? normalized : '处理中'
  }
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
    await refreshKbSettings()
    await refreshKbRagSettings()
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
  await refreshKbSettings()
  await refreshKbRagSettings()
  await refreshDocs()
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
      refreshDocs()
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
})
</script>
