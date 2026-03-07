<template>
  <div class="min-h-full flex flex-col max-w-6xl mx-auto space-y-5 md:space-y-6">
    <ContextSummaryBar
      :kb-name="selectedKb?.name || ''"
      :doc-name="selectedDoc?.filename || ''"
      :focus="effectiveQaFocusContext"
      :source-tag="effectiveQaFocusContext ? (entryFocusContext ? '学习路径上下文' : '问答聚焦上下文') : '当前资料范围'"
      subtitle="回答和引用会优先参考这里展示的资料范围。"
      compact
      tone="info"
    >
      <div
        v-if="entryFocusContext"
        class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
      >
        <span class="workspace-chip">
          <span class="text-muted-foreground">当前学习目标</span>
          <span class="font-semibold">{{ effectiveQaFocusContext }}</span>
        </span>
        <span v-if="showLearningPathMultiDocHint">
          该学习目标可能关联同一资料库中的多个文档来源。
        </span>
      </div>
    </ContextSummaryBar>
    <div class="flex-1 flex flex-col lg:flex-row gap-5 lg:gap-6 min-h-0">
      <!-- Left: Chat Interface -->
      <section data-testid="qa-learning-dialogue-card" class="flex-1 min-h-0 flex flex-col workspace-card overflow-hidden">
        <!-- Header -->
        <div class="p-3 sm:p-4 border-b border-border/70 flex items-center justify-between gap-3 bg-card/60">
          <div class="flex items-center gap-3">
            <MessageSquare class="w-6 h-6 text-primary" />
            <h2 class="text-lg sm:text-xl font-bold">{{ UI_NAMING.learningDialogue }}</h2>
          </div>
          <div class="flex items-center gap-1 sm:gap-2">
            <button
              class="lg:hidden px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-border hover:bg-accent transition-colors"
              @click="qaSidebarOpen = !qaSidebarOpen"
            >
              {{ qaSidebarOpen ? '收起资料面板' : '资料面板' }}
            </button>
          </div>
        </div>
        <div class="px-4 py-3 border-b border-border/70 bg-background/55">
          <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
            <div class="space-y-1">
              <p class="workspace-label text-primary/80">当前状态</p>
              <p class="text-sm font-semibold">{{ qaFlowPrimaryText }}</p>
              <p class="text-xs text-muted-foreground">
                {{ qaFlowSecondaryText }}
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2 sm:justify-end">
              <span
                v-if="qaFlow.usedFallback"
                class="px-2 py-1 rounded-full border border-amber-300 bg-amber-50 text-amber-700 text-[10px] font-semibold tracking-wide"
              >
                已自动回退
              </span>
              <div class="inline-flex rounded-lg border border-border bg-background p-1 shadow-sm">
                <button
                  class="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
                  :class="qaMode === 'normal' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'"
                  :disabled="busy.qa"
                  @click="qaMode = 'normal'"
                >
                  标准回答
                </button>
                <button
                  class="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
                  :class="qaMode === 'explain' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'"
                  :disabled="busy.qa"
                  @click="qaMode = 'explain'"
                >
                  分步讲解
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Messages -->
        <div class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 sm:space-y-6" ref="scrollContainer">
          <EmptyState
            v-if="qaMessages.length === 0"
            class="h-full max-w-lg mx-auto"
            :icon="Sparkles"
            :title="qaEmptyTitle"
            :description="qaEmptyDescription"
            :hint="qaEmptyHint"
            size="lg"
            :primary-action="qaEmptyPrimaryAction"
            @primary="handleQaEmptyPrimary"
          />
          
          <div v-for="(msg, index) in qaMessages" :key="index" class="flex flex-col" :class="msg.role === 'question' ? 'items-end' : 'items-start'">
            <div 
              class="max-w-[92%] sm:max-w-[85%] p-3 sm:p-4 rounded-2xl shadow-sm"
              :class="msg.role === 'question' ? 'bg-primary text-primary-foreground rounded-tr-none' : 'bg-accent text-accent-foreground rounded-tl-none'"
            >
              <div class="flex items-center gap-2 mb-1 opacity-70 text-[10px] font-bold uppercase tracking-wider">
                <component :is="msg.role === 'question' ? User : Bot" class="w-3 h-3" />
                {{ msg.role === 'question' ? '你' : '学习助手' }}
                <span
                  v-if="msg.role !== 'question' && msg.abilityLevel"
                  class="ml-auto px-1.5 py-0.5 rounded-full border text-[9px] font-semibold normal-case tracking-normal"
                  :class="getLevelMeta(msg.abilityLevel).badgeClass"
                >
                  {{ getLevelMeta(msg.abilityLevel).text }}
                </span>
              </div>
              <p v-if="msg.role === 'question'" class="text-sm leading-relaxed whitespace-pre-wrap">{{ msg.content }}</p>
              <div v-else>
                <div
                  v-if="msg.status && msg.status !== 'done'"
                  class="mb-2 flex flex-wrap items-center gap-2 text-[10px]"
                >
                  <span
                    class="px-1.5 py-0.5 rounded-full border font-semibold normal-case tracking-normal"
                    :class="qaMessageStatusBadgeClass(msg)"
                  >
                    {{ qaMessageStatusText(msg) }}
                  </span>
                  <span v-if="msg.errorCode" class="opacity-60">{{ msg.errorCode }}</span>
                </div>
                <div
                  v-if="shouldRenderExplainCards(msg)"
                  class="space-y-3"
                >
                  <div class="flex flex-wrap items-center gap-2 text-[10px]">
                    <span class="px-1.5 py-0.5 rounded-full border border-primary/30 bg-primary/10 text-primary font-semibold">
                      讲解模式
                    </span>
                    <span
                      v-if="msg.explainIncomplete"
                      class="px-1.5 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700 font-semibold"
                    >
                      结构容错展示
                    </span>
                  </div>
                  <section
                    v-for="section in msg.explainSections"
                    :key="section.key"
                    class="rounded-xl border border-accent-foreground/10 bg-background/35 p-3"
                  >
                    <p class="text-[10px] font-bold uppercase tracking-widest opacity-60">
                      {{ section.title }}
                    </p>
                    <div
                      class="mt-2 qa-markdown markdown-content"
                      v-html="renderMarkdown(section.content || '（该部分暂无可解析内容）')"
                    ></div>
                  </section>
                  <p
                    v-if="msg.streaming"
                    class="mt-1 text-sm leading-relaxed"
                  >
                    <span class="qa-stream-cursor" aria-hidden="true"></span>
                  </p>
                </div>
                <div
                  v-else-if="msg.content && msg.content.trim()"
                  class="qa-markdown markdown-content"
                  v-html="renderMarkdown(msg.content)"
                ></div>
                <p
                  v-else
                  class="text-sm leading-relaxed opacity-70 italic flex items-center gap-1"
                >
                  {{ msg.streaming ? '正在生成回答…' : '暂无回答内容' }}
                  <span v-if="msg.streaming" class="qa-stream-cursor" aria-hidden="true"></span>
                </p>
                <p
                  v-if="msg.streaming && msg.content && msg.content.trim()"
                  class="mt-1 text-sm leading-relaxed"
                >
                  <span class="qa-stream-cursor" aria-hidden="true"></span>
                </p>
              </div>
              
              <!-- Sources -->
              <div v-if="msg.sources && msg.sources.length" class="mt-4 pt-3 border-t border-accent-foreground/10 space-y-2">
                <p class="text-[10px] font-bold uppercase opacity-50">参考来源（{{ msg.sources.length }}）</p>
                <p v-if="selectedKbId" class="text-[10px] opacity-60">
                  来源可能来自该资料库下多个文档片段。
                </p>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="(source, sIdx) in msg.sources"
                    :key="sIdx"
                    class="text-[10px] bg-background/50 px-2 py-1 rounded-md flex items-center gap-1.5 border border-accent-foreground/5 hover:border-primary/40 hover:text-primary transition-colors"
                    @click="openQaSource(source)"
                  >
                    <FileText class="w-3 h-3 text-primary" />
                    <span class="font-medium truncate max-w-[120px]">{{ source.source }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="p-3 sm:p-4 border-t border-border/70 bg-card/55 space-y-4">
          <div class="flex flex-col sm:flex-row gap-2">
            <textarea
              v-model="qaInput"
              @keydown.enter.prevent="askQuestion"
              :placeholder="effectiveQaFocusContext ? `关于「${effectiveQaFocusContext}」，你想了解什么？` : '在此输入你的问题…'"
              class="flex-1 bg-background border border-input rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-primary resize-none h-[88px] sm:h-[52px]"
              :disabled="!selectedKbId || busy.qa || qaActionBlocked"
            ></textarea>
            <button
              @click="askQuestion"
              class="bg-primary text-primary-foreground p-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center sm:w-auto w-full"
              :disabled="!selectedKbId || !qaInput.trim() || busy.qa || qaActionBlocked"
            >
              <Send class="w-6 h-6" />
            </button>
          </div>
          <p v-if="!selectedKbId" class="text-[10px] text-destructive mt-1 text-center font-bold uppercase tracking-widest">
            请先在右侧选择资料范围
          </p>
          <p v-else-if="qaActionBlocked" class="text-[10px] text-amber-700 mt-1 text-center font-bold uppercase tracking-widest">
            先完成模型接入配置再开始提问
          </p>
          <AdvancedPanel
            title="高级选项"
            eyebrow=""
            description="不需要每次调整的选项统一放在这里，日常提问时通常无需展开。"
            :default-open="qaAdvancedDefaultOpen"
            content-class="max-h-[42vh] overflow-y-auto pr-1"
          >
            <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
              <button
                type="button"
                class="inline-flex items-center justify-between gap-2 rounded-xl border px-3 py-3 text-sm font-semibold transition-colors"
                :class="qaAutoAdapt ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border bg-background text-muted-foreground hover:bg-accent'"
                :disabled="busy.qa"
                @click="setQaAutoAdapt(!qaAutoAdapt)"
              >
                <span>{{ qaAutoAdapt ? '自适应开启' : '自适应关闭' }}</span>
                <span class="text-xs">{{ qaAutoAdapt ? '按画像动态调整' : '固定回答策略' }}</span>
              </button>
              <button
                type="button"
                class="rounded-xl border border-border bg-background px-3 py-3 text-sm font-semibold hover:bg-accent transition-colors disabled:opacity-50"
                :disabled="busy.qa || settingsStore.savingUser"
                @click="saveCurrentQaModeAsDefault"
              >
                {{ settingsStore.savingUser ? '保存中…' : '保存为默认' }}
              </button>
              <button
                type="button"
                class="rounded-xl border border-border bg-background px-3 py-3 text-sm font-semibold hover:bg-accent transition-colors"
                :disabled="busy.qa"
                @click="router.push('/settings')"
              >
                去设置中心
              </button>
              <button
                type="button"
                class="rounded-xl border border-border bg-background px-3 py-3 text-sm font-semibold hover:bg-accent transition-colors"
                @click="clearLocalMessages"
              >
                清空当前显示
              </button>
            </div>

            <div v-if="qaAutoAdapt" class="rounded-xl border border-border bg-background p-4 space-y-3">
              <div class="flex items-center justify-between gap-2">
                <div>
                  <p class="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">回答自适应依据</p>
                  <p class="mt-1 text-sm font-semibold">{{ currentLevelMeta.text }}</p>
                </div>
                <span class="text-[10px] font-semibold px-2 py-1 rounded-full border" :class="currentLevelMeta.badgeClass">
                  {{ currentLevelMeta.code }}
                </span>
              </div>

              <p class="text-sm text-muted-foreground">{{ adaptiveModeSummary }}</p>

              <div class="space-y-2">
                <div class="flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>难度分配</span>
                  <span>{{ adaptivePlanSummary }}</span>
                </div>
                <div class="space-y-1.5">
                  <div v-for="item in adaptivePlanBars" :key="item.key" class="space-y-1">
                    <div class="flex items-center justify-between text-[11px]">
                      <span class="text-muted-foreground">{{ item.label }}</span>
                      <span class="font-semibold">{{ item.percent }}%</span>
                    </div>
                    <div class="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div class="h-full transition-all duration-300" :class="item.barClass" :style="{ width: `${item.percent}%` }"></div>
                    </div>
                  </div>
                </div>
              </div>

              <p class="text-xs text-muted-foreground leading-relaxed">{{ adaptiveReasonText }}</p>

              <div v-if="adaptiveWeakConcepts.length" class="space-y-2">
                <p class="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">薄弱知识点 Top 3</p>
                <div class="flex flex-wrap gap-1.5">
                  <span
                    v-for="concept in adaptiveWeakConcepts"
                    :key="concept"
                    class="px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-primary text-[10px] font-semibold"
                  >
                    {{ concept }}
                  </span>
                </div>
              </div>

              <div class="grid grid-cols-3 gap-2 text-[11px]">
                <div class="rounded-lg border border-border bg-accent/30 px-2 py-1.5 text-center">
                  <p class="text-muted-foreground">正确率</p>
                  <p class="font-semibold">{{ adaptiveInsight.signals.recentAccuracyPercent }}%</p>
                </div>
                <div class="rounded-lg border border-border bg-accent/30 px-2 py-1.5 text-center">
                  <p class="text-muted-foreground">挫败感</p>
                  <p class="font-semibold">{{ adaptiveInsight.signals.frustrationPercent }}%</p>
                </div>
                <div class="rounded-lg border border-border bg-accent/30 px-2 py-1.5 text-center">
                  <p class="text-muted-foreground">累计尝试</p>
                  <p class="font-semibold">{{ adaptiveInsight.signals.totalAttempts }}</p>
                </div>
              </div>

              <p v-if="adaptiveError" class="text-[11px] text-amber-700">{{ adaptiveError }}</p>
            </div>
          </AdvancedPanel>
        </div>
      </section>

      <!-- Right: Knowledge Base Selection -->
      <aside
        class="w-full lg:w-72 xl:w-[20rem] shrink-0 space-y-4 lg:space-y-5 flex-col min-h-0 overflow-y-auto pr-1 pb-2"
        :class="qaSidebarOpen ? 'flex' : 'hidden lg:flex'"
      >
        <AdvancedPanel
          data-testid="qa-scope-card"
          :title="UI_NAMING.currentScope"
          eyebrow=""
          description="先确定当前基于哪份资料提问，必要时再进一步聚焦到某个重点。"
          :default-open="true"
          content-class="max-h-[52vh] overflow-y-auto pr-1"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <Database class="w-5 h-5 text-primary" />
              <div class="text-sm font-semibold">资料选择</div>
            </div>
            <button
              type="button"
              class="lg:hidden p-2 -mr-2 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title="收起面板"
              @click="qaSidebarOpen = false"
            >
              <PanelRightClose class="w-5 h-5" />
            </button>
          </div>

          <template v-if="busy.init">
            <SkeletonBlock type="list" :lines="3" />
          </template>
          <KnowledgeScopePicker
            v-else
            :kb-id="selectedKbId"
            :doc-id="selectedDocId"
            :kbs="kbs"
            :docs="docsInKb"
            :kb-loading="appContext.kbsLoading"
            :docs-loading="busy.docs"
            mode="kb-and-optional-doc"
            kb-label="目标资料库"
            doc-label="限定文档（可选）"
            @update:kb-id="selectedKbId = $event"
            @update:doc-id="selectedDocId = $event"
          >
            <p class="text-[11px] text-muted-foreground">
              默认按整个资料库回答；如果你只想围绕某份文档提问，可继续限定文档。
            </p>
          </KnowledgeScopePicker>

          <div v-if="selectedKbId" class="space-y-2">
            <div class="flex items-center justify-between gap-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">重点知识点（可选）</label>
              <button
                v-if="qaManualFocus"
                type="button"
                class="text-[10px] text-muted-foreground hover:text-foreground"
                @click="clearQaManualFocus"
              >
                清空
              </button>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2">
              <input
                v-model="qaFocusSearch"
                type="text"
                placeholder="搜索重点知识点（如：牛顿定律）"
                class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                @keydown.enter.prevent="applySelectedQaFocusCandidate"
              />
              <button
                type="button"
                class="px-3 py-2 rounded-lg border border-input bg-background text-sm hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="busy.focusKeypoints || !qaFocusCandidate"
                @click="applySelectedQaFocusCandidate"
              >
                应用
              </button>
            </div>
            <select
              v-model="qaFocusCandidate"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
              :disabled="busy.focusKeypoints || !filteredQaFocusOptions.length"
            >
              <option value="">{{ qaFocusSelectPlaceholder }}</option>
              <option v-for="item in filteredQaFocusOptions" :key="item.id" :value="item.text">
                {{ item.text }}
              </option>
            </select>
            <p class="text-[10px] text-muted-foreground">
              仅显示当前资料范围内可用的重点知识点。
            </p>
            <p class="text-[10px] text-muted-foreground">
              当前聚焦：{{ effectiveQaFocusContext || '未设置' }}
            </p>
          </div>

          <div v-if="selectedKb" class="grid grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 gap-3 text-[11px]">
            <div class="min-w-0 rounded-lg border border-border bg-accent/20 px-3 py-2">
              <p class="text-muted-foreground leading-tight break-words">资料库文档</p>
              <p class="mt-1 text-sm font-semibold">{{ Array.isArray(docsInKb) ? docsInKb.length : 0 }}</p>
            </div>
            <div class="min-w-0 rounded-lg border border-border bg-accent/20 px-3 py-2">
              <p class="text-muted-foreground leading-tight break-words">相关会话</p>
              <p class="mt-1 text-sm font-semibold">{{ selectedKbSessions.length }}</p>
            </div>
            <div class="min-w-0 rounded-lg border border-border bg-accent/20 px-3 py-2">
              <p class="text-muted-foreground leading-tight break-words">就绪文档</p>
              <p class="mt-1 text-sm font-semibold text-green-600">{{ docsReadyCount }}</p>
            </div>
            <div class="min-w-0 rounded-lg border border-border bg-accent/20 px-3 py-2">
              <p class="text-muted-foreground leading-tight break-words">处理中 / 失败</p>
              <p class="mt-1 text-sm font-semibold">
                <span class="text-blue-600">{{ docsProcessingCount }}</span>/<span class="text-destructive">{{ docsErrorCount }}</span>
              </p>
            </div>
          </div>
        </AdvancedPanel>

        <AdvancedPanel
          :title="UI_NAMING.referenceSources"
          eyebrow=""
          description="提问后可以在这里查看回答引用的片段，以及检索和生成的耗时。"
          :default-open="false"
          content-class="max-h-[44vh] overflow-y-auto pr-1"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground">本次回答来源</h3>
            <span
              class="text-[10px] font-semibold px-2 py-1 rounded-full border"
              :class="qaFlowPanelBadgeClass"
            >
              {{ qaFlowPanelBadgeText }}
            </span>
          </div>
          <div class="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
            <span v-if="qaFlow.retrievedCount > 0" class="px-2 py-1 rounded border border-border bg-accent/20">
              {{ UX_TEXT.retrievedContentLabel }} {{ qaFlow.retrievedCount }}
            </span>
            <span v-if="qaFlow.timings.retrieve_ms" class="px-2 py-1 rounded border border-border bg-accent/20">
              {{ UX_TEXT.retrievalDurationLabel }} {{ qaFlow.timings.retrieve_ms }} ms
            </span>
            <span v-if="qaFlow.timings.generate_ms" class="px-2 py-1 rounded border border-border bg-accent/20">
              生成 {{ qaFlow.timings.generate_ms }} ms
            </span>
            <span v-if="qaFlow.timings.total_ms" class="px-2 py-1 rounded border border-border bg-accent/20">
              总耗时 {{ qaFlow.timings.total_ms }} ms
            </span>
          </div>

          <div v-if="busy.qa && qaSourcePanelSources.length === 0" class="space-y-2">
            <SkeletonBlock type="list" :lines="3" />
            <p class="text-xs text-muted-foreground">{{ UX_TEXT.collectingSources }}</p>
          </div>

          <div v-else-if="qaSourcePanelSources.length" class="space-y-2 max-h-56 overflow-y-auto pr-1">
            <button
              v-for="(source, index) in qaSourcePanelSources"
              :key="`${source.doc_id || 'doc'}-${source.page ?? 'x'}-${source.chunk ?? index}`"
              class="w-full text-left p-2 rounded-lg border border-border hover:border-primary/40 hover:bg-accent/20 transition-colors"
              @click="openQaSource(source)"
            >
              <div class="flex items-start gap-2">
                <FileText class="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <div class="min-w-0 flex-1">
                  <p class="text-xs font-semibold truncate">{{ source.source || `来源 ${index + 1}` }}</p>
                  <p class="mt-1 text-[11px] text-muted-foreground line-clamp-2">{{ source.snippet || '点击查看原文片段' }}</p>
                </div>
              </div>
            </button>
          </div>

          <EmptyState
            v-else
            :icon="FileText"
            title="暂无来源"
            description="提问后会在这里显示本次回答引用的文档片段。"
            :hint="busy.qa ? UX_TEXT.waitingSources : '点击来源项可查看原文片段。'"
            size="sm"
          />
        </AdvancedPanel>

        <AdvancedPanel
          :title="UI_NAMING.sessionHistory"
          eyebrow=""
          description="如果你想保留连续追问或清理历史记录，可在这里处理。"
          :default-open="false"
          content-class="max-h-[52vh] overflow-y-auto pr-1"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground">历史会话</h3>
            <button
              class="text-[10px] font-semibold px-2 py-1 rounded border border-border hover:bg-accent"
              :disabled="busy.sessionAction || !selectedKbId"
              @click="createSession"
            >
              新建会话
            </button>
          </div>
          <div class="space-y-2">
            <select
              v-model="selectedSessionId"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
            >
              <option value="">未选择（将自动新建）</option>
              <option v-for="session in sessionSelectOptions" :key="session.id" :value="session.id">
                {{ sessionLabel(session) }}
              </option>
            </select>
            <div
              v-if="sessionsTotal > 0"
              class="flex items-center justify-between gap-2 text-[10px] text-muted-foreground"
            >
              <span>第 {{ sessionsPageNumber }} / {{ sessionsTotalPages }} 页（共 {{ sessionsTotal }} 条）</span>
              <div class="flex items-center gap-1">
                <button
                  class="px-2 py-1 rounded border border-border hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="busy.sessions || sessionsOffset <= 0"
                  @click="goToPrevSessionsPage"
                >
                  上一页
                </button>
                <button
                  class="px-2 py-1 rounded border border-border hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="busy.sessions || !sessionsHasMore"
                  @click="goToNextSessionsPage"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>

          <div v-if="selectedSessionId" class="space-y-2">
            <input
              v-model="sessionTitleInput"
              type="text"
              placeholder="会话名称"
              class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
            />
            <div class="grid grid-cols-3 gap-2">
              <button
                class="text-xs py-2 rounded border border-border hover:bg-accent"
                :disabled="busy.sessionAction"
                @click="renameCurrentSession"
              >
                重命名
              </button>
              <button
                class="text-xs py-2 rounded border border-border hover:bg-accent"
                :disabled="busy.sessionAction"
                @click="clearCurrentSessionMessages"
              >
                清空消息
              </button>
              <button
                class="text-xs py-2 rounded border border-destructive/40 text-destructive hover:bg-destructive/10"
                :disabled="busy.sessionAction"
                @click="deleteCurrentSession"
              >
                删除会话
              </button>
            </div>
          </div>

          <div class="rounded-lg border border-border bg-accent/20 px-3 py-3 text-xs text-muted-foreground space-y-1">
            <p>当前显示消息：{{ qaMessages.length }} 条</p>
            <p>“清空当前显示”只影响本页显示，不会删除服务端历史记录。</p>
          </div>
        </AdvancedPanel>
      </aside>
    </div>
    <SourcePreviewModal
      :open="sourcePreview.open"
      :loading="sourcePreview.loading"
      :title="sourcePreview.title"
      :source-label="sourcePreview.sourceLabel"
      :page="null"
      :chunk="null"
      :snippet="sourcePreview.snippet"
      :error="sourcePreview.error"
      @close="closeSourcePreview"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessageSquare, Send, Database, FileText, Sparkles, User, Bot, PanelRightClose } from 'lucide-vue-next'
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiSsePost,
  getDifficultyPlan,
  getProfile,
  toUserFacingApiErrorMessage,
} from '../api'
import { useToast } from '../composables/useToast'
import { useAppKnowledgeScope } from '../composables/useAppKnowledgeScope'
import { useSettingsStore } from '../stores/settings'
import EmptyState from '../components/ui/EmptyState.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import SourcePreviewModal from '../components/ui/SourcePreviewModal.vue'
import KnowledgeScopePicker from '../components/context/KnowledgeScopePicker.vue'
import ContextSummaryBar from '../components/context/ContextSummaryBar.vue'
import AdvancedPanel from '../components/ui/AdvancedPanel.vue'
import { parseExplainMarkdownSections } from '../utils/qaExplain'
import { renderMarkdown } from '../utils/markdown'
import { parseRouteContext } from '../utils/routeContext'
import { UX_TEXT } from '../constants/uxText'
import { UI_NAMING } from '../constants/uiNaming'
import {
  buildAdaptiveInsight,
  getAbilityLevelMeta as resolveAbilityLevelMeta,
  normalizeAbilityLevel,
} from '../utils/adaptiveTransparency'

