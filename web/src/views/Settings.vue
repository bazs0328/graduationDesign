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
          <h1 class="text-2xl font-black tracking-tight">学习偏好设置</h1>
          <p class="text-sm text-muted-foreground max-w-3xl leading-relaxed">
            默认只展示学习常用选项；系统级模型、文档识别能力与密钥状态可在高级诊断中查看。
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
      <div class="rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="space-y-1">
            <h2 class="text-lg font-bold tracking-tight flex items-center gap-2">
              <ShieldCheck class="w-5 h-5 text-primary" />
              高级设置与诊断
            </h2>
            <p class="text-xs text-muted-foreground">
              日常学习无需调整本区域；仅在排查模型或系统问题时展开。
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent disabled:opacity-50"
              :disabled="settingsStore.loading"
              @click="reloadSettings(true)"
            >
              {{ settingsStore.loading ? '刷新中…' : '刷新状态' }}
            </button>
            <button
              type="button"
              class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent"
              @click="advancedDiagnosticsOpen = !advancedDiagnosticsOpen"
            >
              {{ advancedDiagnosticsOpen ? '收起高级诊断' : '展开高级诊断' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="advancedDiagnosticsOpen && settingsStore.loading && !systemStatus" class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div v-for="idx in 3" :key="idx" class="rounded-2xl border border-border bg-card p-4">
          <SkeletonBlock type="list" :lines="4" />
        </div>
      </div>

      <div v-else-if="advancedDiagnosticsOpen" class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="rounded-2xl border border-border bg-card p-4 space-y-3 shadow-sm">
          <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">模型状态（高级）</div>
          <div class="space-y-2">
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm text-muted-foreground">文本模型</span>
              <span class="px-2 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold">
                {{ systemStatus?.llm_provider || '—' }}
              </span>
            </div>
            <div class="text-[11px] text-muted-foreground">
              配置值：{{ systemStatus?.llm_provider_configured || '—' }} · 来源：{{ providerSourceLabel(systemStatus?.llm_provider_source) }}
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm text-muted-foreground">{{ UX_TEXT.vectorModelLabel }}</span>
              <span class="px-2 py-1 rounded-full bg-secondary text-secondary-foreground text-xs font-semibold">
                {{ systemStatus?.embedding_provider || '—' }}
              </span>
            </div>
            <div class="text-[11px] text-muted-foreground">
              配置值：{{ systemStatus?.embedding_provider_configured || '—' }} · 来源：{{ providerSourceLabel(systemStatus?.embedding_provider_source) }}
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-border bg-card p-4 space-y-3 shadow-sm">
          <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">检索策略默认值（高级）</div>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2">
              <div class="text-xs text-muted-foreground">{{ UX_TEXT.referenceCountLabel }}</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults_from_env?.qa_top_k ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2">
              <div class="text-xs text-muted-foreground">{{ UX_TEXT.candidateRangeLabel }}</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults_from_env?.qa_fetch_k ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2 col-span-2">
              <div class="text-xs text-muted-foreground">{{ UX_TEXT.retrievalStrategyLabel }}</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults_from_env?.rag_mode ?? '—' }}</div>
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-border bg-card p-4 space-y-3 shadow-sm">
          <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">能力与密钥状态（高级）</div>
          <div class="space-y-2 text-sm">
            <div class="flex items-center justify-between gap-2">
              <span class="text-muted-foreground">文档识别能力</span>
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
              <span class="text-muted-foreground">文档解析模式</span>
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

      <div v-if="advancedDiagnosticsOpen" class="rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-sm space-y-3">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground">系统高级参数（可编辑）</h3>
            <p class="mt-1 text-xs text-muted-foreground">
              这里的值会覆盖后端默认参数并持久化保存，适合减少 `.env` 维护负担。
            </p>
          </div>
          <div class="text-xs text-muted-foreground space-y-1">
            <div>可编辑键：{{ systemAdvanced.editableKeys.length }} 项</div>
            <div>当前覆盖：{{ Object.keys(systemAdvancedDraft || {}).length }} 项</div>
          </div>
        </div>

        <div v-if="systemSchemaGroups.length === 0" class="rounded-xl border border-dashed border-border bg-background/40 p-4 text-sm text-muted-foreground">
          未获取到系统参数 schema，请稍后刷新重试。
        </div>

        <div v-else class="space-y-4">
          <div
            v-for="group in systemSchemaGroups"
            :key="group.id"
            class="rounded-xl border border-border/80 bg-background/40 p-4 space-y-3"
          >
            <h4 class="text-xs font-bold uppercase tracking-widest text-muted-foreground">{{ group.label }}</h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div
                v-for="field in fieldsForGroup(group.id)"
                :key="field.key"
                class="rounded-lg border border-border bg-card p-3 space-y-2"
              >
                <div class="flex items-center justify-between gap-2">
                  <label class="text-sm font-semibold">{{ field.label }}</label>
                  <span
                    class="text-[10px] font-semibold px-2 py-0.5 rounded-full border"
                    :class="hasSystemOverride(field.key) ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border bg-background text-muted-foreground'"
                  >
                    {{ hasSystemOverride(field.key) ? '已覆盖' : '跟随默认' }}
                  </span>
                </div>

                <p v-if="field.description" class="text-xs text-muted-foreground">{{ field.description }}</p>

                <div v-if="field.input_type === 'switch'" class="flex items-center justify-between rounded-lg border border-border px-3 py-2 bg-background">
                  <span class="text-sm text-muted-foreground">状态</span>
                  <input
                    type="checkbox"
                    class="h-4 w-4"
                    :checked="Boolean(getSystemDisplayValue(field))"
                    @change="onSystemSwitchChange(field, $event.target.checked)"
                  />
                </div>

                <select
                  v-else-if="field.input_type === 'select'"
                  :value="selectInputValue(field)"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @change="onSystemSelectChange(field, $event.target.value)"
                >
                  <option
                    v-for="option in field.options"
                    :key="`${field.key}-${optionKey(option.value)}`"
                    :value="optionKey(option.value)"
                  >
                    {{ option.label }}
                  </option>
                </select>

                <input
                  v-else-if="field.input_type === 'number'"
                  type="number"
                  :value="numberInputValue(field)"
                  :min="field.min ?? undefined"
                  :max="field.max ?? undefined"
                  :step="field.step ?? undefined"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="onSystemNumberInput(field, $event.target.value)"
                />

                <input
                  v-else
                  type="text"
                  :value="textInputValue(field)"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="onSystemTextInput(field, $event.target.value)"
                />

                <div class="flex items-center justify-between gap-2 text-xs">
                  <span class="text-muted-foreground">
                    当前生效：{{ formatSystemValue(getSystemEffectiveValue(field.key), field) }}
                  </span>
                  <button
                    v-if="hasSystemOverride(field.key)"
                    type="button"
                    class="px-2 py-1 rounded border border-input hover:bg-accent"
                    @click="clearSystemOverride(field.key)"
                  >
                    清除覆盖
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <p v-if="systemOverridesError" class="text-sm text-destructive">{{ systemOverridesError }}</p>

        <div class="flex flex-wrap items-center justify-between gap-3">
          <p class="text-xs text-muted-foreground">
            系统参数会优先采用“覆盖值”；清除覆盖后自动回退到默认值。
          </p>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent disabled:opacity-50"
              :disabled="settingsStore.savingSystem || Object.keys(systemAdvanced.overrides || {}).length === 0"
              @click="resetSystemAdvancedSettings"
            >
              恢复系统默认
            </button>
            <button
              type="button"
              class="px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-50"
              :disabled="settingsStore.savingSystem || !settingsStore.systemAdvancedDirty"
              @click="saveSystemAdvancedSettings"
            >
              {{ settingsStore.savingSystem ? '保存中…' : '保存系统参数' }}
            </button>
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
      advanced-label="高级学习参数"
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">手动参考片段数量（可空）</label>
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">手动候选范围（可空）</label>
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
            当手动值为空时，系统会自动按预设估算参考片段数量与候选范围。
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
      v-if="selectedKbId && advancedDiagnosticsOpen"
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">参考片段数量覆盖（可空）</label>
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">候选范围覆盖（可空）</label>
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

    <div
      v-else-if="!selectedKbId"
      class="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground"
    >
      当前未选择知识库。先在侧边栏或上传页选择一个知识库后，即可配置该知识库覆盖设置。
    </div>

    <div v-else class="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">
      知识库单独设置已隐藏。展开“高级设置与诊断”后可按知识库微调。
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { SlidersHorizontal, ShieldCheck } from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { useAppKnowledgeScope } from '../composables/useAppKnowledgeScope'
import { useSettingsStore } from '../stores/settings'
import { UX_TEXT } from '../constants/uxText'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import KbSelector from '../components/context/KbSelector.vue'
import SettingsPanel from '../components/settings/SettingsPanel.vue'

