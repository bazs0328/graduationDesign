<template>
  <div class="space-y-6 md:space-y-8 max-w-6xl mx-auto">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card p-5 sm:p-6 shadow-sm">
      <div class="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.10),transparent_55%)]"></div>
      <div class="relative flex flex-wrap items-start justify-between gap-4">
        <div class="space-y-2">
          <div class="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            <SlidersHorizontal class="w-3.5 h-3.5" />
            设置中心
          </div>
          <h1 class="text-2xl font-black tracking-tight">把常用配置从 `.env` 带回界面</h1>
          <p class="text-sm text-muted-foreground max-w-3xl leading-relaxed">
            面向非技术用户开放常用问答/测验偏好；系统级模型、OCR 和密钥配置仍由管理员在后端维护。
          </p>
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-xl border border-border bg-background/70 px-3 py-2">
            <div class="text-muted-foreground">当前知识库</div>
            <div class="font-semibold truncate max-w-[180px]">{{ selectedKbName || '未选择' }}</div>
          </div>
          <div class="rounded-xl border border-border bg-background/70 px-3 py-2">
            <div class="text-muted-foreground">状态</div>
            <div class="font-semibold" :class="settingsStore.error ? 'text-amber-600' : 'text-green-600'">
              {{ settingsStore.error ? '回退默认配置' : '配置可用' }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="space-y-4">
      <div class="flex items-center justify-between gap-3">
        <h2 class="text-lg font-bold tracking-tight flex items-center gap-2">
          <ShieldCheck class="w-5 h-5 text-primary" />
          系统状态（只读）
        </h2>
        <button
          type="button"
          class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent disabled:opacity-50"
          :disabled="settingsStore.loading"
          @click="reloadSettings(true)"
        >
          {{ settingsStore.loading ? '刷新中…' : '刷新状态' }}
        </button>
      </div>

      <div v-if="settingsStore.loading && !systemStatus" class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div v-for="idx in 3" :key="idx" class="rounded-2xl border border-border bg-card p-4">
          <SkeletonBlock type="list" :lines="4" />
        </div>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="rounded-2xl border border-border bg-card p-4 space-y-3 shadow-sm">
          <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">模型配置</div>
          <div class="space-y-2">
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm text-muted-foreground">LLM</span>
              <span class="px-2 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold">
                {{ systemStatus?.llm_provider || '—' }}
              </span>
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm text-muted-foreground">Embedding</span>
              <span class="px-2 py-1 rounded-full bg-secondary text-secondary-foreground text-xs font-semibold">
                {{ systemStatus?.embedding_provider || '—' }}
              </span>
            </div>
          </div>
          <p class="text-xs text-muted-foreground leading-relaxed">
            模型与密钥仍由后端 `.env` 管理，本页仅展示状态并提供用户侧体验参数。
          </p>
        </div>

        <div class="rounded-2xl border border-border bg-card p-4 space-y-3 shadow-sm">
          <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">RAG 默认值</div>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2">
              <div class="text-xs text-muted-foreground">top_k</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults_from_env?.qa_top_k ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2">
              <div class="text-xs text-muted-foreground">fetch_k</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults_from_env?.qa_fetch_k ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2 col-span-2">
              <div class="text-xs text-muted-foreground">RAG 模式</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults_from_env?.rag_mode ?? '—' }}</div>
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-border bg-card p-4 space-y-3 shadow-sm">
          <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">能力开关</div>
          <div class="space-y-2 text-sm">
            <div class="flex items-center justify-between gap-2">
              <span class="text-muted-foreground">OCR</span>
              <span
                class="px-2 py-1 rounded-full text-[10px] font-semibold border"
                :class="systemStatus?.ocr_enabled ? 'border-green-200 bg-green-50 text-green-700' : 'border-border bg-background text-muted-foreground'"
              >
                {{ systemStatus?.ocr_enabled ? '开启' : '关闭' }}
              </span>
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-muted-foreground">需要登录</span>
              <span
                class="px-2 py-1 rounded-full text-[10px] font-semibold border"
                :class="systemStatus?.auth_require_login ? 'border-green-200 bg-green-50 text-green-700' : 'border-border bg-background text-muted-foreground'"
              >
                {{ systemStatus?.auth_require_login ? '开启' : '关闭' }}
              </span>
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-muted-foreground">PDF Parser</span>
              <span class="text-xs font-semibold">{{ systemStatus?.pdf_parser_mode || '—' }}</span>
            </div>
          </div>
          <div class="pt-1 border-t border-border/60">
            <div class="text-xs font-semibold text-muted-foreground mb-2">密钥状态（仅状态，不显示明文）</div>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="(ok, key) in (systemStatus?.secrets_configured || {})"
                :key="key"
                class="px-2 py-1 rounded-full text-[10px] font-semibold border"
                :class="ok ? 'border-green-200 bg-green-50 text-green-700' : 'border-border bg-background text-muted-foreground'"
              >
                {{ key }}: {{ ok ? 'OK' : '未配置' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <SettingsPanel
      title="用户默认设置"
      description="这组设置会作为你在所有知识库中的默认体验参数。"
      :dirty="settingsStore.userDirty"
      :saving="settingsStore.savingUser"
      :error="panelError('user')"
      :advanced-open="userAdvancedOpen"
      advanced-label="高级检索参数"
      @update:advanced-open="userAdvancedOpen = $event"
      @save="saveUserDefaults"
      @reset="resetUserDefaults"
    >
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">问答回答风格</label>
          <select
            :value="userDraft.qa.mode"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            @change="updateUserSection('qa', { mode: $event.target.value })"
          >
            <option value="normal">标准回答</option>
            <option value="explain">分步讲解</option>
          </select>
        </div>

        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">问答检索预设</label>
          <select
            :value="userDraft.qa.retrieval_preset"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            @change="updateUserSection('qa', { retrieval_preset: $event.target.value })"
          >
            <option value="fast">快速（响应更快）</option>
            <option value="balanced">均衡（推荐）</option>
            <option value="deep">深度（检索更多）</option>
          </select>
        </div>

        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">默认题量</label>
          <input
            type="number"
            min="1"
            max="20"
            :value="userDraft.quiz.count_default"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            @input="updateUserSection('quiz', { count_default: clampInt($event.target.value, 1, 20, 5) })"
          />
        </div>

        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">默认难度（手动模式）</label>
          <select
            :value="userDraft.quiz.difficulty_default"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            :disabled="Boolean(userDraft.quiz.auto_adapt_default)"
            @change="updateUserSection('quiz', { difficulty_default: $event.target.value })"
          >
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label class="rounded-xl border border-border bg-background/40 px-4 py-3 flex items-center justify-between gap-3 cursor-pointer">
          <span class="text-sm font-medium">测验默认启用自适应</span>
          <input
            type="checkbox"
            class="h-4 w-4"
            :checked="Boolean(userDraft.quiz.auto_adapt_default)"
            @change="updateUserSection('quiz', { auto_adapt_default: $event.target.checked })"
          />
        </label>

        <label class="rounded-xl border border-border bg-background/40 px-4 py-3 flex items-center justify-between gap-3 cursor-pointer">
          <span class="text-sm font-medium">默认展开高级参数</span>
          <input
            type="checkbox"
            class="h-4 w-4"
            :checked="Boolean(userDraft.ui.show_advanced_controls)"
            @change="updateUserSection('ui', { show_advanced_controls: $event.target.checked })"
          />
        </label>

        <label class="rounded-xl border border-border bg-background/40 px-4 py-3 flex items-center justify-between gap-3 cursor-pointer">
          <span class="text-sm font-medium">上传后显示后续建议</span>
          <input
            type="checkbox"
            class="h-4 w-4"
            :checked="Boolean(userDraft.upload.post_upload_suggestions)"
            @change="updateUserSection('upload', { post_upload_suggestions: $event.target.checked })"
          />
        </label>
      </div>

      <div class="space-y-2">
        <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">界面密度</label>
        <div class="inline-flex rounded-lg border border-border bg-background p-1">
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
            :class="userDraft.ui.density === 'comfortable' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'"
            @click="updateUserSection('ui', { density: 'comfortable' })"
          >
            舒适
          </button>
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
            :class="userDraft.ui.density === 'compact' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'"
            @click="updateUserSection('ui', { density: 'compact' })"
          >
            紧凑
          </button>
        </div>
      </div>

      <template #advanced>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">手动 top_k（可空）</label>
            <input
              type="number"
              min="1"
              max="20"
              :value="nullableNumberInput(userDraft.qa.top_k)"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              placeholder="留空则使用预设"
              @input="updateUserSection('qa', { top_k: parseNullableInt($event.target.value, 1, 20) })"
            />
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">手动 fetch_k（可空）</label>
            <input
              type="number"
              min="1"
              max="50"
              :value="nullableNumberInput(userDraft.qa.fetch_k)"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              placeholder="留空则使用预设"
              @input="updateUserSection('qa', { fetch_k: parseNullableInt($event.target.value, 1, 50) })"
            />
          </div>
        </div>
        <div class="flex items-center justify-between gap-3 text-xs">
          <p class="text-muted-foreground">
            当手动值为空时，系统将按预设自动映射（如 `balanced` -> `top_k=4`, `fetch_k=12`）。
          </p>
          <button
            type="button"
            class="px-3 py-2 rounded-lg border border-input font-semibold hover:bg-accent"
            @click="updateUserSection('qa', { top_k: null, fetch_k: null })"
          >
            清空手动值
          </button>
        </div>
      </template>
    </SettingsPanel>

    <SettingsPanel
      v-if="selectedKbId"
      title="当前知识库覆盖设置"
      description="只覆盖当前知识库的问答与测验偏好；留空表示跟随用户默认设置。"
      :dirty="settingsStore.kbDirty"
      :saving="settingsStore.savingKb"
      :error="panelError('kb')"
      :advanced-open="kbAdvancedOpen"
      advanced-label="高级覆盖参数"
      @update:advanced-open="kbAdvancedOpen = $event"
      @save="saveKbOverrides"
      @reset="resetKbOverrides"
    >
      <div class="rounded-xl border border-border bg-background/40 p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-xs font-bold uppercase tracking-widest text-muted-foreground">作用对象</p>
            <p class="text-sm font-semibold">{{ selectedKbName }}</p>
          </div>
          <KbSelector
            class="min-w-[220px]"
            :model-value="selectedKbId"
            :kbs="kbs"
            label=""
            placeholder="请选择知识库"
            :loading="appContext.kbsLoading"
            @update:model-value="selectedKbId = $event"
          />
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">问答模式覆盖</label>
          <select
            :value="kbDraft.qa.mode || ''"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            @change="updateKbSection('qa', { mode: emptyToNull($event.target.value) })"
          >
            <option value="">跟随用户默认</option>
            <option value="normal">标准回答</option>
            <option value="explain">分步讲解</option>
          </select>
        </div>

        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">检索预设覆盖</label>
          <select
            :value="kbDraft.qa.retrieval_preset || ''"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            @change="updateKbSection('qa', { retrieval_preset: emptyToNull($event.target.value) })"
          >
            <option value="">跟随用户默认</option>
            <option value="fast">快速</option>
            <option value="balanced">均衡</option>
            <option value="deep">深度</option>
          </select>
        </div>

        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">默认题量覆盖</label>
          <input
            type="number"
            min="1"
            max="20"
            :value="nullableNumberInput(kbDraft.quiz.count_default)"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            placeholder="留空则跟随默认"
            @input="updateKbSection('quiz', { count_default: parseNullableInt($event.target.value, 1, 20) })"
          />
        </div>

        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">手动难度覆盖</label>
          <select
            :value="kbDraft.quiz.difficulty_default || ''"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            @change="updateKbSection('quiz', { difficulty_default: emptyToNull($event.target.value) })"
          >
            <option value="">跟随用户默认</option>
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
        </div>
      </div>

      <div class="space-y-2">
        <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">自适应模式覆盖</label>
        <select
          :value="nullableBoolToSelect(kbDraft.quiz.auto_adapt_default)"
          class="w-full md:w-[320px] bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
          @change="updateKbSection('quiz', { auto_adapt_default: selectToNullableBool($event.target.value) })"
        >
          <option value="">跟随用户默认</option>
          <option value="true">始终开启</option>
          <option value="false">始终关闭</option>
        </select>
      </div>

      <template #advanced>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">top_k 覆盖（可空）</label>
            <input
              type="number"
              min="1"
              max="20"
              :value="nullableNumberInput(kbDraft.qa.top_k)"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              placeholder="留空则跟随默认"
              @input="updateKbSection('qa', { top_k: parseNullableInt($event.target.value, 1, 20) })"
            />
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">fetch_k 覆盖（可空）</label>
            <input
              type="number"
              min="1"
              max="50"
              :value="nullableNumberInput(kbDraft.qa.fetch_k)"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
              placeholder="留空则跟随默认"
              @input="updateKbSection('qa', { fetch_k: parseNullableInt($event.target.value, 1, 50) })"
            />
          </div>
        </div>
        <div class="text-xs text-muted-foreground">
          留空表示跟随用户默认；若用户默认也为空，则按预设映射自动计算。
        </div>
      </template>
    </SettingsPanel>

    <div v-else class="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">
      当前未选择知识库。先在侧边栏或上传页选择一个知识库后，即可配置该知识库覆盖设置。
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { SlidersHorizontal, ShieldCheck } from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { useAppContextStore } from '../stores/appContext'
import { useSettingsStore } from '../stores/settings'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import KbSelector from '../components/context/KbSelector.vue'
import SettingsPanel from '../components/settings/SettingsPanel.vue'

const { showToast } = useToast()
const appContext = useAppContextStore()
appContext.hydrate()
const settingsStore = useSettingsStore()

const userAdvancedOpen = ref(false)
const kbAdvancedOpen = ref(false)
const lastUserActionError = ref('')
const lastKbActionError = ref('')

const resolvedUserId = computed(() => appContext.resolvedUserId || 'default')
const kbs = computed(() => appContext.kbs)
const selectedKbId = computed({
  get: () => appContext.selectedKbId,
  set: (value) => appContext.setSelectedKbId(value),
})
const selectedKbName = computed(() => {
  const kb = kbs.value.find((item) => item.id === selectedKbId.value)
  return kb?.name || ''
})

const systemStatus = computed(() => settingsStore.systemStatus)
const userDraft = computed(() => settingsStore.userDraft)
const kbDraft = computed(() => settingsStore.kbDraft)

function emptyToNull(value) {
  const normalized = String(value ?? '').trim()
  return normalized ? normalized : null
}

function clampInt(value, min, max, fallback) {
  const num = Number(value)
  if (!Number.isFinite(num)) return fallback
  return Math.max(min, Math.min(max, Math.round(num)))
}

function parseNullableInt(value, min, max) {
  const raw = String(value ?? '').trim()
  if (!raw) return null
  const num = Number(raw)
  if (!Number.isFinite(num)) return null
  return Math.max(min, Math.min(max, Math.round(num)))
}

function nullableNumberInput(value) {
  return value == null ? '' : String(value)
}

function nullableBoolToSelect(value) {
  if (value === true) return 'true'
  if (value === false) return 'false'
  return ''
}

function selectToNullableBool(value) {
  if (value === 'true') return true
  if (value === 'false') return false
  return null
}

function updateUserSection(section, patch) {
  lastUserActionError.value = ''
  settingsStore.setUserDraftSection(section, patch)
}

function updateKbSection(section, patch) {
  lastKbActionError.value = ''
  settingsStore.setKbDraftSection(section, patch)
}

function panelError(scope) {
  if (scope === 'user') return lastUserActionError.value || ''
  return lastKbActionError.value || ''
}

async function reloadSettings(force = false) {
  try {
    await settingsStore.load({
      userId: resolvedUserId.value,
      kbId: selectedKbId.value || '',
      force,
    })
    if (!userAdvancedOpen.value) {
      userAdvancedOpen.value = Boolean(settingsStore.userDraft?.ui?.show_advanced_controls)
    }
  } catch {
    // global error toast already handled
  }
}

async function saveUserDefaults() {
  lastUserActionError.value = ''
  try {
    await settingsStore.saveUser(resolvedUserId.value)
    showToast('用户默认设置已保存', 'success')
  } catch (err) {
    lastUserActionError.value = err?.message || '保存失败'
  }
}

async function saveKbOverrides() {
  if (!selectedKbId.value) return
  lastKbActionError.value = ''
  try {
    await settingsStore.saveKb(selectedKbId.value, resolvedUserId.value)
    showToast('知识库覆盖设置已保存', 'success')
  } catch (err) {
    lastKbActionError.value = err?.message || '保存失败'
  }
}

async function resetUserDefaults() {
  lastUserActionError.value = ''
  try {
    await settingsStore.reset('user', { userId: resolvedUserId.value, kbId: selectedKbId.value || '' })
    showToast('用户默认设置已重置', 'success')
  } catch (err) {
    lastUserActionError.value = err?.message || '重置失败'
  }
}

async function resetKbOverrides() {
  if (!selectedKbId.value) return
  lastKbActionError.value = ''
  try {
    await settingsStore.reset('kb', { userId: resolvedUserId.value, kbId: selectedKbId.value })
    showToast('知识库覆盖设置已重置', 'success')
  } catch (err) {
    lastKbActionError.value = err?.message || '重置失败'
  }
}

onMounted(async () => {
  try {
    if (!appContext.kbs.length) {
      await appContext.loadKbs()
    }
  } catch {
    // global error toast handled elsewhere
  }
  await reloadSettings(true)
})

watch(selectedKbId, async () => {
  await reloadSettings(true)
})
</script>