const { showToast } = useToast()
const settingsStore = useSettingsStore()
const router = useRouter()
const route = useRoute()

const {
  appContext,
  resolvedUserId,
  kbs,
  selectedKbId,
  selectedDocId,
  kbDocs,
  docsInKb,
  docsInKbLoading,
} = useAppKnowledgeScope({ withDocs: true })
const sessions = ref([])
const sessionCacheMap = ref({})
const sessionsTotal = ref(0)
const sessionsOffset = ref(0)
const sessionsLimit = ref(20)
const sessionsHasMore = ref(false)
const selectedSessionId = ref('')
const sessionTitleInput = ref('')
const qaInput = ref('')
const qaMessages = ref([])
const qaAbilityLevel = ref('intermediate')
const qaMode = ref('normal')
const qaAutoAdapt = ref(true)
const qaFocusSearch = ref('')
const qaFocusCandidate = ref('')
const qaFocusOptions = ref([])
const qaManualFocus = ref('')
const adaptiveProfile = ref(null)
const adaptivePlan = ref(null)
const adaptiveLoading = ref(false)
const adaptiveError = ref('')
const qaSidebarOpen = ref(false)
const qaFlow = ref(createQaFlowState())
const syncingFromSession = ref(false)
const preserveQaFlowOnNextSessionLoad = ref(false)
const lastAutoQaRouteKey = ref('')
const autoQaMissingContextToastKey = ref('')
const sourcePreview = ref({
  open: false,
  loading: false,
  title: '',
  sourceLabel: '',
  page: null,
  chunk: null,
  snippet: '',
  error: '',
})
const busy = ref({
  qa: false,
  init: false,
  docs: false,
  focusKeypoints: false,
  sessions: false,
  sessionAction: false
})
const scrollContainer = ref(null)
const lastQaSubmitFingerprint = ref('')
const lastQaSubmitAt = ref(0)