const { showToast } = useToast()
const { appContext, resolvedUserId, kbs, selectedKbId } = useAppKnowledgeScope()
const settingsStore = useSettingsStore()

const userAdvancedOpen = ref(false)
const kbAdvancedOpen = ref(false)
const advancedDiagnosticsOpen = ref(false)
const lastUserActionError = ref('')
const lastKbActionError = ref('')
const systemOverridesError = ref('')

const selectedKbName = computed(() => {
  const kb = kbs.value.find((item) => item.id === selectedKbId.value)
  return kb?.name || ''
})

const systemStatus = computed(() => settingsStore.systemStatus)
const systemAdvanced = computed(() => settingsStore.systemAdvanced)
const systemAdvancedDraft = computed(() => settingsStore.systemAdvancedDraft || {})
const systemSchemaGroups = computed(() => systemAdvanced.value?.schema?.groups || [])
const systemSchemaFields = computed(() => systemAdvanced.value?.schema?.fields || [])
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

function providerSourceLabel(value) {
  if (value === 'auto') return '自动'
  if (value === 'manual') return '手动'
  return '—'
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

function buildSystemOverridesPatch(current, next) {
  const patch = {}
  for (const key of Object.keys(current || {})) {
    if (!Object.prototype.hasOwnProperty.call(next || {}, key)) {
      patch[key] = null
    }
  }
  for (const [key, value] of Object.entries(next || {})) {
    patch[key] = value
  }
  return patch
}

function fieldsForGroup(groupId) {
  return systemSchemaFields.value.filter((field) => field.group === groupId)
}

function hasSystemOverride(key) {
  return Object.prototype.hasOwnProperty.call(systemAdvancedDraft.value || {}, key)
}

function getSystemEffectiveValue(key) {
  return systemAdvanced.value?.effective?.[key]
}

function getSystemDisplayValue(field) {
  if (hasSystemOverride(field.key)) {
    return systemAdvancedDraft.value[field.key]
  }
  return getSystemEffectiveValue(field.key)
}

function setSystemDraft(next) {
  settingsStore.setSystemAdvancedDraft(next || {})
}

function setSystemOverrideValue(key, value) {
  const next = { ...(systemAdvancedDraft.value || {}) }
  next[key] = value
  setSystemDraft(next)
}

function clearSystemOverride(key) {
  const next = { ...(systemAdvancedDraft.value || {}) }
  delete next[key]
  setSystemDraft(next)
}

function optionKey(value) {
  return JSON.stringify(value)
}

function selectInputValue(field) {
  const current = getSystemDisplayValue(field)
  const key = optionKey(current)
  if ((field.options || []).some((option) => optionKey(option.value) === key)) {
    return key
  }
  const first = (field.options || [])[0]
  return first ? optionKey(first.value) : ''
}

function onSystemSelectChange(field, rawValue) {
  const resolved = (field.options || []).find((option) => optionKey(option.value) === rawValue)
  if (!resolved) return
  setSystemOverrideValue(field.key, resolved.value)
}

function numberInputValue(field) {
  const value = getSystemDisplayValue(field)
  if (value === null || value === undefined) return ''
  return String(value)
}

function onSystemNumberInput(field, rawValue) {
  const text = String(rawValue ?? '').trim()
  if (!text) {
    if (field.nullable) clearSystemOverride(field.key)
    return
  }
  const num = Number(text)
  if (!Number.isFinite(num)) return
  const isIntegerField = Number.isInteger(Number(field.step)) && Number(field.step) >= 1
  const normalized = isIntegerField ? Math.round(num) : num
  setSystemOverrideValue(field.key, normalized)
}

function textInputValue(field) {
  const value = getSystemDisplayValue(field)
  if (value === null || value === undefined) return ''
  return String(value)
}

function onSystemTextInput(field, rawValue) {
  const value = String(rawValue ?? '')
  if (!value && field.nullable) {
    clearSystemOverride(field.key)
    return
  }
  setSystemOverrideValue(field.key, value)
}

function onSystemSwitchChange(field, checked) {
  setSystemOverrideValue(field.key, Boolean(checked))
}

function formatSystemValue(value, field) {
  if (value === null || value === undefined || value === '') return '（空）'
  if (field?.input_type === 'switch') return value ? '开启' : '关闭'
  return String(value)
}

async function saveSystemAdvancedSettings() {
  systemOverridesError.value = ''
  try {
    const patch = buildSystemOverridesPatch(
      systemAdvanced.value?.overrides || {},
      systemAdvancedDraft.value || {},
    )
    await settingsStore.saveSystemAdvanced(patch)
    showToast('系统高级参数已保存', 'success')
  } catch (err) {
    systemOverridesError.value = err?.message || '保存失败'
  }
}

async function resetSystemAdvancedSettings() {
  systemOverridesError.value = ''
  try {
    await settingsStore.resetSystemAdvanced()
    showToast('系统高级参数已恢复默认', 'success')
  } catch (err) {
    systemOverridesError.value = err?.message || '重置失败'
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

watch(
  () => systemAdvanced.value?.overrides,
  (next) => {
    settingsStore.setSystemAdvancedDraft(next || {})
  },
  { deep: true, immediate: true },
)
</script>
