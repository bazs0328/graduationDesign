<template>
  <div class="space-y-5 md:space-y-6 max-w-6xl mx-auto">
    <section class="workspace-toolbar p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="space-y-2">
          <div class="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            <SlidersHorizontal class="w-3.5 h-3.5" />
            配置
          </div>
          <h1 class="text-2xl font-bold tracking-tight">{{ UI_NAMING.settings }}</h1>
          <p class="workspace-copy max-w-3xl">
            模型接入、学习偏好与诊断；日常使用时主要关注模型接入和学习偏好。
          </p>
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div class="workspace-card-soft px-3 py-2">
            <div class="text-muted-foreground">当前资料库</div>
            <div class="font-semibold truncate max-w-[180px]">{{ selectedKbName || '未选择' }}</div>
          </div>
          <div class="workspace-card-soft px-3 py-2">
            <div class="text-muted-foreground">状态</div>
            <div class="font-semibold" :class="settingsStore.error ? 'text-amber-600' : 'text-green-600'">
              {{ settingsStore.error ? '已回退到默认配置' : '配置可用' }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <div class="workspace-card-soft inline-flex w-full max-w-fit gap-1 p-1">
      <button
        type="button"
        class="px-4 py-2 rounded-xl text-sm font-semibold transition-colors"
        :class="settingsTab === 'provider' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent'"
        @click="settingsTab = 'provider'"
      >
        模型接入
      </button>
      <button
        type="button"
        class="px-4 py-2 rounded-xl text-sm font-semibold transition-colors"
        :class="settingsTab === 'preferences' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent'"
        @click="settingsTab = 'preferences'"
      >
        学习偏好
      </button>
      <button
        type="button"
        class="px-4 py-2 rounded-xl text-sm font-semibold transition-colors"
        :class="settingsTab === 'advanced' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent'"
        @click="settingsTab = 'advanced'"
      >
        高级诊断
      </button>
    </div>

    <section v-if="settingsTab === 'provider'" class="space-y-4">
      <div class="workspace-card p-5 sm:p-6 space-y-5">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="space-y-2">
            <div class="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              模型接入配置
            </div>
            <h2 class="text-xl font-black tracking-tight">模型服务配置</h2>
            <p class="text-sm text-muted-foreground max-w-3xl leading-relaxed">
              配置会安全保存在本地持久化文件中，无需手动修改 `.env`。完成配置后即可使用摘要、问答和测验。
            </p>
          </div>
          <div class="rounded-2xl border border-border bg-background/70 px-4 py-3 text-sm space-y-1 min-w-[220px]">
            <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">当前状态</div>
            <div class="font-semibold" :class="providerFeaturesReady ? 'text-green-600' : 'text-amber-700'">
              {{ providerFeaturesReady ? '模型接入已就绪' : '仍需完成基础配置' }}
            </div>
            <div class="text-xs text-muted-foreground">
              对话：{{ providerSetup?.current_llm_provider || '未配置' }} · 向量：{{ providerSetup?.current_embedding_provider || '未配置' }}
            </div>
          </div>
        </div>

        <div
          v-if="Array.isArray(systemStatus?.notices) && systemStatus.notices.length > 0"
          class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900 space-y-2"
        >
          <p class="font-semibold">检测到旧配置，系统已自动兼容处理</p>
          <ul class="list-disc pl-5 space-y-1">
            <li v-for="notice in systemStatus.notices" :key="notice">
              {{ notice }}
            </li>
          </ul>
        </div>

        <div class="space-y-5">
          <div v-if="!providerFeaturesReady" class="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-4 space-y-2">
            <p class="text-sm font-semibold text-amber-900">继续使用前，请先完成模型接入配置</p>
            <p class="text-sm text-amber-900/80 leading-relaxed">
              当前仍缺少部分基础配置。完成后，摘要、问答和测验功能会自动恢复可用。
            </p>
            <p v-if="providerMissingSummary" class="text-xs text-amber-800">
              缺少项：{{ providerMissingSummary }}
            </p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">对话模型提供商</label>
              <select
                :value="providerDraft.llm_provider"
                class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                @change="setProviderRoot('llm_provider', $event.target.value)"
              >
                <option v-for="option in llmProviderOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">向量模型提供商</label>
              <select
                :value="providerDraft.embedding_provider"
                class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                @change="setProviderRoot('embedding_provider', $event.target.value)"
              >
                <option v-for="option in embeddingProviderOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>
          </div>

          <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <article class="rounded-2xl border border-border bg-background/50 p-4 space-y-4">
              <div class="space-y-1">
                <div class="flex items-center justify-between gap-2">
                  <h3 class="text-base font-bold tracking-tight">DeepSeek</h3>
                  <span class="text-[10px] font-semibold px-2 py-1 rounded-full border" :class="providerBadgeClass(providerDraft.llm_provider === 'deepseek')">
                    {{ providerDraft.llm_provider === 'deepseek' ? '当前使用' : '可配置' }}
                  </span>
                </div>
                <p class="text-xs text-muted-foreground">适合作为对话模型服务；当前不作为官方向量服务来源展示。</p>
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">API 密钥</label>
                <div v-if="providerDraft.deepseek.api_key_configured && !providerDraft.deepseek.editing_api_key && !providerDraft.deepseek.clear_api_key" class="rounded-xl border border-border bg-card px-3 py-3 space-y-3">
                  <p class="text-sm font-medium">已保存 {{ providerDraft.deepseek.api_key_masked || '••••' }}</p>
                  <div class="flex flex-wrap gap-2">
                    <button type="button" class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent" @click="beginProviderKeyEdit('deepseek')">更换密钥</button>
                    <button type="button" class="px-3 py-2 rounded-lg border border-amber-300 text-sm font-semibold text-amber-700 hover:bg-amber-50" @click="clearProviderKey('deepseek')">清除密钥</button>
                  </div>
                </div>
                <input
                  v-else
                  type="password"
                  :value="providerDraft.deepseek.api_key_input"
                  placeholder="输入 DeepSeek API 密钥"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="updateProviderSection('deepseek', { api_key_input: $event.target.value, clear_api_key: false })"
                />
                <p v-if="providerDraft.deepseek.clear_api_key" class="text-xs text-amber-700">
                  保存后将清除当前 DeepSeek API 密钥。
                </p>
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">服务地址</label>
                <input
                  type="text"
                  :value="providerDraft.deepseek.base_url"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="updateProviderSection('deepseek', { base_url: $event.target.value })"
                />
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">对话模型</label>
                <input
                  type="text"
                  :value="providerDraft.deepseek.model"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="updateProviderSection('deepseek', { model: $event.target.value })"
                />
              </div>

            </article>

            <article class="rounded-2xl border border-border bg-background/50 p-4 space-y-4">
              <div class="space-y-1">
                <div class="flex items-center justify-between gap-2">
                  <h3 class="text-base font-bold tracking-tight">Qwen</h3>
                  <span class="text-[10px] font-semibold px-2 py-1 rounded-full border" :class="providerBadgeClass(providerDraft.llm_provider === 'qwen' || providerDraft.embedding_provider === 'qwen')">
                    {{ providerDraft.llm_provider === 'qwen' || providerDraft.embedding_provider === 'qwen' ? '当前使用' : '可配置' }}
                  </span>
                </div>
                <p class="text-xs text-muted-foreground">适合作为对话模型服务；DashScope 向量服务会复用这里的 API 密钥。</p>
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">API 密钥</label>
                <div v-if="providerDraft.qwen.api_key_configured && !providerDraft.qwen.editing_api_key && !providerDraft.qwen.clear_api_key" class="rounded-xl border border-border bg-card px-3 py-3 space-y-3">
                  <p class="text-sm font-medium">已保存 {{ providerDraft.qwen.api_key_masked || '••••' }}</p>
                  <div class="flex flex-wrap gap-2">
                    <button type="button" class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent" @click="beginProviderKeyEdit('qwen')">更换密钥</button>
                    <button type="button" class="px-3 py-2 rounded-lg border border-amber-300 text-sm font-semibold text-amber-700 hover:bg-amber-50" @click="clearProviderKey('qwen')">清除密钥</button>
                  </div>
                </div>
                <input
                  v-else
                  type="password"
                  :value="providerDraft.qwen.api_key_input"
                  placeholder="输入 Qwen / DashScope API 密钥"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="updateProviderSection('qwen', { api_key_input: $event.target.value, clear_api_key: false })"
                />
                <p v-if="providerDraft.qwen.clear_api_key" class="text-xs text-amber-700">
                  保存后将清除当前 Qwen / DashScope API 密钥。
                </p>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div class="space-y-2">
                  <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">地区预设</label>
                  <select
                    :value="providerDraft.qwen.region"
                    class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                    @change="applyRegionPreset('qwen', $event.target.value)"
                  >
                    <option v-for="preset in qwenRegionOptions" :key="preset.id" :value="preset.id">
                      {{ preset.label }}
                    </option>
                  </select>
                </div>
                <div class="space-y-2">
                  <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">对话模型</label>
                  <input
                    type="text"
                    :value="providerDraft.qwen.model"
                    class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                    @input="updateProviderSection('qwen', { model: $event.target.value })"
                  />
                </div>
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">服务地址</label>
                <input
                  type="text"
                  :value="providerDraft.qwen.base_url"
                  :disabled="providerDraft.qwen.region !== 'custom'"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-accent/40 disabled:text-muted-foreground"
                  @input="updateProviderSection('qwen', { base_url: $event.target.value })"
                />
              </div>

              <div v-if="providerDraft.embedding_provider === 'qwen'" class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">向量模型</label>
                <input
                  type="text"
                  :value="providerDraft.qwen.embedding_model"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="updateProviderSection('qwen', { embedding_model: $event.target.value })"
                />
              </div>
            </article>

            <article class="rounded-2xl border border-border bg-background/50 p-4 space-y-4">
              <div class="space-y-1">
                <div class="flex items-center justify-between gap-2">
                  <h3 class="text-base font-bold tracking-tight">DashScope</h3>
                  <span class="text-[10px] font-semibold px-2 py-1 rounded-full border" :class="providerBadgeClass(providerDraft.embedding_provider === 'dashscope')">
                    {{ providerDraft.embedding_provider === 'dashscope' ? '当前使用' : '可配置' }}
                  </span>
                </div>
                <p class="text-xs text-muted-foreground">仅提供向量服务，复用 Qwen 区域中的 API 密钥。</p>
              </div>

              <div class="rounded-xl border border-border bg-card px-3 py-3 text-sm text-muted-foreground">
                DashScope 不单独填写 API 密钥，将复用上方 Qwen 配置中的密钥。
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">地区预设</label>
                <select
                  :value="providerDraft.dashscope.region"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @change="applyRegionPreset('dashscope', $event.target.value)"
                >
                  <option v-for="preset in dashscopeRegionOptions" :key="preset.id" :value="preset.id">
                    {{ preset.label }}
                  </option>
                </select>
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">服务地址</label>
                <input
                  type="text"
                  :value="providerDraft.dashscope.base_url"
                  :disabled="providerDraft.dashscope.region !== 'custom'"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary disabled:bg-accent/40 disabled:text-muted-foreground"
                  @input="updateProviderSection('dashscope', { base_url: $event.target.value })"
                />
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">向量模型</label>
                <input
                  type="text"
                  :value="providerDraft.dashscope.embedding_model"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                  @input="updateProviderSection('dashscope', { embedding_model: $event.target.value })"
                />
              </div>
            </article>
          </div>

          <div class="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-border bg-background/50 px-4 py-4">
            <div class="space-y-1">
              <p class="text-sm font-semibold">保存后立即生效</p>
              <p class="text-xs text-muted-foreground">
                配置会保存到本地持久化文件中，页面仅显示掩码，不会回显 API 密钥明文。
              </p>
              <p v-if="providerTestResult" class="text-xs" :class="providerTestResult.ok ? 'text-green-700' : 'text-destructive'">
                {{ providerTestResult.message }}
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent disabled:opacity-50"
                :disabled="settingsStore.providerTesting"
                @click="runProviderConnectionTest"
              >
                {{ settingsStore.providerTesting ? '测试中…' : '测试连接' }}
              </button>
              <button
                type="button"
                class="px-3 py-2 rounded-lg border border-input text-sm font-semibold hover:bg-accent disabled:opacity-50"
                :disabled="settingsStore.providerSaving || !settingsStore.providerDirty"
                @click="settingsStore.discardProviderDraft()"
              >
                放弃修改
              </button>
              <button
                type="button"
                class="px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-50"
                :disabled="settingsStore.providerSaving || !settingsStore.providerDirty"
                @click="saveProviderSettings"
              >
                {{ settingsStore.providerSaving ? '保存中…' : '保存配置' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="settingsTab === 'advanced'" class="space-y-4">
      <div class="workspace-card p-4 sm:p-5">
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
              设定值：{{ systemStatus?.llm_provider_configured || '—' }} · 来源：{{ providerSourceLabel(systemStatus?.llm_provider_source) }}
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm text-muted-foreground">{{ UX_TEXT.vectorModelLabel }}</span>
              <span class="px-2 py-1 rounded-full bg-secondary text-secondary-foreground text-xs font-semibold">
                {{ systemStatus?.embedding_provider || '—' }}
              </span>
            </div>
            <div class="text-[11px] text-muted-foreground">
              设定值：{{ systemStatus?.embedding_provider_configured || '—' }} · 来源：{{ providerSourceLabel(systemStatus?.embedding_provider_source) }}
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-border bg-card p-4 space-y-3 shadow-sm">
          <div class="text-xs font-bold uppercase tracking-widest text-muted-foreground">检索策略默认值（高级）</div>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2">
              <div class="text-xs text-muted-foreground">{{ UX_TEXT.referenceCountLabel }}</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults?.qa_top_k ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2">
              <div class="text-xs text-muted-foreground">{{ UX_TEXT.candidateRangeLabel }}</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults?.qa_fetch_k ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-border bg-background/50 px-3 py-2 col-span-2">
              <div class="text-xs text-muted-foreground">{{ UX_TEXT.retrievalStrategyLabel }}</div>
              <div class="font-semibold">{{ systemStatus?.qa_defaults?.rag_mode ?? '—' }}</div>
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
                {{ secretStatusLabel(key) }}: {{ ok ? 'OK' : '未配置' }}
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
              这里的值会在系统默认值之上应用本地覆盖并持久化保存，适合在页面内集中维护常用设置。
            </p>
          </div>
          <div class="text-xs text-muted-foreground space-y-1">
            <div>可编辑键：{{ systemAdvanced.editableKeys.length }} 项</div>
            <div>当前覆盖：{{ Object.keys(systemAdvancedDraft || {}).length }} 项</div>
          </div>
        </div>

        <div v-if="systemSchemaGroups.length === 0" class="rounded-xl border border-dashed border-border bg-background/40 p-4 text-sm text-muted-foreground">
          暂时未获取到系统参数说明，请稍后刷新重试。
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
      v-if="settingsTab === 'preferences'"
      title="用户默认设置"
      description="这组设置会作为你在所有学习资料库中的默认体验参数。"
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
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">检索深度</label>
          <select
            :value="userDraft.qa.retrieval_preset"
            class="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            @change="updateUserSection('qa', { retrieval_preset: $event.target.value })"
          >
            <option value="fast">快速（参考更少）</option>
            <option value="balanced">均衡（推荐）</option>
            <option value="deep">深入（参考更广）</option>
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">兜底参考片段数量（可空）</label>
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">兜底候选范围（可空）</label>
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
            系统会优先根据问题类型和资料范围动态调整；只有动态策略关闭或不可用时，才使用这些兜底值。
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
      v-if="settingsTab === 'preferences' && selectedKbId"
      title="当前资料库覆盖设置"
      description="只覆盖当前资料库的问答与测验偏好；留空表示跟随用户默认设置。"
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
            placeholder="请选择资料库"
            :loading="appContext.kbsLoading"
            @update:model-value="selectedKbId = $event"
          />
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="space-y-2">
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">回答风格覆盖</label>
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
          <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">检索深度覆盖</label>
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">兜底参考片段数量覆盖（可空）</label>
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
            <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">兜底候选范围覆盖（可空）</label>
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
          留空表示跟随用户默认；当动态检索关闭或不可用时，系统会回退到这里对应的默认/预设值。
        </div>
      </template>
    </SettingsPanel>

    <div
      v-else-if="settingsTab === 'preferences' && !selectedKbId"
      class="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground"
    >
      当前未选择资料库。先在侧边栏或上传页选择一个资料库后，即可配置该资料库覆盖设置。
    </div>

    <div v-else-if="settingsTab === 'preferences'" class="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">
      资料库单独设置已隐藏。展开“高级设置与诊断”后可按资料库微调。
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
import { UI_NAMING } from '../constants/uiNaming'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import KbSelector from '../components/context/KbSelector.vue'
import SettingsPanel from '../components/settings/SettingsPanel.vue'

const { showToast } = useToast()
const { appContext, resolvedUserId, kbs, selectedKbId } = useAppKnowledgeScope()
const settingsStore = useSettingsStore()

const userAdvancedOpen = ref(false)
const kbAdvancedOpen = ref(false)
const advancedDiagnosticsOpen = ref(false)
const settingsTab = ref('provider')
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
const providerConfig = computed(() => settingsStore.providerConfig)
const providerDraft = computed(() => settingsStore.providerDraft)
const providerSetup = computed(() => settingsStore.providerSetup)
const providerTestResult = computed(() => settingsStore.providerTestResult)
const providerFeaturesReady = computed(() => settingsStore.llmFeaturesReady)
const llmProviderOptions = computed(() => (
  (providerConfig.value?.supportedLlmProviders || ['auto', 'deepseek', 'qwen']).map((value) => ({
    value,
    label: providerOptionLabel(value),
  }))
))
const embeddingProviderOptions = computed(() => (
  (providerConfig.value?.supportedEmbeddingProviders || ['auto', 'qwen', 'dashscope']).map((value) => ({
    value,
    label: providerOptionLabel(value),
  }))
))
const qwenRegionOptions = computed(() => providerConfig.value?.regionPresets?.qwen || [])
const dashscopeRegionOptions = computed(() => providerConfig.value?.regionPresets?.dashscope || [])
const providerMissingSummary = computed(() => (
  (providerSetup.value?.missing || [])
    .map((item) => providerMissingLabel(item))
    .filter(Boolean)
    .join('、')
))

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

function providerOptionLabel(value) {
  if (value === 'auto') return '自动选择'
  if (value === 'deepseek') return 'DeepSeek'
  if (value === 'qwen') return 'Qwen'
  if (value === 'dashscope') return 'DashScope'
  return String(value || '—')
}

function providerMissingLabel(value) {
  const labels = {
    'deepseek.api_key': 'DeepSeek API 密钥',
    'deepseek.base_url': 'DeepSeek 服务地址',
    'deepseek.model': 'DeepSeek 对话模型',
    'qwen.api_key': 'Qwen API 密钥',
    'qwen.base_url': 'Qwen 服务地址',
    'qwen.model': 'Qwen 对话模型',
    'qwen.embedding_model': 'Qwen 向量模型',
    'dashscope.base_url': 'DashScope 服务地址',
    'dashscope.embedding_model': 'DashScope 向量模型',
  }
  return labels[value] || value
}

function secretStatusLabel(value) {
  const labels = {
    deepseek_api_key: 'DeepSeek API 密钥',
    qwen_api_key: 'Qwen API 密钥',
    auth_secret_key_configured: '系统认证密钥',
  }
  return labels[value] || value
}

function providerBadgeClass(active) {
  return active
    ? 'border-primary/30 bg-primary/10 text-primary'
    : 'border-border bg-background text-muted-foreground'
}

function setProviderRoot(key, value) {
  settingsStore.setProviderDraft({ [key]: value })
}

function updateProviderSection(section, patch) {
  settingsStore.setProviderDraft({ [section]: patch })
}

function beginProviderKeyEdit(section) {
  updateProviderSection(section, {
    editing_api_key: true,
    clear_api_key: false,
    api_key_input: '',
  })
}

function clearProviderKey(section) {
  updateProviderSection(section, {
    editing_api_key: false,
    clear_api_key: true,
    api_key_input: '',
  })
}

function applyRegionPreset(section, regionId) {
  const presetOptions = section === 'qwen' ? qwenRegionOptions.value : dashscopeRegionOptions.value
  const preset = presetOptions.find((item) => item.id === regionId)
  if (!preset) return
  const patch = { region: regionId }
  if (regionId !== 'custom' && preset.base_url) {
    patch.base_url = preset.base_url
  }
  updateProviderSection(section, patch)
}

const providerTestTarget = computed(() => {
  if (['deepseek', 'qwen'].includes(providerDraft.value?.llm_provider)) return 'llm'
  if (['qwen', 'dashscope'].includes(providerDraft.value?.embedding_provider)) return 'embedding'
  return 'auto'
})

async function saveProviderSettings() {
  try {
    await settingsStore.saveProviderConfig()
    showToast('模型接入配置已保存', 'success')
  } catch {
    // global error toast handled by api layer
  }
}

async function runProviderConnectionTest() {
  try {
    const result = await settingsStore.testProviderConfig({ target: providerTestTarget.value })
    showToast(result?.message || '连接测试成功', 'success')
  } catch {
    // global error toast handled by api layer
  }
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
    showToast('资料库覆盖设置已保存', 'success')
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
    showToast('资料库覆盖设置已重置', 'success')
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