const STREAM_NON_FALLBACK_CODES = new Set(['validation_error', 'not_found', 'no_results'])
const QA_EXPLAIN_DISPLAY_THRESHOLD = 3
const QA_SUBMIT_DEDUPE_WINDOW_MS = 1200
const QA_AUTO_ADAPT_STORAGE_KEY = 'gradtutor_qa_auto_adapt'
	
const selectedKb = computed(() => {
  return kbs.value.find(k => k.id === selectedKbId.value) || null
})

const selectedDoc = computed(() => {
  return docsInKb.value.find(d => d.id === selectedDocId.value) || null
})
const selectedSession = computed(() => {
  if (!selectedSessionId.value) return null
  return sessionCacheMap.value[selectedSessionId.value] || sessions.value.find((session) => session.id === selectedSessionId.value) || null
})
const cachedSessions = computed(() =>
  Object.values(sessionCacheMap.value)
    .filter(Boolean)
    .sort((a, b) => {
      const aTime = new Date(a.created_at || 0).getTime()
      const bTime = new Date(b.created_at || 0).getTime()
      if (bTime !== aTime) return bTime - aTime
      return String(b.id || '').localeCompare(String(a.id || ''))
    })
)
const sessionSelectOptions = computed(() => {
  const items = []
  const seen = new Set()
  const selected = selectedSession.value
  if (selected && selected.id && !sessions.value.some((item) => item.id === selected.id)) {
    items.push(selected)
    seen.add(selected.id)
  }
  for (const session of sessions.value) {
    if (!session?.id || seen.has(session.id)) continue
    items.push(session)
    seen.add(session.id)
  }
  return items
})
const selectedKbSessions = computed(() =>
  cachedSessions.value.filter((session) => session.kb_id === selectedKbId.value)
)
const sessionsTotalPages = computed(() => {
  if (sessionsTotal.value <= 0) return 1
  return Math.max(1, Math.ceil(sessionsTotal.value / sessionsLimit.value))
})
const sessionsPageNumber = computed(() => Math.floor(sessionsOffset.value / sessionsLimit.value) + 1)
const docsReadyCount = computed(() =>
  docsInKb.value.filter((doc) => doc.status === 'ready').length
)
const docsProcessingCount = computed(() =>
  docsInKb.value.filter((doc) => doc.status === 'processing').length
)
const docsErrorCount = computed(() =>
  docsInKb.value.filter((doc) => doc.status === 'error').length
)
const hasAnyKb = computed(() => kbs.value.length > 0)
const qaEmptyTitle = computed(() => {
  if (!hasAnyKb.value) return '先上传文档再开始问答'
  if (!selectedKbId.value) return '先选择一个资料库'
  return '开始你的第一次提问'
})
const qaEmptyDescription = computed(() => {
  if (!hasAnyKb.value) return '当前还没有资料库，上传文档后即可开始基于资料的学习问答。'
  if (!selectedKbId.value) return '先在右侧选择资料范围，输入框会自动解锁。'
  return '可以直接问概念解释、公式推导或对比分析。'
})
const qaEmptyHint = computed(() => {
  if (!hasAnyKb.value) return '上传并解析完成后，可按资料库或文档范围提问。'
  if (!selectedKbId.value) return '如需限定范围，可继续选择具体文档。'
  return effectiveQaFocusContext.value
    ? `已聚焦知识点「${effectiveQaFocusContext.value}」，可直接围绕该知识点提问。`
    : '点击下方按钮可自动填入一个示例问题。'
})
const qaEmptyPrimaryAction = computed(() => {
  if (!hasAnyKb.value) return { label: '去上传文档' }
  if (!selectedKbId.value) return null
  return { label: '填入示例问题', variant: 'secondary' }
})
const qaAdvancedDefaultOpen = computed(() => false)
const providerSetup = computed(() => settingsStore.providerSetup)
const qaActionBlocked = computed(() => {
  const setup = providerSetup.value
  if (!setup) return false
  return !setup.llm_ready || !setup.embedding_ready
})
const qaFlowPrimaryText = computed(() => {
  const phase = qaFlow.value.phase
  if (phase === 'retrieving') return '正在查找资料'
  if (phase === 'generating' || phase === 'saving') return '正在生成回答'
  if (phase === 'done') return '已完成'
  if (phase === 'failed') return '失败'
  return '等待提问'
})
const qaFlowSecondaryText = computed(() => {
  if (qaFlow.value.phase === 'done' && qaFlow.value.result === 'no_results') {
    return '这次没有找到足够相关的内容，可以换个问法或缩小资料范围。'
  }
  if (qaFlow.value.phase === 'failed') {
    return qaFlow.value.message || '本次提问未成功完成。'
  }
  if (effectiveQaFocusContext.value) {
    return `当前已围绕「${effectiveQaFocusContext.value}」聚焦提问。`
  }
  return '输入问题后，系统会自动基于当前资料范围组织回答。'
})

const adaptiveInsight = computed(() =>
  buildAdaptiveInsight({
    profile: adaptiveProfile.value || { ability_level: qaAbilityLevel.value },
    plan: adaptivePlan.value,
  })
)
const currentLevelMeta = computed(() => adaptiveInsight.value.levelMeta || resolveAbilityLevelMeta(qaAbilityLevel.value))
const adaptiveModeSummary = computed(() => (
  qaMode.value === 'explain'
    ? '当前回答模式：分步讲解'
    : '当前回答模式：标准回答'
))
const adaptivePlanBars = computed(() => ([
  {
    key: 'easy',
    label: '简单',
    percent: adaptiveInsight.value.planPercent.easy,
    barClass: 'bg-green-500',
  },
  {
    key: 'medium',
    label: '中等',
    percent: adaptiveInsight.value.planPercent.medium,
    barClass: 'bg-blue-500',
  },
  {
    key: 'hard',
    label: '困难',
    percent: adaptiveInsight.value.planPercent.hard,
    barClass: 'bg-amber-500',
  },
]))
const adaptivePlanSummary = computed(() => (
  `简 ${adaptiveInsight.value.planPercent.easy}% · `
  + `中 ${adaptiveInsight.value.planPercent.medium}% · `
  + `难 ${adaptiveInsight.value.planPercent.hard}%`
))
const adaptiveReasonText = computed(() => adaptiveInsight.value.reasonText || '系统会根据学习画像动态调整回答策略。')
const adaptiveWeakConcepts = computed(() => adaptiveInsight.value.weakConceptsTop3 || [])
const entryFocusContext = computed(() => appContext.routeContext.focus)
const effectiveQaFocusContext = computed(() => {
  const manual = String(qaManualFocus.value || '').trim()
  if (manual) return manual
  return String(entryFocusContext.value || '').trim()
})
const scopedQaFocusOptions = computed(() => {
  const options = Array.isArray(qaFocusOptions.value) ? qaFocusOptions.value : []
  const docId = String(selectedDocId.value || '').trim()
  if (!docId) return options
  return options.filter((item) => {
    const sourceDocIds = Array.isArray(item?.sourceDocIds) ? item.sourceDocIds : []
    return sourceDocIds.includes(docId)
  })
})
const filteredQaFocusOptions = computed(() => {
  const keyword = String(qaFocusSearch.value || '').trim().toLowerCase()
  const selectedText = String(qaManualFocus.value || '').trim().toLowerCase()
  const options = Array.isArray(scopedQaFocusOptions.value) ? scopedQaFocusOptions.value : []
  return options
    .filter((item) => {
      const text = String(item?.text || '').trim()
      if (!text) return false
      if (selectedText && text.toLowerCase() === selectedText) return false
      if (!keyword) return true
      return text.toLowerCase().includes(keyword)
    })
    .slice(0, 80)
})
const currentQaFocusOption = computed(() => {
  const target = String(effectiveQaFocusContext.value || '').trim()
  if (!target) return null
  return qaFocusOptions.value.find((item) => String(item?.text || '').trim() === target) || null
})
const showLearningPathMultiDocHint = computed(() => {
  if (!entryFocusContext.value) return false
  if (currentQaFocusOption.value?.sourceDocCount > 1) return true
  return !selectedDocId.value
})
const qaFocusSelectPlaceholder = computed(() => {
  if (busy.value.focusKeypoints) return '正在加载知识点...'
  if (filteredQaFocusOptions.value.length) return '请选择知识点'
  return selectedDocId.value ? '该文档暂无可选聚合知识点' : '暂无可选聚合知识点'
})
const entryDocContextId = computed(() => parseRouteContext(route.query).docId)
const latestAssistantMessage = computed(() => {
  for (let i = qaMessages.value.length - 1; i >= 0; i -= 1) {
    const msg = qaMessages.value[i]
    if (msg?.role === 'answer') return msg
  }
  return null
})
const qaStreamingMessage = computed(() => {
  for (let i = qaMessages.value.length - 1; i >= 0; i -= 1) {
    const msg = qaMessages.value[i]
    if (msg?.role === 'answer' && msg.streaming) return msg
  }
  return null
})
const qaSourcePanelMessage = computed(() => qaStreamingMessage.value || latestAssistantMessage.value || null)
const qaSourcePanelSources = computed(() => {
  const sources = qaSourcePanelMessage.value?.sources
  return Array.isArray(sources) ? sources : []
})
const qaFlowPanelBadgeText = computed(() => {
  const phase = qaFlow.value.phase
  if (phase === 'retrieving') return UX_TEXT.retrievalInProgress
  if (phase === 'generating') return '生成中'
  if (phase === 'saving') return '保存中'
  if (phase === 'done' && qaFlow.value.result === 'no_results') return '无结果'
  if (phase === 'done') return '完成'
  if (phase === 'failed') return '失败'
  return '就绪'
})
const qaFlowPanelBadgeClass = computed(() => {
  const phase = qaFlow.value.phase
  if (phase === 'retrieving' || phase === 'generating' || phase === 'saving') {
    return 'border-blue-200 bg-blue-50 text-blue-700'
  }
  if (phase === 'done' && qaFlow.value.result === 'no_results') {
    return 'border-amber-200 bg-amber-50 text-amber-700'
  }
  if (phase === 'done') {
    return 'border-green-200 bg-green-50 text-green-700'
  }
  if (phase === 'failed') {
    return 'border-red-200 bg-red-50 text-red-700'
  }
  return 'border-border text-muted-foreground'
})
const effectiveQaSettings = computed(() => settingsStore.effectiveSettings?.qa || {})

function getLevelMeta(level) {
  return resolveAbilityLevelMeta(level)
}

function normalizeQaMode(mode) {
  const normalized = String(mode || '').trim().toLowerCase()
  return normalized === 'explain' ? 'explain' : 'normal'
}

function readQaAutoAdaptPreference() {
  try {
    const raw = String(window.localStorage.getItem(QA_AUTO_ADAPT_STORAGE_KEY) || '').trim().toLowerCase()
    if (['0', 'false', 'off'].includes(raw)) return false
    if (['1', 'true', 'on'].includes(raw)) return true
  } catch {
    // ignore storage error
  }
  return true
}

function persistQaAutoAdaptPreference(enabled) {
  try {
    window.localStorage.setItem(QA_AUTO_ADAPT_STORAGE_KEY, enabled ? '1' : '0')
  } catch {
    // ignore storage error
  }
}

function setQaAutoAdapt(value) {
  const enabled = Boolean(value)
  if (qaAutoAdapt.value === enabled) return
  qaAutoAdapt.value = enabled
  persistQaAutoAdaptPreference(enabled)
  if (enabled) {
    void refreshAdaptiveTransparency()
  } else {
    adaptiveLoading.value = false
    adaptiveError.value = ''
  }
}

function applyQaModeFromSettings() {
  qaMode.value = normalizeQaMode(effectiveQaSettings.value?.mode)
}

async function loadQaViewSettings(force = false) {
  try {
    await settingsStore.load({
      userId: resolvedUserId.value,
      kbId: selectedKbId.value || '',
      force,
    })
    applyQaModeFromSettings()
  } catch {
    // error toast handled globally
  }
}

async function saveCurrentQaModeAsDefault() {
  try {
    if (!settingsStore.systemStatus) {
      await loadQaViewSettings(true)
    }
    settingsStore.setUserDraftSection('qa', { mode: normalizeQaMode(qaMode.value) })
    await settingsStore.saveUser(resolvedUserId.value)
    if (selectedKbId.value) {
      await settingsStore.load({
        userId: resolvedUserId.value,
        kbId: selectedKbId.value,
        force: true,
      })
    }
    showToast('已保存当前回答模式为默认设置', 'success')
  } catch {
    // error toast handled globally
  }
}

function createQaFlowState() {
  return {
    phase: 'idle',
    message: '',
    result: null,
    retrievedCount: 0,
    timings: {},
    usedFallback: false,
    errorCode: null,
  }
}

function resetQaFlow() {
  qaFlow.value = createQaFlowState()
}

function updateQaFlow(patch = {}) {
  qaFlow.value = {
    ...qaFlow.value,
    ...patch,
    timings: {
      ...(qaFlow.value?.timings || {}),
      ...(patch.timings || {}),
    },
  }
}

function qaMessageStatusText(msg) {
  if (!msg || msg.role === 'question') return ''
  if (msg.status === 'pending') return '排队中'
  if (msg.status === 'streaming') return msg.content?.trim() ? '生成中' : '准备生成'
  if (msg.status === 'fallback') return '已回退非流式'
  if (msg.status === 'error') return '生成失败'
  return '已完成'
}

function qaMessageStatusBadgeClass(msg) {
  if (!msg) return 'border-border text-muted-foreground'
  if (msg.status === 'fallback') return 'border-amber-300 bg-amber-50 text-amber-700'
  if (msg.status === 'error') return 'border-red-300 bg-red-50 text-red-700'
  if (msg.status === 'streaming' || msg.status === 'pending') return 'border-blue-300 bg-blue-50 text-blue-700'
  return 'border-green-300 bg-green-50 text-green-700'
}

function normalizeQaSource(raw) {
  if (!raw || typeof raw !== 'object') return null
  const rawSource = typeof raw.source === 'string' ? raw.source.trim() : ''
  const cleanedSource = rawSource
    .replace(/\s+p\.\d+\s+c\.\d+/ig, '')
    .replace(/\s+p\.\d+/ig, '')
    .replace(/\s+c\.\d+/ig, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
  let friendlySource = cleanedSource || rawSource
  if (!friendlySource) {
    friendlySource = raw.doc_id ? `文档片段 (${String(raw.doc_id).slice(0, 8)})` : '文档片段'
  } else if (/^document(\b|[\s._-])/i.test(friendlySource) || /^document$/i.test(friendlySource)) {
    friendlySource = friendlySource.replace(/^document/i, '文档片段')
  }
  return {
    source: friendlySource,
    snippet: raw.snippet || '',
    doc_id: raw.doc_id ?? null,
    kb_id: raw.kb_id ?? null,
    page: raw.page ?? null,
    chunk: raw.chunk ?? null,
  }
}

function applyExplainStateToAssistantMessage(msg) {
  if (!msg || msg.role !== 'answer') return msg
  const parsed = parseExplainMarkdownSections(msg.content || '')
  const requestedMode = normalizeQaMode(msg.requestedMode)
  const resolvedMode = normalizeQaMode(msg.resolvedMode || msg.mode || requestedMode)
  const explicitExplain = requestedMode === 'explain' || resolvedMode === 'explain'
  const canRenderExplain = parsed.sections.length >= QA_EXPLAIN_DISPLAY_THRESHOLD && parsed.isExplainLike

  msg.requestedMode = requestedMode
  msg.resolvedMode = resolvedMode
  msg.explainSections = parsed.sections
  msg.explainMissing = parsed.missing
  msg.explainIncomplete = explicitExplain && parsed.missing.length > 0
  msg.displayMode = (explicitExplain || parsed.isExplainLike) && canRenderExplain ? 'explain' : 'normal'
  return msg
}

function makeAssistantPlaceholder(requestedMode = qaMode.value) {
  const normalizedRequestedMode = normalizeQaMode(requestedMode)
  return applyExplainStateToAssistantMessage({
    role: 'answer',
    content: '',
    sources: [],
    abilityLevel: qaAbilityLevel.value,
    streaming: true,
    status: 'pending',
    errorCode: null,
    requestedMode: normalizedRequestedMode,
    resolvedMode: normalizedRequestedMode,
    displayMode: normalizedRequestedMode === 'explain' ? 'explain' : 'normal',
    explainSections: [],
    explainMissing: [],
    explainIncomplete: false,
  })
}

function shouldRenderExplainCards(msg) {
  return (
    msg?.role === 'answer'
    && msg?.displayMode === 'explain'
    && Array.isArray(msg?.explainSections)
    && msg.explainSections.length > 0
  )
}

function streamPayloadError(payload = {}) {
  const err = new Error(payload.message || '流式回答失败')
  err.qaStream = {
    code: payload.code || 'unknown',
    stage: payload.stage || 'generating',
    retryable: payload.retryable !== false,
    message: payload.message || '流式回答失败',
  }
  return err
}

function isStreamErrorRetryable(err) {
  const code = err?.qaStream?.code
  if (code && STREAM_NON_FALLBACK_CODES.has(code)) return false
  if (typeof err?.qaStream?.retryable === 'boolean') return err.qaStream.retryable
  return true
}

function buildQaPayload(question, activeSessionId, requestedMode = qaMode.value) {
  const normalizedRequestedMode = normalizeQaMode(requestedMode)
  const payload = {
    question,
    user_id: resolvedUserId.value,
    mode: normalizedRequestedMode,
  }
  const retrievalPreset = String(effectiveQaSettings.value?.retrieval_preset || '').trim().toLowerCase()
  if (['fast', 'balanced', 'deep'].includes(retrievalPreset)) {
    payload.retrieval_preset = retrievalPreset
  }
  const topK = Number(effectiveQaSettings.value?.top_k)
  if (Number.isFinite(topK) && topK > 0) {
    payload.top_k = topK
  }
  const fetchK = Number(effectiveQaSettings.value?.fetch_k)
  if (Number.isFinite(fetchK) && fetchK > 0) {
    payload.fetch_k = fetchK
  }
  if (activeSessionId) {
    payload.session_id = activeSessionId
  }
  if (selectedSession.value?.doc_id) {
    payload.doc_id = selectedSession.value.doc_id
  } else if (selectedSession.value?.kb_id) {
    payload.kb_id = selectedSession.value.kb_id
  } else if (selectedDocId.value) {
    payload.doc_id = selectedDocId.value
  } else {
    payload.kb_id = selectedKbId.value
  }
  if (effectiveQaFocusContext.value) {
    payload.focus = effectiveQaFocusContext.value
  }
  return payload
}

function buildQaSubmitFingerprint(question) {
  const normalizedQuestion = (question || '').trim()
  if (!normalizedQuestion) return ''
  return [
    selectedKbId.value || '',
    selectedDocId.value || '',
    selectedSessionId.value || '',
    normalizeQaMode(qaMode.value),
    qaAutoAdapt.value ? 'adaptive-on' : 'adaptive-off',
    effectiveQaFocusContext.value || '',
    normalizedQuestion,
  ].join('::')
}

function isDuplicateQaSubmit(fingerprint) {
  if (!fingerprint) return false
  const now = Date.now()
  const isDuplicate = (
    lastQaSubmitFingerprint.value === fingerprint
    && (now - lastQaSubmitAt.value) < QA_SUBMIT_DEDUPE_WINDOW_MS
  )
  if (!isDuplicate) {
    lastQaSubmitFingerprint.value = fingerprint
    lastQaSubmitAt.value = now
  }
  return isDuplicate
}

function goToUpload() {
  router.push({ path: '/upload' })
}

function fillSampleQuestion() {
  if (effectiveQaFocusContext.value) {
    qaInput.value = `请用通俗的方式讲解「${effectiveQaFocusContext.value}」，并给出一个简单例子。`
    return
  }
  qaInput.value = '请先概括这个资料库中最重要的 3 个概念，并说明它们之间的关系。'
}

function handleQaEmptyPrimary() {
  if (!hasAnyKb.value) {
    goToUpload()
    return
  }
  if (!selectedKbId.value) return
  fillSampleQuestion()
}

function normalizeQaFocusOptions(items = []) {
  const out = []
  for (const item of items) {
    const id = String(item?.id || '').trim()
    const text = String(item?.text || '').trim()
    if (!text) continue
    const sourceDocIds = [
      ...new Set(
        (Array.isArray(item?.source_doc_ids) ? item.source_doc_ids : [])
          .map((docId) => String(docId || '').trim())
          .filter(Boolean)
      )
    ]
    out.push({
      id: id || text,
      text,
      memberCount: Number(item?.member_count || 1),
      sourceDocCount: sourceDocIds.length,
      sourceDocIds,
    })
  }
  return out
}

function syncQaFocusCandidateSelection() {
  if (
    qaFocusCandidate.value
    && !filteredQaFocusOptions.value.some((item) => item.text === qaFocusCandidate.value)
  ) {
    qaFocusCandidate.value = ''
  }
}

function applySelectedQaFocusCandidate() {
  const text = String(qaFocusCandidate.value || '').trim()
  if (!text) return
  qaManualFocus.value = text
  qaFocusCandidate.value = ''
}

function clearQaManualFocus() {
  qaManualFocus.value = ''
  qaFocusSearch.value = ''
  qaFocusCandidate.value = ''
}

function pruneQaManualFocusToCurrentDocScope() {
  if (!selectedDocId.value) return
  if (!Array.isArray(qaFocusOptions.value)) return
  if (!qaFocusOptions.value.length && busy.value.focusKeypoints) return
  const current = String(qaManualFocus.value || '').trim()
  if (!current) return
  const allowed = new Set(
    (Array.isArray(scopedQaFocusOptions.value) ? scopedQaFocusOptions.value : [])
      .map((item) => String(item?.text || '').trim())
      .filter(Boolean)
  )
  if (!allowed.has(current)) {
    qaManualFocus.value = ''
  }
}

async function refreshQaFocusOptions() {
  if (!selectedKbId.value) {
    qaFocusOptions.value = []
    qaFocusCandidate.value = ''
    busy.value.focusKeypoints = false
    return
  }
  busy.value.focusKeypoints = true
  const requestKbId = selectedKbId.value
  try {
    const params = new URLSearchParams()
    params.set('user_id', resolvedUserId.value)
    params.set('grouped', 'true')
    params.set('only_unlocked', 'true')
    const res = await apiGet(`/api/keypoints/kb/${encodeURIComponent(requestKbId)}?${params.toString()}`)
    if (selectedKbId.value !== requestKbId) return
    qaFocusOptions.value = normalizeQaFocusOptions(Array.isArray(res?.keypoints) ? res.keypoints : [])
  } catch {
    if (selectedKbId.value !== requestKbId) return
    qaFocusOptions.value = []
    // error toast handled globally
  } finally {
    if (selectedKbId.value === requestKbId) {
      busy.value.focusKeypoints = false
    }
  }
  pruneQaManualFocusToCurrentDocScope()
  syncQaFocusCandidateSelection()
}

async function refreshDocsInKb() {
  if (!selectedKbId.value) {
    kbDocs.reset()
    busy.value.docs = false
    return
  }
  try {
    await kbDocs.refresh()
  } catch {
    // error toast handled globally
  }
}

function mergeSessionCache(items) {
  if (!Array.isArray(items) || items.length === 0) return
  const next = { ...sessionCacheMap.value }
  for (const session of items) {
    if (!session?.id) continue
    next[session.id] = session
  }
  sessionCacheMap.value = next
}

function removeSessionFromCache(sessionId) {
  if (!sessionId || !sessionCacheMap.value[sessionId]) return
  const next = { ...sessionCacheMap.value }
  delete next[sessionId]
  sessionCacheMap.value = next
}

async function goToPrevSessionsPage() {
  if (busy.value.sessions || sessionsOffset.value <= 0) return
  const nextOffset = Math.max(0, sessionsOffset.value - sessionsLimit.value)
  await refreshSessions({ offset: nextOffset })
}

async function goToNextSessionsPage() {
  if (busy.value.sessions || !sessionsHasMore.value) return
  const nextOffset = sessionsOffset.value + sessionsLimit.value
  await refreshSessions({ offset: nextOffset })
}

async function refreshSessions(options = {}) {
  const { resetPage = false, offset = null } = options
  if (resetPage) {
    sessionsOffset.value = 0
  } else if (Number.isFinite(Number(offset))) {
    sessionsOffset.value = Math.max(0, Number(offset))
  }
  busy.value.sessions = true
  try {
    while (true) {
      const params = new URLSearchParams()
      params.set('user_id', resolvedUserId.value)
      params.set('offset', String(sessionsOffset.value))
      params.set('limit', String(sessionsLimit.value))
      const result = await apiGet(`/api/chat/sessions/page?${params.toString()}`)
      const items = Array.isArray(result?.items) ? result.items : []
      const total = Math.max(0, Number(result?.total) || 0)
      sessions.value = items
      sessionsTotal.value = total
      sessionsOffset.value = Math.max(0, Number(result?.offset) || 0)
      sessionsLimit.value = Math.max(1, Number(result?.limit) || sessionsLimit.value || 20)
      sessionsHasMore.value = Boolean(result?.has_more)
      mergeSessionCache(items)

      if (total > 0 && items.length === 0 && sessionsOffset.value > 0) {
        const lastPageOffset = Math.max(0, (Math.ceil(total / sessionsLimit.value) - 1) * sessionsLimit.value)
        if (lastPageOffset !== sessionsOffset.value) {
          sessionsOffset.value = lastPageOffset
          continue
        }
      }
      break
    }
  } catch {
    // error toast handled globally
    sessions.value = []
    sessionsHasMore.value = false
  } finally {
    busy.value.sessions = false
  }
}

function mapServerMessage(message) {
  if (message.role === 'user') {
    return { role: 'question', content: message.content }
  }
  return applyExplainStateToAssistantMessage({
    role: 'answer',
    content: message.content,
    sources: Array.isArray(message.sources) ? message.sources.map(normalizeQaSource).filter(Boolean) : [],
    streaming: false,
    status: 'done',
    errorCode: null,
    requestedMode: 'normal',
    resolvedMode: 'normal',
    displayMode: 'normal',
    explainSections: [],
    explainMissing: [],
    explainIncomplete: false,
  })
}

async function loadSessionMessages(sessionId) {
  if (!sessionId) {
    qaMessages.value = []
    resetQaFlow()
    return
  }
  try {
    const rows = await apiGet(`/api/chat/sessions/${sessionId}/messages?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    qaMessages.value = Array.isArray(rows) ? rows.map(mapServerMessage) : []
  } catch {
    qaMessages.value = []
  }
}

function sessionLabel(session) {
  const title = session.title || '未命名会话'
  const kbText = session.kb_id ? `资料库：${session.kb_id}` : '未绑定资料库'
  return `${title} (${kbText})`
}

async function createSession(options = {}) {
  const { silent = false, activate = true } = options
  if (!selectedKbId.value) {
    if (!silent) {
      showToast('请先选择资料库', 'error')
    }
    return null
  }
  busy.value.sessionAction = true
  try {
    const payload = {
      user_id: resolvedUserId.value,
      kb_id: selectedKbId.value
    }
    if (selectedDocId.value) {
      payload.doc_id = selectedDocId.value
    }
    const session = await apiPost('/api/chat/sessions', payload)
    const sessionId = session?.id || null
    mergeSessionCache(session ? [session] : [])
    await refreshSessions({ resetPage: true })
    if (activate && sessionId) {
      selectedSessionId.value = sessionId
      sessionTitleInput.value = session.title || ''
      qaMessages.value = []
      resetQaFlow()
    }
    if (!silent) {
      showToast('已创建新会话', 'success')
    }
    return sessionId
  } catch {
    return null
  } finally {
    busy.value.sessionAction = false
  }
}

async function renameCurrentSession() {
  if (!selectedSessionId.value) return
  busy.value.sessionAction = true
  try {
    const updated = await apiPatch(`/api/chat/sessions/${selectedSessionId.value}`, {
      user_id: resolvedUserId.value,
      name: sessionTitleInput.value
    })
    mergeSessionCache(updated ? [updated] : [])
    await refreshSessions()
    showToast('会话已重命名', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.sessionAction = false
  }
}

async function clearCurrentSessionMessages() {
  if (!selectedSessionId.value) return
  const confirmed = window.confirm('确认清空当前会话在服务端保存的所有消息？')
  if (!confirmed) return
  busy.value.sessionAction = true
  try {
    await apiDelete(`/api/chat/sessions/${selectedSessionId.value}/messages?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    qaMessages.value = []
    resetQaFlow()
    showToast('会话消息已清空', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.sessionAction = false
  }
}

async function deleteCurrentSession() {
  if (!selectedSessionId.value) return
  const confirmed = window.confirm('确认删除当前会话？删除后不可恢复。')
  if (!confirmed) return
  busy.value.sessionAction = true
  try {
    const deletingSessionId = selectedSessionId.value
    await apiDelete(`/api/chat/sessions/${deletingSessionId}?user_id=${encodeURIComponent(resolvedUserId.value)}`)
    removeSessionFromCache(deletingSessionId)
    selectedSessionId.value = ''
    sessionTitleInput.value = ''
    qaMessages.value = []
    resetQaFlow()
    await refreshSessions()
    showToast('会话已删除', 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.sessionAction = false
  }
}

function clearLocalMessages() {
  qaMessages.value = []
  resetQaFlow()
}

function closeSourcePreview() {
  sourcePreview.value.open = false
}

async function openQaSource(source) {
  if (!source || typeof source !== 'object') return
  const docId = source.doc_id || selectedDocId.value || selectedSession.value?.doc_id || ''
  if (!docId) {
    showToast('该来源缺少文档定位信息', 'error')
    return
  }
  sourcePreview.value = {
    open: true,
    loading: true,
    title: '问答来源预览',
    sourceLabel: source.source || '',
    page: Number.isFinite(Number(source.page)) ? Number(source.page) : null,
    chunk: Number.isFinite(Number(source.chunk)) ? Number(source.chunk) : null,
    snippet: '',
    error: '',
  }
  try {
    const params = new URLSearchParams()
    params.set('user_id', resolvedUserId.value)
    if (source.page !== undefined && source.page !== null) params.set('page', String(source.page))
    if (source.chunk !== undefined && source.chunk !== null) params.set('chunk', String(source.chunk))
    if (source.snippet) params.set('q', String(source.snippet).slice(0, 120))
    const res = await apiGet(`/api/docs/${docId}/preview?${params.toString()}`)
    sourcePreview.value = {
      open: true,
      loading: false,
      title: `${res.filename || '文档'} 原文片段`,
      sourceLabel: res.source || source.source || res.filename || '',
      page: res.page ?? null,
      chunk: res.chunk ?? null,
      snippet: res.snippet || '',
      error: '',
    }
  } catch (err) {
    sourcePreview.value.loading = false
    sourcePreview.value.error = toUserFacingApiErrorMessage(err, '暂时无法加载来源片段，请稍后重试')
  }
}

function applyDocContextSelection() {
  if (!entryDocContextId.value) return
  if (docsInKb.value.some((doc) => doc.id === entryDocContextId.value)) {
    selectedDocId.value = entryDocContextId.value
  }
}

const syncingRouteContext = ref(false)

function buildAutoQaRouteKey(parsed) {
  return [
    parsed.qaFrom || '',
    parsed.qaMode || '',
    parsed.qaQuestion || '',
    parsed.kbId || '',
    parsed.docId || '',
  ].join('|')
}

async function clearTransientQaRouteParams(options = {}) {
  const { clearFocus = false } = options
  const nextQuery = { ...(route.query || {}) }
  let changed = false
  for (const key of ['qa_mode', 'qa_autosend', 'qa_question', 'qa_from']) {
    if (Object.prototype.hasOwnProperty.call(nextQuery, key)) {
      delete nextQuery[key]
      changed = true
    }
  }
  if (clearFocus && Object.prototype.hasOwnProperty.call(nextQuery, 'focus')) {
    delete nextQuery.focus
    changed = true
  }
  if (!changed) return
  await router.replace({ path: route.path, query: nextQuery })
}

async function maybeAutoAskFromRoute() {
  const parsed = parseRouteContext(route.query)
  if (parsed.qaMode) {
    qaMode.value = normalizeQaMode(parsed.qaMode)
  }
  if (parsed.qaQuestion) {
    qaInput.value = parsed.qaQuestion
  }
  const shouldAutoSend = parsed.qaMode === 'explain' && parsed.qaAutoSend === '1' && !!parsed.qaQuestion
  if (!shouldAutoSend || busy.value.qa) return

  const routeKey = buildAutoQaRouteKey(parsed)
  if (lastAutoQaRouteKey.value === routeKey) return

  if (!selectedKbId.value && !selectedSessionId.value) {
    if (autoQaMissingContextToastKey.value !== routeKey) {
      autoQaMissingContextToastKey.value = routeKey
      showToast('请先选择资料库后再发送', 'error')
    }
    return
  }

  lastAutoQaRouteKey.value = routeKey
  try {
    await askQuestion({ modeOverride: parsed.qaMode })
  } finally {
    await clearTransientQaRouteParams({
      clearFocus: parsed.qaFrom === 'quiz_wrong',
    })
  }
}

async function syncFromRoute(options = {}) {
  if (syncingRouteContext.value) return
  syncingRouteContext.value = true
  try {
    try {
      await appContext.applyRouteContext(route.query, {
        ensureKbs: options.ensureKbs === true,
        fallbackToFirstKb: true,
      })
    } catch {
      // error toast handled globally
    }
    if (options.refreshDocs && selectedKbId.value) {
      await refreshDocsInKb()
    }
    applyDocContextSelection()
    await maybeAutoAskFromRoute()
  } finally {
    syncingRouteContext.value = false
  }
}

async function refreshAdaptiveTransparency() {
  if (!qaAutoAdapt.value || !resolvedUserId.value) return
  adaptiveLoading.value = true
  adaptiveError.value = ''
  try {
    const [profile, plan] = await Promise.all([
      getProfile(resolvedUserId.value),
      getDifficultyPlan(resolvedUserId.value),
    ])
    adaptiveProfile.value = profile || null
    adaptivePlan.value = plan || null
    qaAbilityLevel.value = normalizeAbilityLevel(profile?.ability_level || qaAbilityLevel.value)
  } catch {
    adaptiveError.value = '依据暂不可用，已使用默认画像展示。'
    if (!adaptiveProfile.value) {
      adaptiveProfile.value = { ability_level: qaAbilityLevel.value }
    }
  } finally {
    adaptiveLoading.value = false
  }
}

async function askQuestion(options = {}) {
  const requestedMode = normalizeQaMode(options?.modeOverride || qaMode.value)
  if (qaActionBlocked.value) {
    showToast('先完成模型接入配置后再开始提问', 'error')
    return
  }
  if (!selectedKbId.value || !qaInput.value.trim() || busy.value.qa) return
  
  const question = qaInput.value.trim()
  const submitFingerprint = buildQaSubmitFingerprint(question)
  if (isDuplicateQaSubmit(submitFingerprint)) return
  qaInput.value = ''
  qaMessages.value.push({ role: 'question', content: question })
  const placeholderIndex = qaMessages.value.push(makeAssistantPlaceholder(requestedMode)) - 1
  
  resetQaFlow()
  updateQaFlow({
    phase: 'retrieving',
    message: '正在查找相关参考内容...',
  })
  busy.value.qa = true
  scrollToBottom()
  let activeSessionId = selectedSessionId.value
  
  try {
    if (!activeSessionId) {
      activeSessionId = await createSession({ silent: true, activate: false })
    }
    const payload = buildQaPayload(question, activeSessionId, requestedMode)

    let streamDone = false
    await apiSsePost('/api/qa/stream', payload, {
      onStatus(data = {}) {
        const nextPhase = data.stage || qaFlow.value.phase
        updateQaFlow({
          phase: nextPhase,
          message: data.message || qaFlow.value.message,
          result: data.result ?? qaFlow.value.result,
          retrievedCount: Number.isFinite(Number(data.retrieved_count))
            ? Number(data.retrieved_count)
            : qaFlow.value.retrievedCount,
          timings: data.timings || {},
          errorCode: nextPhase === 'failed' ? (qaFlow.value.errorCode || 'unknown') : qaFlow.value.errorCode,
        })
        const msg = qaMessages.value[placeholderIndex]
        if (!msg || msg.role !== 'answer') return
        if (nextPhase === 'retrieving') {
          msg.status = 'pending'
          msg.streaming = true
        } else if (nextPhase === 'generating') {
          msg.status = 'streaming'
          msg.streaming = true
        } else if (nextPhase === 'saving') {
          msg.status = 'streaming'
          msg.streaming = true
        } else if (nextPhase === 'done') {
          msg.streaming = false
          if (qaFlow.value.usedFallback) {
            msg.status = 'fallback'
          } else if (data.result === 'no_results') {
            msg.status = 'done'
          } else {
            msg.status = 'done'
          }
        } else if (nextPhase === 'failed') {
          msg.status = 'error'
          msg.streaming = false
        }
      },
      onChunk(data = {}) {
        const msg = qaMessages.value[placeholderIndex]
        if (!msg || msg.role !== 'answer') return
        msg.streaming = true
        msg.status = 'streaming'
        msg.content = `${msg.content || ''}${data.delta || ''}`
        applyExplainStateToAssistantMessage(msg)
      },
      onSources(data = {}) {
        const msg = qaMessages.value[placeholderIndex]
        if (!msg || msg.role !== 'answer') return
        msg.sources = Array.isArray(data.sources) ? data.sources.map(normalizeQaSource).filter(Boolean) : []
        if (Number.isFinite(Number(data.retrieved_count))) {
          updateQaFlow({ retrievedCount: Number(data.retrieved_count) })
        }
      },
      onDone(data = {}) {
        streamDone = true
        const responseLevel = normalizeAbilityLevel(data.ability_level || qaAbilityLevel.value)
        qaAbilityLevel.value = responseLevel
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.abilityLevel = responseLevel
          msg.streaming = false
          msg.resolvedMode = normalizeQaMode(data.mode || msg.resolvedMode || msg.requestedMode)
          if ((!msg.content || !msg.content.trim()) && data.result === 'no_results') {
            msg.content = '无法找到与该问题相关的内容。'
          }
          applyExplainStateToAssistantMessage(msg)
          msg.status = qaFlow.value.usedFallback ? 'fallback' : 'done'
        }
        updateQaFlow({
          phase: 'done',
          message: data.result === 'no_results' ? '未检索到相关内容' : '回答生成完成',
          result: data.result || 'ok',
          retrievedCount: Number.isFinite(Number(data.retrieved_count))
            ? Number(data.retrieved_count)
            : qaFlow.value.retrievedCount,
          timings: data.timings || {},
          errorCode: null,
        })
        void refreshAdaptiveTransparency()
        if (!selectedSessionId.value && activeSessionId) {
          preserveQaFlowOnNextSessionLoad.value = true
          selectedSessionId.value = activeSessionId
        }
      },
      onError(data = {}) {
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.streaming = false
          msg.status = 'error'
          msg.errorCode = data.code || 'unknown'
        }
        updateQaFlow({
          phase: 'failed',
          message: data.message || '流式回答失败',
          errorCode: data.code || 'unknown',
        })
        throw streamPayloadError(data)
      },
    })

    if (streamDone) {
      await refreshSessions({ resetPage: true })
      if (!selectedSessionId.value && activeSessionId) {
        preserveQaFlowOnNextSessionLoad.value = true
        selectedSessionId.value = activeSessionId
      }
    }
  } catch (err) {
    const canFallback = isStreamErrorRetryable(err)
    if (canFallback) {
      updateQaFlow({
        phase: 'failed',
        message: '流式连接中断，正在回退到非流式请求...',
      })
      try {
        const payload = buildQaPayload(question, activeSessionId)
        const res = await apiPost('/api/qa', payload)
        const responseLevel = normalizeAbilityLevel(res?.ability_level || qaAbilityLevel.value)
        qaAbilityLevel.value = responseLevel
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.content = res?.answer || ''
          msg.sources = Array.isArray(res?.sources) ? res.sources.map(normalizeQaSource).filter(Boolean) : []
          msg.abilityLevel = responseLevel
          msg.resolvedMode = normalizeQaMode(res?.mode || msg.resolvedMode || msg.requestedMode)
          msg.streaming = false
          applyExplainStateToAssistantMessage(msg)
          msg.status = 'fallback'
          msg.errorCode = null
        }
        updateQaFlow({
          phase: 'done',
          message: '流式中断，已自动回退为非流式回答',
          usedFallback: true,
          result: res?.answer ? 'ok' : qaFlow.value.result,
          errorCode: null,
        })
        void refreshAdaptiveTransparency()
        await refreshSessions({ resetPage: true })
        if (!selectedSessionId.value && (res?.session_id || activeSessionId)) {
          preserveQaFlowOnNextSessionLoad.value = true
          selectedSessionId.value = res?.session_id || activeSessionId
        }
      } catch (fallbackErr) {
        const msg = qaMessages.value[placeholderIndex]
        if (msg && msg.role === 'answer') {
          msg.content = `错误：${fallbackErr.message}`
          msg.streaming = false
          msg.status = 'error'
          msg.errorCode = fallbackErr?.qaStream?.code || 'fallback_failed'
        }
        updateQaFlow({
          phase: 'failed',
          message: fallbackErr?.message || '问答请求失败',
          errorCode: fallbackErr?.qaStream?.code || 'fallback_failed',
        })
      }
    } else {
      const friendlyErrorMessage = toUserFacingApiErrorMessage(
        err,
        '这次回答没有成功生成，请稍后再试'
      )
      const msg = qaMessages.value[placeholderIndex]
      if (msg && msg.role === 'answer') {
        msg.content = friendlyErrorMessage
        msg.streaming = false
        msg.status = 'error'
        msg.errorCode = err?.qaStream?.code || 'request_failed'
      } else {
        qaMessages.value.push({ role: 'answer', content: friendlyErrorMessage, status: 'error' })
      }
      updateQaFlow({
        phase: 'failed',
        message: friendlyErrorMessage,
        errorCode: err?.qaStream?.code || 'request_failed',
      })
    }
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

onMounted(async () => {
  qaAutoAdapt.value = readQaAutoAdaptPreference()
  busy.value.init = true
  try {
    try {
      await appContext.loadKbs()
    } catch {
      // error toast handled globally
    }
    await Promise.all([refreshAdaptiveTransparency(), refreshSessions(), loadQaViewSettings(true)])
    await syncFromRoute({ refreshDocs: false })
    if (selectedKbId.value) {
      await refreshDocsInKb()
      applyDocContextSelection()
    } else {
      docsInKb.value = []
    }
    await refreshQaFocusOptions()
  } finally {
    busy.value.init = false
  }
})

onActivated(async () => {
  await Promise.all([loadQaViewSettings(), refreshAdaptiveTransparency()])
  await syncFromRoute({
    ensureKbs: !appContext.kbs.length,
    refreshDocs: false,
  })
  await refreshQaFocusOptions()
})

watch(
  () => route.fullPath,
  async () => {
    if (busy.value.init) return
    await syncFromRoute({ refreshDocs: false })
  }
)

watch(selectedKbId, async () => {
  if (!syncingFromSession.value && selectedSessionId.value) {
    selectedSessionId.value = ''
    sessionTitleInput.value = ''
    qaMessages.value = []
    resetQaFlow()
  }
  qaManualFocus.value = ''
  qaFocusSearch.value = ''
  qaFocusCandidate.value = ''
  qaFocusOptions.value = []
  selectedDocId.value = ''
  await Promise.all([refreshDocsInKb(), loadQaViewSettings(true)])
  applyDocContextSelection()
  await refreshQaFocusOptions()
})

watch(docsInKbLoading, (loading) => {
  busy.value.docs = !!loading
}, { immediate: true })

watch(selectedDocId, () => {
  if (!syncingFromSession.value && selectedSessionId.value) {
    selectedSessionId.value = ''
    sessionTitleInput.value = ''
    qaMessages.value = []
    resetQaFlow()
  }
  pruneQaManualFocusToCurrentDocScope()
  syncQaFocusCandidateSelection()
})

watch(selectedSessionId, async (sessionId) => {
  if (!sessionId) {
    sessionTitleInput.value = ''
    qaMessages.value = []
    resetQaFlow()
    return
  }
  const session = sessionCacheMap.value[sessionId] || sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    preserveQaFlowOnNextSessionLoad.value = false
    return
  }
  const skipFlowReset = preserveQaFlowOnNextSessionLoad.value
  preserveQaFlowOnNextSessionLoad.value = false

  sessionTitleInput.value = session.title || ''
  syncingFromSession.value = true
  try {
    if (session.kb_id && selectedKbId.value !== session.kb_id) {
      selectedKbId.value = session.kb_id
    }
    await refreshDocsInKb()
    selectedDocId.value = session.doc_id || ''
  } finally {
    syncingFromSession.value = false
  }
  if (!busy.value.qa && !skipFlowReset) {
    resetQaFlow()
  }
  await loadSessionMessages(sessionId)
})

watch(qaMessages, () => scrollToBottom(), { deep: true })

</script>

<style scoped>
.qa-stream-cursor {
  display: inline-block;
  width: 0.45rem;
  height: 1em;
  vertical-align: text-bottom;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.8;
  animation: qaCursorBlink 1s steps(2, start) infinite;
}

@keyframes qaCursorBlink {
  0%,
  49% {
    opacity: 0.8;
  }
  50%,
  100% {
    opacity: 0.15;
  }
}
</style>
