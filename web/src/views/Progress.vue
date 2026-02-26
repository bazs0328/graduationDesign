<template>
  <div class="space-y-6 md:space-y-8 max-w-6xl mx-auto">
    <!-- Top Stats Bar -->
    <section v-if="!busy.init && progress" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
      <div v-for="stat in topStats" :key="stat.label" class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm flex items-center gap-4">
        <div class="w-12 h-12 rounded-lg flex items-center justify-center" :class="stat.color">
          <component :is="stat.icon" class="w-6 h-6" />
        </div>
        <div>
          <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{{ stat.label }}</p>
          <p class="text-xl sm:text-2xl font-black">{{ stat.value }}</p>
        </div>
      </div>
    </section>
    <section v-else-if="busy.init" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
      <div v-for="index in 4" :key="`top-skeleton-${index}`" class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm">
        <SkeletonBlock type="card" :lines="3" />
      </div>
    </section>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-8">
      <!-- Left: KB Breakdown & Recommendations -->
      <div class="lg:col-span-2 space-y-8">
        <section v-if="busy.init" class="bg-card border border-border rounded-xl p-6 shadow-sm">
          <SkeletonBlock type="card" :lines="6" />
        </section>
        <LearnerProfileCard v-else :profile="profile" :kb-id="profileContextKbId" />
        <!-- KB Selector & Stats -->
        <section class="bg-card border border-border rounded-xl p-4 sm:p-6 lg:p-8 shadow-sm space-y-6 lg:space-y-8">
          <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div class="flex items-center gap-3">
              <Database class="w-6 h-6 text-primary" />
              <h2 class="text-xl md:text-2xl font-bold">知识库统计</h2>
            </div>
            <select v-model="selectedKbId" class="bg-background border border-input rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-primary text-sm min-w-[200px]">
              <option disabled value="">选择知识库…</option>
              <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
          </div>

          <div v-if="busy.init" class="py-2">
            <SkeletonBlock type="card" :lines="5" />
          </div>
          <div v-else-if="kbProgress" class="grid grid-cols-2 md:grid-cols-4 gap-6 animate-in fade-in slide-in-from-bottom-2">
            <div v-for="s in kbStatItems" :key="s.label" class="space-y-1">
              <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{{ s.label }}</p>
              <p class="text-xl font-bold">{{ s.value }}</p>
            </div>
          </div>
          <EmptyState
            v-else
            :icon="Database"
            :title="kbs.length === 0 ? '先上传文档再查看统计' : '选择知识库查看详细统计'"
            :description="kbs.length === 0 ? '当前还没有知识库，上传并解析文档后会显示知识库维度的统计数据。' : '右上角选择知识库后，可查看文档数、测验次数、问答次数和平均分。'"
            :hint="kbs.length === 0 ? '上传完成后返回本页即可自动汇总。' : '统计会随问答、摘要、测验等行为持续更新。'"
            :primary-action="kbs.length === 0 ? { label: '去上传文档' } : null"
            @primary="goToUpload"
          />
        </section>

        <!-- Recommendations -->
        <section class="bg-card border border-border rounded-xl p-4 sm:p-6 lg:p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Sparkles class="w-6 h-6 text-primary" />
              <h2 class="text-xl md:text-2xl font-bold">智能推荐</h2>
              <span v-if="recommendationsUpdatedLabel && !busy.init" class="text-xs text-muted-foreground">
                更新于 {{ recommendationsUpdatedLabel }}
              </span>
              <span v-if="busy.recommendations && !busy.init" class="text-sm text-muted-foreground flex items-center gap-2">
                <RefreshCw class="w-4 h-4 animate-spin" />
                <span>正在加载推荐...</span>
              </span>
            </div>
            <button @click="fetchRecommendations" class="p-2 hover:bg-accent rounded-lg transition-colors" :disabled="busy.recommendations">
              <RefreshCw class="w-5 h-5" :class="{ 'animate-spin': busy.recommendations }" />
            </button>
          </div>

          <div v-if="busy.init || busy.recommendations" class="space-y-4">
            <SkeletonBlock type="card" :lines="8" />
          </div>
          <template v-else>
            <div v-if="nextRecommendation" class="rounded-xl border border-primary/25 bg-primary/5 p-4 space-y-3">
              <p class="text-[10px] font-bold uppercase tracking-widest text-primary">下一步建议</p>
              <div class="flex items-start justify-between gap-3">
                <div class="space-y-1 min-w-0">
                  <p class="text-sm font-semibold truncate">
                    {{ nextRecommendation.doc_name || '文档' }} · {{ actionLabel(nextRecommendation.action?.type) }}
                  </p>
                  <div
                    v-if="nextRecommendation.reason"
                    class="progress-markdown markdown-content text-xs text-muted-foreground"
                    v-html="renderMarkdown(nextRecommendation.reason)"
                  ></div>
                </div>
                <button
                  class="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition-opacity whitespace-nowrap"
                  @click="runRecommendation(nextRecommendation, nextRecommendation.action)"
                >
                  {{ recommendationActionBtnLabel(nextRecommendation.action) }}
                </button>
              </div>
            </div>
            <div v-if="recommendations.length" class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div v-for="item in recommendations" :key="item.doc_id" class="p-5 bg-background border border-border rounded-xl hover:border-primary/30 transition-all group space-y-4">
                <div class="flex items-start justify-between gap-3">
                  <div class="flex items-center gap-2 min-w-0">
                    <FileText class="w-5 h-5 text-primary flex-shrink-0" />
                    <h4 class="font-bold truncate max-w-[180px]">{{ item.doc_name || '文档' }}</h4>
                  </div>
                  <div class="flex flex-col items-end gap-2">
                    <span class="text-[10px] px-2 py-0.5 rounded-full border font-semibold" :class="recommendationStatusClass(item.status)">
                      {{ recommendationStatusLabel(item.status) }}
                    </span>
                    <button
                      v-if="primaryRecommendationAction(item)"
                      class="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-[11px] font-semibold hover:opacity-90 transition-opacity whitespace-nowrap"
                      @click="runRecommendation(item, primaryRecommendationAction(item))"
                    >
                      {{ recommendationActionBtnLabel(primaryRecommendationAction(item)) }}
                    </button>
                  </div>
                </div>
                <div
                  v-if="item.summary"
                  class="progress-markdown markdown-content text-xs text-muted-foreground"
                  v-html="renderMarkdown(item.summary)"
                ></div>
                <div class="grid grid-cols-2 gap-3 text-[11px]">
                  <div class="rounded-md border border-border bg-accent/30 px-2 py-1.5">
                    <p class="text-muted-foreground">完成度</p>
                    <p class="font-semibold">{{ Math.round(item.completion_score || 0) }}%</p>
                  </div>
                  <div class="rounded-md border border-border bg-accent/30 px-2 py-1.5">
                    <p class="text-muted-foreground">紧急度</p>
                    <p class="font-semibold">{{ Math.round(item.urgency_score || 0) }}</p>
                  </div>
                </div>
                <div class="h-1.5 rounded-full bg-accent overflow-hidden">
                  <div class="h-full bg-primary/80 transition-all duration-500" :style="{ width: `${Math.round(item.completion_score || 0)}%` }"></div>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="action in item.actions"
                    :key="`${item.doc_id}-${action.type}-tag`"
                    class="px-2 py-1 bg-primary/10 text-primary text-[10px] font-bold rounded-full uppercase hover:bg-primary/20 transition-colors"
                    @click="runRecommendation(item, action)"
                  >
                    {{ actionLabel(action.type) }}
                  </button>
                </div>
                <div class="space-y-2">
                  <div v-for="action in item.actions" :key="`${item.doc_id}-${action.type}-reason`" class="flex gap-2 text-xs">
                    <div class="mt-1 w-1 h-1 bg-primary rounded-full flex-shrink-0"></div>
                    <div class="space-y-1">
                      <div
                        class="progress-markdown markdown-content text-muted-foreground"
                        v-html="renderMarkdown(action.reason)"
                      ></div>
                      <p v-if="recommendationActionHint(action)" class="text-[11px] text-primary">{{ recommendationActionHint(action) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <EmptyState
              v-else
              :icon="Sparkles"
              :title="selectedKbId ? '该知识库暂时没有推荐' : (kbs.length === 0 ? '先上传文档获取推荐' : '先选择知识库查看推荐')"
              :description="selectedKbId ? '通常在生成摘要、提取要点、完成测验或问答后，系统会给出下一步学习建议。' : (kbs.length === 0 ? '系统需要基于知识库内容与学习行为生成个性化推荐。' : '选择一个知识库后，系统会展示该知识库的下一步学习动作。')"
              :hint="selectedKbId ? '你可以先去测验或问答，积累学习记录后再查看推荐。' : (kbs.length === 0 ? '上传并解析文档后即可开始生成推荐。' : '推荐会附带建议原因和可执行动作。')"
              :primary-action="selectedKbId ? { label: '去测验' } : (kbs.length === 0 ? { label: '去上传文档' } : null)"
              :secondary-action="selectedKbId ? { label: '去问答', variant: 'outline' } : null"
              @primary="handleRecommendationsEmptyPrimary"
              @secondary="goToQaFromProgressContext"
            />
          </template>
        </section>

        <!-- Learning Path -->
        <section class="bg-card border border-border rounded-xl p-4 sm:p-6 lg:p-8 shadow-sm space-y-6">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <GitBranch class="w-6 h-6 text-primary" />
              <h2 class="text-xl md:text-2xl font-bold">学习路径</h2>
              <span v-if="busy.pathLoad && !busy.init" class="text-sm text-muted-foreground flex items-center gap-2">
                <RefreshCw class="w-4 h-4 animate-spin" />
                <span>正在加载学习路径...</span>
              </span>
              <span v-else-if="busy.pathBuild" class="text-sm text-muted-foreground flex items-center gap-2">
                <RefreshCw class="w-4 h-4 animate-spin" />
                <span>正在重建学习路径...</span>
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button @click="rebuildPath" class="p-2 hover:bg-accent rounded-lg transition-colors text-xs flex items-center gap-1" :disabled="busy.pathBuild || busy.pathLoad">
                <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': busy.pathBuild || busy.pathLoad }" />
                <span class="hidden sm:inline">重建</span>
              </button>
            </div>
          </div>

          <div v-if="busy.init || busy.pathLoad || busy.pathBuild" class="space-y-4">
            <SkeletonBlock type="card" :lines="8" />
          </div>
          <div v-else-if="learningPath.length" class="space-y-6">
            <div class="rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-xs text-muted-foreground">
              学习路径中的知识点已按知识库跨文档去重合并，掌握度为聚合口径。
            </div>
            <!-- Path summary -->
            <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div v-for="stat in pathSummaryCards" :key="stat.label" class="rounded-lg border border-border bg-background p-3 space-y-1">
                <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{{ stat.label }}</p>
                <p class="text-lg font-extrabold">{{ stat.value }}</p>
              </div>
            </div>

            <div class="rounded-lg border border-emerald-200 bg-emerald-50/70 p-4 space-y-2">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-sm font-bold text-emerald-800">当前可学队列</h3>
                <span class="text-[11px] text-emerald-700">
                  {{ currentLearnableQueue.length }} / {{ learningPath.filter((item) => item.priority !== 'completed').length }} 项可直接推进
                </span>
              </div>
              <div v-if="currentLearnableQueue.length" class="flex flex-wrap gap-2">
                <button
                  v-for="item in currentLearnableQueue"
                  :key="item.keypoint_id"
                  class="inline-flex items-center gap-2 px-3 py-1.5 rounded-md border border-emerald-200 bg-white text-xs hover:bg-emerald-50 transition-colors"
                  @click="goToAction(item)"
                >
                  <span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 font-bold">{{ item.step }}</span>
                  <span class="max-w-[180px] truncate">{{ item.text }}</span>
                </button>
              </div>
              <p v-else class="text-xs text-emerald-700/80">
                当前没有已解锁且未完成的知识点，先完成前置项后会自动解锁后续内容。
              </p>
            </div>

            <!-- Stage & module views -->
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div class="rounded-lg border border-border p-4 space-y-3">
                <h3 class="text-sm font-bold">阶段视图</h3>
                <div class="space-y-3 max-h-[260px] overflow-y-auto pr-1">
                  <div v-for="stage in displayStages" :key="stage.stage_id" class="rounded-lg border border-border bg-background p-3 space-y-2">
                    <div class="flex items-center justify-between gap-2">
                      <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full" :style="{ background: stageColor(stage.stage_id) }"></span>
                        <p class="font-semibold text-sm">{{ stage.name }}</p>
                      </div>
                      <span class="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                        {{ formatMinutes(stage.estimated_time || 0) }}
                      </span>
                    </div>
                    <div
                      class="progress-markdown markdown-content text-xs text-muted-foreground"
                      v-html="renderMarkdown(stage.description)"
                    ></div>
                    <div class="h-2 rounded-full bg-accent overflow-hidden">
                      <div class="h-full bg-primary transition-all duration-500" :style="{ width: `${stageProgress(stage)}%` }"></div>
                    </div>
                    <div class="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>进度 {{ stageProgress(stage) }}%</span>
                      <span>知识点 {{ stage.keypoint_ids.length }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="rounded-lg border border-border p-4 space-y-3">
                <h3 class="text-sm font-bold">模块视图</h3>
                <div class="space-y-3 max-h-[260px] overflow-y-auto pr-1">
                  <div v-for="module in displayModules" :key="module.module_id" class="rounded-lg border border-border bg-background p-3 space-y-2">
                    <div class="flex items-center justify-between gap-2">
                      <p class="font-semibold text-sm truncate">{{ module.name }}</p>
                      <span class="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                        {{ formatMinutes(module.estimated_time || 0) }}
                      </span>
                    </div>
                    <div
                      class="progress-markdown markdown-content text-xs text-muted-foreground"
                      v-html="renderMarkdown(module.description)"
                    ></div>
                    <div class="h-2 rounded-full bg-accent overflow-hidden">
                      <div class="h-full bg-emerald-500 transition-all duration-500" :style="{ width: `${moduleProgress(module)}%` }"></div>
                    </div>
                    <div class="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>进度 {{ moduleProgress(module) }}%</span>
                      <span>知识点 {{ module.keypoint_ids.length }}</span>
                    </div>
                    <p v-if="module.prerequisite_modules?.length" class="text-[11px] text-orange-500">
                      前置模块：{{ modulePrereqLabels(module).join('、') }}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <!-- ECharts graph -->
            <div class="border border-border rounded-lg bg-background p-2">
              <div class="overflow-auto rounded-md" :style="{ height: `${pathChartViewportHeight}px` }">
                <div
                  class="min-w-full"
                  :style="{ width: `${pathChartCanvasWidth}px`, height: `${pathChartCanvasHeight}px` }"
                >
                  <LearningPathGraph
                    :option="pathChartOption"
                    :width="pathChartCanvasWidth"
                    :height="pathChartCanvasHeight"
                  />
                </div>
              </div>
            </div>

            <!-- Legend -->
            <div class="space-y-2 text-xs text-muted-foreground">
              <div class="flex flex-wrap items-center gap-4">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-foreground">状态颜色：</span>
                  <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-emerald-500 inline-block"></span> 当前可学</span>
                  <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-orange-400 inline-block"></span> 阻塞</span>
                  <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-slate-400 inline-block"></span> 已掌握</span>
                </div>
                <span class="text-border">|</span>
                <div class="flex items-center gap-3">
                  <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rounded-full border border-border bg-white inline-block"></span> 节点显示步骤号</span>
                  <span class="inline-flex items-center gap-1"><span class="w-3 h-3 rotate-45 bg-primary/40 inline-block"></span> 里程碑</span>
                </div>
              </div>
              <p>竖向背景带表示先修层级列，越靠右通常依赖越多。</p>
              <p>标注“KB聚合”的步骤表示该概念合并了多个文档来源。</p>
            </div>

            <!-- Step list -->
            <details class="group">
              <summary class="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                <ChevronDown class="w-4 h-4 transition-transform group-open:rotate-180" />
                查看详细步骤列表（{{ learningPath.length }} 项）
              </summary>
              <div class="mt-3 space-y-2 max-h-[320px] overflow-y-auto pr-2">
                <div v-for="item in learningPath" :key="item.keypoint_id"
                  class="flex items-start gap-3 p-3 border border-border rounded-lg text-sm"
                  :class="{
                    'opacity-50': item.priority === 'completed',
                    'border-orange-200 bg-orange-50/30': isLearningPathItemBlocked(item),
                  }">
                  <span class="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                    :class="stepBadgeClass(item.priority)">
                    {{ item.step }}
                  </span>
                  <div class="flex-1 min-w-0 space-y-1">
                    <div class="flex items-center gap-2 flex-wrap">
                      <div class="progress-item-markdown markdown-content font-medium leading-tight" v-html="renderMarkdown(item.text)"></div>
                      <span
                        class="text-[10px] px-2 py-0.5 rounded-full border font-semibold"
                        :class="learningPathItemStateClass(item)"
                      >
                        {{ learningPathItemStateLabel(item) }}
                      </span>
                      <template v-if="item.member_count > 1">
                        <span class="text-[10px] px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-primary font-semibold">
                          KB聚合
                        </span>
                        <span
                          class="text-[10px] text-muted-foreground"
                          :title="item.source_doc_names?.length ? item.source_doc_names.join('、') : undefined"
                        >
                          来自 {{ (item.source_doc_ids?.length || item.member_count) }} 个文档
                        </span>
                      </template>
                      <span v-if="item.milestone" class="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-semibold">里程碑</span>
                    </div>
                    <div class="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                      <span class="truncate max-w-[120px]">{{ item.doc_name || '文档' }}</span>
                      <span>·</span>
                      <span>{{ stageLabel(item.stage) }}</span>
                      <span>·</span>
                      <span>掌握度 {{ masteryPercent(item.mastery_level) }}%</span>
                      <span>·</span>
                      <span>难度 {{ Math.round((item.difficulty || 0) * 100) }}</span>
                      <span>·</span>
                      <span>先修层级 {{ item.path_level ?? 0 }}</span>
                      <span>·</span>
                      <span>约 {{ item.estimated_time || 0 }} 分钟</span>
                    </div>
                    <div v-if="unmetPrereqLabels(item).length" class="text-xs text-orange-500">
                      缺少前置：{{ unmetPrereqLabels(item).join('、') }}
                    </div>
                    <div v-if="(item.unlocks_count || 0) > 0" class="text-xs text-muted-foreground">
                      完成后可解锁/推进后续 {{ item.unlocks_count }} 项
                    </div>
                  </div>
                  <button v-if="item.priority !== 'completed'"
                    class="flex-shrink-0 px-3 py-1 bg-primary/10 text-primary rounded-md text-xs font-medium hover:bg-primary/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-primary/10"
                    :disabled="isLearningPathItemBlocked(item)"
                    @click="goToAction(item)">
                    {{ actionBtnLabel(item.action) }}
                  </button>
                </div>
              </div>
            </details>
          </div>

          <!-- Empty state -->
          <EmptyState
            v-else-if="!busy.pathLoad && !busy.pathBuild"
            :icon="GitBranch"
            title="先生成知识点，再构建学习路径"
            description="学习路径依赖知识点数据与掌握度信息。为文档提取要点后，系统才能分析依赖关系并规划学习顺序。"
            hint="建议先进入摘要页面提取要点，然后返回此页查看路径。"
            :primary-action="{ label: '去摘要/提取要点' }"
            :secondary-action="{ label: '去上传文档', variant: 'outline' }"
            @primary="goToSummaryFromProgress"
            @secondary="goToUpload"
          />
        </section>
      </div>

    <!-- Right: Activity Feed -->
      <section class="bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col h-[750px]">
        <div class="flex items-center gap-3 mb-6">
          <Activity class="w-6 h-6 text-primary" />
          <h2 class="text-xl font-bold">最近动态</h2>
        </div>

        <div class="flex-1 overflow-y-auto space-y-6 pr-2">
          <div v-if="busy.init" class="space-y-4">
            <SkeletonBlock type="list" :lines="6" />
          </div>
          <EmptyState
            v-else-if="activity.length === 0"
            class="h-full"
            :icon="Clock"
            :title="selectedKbId ? '还没有最近动态' : (kbs.length === 0 ? '先上传文档开始学习记录' : '选择知识库后开始积累动态')"
            :description="selectedKbId ? '完成摘要、问答或测验后，这里会记录最近学习行为。' : (kbs.length === 0 ? '上传文档、提取要点、问答和测验都会写入活动流。' : '选择知识库后进行问答或测验，动态会自动更新。')"
            :hint="selectedKbId ? '可以先发起一次测验，快速产生首条学习记录。' : '活动流可用于展示学习节奏与近期进展。'"
            size="sm"
            :primary-action="selectedKbId ? { label: '去测验' } : (kbs.length === 0 ? { label: '去上传文档' } : null)"
            @primary="handleActivityEmptyPrimary"
          />
          <div v-for="(item, idx) in activity" :key="idx" class="relative pl-6 border-l-2 border-border pb-6 last:pb-0">
            <div class="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-background border-2 border-primary"></div>
            <div class="space-y-1">
              <p class="text-sm font-bold leading-none">{{ activityLabel(item) }}</p>
              <p v-if="item.doc_name" class="text-xs text-primary font-medium">{{ item.doc_name }}</p>
              <div
                v-if="item.detail"
                class="progress-markdown markdown-content text-xs text-muted-foreground"
                v-html="renderMarkdown(item.detail)"
              ></div>
              <div v-if="item.score !== null" class="mt-2 inline-flex items-center gap-2 px-2 py-1 bg-secondary rounded text-[10px] font-bold">
                得分：{{ Math.round(item.score * 100) }}%（{{ item.total }} 题）
              </div>
              <p class="text-[10px] text-muted-foreground pt-1">{{ new Date(item.timestamp).toLocaleString() }}</p>
            </div>
          </div>
        </div>
        <div
          v-if="!busy.init && activity.length > 0"
          class="mt-4 pt-4 border-t border-border/70 flex items-center justify-between gap-3 text-xs"
        >
          <span class="text-muted-foreground">已显示 {{ activity.length }} / {{ activityTotal }}</span>
          <button
            v-if="activityHasMore"
            class="px-3 py-1.5 rounded border border-border hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="busy.activityMore"
            @click="loadMoreActivity"
          >
            {{ busy.activityMore ? '加载中…' : '加载更多' }}
          </button>
          <span v-else class="text-muted-foreground">已显示全部</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, computed, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  FileText,
  PenTool,
  MessageSquare,
  Database,
  Activity,
  Sparkles,
  RefreshCw,
  Clock,
  TrendingUp,
  GitBranch,
  ChevronDown,
} from 'lucide-vue-next'
import { apiGet, getProfile, buildLearningPath } from '../api'
import { useToast } from '../composables/useToast'
import { useAppContextStore } from '../stores/appContext'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { MASTERY_MASTERED, masteryPercent } from '../utils/mastery'
import { renderMarkdown } from '../utils/markdown'
import { buildRouteContextQuery, normalizeDifficulty } from '../utils/routeContext'
import {
  LEARNING_PATH_CHART_LAYOUT,
  buildLearningPathChartLayout,
  learningPathEdgeKey,
} from '../utils/learningPathChartLayout'

const { showToast } = useToast()
const LearnerProfileCard = defineAsyncComponent({
  loader: () => import('../components/LearnerProfileCard.vue'),
  loadingComponent: SkeletonBlock,
  delay: 0,
  suspensible: false,
})
const LearningPathGraph = defineAsyncComponent({
  loader: () => import('../components/progress/LearningPathGraph.vue'),
  loadingComponent: SkeletonBlock,
  delay: 0,
  suspensible: false,
})

const STAGE_ORDER = ['foundation', 'intermediate', 'advanced', 'application']
const STAGE_META = {
  foundation: { name: '基础阶段', description: '先建立核心概念与术语理解。' },
  intermediate: { name: '进阶阶段', description: '连接概念并形成系统化理解。' },
  advanced: { name: '高级阶段', description: '攻克复杂推理与综合分析问题。' },
  application: { name: '应用阶段', description: '迁移到实战场景并完成综合应用。' },
}
const STAGE_COLOR_MAP = {
  foundation: '#3b82f6',
  intermediate: '#10b981',
  advanced: '#f59e0b',
  application: '#ef4444',
}
const PROGRESS_REC_CACHE_TTL_MS = 5 * 60 * 1000
const PROGRESS_REC_CACHE_PREFIX = 'gradtutor_progress_rec_v1:'

const router = useRouter()
const route = useRoute()
const appContext = useAppContextStore()
appContext.hydrate()
const resolvedUserId = computed(() => appContext.resolvedUserId || 'default')
const progress = ref(null)
const profile = ref(null)
const activity = ref([])
const activityTotal = ref(0)
const activityLimit = ref(30)
const activityHasMore = ref(false)
const recommendations = ref([])
const nextRecommendation = ref(null)
const recommendationsUpdatedAt = ref('')
const learningPath = ref([])
const learningPathEdges = ref([])
const learningPathStages = ref([])
const learningPathModules = ref([])
const learningPathSummary = ref({})
const kbs = computed(() => appContext.kbs)
const selectedKbId = computed({
  get: () => appContext.selectedKbId,
  set: (value) => appContext.setSelectedKbId(value),
})
const busy = ref({
  init: false,
  recommendations: false,
  pathLoad: false,
  pathBuild: false,
  activityMore: false,
})

const topStats = computed(() => {
  if (!progress.value) return []
  return [
    { label: '文档数', value: progress.value.total_docs, icon: FileText, color: 'bg-blue-500/10 text-blue-500' },
    { label: '测验数', value: progress.value.total_attempts, icon: PenTool, color: 'bg-orange-500/10 text-orange-500' },
    { label: '问答数', value: progress.value.total_questions, icon: MessageSquare, color: 'bg-green-500/10 text-green-500' },
    { label: '平均分', value: `${Math.round(progress.value.avg_score * 100)}%`, icon: TrendingUp, color: 'bg-purple-500/10 text-purple-500' },
  ]
})

const kbProgress = computed(() => {
  if (!progress.value || !selectedKbId.value) return null
  return progress.value.by_kb.find((kb) => kb.kb_id === selectedKbId.value) || null
})

const profileContextKbId = computed(() => selectedKbId.value || kbs.value[0]?.id || '')

const kbStatItems = computed(() => {
  if (!kbProgress.value) return []
  return [
    { label: '文档', value: kbProgress.value.total_docs },
    { label: '测验', value: kbProgress.value.total_attempts },
    { label: '问答', value: kbProgress.value.total_questions },
    { label: '平均分', value: `${Math.round(kbProgress.value.avg_score * 100)}%` },
  ]
})

const itemById = computed(() => {
  const map = {}
  for (const item of learningPath.value) {
    map[item.keypoint_id] = item
  }
  return map
})

const displayStages = computed(() => {
  if (learningPathStages.value.length) return learningPathStages.value
  if (!learningPath.value.length) return []
  const grouped = {}
  for (const item of learningPath.value) {
    const stageId = item.stage || 'foundation'
    if (!grouped[stageId]) grouped[stageId] = []
    grouped[stageId].push(item)
  }
  return STAGE_ORDER
    .filter((stageId) => grouped[stageId]?.length)
    .map((stageId) => ({
      stage_id: stageId,
      name: stageLabel(stageId),
      description: STAGE_META[stageId]?.description || '',
      keypoint_ids: grouped[stageId].map((item) => item.keypoint_id),
      estimated_time: grouped[stageId].reduce((sum, item) => sum + (item.estimated_time || 0), 0),
      milestone_keypoint_id: grouped[stageId].find((item) => item.milestone)?.keypoint_id || grouped[stageId][grouped[stageId].length - 1]?.keypoint_id,
    }))
})

const displayModules = computed(() => {
  if (learningPathModules.value.length) return learningPathModules.value
  if (!learningPath.value.length) return []
  const grouped = {}
  for (const item of learningPath.value) {
    const moduleId = item.module || `doc-${item.doc_id}`
    if (!grouped[moduleId]) {
      grouped[moduleId] = {
        module_id: moduleId,
        name: item.doc_name ? `${item.doc_name}模块` : `模块 ${Object.keys(grouped).length + 1}`,
        description: '按文档自动分组的学习模块。',
        keypoint_ids: [],
        prerequisite_modules: [],
        estimated_time: 0,
      }
    }
    grouped[moduleId].keypoint_ids.push(item.keypoint_id)
    grouped[moduleId].estimated_time += item.estimated_time || 0
  }
  return Object.values(grouped)
})

const moduleNameMap = computed(() => {
  const map = {}
  for (const module of displayModules.value) {
    map[module.module_id] = module.name
  }
  return map
})

const summaryResolved = computed(() => {
  if (learningPathSummary.value && Object.keys(learningPathSummary.value).length) {
    return learningPathSummary.value
  }
  const totalItems = learningPath.value.length
  const completedItems = learningPath.value.filter((item) => item.priority === 'completed').length
  const totalEstimatedTime = learningPath.value.reduce((sum, item) => sum + (item.estimated_time || 0), 0)
  let currentStage = 'completed'
  for (const stage of displayStages.value) {
    const unfinished = stage.keypoint_ids.some((keypointId) => itemById.value[keypointId]?.priority !== 'completed')
    if (unfinished) {
      currentStage = stage.stage_id
      break
    }
  }
  return {
    total_items: totalItems,
    completed_items: completedItems,
    completion_rate: totalItems ? completedItems / totalItems : 0,
    total_estimated_time: totalEstimatedTime,
    stages_count: displayStages.value.length,
    modules_count: displayModules.value.length,
    current_stage: currentStage,
    current_stage_label: currentStage === 'completed' ? '全部完成' : stageLabel(currentStage),
  }
})

const pathSummaryCards = computed(() => {
  const summary = summaryResolved.value
  return [
    { label: '总时长', value: formatMinutes(summary.total_estimated_time || 0) },
    { label: '阶段数', value: summary.stages_count || 0 },
    { label: '模块数', value: summary.modules_count || 0 },
    { label: '完成度', value: `${Math.round((summary.completion_rate || 0) * 100)}%` },
    { label: '当前阶段', value: summary.current_stage_label || stageLabel(summary.current_stage) },
  ]
})

const currentLearnableQueue = computed(() => {
  return learningPath.value
    .filter((item) => item.priority !== 'completed' && item.is_unlocked !== false)
    .sort((a, b) => (Number(a.step) || 0) - (Number(b.step) || 0))
    .slice(0, 5)
})

const recommendationsUpdatedLabel = computed(() => {
  if (!recommendationsUpdatedAt.value) return ''
  const dt = new Date(recommendationsUpdatedAt.value)
  if (Number.isNaN(dt.getTime())) return ''
  return dt.toLocaleString()
})

function normalizeRecommendationAction(action) {
  if (!action || typeof action !== 'object') return null
  const fallbackPriorityMap = {
    summary: 100,
    keypoints: 95,
    review: 85,
    quiz: 80,
    qa: 65,
    challenge: 55,
  }
  return {
    ...action,
    priority: Number(action.priority) || fallbackPriorityMap[action.type] || 50,
  }
}

function normalizeRecommendationItems(items) {
  if (!Array.isArray(items)) return []
  return items.map((item) => ({
    ...item,
    completion_score: Number(item.completion_score) || 0,
    urgency_score: Number(item.urgency_score) || 0,
    actions: (item.actions || [])
      .map((action) => normalizeRecommendationAction(action))
      .filter(Boolean)
      .sort((a, b) => (b.priority || 0) - (a.priority || 0)),
  }))
}

function normalizeLearningPathItem(item) {
  if (!item || typeof item !== 'object') return item
  const sourceDocIds = Array.isArray(item.source_doc_ids)
    ? item.source_doc_ids.map((v) => String(v || '').trim()).filter(Boolean)
    : []
  const sourceDocNames = Array.isArray(item.source_doc_names)
    ? item.source_doc_names.map((v) => String(v || '').trim()).filter(Boolean)
    : []
  const prerequisiteIds = Array.isArray(item.prerequisite_ids)
    ? item.prerequisite_ids.map((v) => String(v || '').trim()).filter(Boolean)
    : []
  const unmetPrerequisiteIds = Array.isArray(item.unmet_prerequisite_ids)
    ? item.unmet_prerequisite_ids.map((v) => String(v || '').trim()).filter(Boolean)
    : []
  const legacyPrereqTexts = Array.isArray(item.prerequisites)
    ? item.prerequisites.map((v) => String(v || '').trim()).filter(Boolean)
    : []
  const hasUnlockFlag = Object.prototype.hasOwnProperty.call(item, 'is_unlocked')
  const inferredUnlocked = legacyPrereqTexts.length === 0 && unmetPrerequisiteIds.length === 0
  return {
    ...item,
    member_count: Math.max(1, Number(item.member_count) || 1),
    prerequisites: legacyPrereqTexts,
    prerequisite_ids: prerequisiteIds,
    unmet_prerequisite_ids: unmetPrerequisiteIds,
    is_unlocked: hasUnlockFlag ? item.is_unlocked !== false : inferredUnlocked,
    path_level: Math.max(0, Number(item.path_level) || 0),
    unlocks_count: Math.max(0, Number(item.unlocks_count) || 0),
    source_doc_ids: sourceDocIds,
    source_doc_names: sourceDocNames,
  }
}

function normalizeLearningPathItems(items) {
  if (!Array.isArray(items)) return []
  return items.map((item) => normalizeLearningPathItem(item)).filter(Boolean)
}

async function fetchProgress() {
  try {
    progress.value = await apiGet(`/api/progress?user_id=${encodeURIComponent(resolvedUserId.value)}`)
  } catch {
    // error toast handled globally
  }
}

async function fetchProfile() {
  try {
    profile.value = await getProfile(resolvedUserId.value)
  } catch {
    // error toast handled globally
  }
}

async function fetchActivity(options = {}) {
  const {
    reset = true,
    append = false,
    offset = null,
  } = options
  const targetOffset = reset
    ? 0
    : Math.max(0, Number.isFinite(Number(offset)) ? Number(offset) : activity.value.length)
  if (append) {
    busy.value.activityMore = true
  }
  try {
    const params = new URLSearchParams()
    params.set('user_id', resolvedUserId.value)
    params.set('limit', String(activityLimit.value))
    params.set('offset', String(targetOffset))
    const res = await apiGet(`/api/activity?${params.toString()}`)
    const items = Array.isArray(res?.items) ? res.items : []
    activity.value = append ? [...activity.value, ...items] : items
    activityTotal.value = Math.max(0, Number(res?.total) || 0)
    activityLimit.value = Math.max(1, Number(res?.limit) || activityLimit.value || 30)
    activityHasMore.value = Boolean(res?.has_more)
  } catch {
    if (!append) {
      activity.value = []
      activityTotal.value = 0
      activityHasMore.value = false
    }
    // error toast handled globally
  } finally {
    if (append) {
      busy.value.activityMore = false
    }
  }
}

async function loadMoreActivity() {
  if (busy.value.activityMore || !activityHasMore.value) return
  await fetchActivity({ reset: false, append: true, offset: activity.value.length })
}

function resetLearningPathState() {
  learningPath.value = []
  learningPathEdges.value = []
  learningPathStages.value = []
  learningPathModules.value = []
  learningPathSummary.value = {}
}

function recommendationCacheKey(kbId) {
  if (!kbId) return ''
  return `${PROGRESS_REC_CACHE_PREFIX}${resolvedUserId.value || 'default'}:${kbId}`
}

function readRecommendationCache(kbId) {
  const key = recommendationCacheKey(kbId)
  if (!key) return null
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    const savedAt = Number(parsed.saved_at || 0)
    if (!savedAt || (Date.now() - savedAt) > PROGRESS_REC_CACHE_TTL_MS) {
      sessionStorage.removeItem(key)
      return null
    }
    return parsed.payload || null
  } catch {
    return null
  }
}

function writeRecommendationCache(kbId) {
  const key = recommendationCacheKey(kbId)
  if (!key) return
  try {
    sessionStorage.setItem(key, JSON.stringify({
      saved_at: Date.now(),
      payload: {
        items: recommendations.value || [],
        next_step: nextRecommendation.value || null,
        generated_at: recommendationsUpdatedAt.value || '',
        learning_path: learningPath.value || [],
        learning_path_edges: learningPathEdges.value || [],
        learning_path_stages: learningPathStages.value || [],
        learning_path_modules: learningPathModules.value || [],
        learning_path_summary: learningPathSummary.value || {},
      },
    }))
  } catch {
    // ignore cache write failures
  }
}

function applyRecommendationsPayload(payload = {}, options = {}) {
  const { hydrateLearningPath = true } = options
  recommendations.value = normalizeRecommendationItems(payload?.items || [])
  nextRecommendation.value = payload?.next_step || null
  recommendationsUpdatedAt.value = payload?.generated_at || ''
  if (hydrateLearningPath) {
    applyLearningPathPayload(payload)
  }
}

function hydrateRecommendationsFromCache(kbId, options = {}) {
  const payload = readRecommendationCache(kbId)
  if (!payload) return false
  applyRecommendationsPayload(payload, options)
  return true
}

function applyLearningPathPayload(payload = {}) {
  learningPath.value = normalizeLearningPathItems(
    Array.isArray(payload?.learning_path)
      ? payload.learning_path
      : (payload?.items || [])
  )
  learningPathEdges.value = Array.isArray(payload?.learning_path_edges)
    ? payload.learning_path_edges
    : (payload?.edges || [])
  learningPathStages.value = Array.isArray(payload?.learning_path_stages)
    ? payload.learning_path_stages
    : (payload?.stages || [])
  learningPathModules.value = Array.isArray(payload?.learning_path_modules)
    ? payload.learning_path_modules
    : (payload?.modules || [])
  learningPathSummary.value = payload?.learning_path_summary || payload?.path_summary || {}
}

async function fetchRecommendations(options = {}) {
  const { hydrateLearningPath = true, preferCache = false } = options
  if (!selectedKbId.value) {
    if (hydrateLearningPath) resetLearningPathState()
    return
  }
  const requestKbId = selectedKbId.value
  if (preferCache && hydrateRecommendationsFromCache(requestKbId, { hydrateLearningPath })) {
    return
  }
  busy.value.recommendations = true
  if (hydrateLearningPath) {
    busy.value.pathLoad = true
    resetLearningPathState()
  }
  nextRecommendation.value = null
  recommendationsUpdatedAt.value = ''
  try {
    const res = await apiGet(`/api/recommendations?user_id=${encodeURIComponent(resolvedUserId.value)}&kb_id=${encodeURIComponent(requestKbId)}&limit=6`)
    if (selectedKbId.value !== requestKbId) return
    applyRecommendationsPayload(res, { hydrateLearningPath })
    writeRecommendationCache(requestKbId)
  } catch {
    if (selectedKbId.value === requestKbId) {
      recommendations.value = []
      if (hydrateLearningPath) resetLearningPathState()
    }
    // error toast handled globally
  } finally {
    busy.value.recommendations = false
    if (hydrateLearningPath) {
      busy.value.pathLoad = false
    }
  }
}

async function fetchLearningPath() {
  if (!selectedKbId.value) return
  const requestKbId = selectedKbId.value
  busy.value.pathLoad = true
  try {
    const res = await apiGet(`/api/learning-path?user_id=${encodeURIComponent(resolvedUserId.value)}&kb_id=${encodeURIComponent(requestKbId)}&limit=20`)
    if (selectedKbId.value !== requestKbId) return
    applyLearningPathPayload(res)
    writeRecommendationCache(requestKbId)
  } catch {
    // error toast handled globally
  } finally {
    busy.value.pathLoad = false
  }
}

async function rebuildPath() {
  if (!selectedKbId.value) return
  busy.value.pathBuild = true
  try {
    await buildLearningPath(resolvedUserId.value, selectedKbId.value, true)
    showToast('学习路径已重建', 'success')
    await fetchLearningPath()
  } catch {
    // error toast handled globally
  } finally {
    busy.value.pathBuild = false
  }
}

function activityLabel(item) {
  switch (item.type) {
    case 'document_upload': return '上传了文档'
    case 'summary_generated': return '生成了摘要'
    case 'keypoints_generated': return '生成了要点'
    case 'question_asked': return '进行了提问'
    case 'quiz_attempt': return '完成了测验'
    default: return item.type
  }
}

function actionLabel(type) {
  switch (type) {
    case 'summary': return '摘要'
    case 'keypoints': return '要点'
    case 'quiz': return '测验'
    case 'qa': return '问答'
    case 'review': return '复习'
    case 'challenge': return '挑战'
    default: return type
  }
}

function difficultyLabel(value) {
  const normalized = normalizeDifficulty(value)
  if (normalized === 'easy') return '简单'
  if (normalized === 'medium') return '中等'
  if (normalized === 'hard') return '困难'
  return ''
}

function recommendationFocusConcept(action) {
  const concepts = action?.params?.focus_concepts
  if (!Array.isArray(concepts)) return ''
  const first = concepts.find((item) => typeof item === 'string' && item.trim())
  return first ? first.trim() : ''
}

function recommendationActionHint(action) {
  if (!action) return ''
  if (action.type === 'quiz') {
    const label = difficultyLabel(action?.params?.difficulty)
    if (label) {
      return `推荐难度：${label}`
    }
  }
  if (action.type === 'review') {
    const concepts = action?.params?.focus_concepts
    if (Array.isArray(concepts) && concepts.length) {
      return `重点：${concepts.slice(0, 3).join('、')}`
    }
  }
  if (action.type === 'challenge') {
    const label = difficultyLabel(action?.params?.difficulty)
    if (label) {
      return `建议难度：${label}`
    }
  }
  return ''
}

function primaryRecommendationAction(item) {
  const actions = item?.actions || []
  if (!actions.length) return null
  return [...actions].sort((a, b) => (b.priority || 0) - (a.priority || 0))[0]
}

function recommendationActionBtnLabel(action) {
  if (action?.cta) return action.cta
  switch (action?.type) {
    case 'summary': return '去生成摘要'
    case 'keypoints': return '去提取要点'
    case 'quiz': return '去测验'
    case 'qa': return '去问答'
    case 'review': return '去复习'
    case 'challenge': return '去挑战'
    default: return '去执行'
  }
}

function goToUpload() {
  router.push({ path: '/upload' })
}

function goToQuizFromProgressContext() {
  if (!selectedKbId.value) return
  router.push({
    path: '/quiz',
    query: buildRouteContextQuery({
      kbId: selectedKbId.value,
    }),
  })
}

function goToQaFromProgressContext() {
  if (!selectedKbId.value) return
  router.push({
    path: '/qa',
    query: buildRouteContextQuery({
      kbId: selectedKbId.value,
    }),
  })
}

function goToSummaryFromProgress() {
  router.push({
    path: '/summary',
    query: buildRouteContextQuery({
      kbId: selectedKbId.value,
    }),
  })
}

function handleRecommendationsEmptyPrimary() {
  if (selectedKbId.value) {
    goToQuizFromProgressContext()
    return
  }
  if (!kbs.value.length) {
    goToUpload()
  }
}

function handleActivityEmptyPrimary() {
  if (selectedKbId.value) {
    goToQuizFromProgressContext()
    return
  }
  if (!kbs.value.length) {
    goToUpload()
  }
}

function recommendationStatusLabel(status) {
  switch (status) {
    case 'blocked': return '待准备'
    case 'ready_for_practice': return '待练习'
    case 'needs_practice': return '需巩固'
    case 'ready_for_challenge': return '可挑战'
    case 'on_track': return '进行中'
    default: return '待处理'
  }
}

function recommendationStatusClass(status) {
  switch (status) {
    case 'blocked': return 'text-red-700 bg-red-50 border-red-200'
    case 'ready_for_practice': return 'text-amber-700 bg-amber-50 border-amber-200'
    case 'needs_practice': return 'text-orange-700 bg-orange-50 border-orange-200'
    case 'ready_for_challenge': return 'text-emerald-700 bg-emerald-50 border-emerald-200'
    case 'on_track': return 'text-blue-700 bg-blue-50 border-blue-200'
    default: return 'text-muted-foreground bg-accent border-border'
  }
}

function runRecommendation(item, action) {
  if (!action) return
  const focusConcept = recommendationFocusConcept(action)
  switch (action.type) {
    case 'summary':
    case 'keypoints': {
      if (!item?.doc_id) return
      router.push({
        path: '/summary',
        query: buildRouteContextQuery({ docId: item.doc_id }),
      })
      return
    }
    case 'quiz':
    case 'challenge': {
      const difficulty = normalizeDifficulty(action?.params?.difficulty)
      router.push({
        path: '/quiz',
        query: buildRouteContextQuery({
          kbId: selectedKbId.value,
          docId: item?.doc_id,
          focus: focusConcept,
          difficulty,
        }),
      })
      return
    }
    case 'qa':
    case 'review': {
      router.push({
        path: '/qa',
        query: buildRouteContextQuery({
          kbId: selectedKbId.value,
          docId: item?.doc_id,
          focus: focusConcept,
        }),
      })
      return
    }
    default:
      return
  }
}

function stageLabel(stageId) {
  return STAGE_META[stageId]?.name || stageId || '阶段'
}

function stageColor(stageId) {
  return STAGE_COLOR_MAP[stageId] || '#64748b'
}

function formatMinutes(minutes) {
  const m = Number(minutes) || 0
  if (m >= 60) {
    const h = Math.floor(m / 60)
    const r = m % 60
    return r ? `${h}h${r}m` : `${h}h`
  }
  return `${m}m`
}

function stageProgress(stage) {
  if (!stage?.keypoint_ids?.length) return 0
  const completed = stage.keypoint_ids.filter((keypointId) => itemById.value[keypointId]?.priority === 'completed').length
  return Math.round((completed / stage.keypoint_ids.length) * 100)
}

function moduleProgress(module) {
  if (!module?.keypoint_ids?.length) return 0
  const completed = module.keypoint_ids.filter((keypointId) => itemById.value[keypointId]?.priority === 'completed').length
  return Math.round((completed / module.keypoint_ids.length) * 100)
}

function modulePrereqLabels(module) {
  return (module.prerequisite_modules || []).map((moduleId) => moduleNameMap.value[moduleId] || moduleId)
}

function isLearningPathItemBlocked(item) {
  if (!item || item.priority === 'completed') return false
  return item.is_unlocked === false
}

function unmetPrereqLabels(item) {
  if (!item) return []
  const labels = Array.isArray(item.unmet_prerequisite_ids)
    ? item.unmet_prerequisite_ids
      .map((kpId) => itemById.value[kpId]?.text || '')
      .filter((text) => typeof text === 'string' && text.trim())
    : []
  if (labels.length) return labels
  return Array.isArray(item.prerequisites) ? item.prerequisites : []
}

function learningPathItemStateLabel(item) {
  if (!item) return ''
  if (item.priority === 'completed') return '已掌握'
  if (isLearningPathItemBlocked(item)) return '阻塞'
  return '当前可学'
}

function learningPathItemStateClass(item) {
  if (!item) return 'text-muted-foreground bg-accent border-border'
  if (item.priority === 'completed') return 'text-muted-foreground bg-accent border-border'
  if (isLearningPathItemBlocked(item)) return 'text-orange-700 bg-orange-50 border-orange-200'
  return 'text-emerald-700 bg-emerald-50 border-emerald-200'
}

function learningPathNodeState(item) {
  if (!item) return 'locked'
  if (item.priority === 'completed') return 'completed'
  if (isLearningPathItemBlocked(item)) return 'blocked'
  return 'learnable'
}

function learningPathNodeColor(item) {
  switch (learningPathNodeState(item)) {
    case 'completed':
      return '#94a3b8'
    case 'blocked':
      return '#fb923c'
    case 'learnable':
      return '#10b981'
    default:
      return '#64748b'
  }
}

function learningPathNodeBorderColor(item) {
  switch (learningPathNodeState(item)) {
    case 'completed':
      return '#64748b'
    case 'blocked':
      return '#ea580c'
    case 'learnable':
      return '#059669'
    default:
      return '#475569'
  }
}

// -- Learning path chart --
const pathChartLayout = computed(() => buildLearningPathChartLayout(
  learningPath.value,
  learningPathEdges.value,
))

const pathChartCanvasWidth = computed(() => (
  pathChartLayout.value.canvasWidth || LEARNING_PATH_CHART_LAYOUT.minCanvasWidth
))

const pathChartCanvasHeight = computed(() => (
  pathChartLayout.value.canvasHeight || LEARNING_PATH_CHART_LAYOUT.minCanvasHeight
))

const pathChartViewportHeight = computed(() => (
  pathChartLayout.value.viewportHeight || LEARNING_PATH_CHART_LAYOUT.minViewportHeight
))

const pathChartOption = computed(() => {
  if (!learningPath.value.length) return {}

  const layout = pathChartLayout.value
  const chartHeight = pathChartCanvasHeight.value
  const {
    leftPadding,
    topPadding,
    columnGap,
    bandTop,
    bandWidth,
    headerPillTop,
    headerPillHeight,
    separatorBottomPadding,
  } = LEARNING_PATH_CHART_LAYOUT
  const bandHeight = Math.max(0, chartHeight - (bandTop + separatorBottomPadding))
  const separatorTop = bandTop
  const separatorBottom = chartHeight - separatorBottomPadding
  const levelValues = layout.levelValues || []
  const levelCounts = layout.levelCounts || {}
  const nodePositions = layout.nodePositions || {}
  const headerPills = layout.headerPills || []
  const edgeCurvenessByKey = layout.edgeCurvenessByKey || {}

  const nodes = learningPath.value.map((item) => {
    const stageId = item.stage || 'foundation'
    const pathLevel = Math.max(0, Number(item.path_level) || 0)
    const isMastered = item.mastery_level >= MASTERY_MASTERED
    const isBlocked = isLearningPathItemBlocked(item)
    const baseSize = 24 + Math.round((item.importance || 0.5) * 18)
    const prereqLabels = unmetPrereqLabels(item)
    const nodeStepText = String(item.step || '')
    const nodeMeta = nodePositions[item.keypoint_id] || { x: leftPadding, y: topPadding }
    return {
      id: item.keypoint_id,
      name: item.text.length > 20 ? `${item.text.slice(0, 20)}…` : item.text,
      x: nodeMeta.x,
      y: nodeMeta.y,
      symbol: item.milestone ? 'diamond' : 'circle',
      symbolSize: item.milestone ? baseSize + 6 : baseSize,
      itemStyle: {
        color: learningPathNodeColor(item),
        opacity: isMastered ? 0.35 : (isBlocked ? 0.62 : 1),
        borderColor: learningPathNodeBorderColor(item),
        borderWidth: item.milestone ? 3 : 2,
        borderType: isBlocked ? 'dashed' : 'solid',
      },
      label: {
        show: true,
        position: 'inside',
        distance: 0,
        fontSize: 10,
        fontWeight: 700,
        lineHeight: 12,
        color: '#0f172a',
        backgroundColor: 'transparent',
        borderRadius: 0,
        padding: [0, 0],
        formatter: () => nodeStepText,
      },
      tooltip: {
        formatter: () => {
          const prereqs = prereqLabels.length ? `<br/><span style="color:#f59e0b">缺少前置：${prereqLabels.join('、')}</span>` : ''
          return `<b>#${item.step || ''} ${item.text}</b><br/>状态：${learningPathItemStateLabel(item)}<br/>阶段：${stageLabel(stageId)}<br/>先修层级：${pathLevel}<br/>模块：${item.module || '—'}<br/>掌握度：${masteryPercent(item.mastery_level)}%<br/>难度：${Math.round((item.difficulty || 0) * 100)}<br/>重要性：${Math.round((item.importance || 0) * 100)}<br/>预计时长：${item.estimated_time || 0} 分钟${prereqs}`
        },
      },
    }
  })

  const nodeIdSet = new Set(nodes.map((node) => node.id))
  const links = learningPathEdges.value
    .filter((edge) => nodeIdSet.has(edge.from_id) && nodeIdSet.has(edge.to_id))
    .map((edge) => {
      const targetItem = itemById.value[edge.to_id]
      const targetBlocked = isLearningPathItemBlocked(targetItem)
      const confidence = Math.max(0, Math.min(1, Number(edge?.confidence) || 0.5))
      return {
        source: edge.from_id,
        target: edge.to_id,
        lineStyle: {
          color: targetBlocked ? '#f59e0b' : '#94a3b8',
          width: 1.6 + confidence * 1.8,
          curveness: edgeCurvenessByKey[learningPathEdgeKey(edge.from_id, edge.to_id)] ?? 0,
          opacity: targetBlocked ? 0.9 : 0.75,
          type: targetBlocked ? 'dashed' : 'solid',
        },
        symbol: ['none', 'arrow'],
        symbolSize: [0, 10],
      }
    })

  const backgroundGraphics = levelValues.map((level, idx) => ({
    type: 'rect',
    silent: true,
    z: -2,
    shape: {
      x: leftPadding - (bandWidth / 2) + idx * columnGap,
      y: bandTop,
      width: bandWidth,
      height: bandHeight,
      r: 8,
    },
    style: {
      fill: `rgba(148,163,184,${idx % 2 === 0 ? 0.05 : 0.08})`,
      stroke: 'rgba(148,163,184,0.14)',
      lineWidth: 1,
    },
  }))

  const separatorGraphics = levelValues
    .slice(1)
    .map((_, idx) => {
      const boundaryX = leftPadding + ((idx + 1) * columnGap) - (columnGap / 2)
      return {
        type: 'line',
        silent: true,
        z: -1,
        shape: {
          x1: boundaryX,
          y1: separatorTop,
          x2: boundaryX,
          y2: separatorBottom,
        },
        style: {
          stroke: 'rgba(148,163,184,0.22)',
          lineWidth: 1,
          lineDash: [4, 4],
        },
      }
    })

  const headerGraphics = headerPills.flatMap((pill) => {
    return [
      {
        type: 'rect',
        silent: true,
        z: 2,
        shape: {
          x: pill.x,
          y: headerPillTop,
          width: pill.width,
          height: headerPillHeight,
          r: 10,
        },
        style: {
          fill: 'rgba(255,255,255,0.9)',
          stroke: 'rgba(148,163,184,0.2)',
          lineWidth: 1,
          shadowColor: 'rgba(15,23,42,0.03)',
          shadowBlur: 4,
        },
      },
      {
        type: 'text',
        silent: true,
        z: 3,
        left: pill.x + 9,
        top: headerPillTop + 5,
        style: {
          text: pill.title,
          fill: '#475569',
          fontSize: 12,
          fontWeight: 700,
        },
      },
    ]
  })

  const graphics = [...backgroundGraphics, ...separatorGraphics, ...headerGraphics]

  return {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.75)', textStyle: { color: '#fff', fontSize: 12 } },
    graphic: graphics,
    series: [{
      type: 'graph',
      layout: 'none',
      // Keep nodes aligned with static `graphic` level bands; scrolling is handled by the outer container.
      roam: false,
      draggable: false,
      data: nodes,
      links,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 10],
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 2.5 },
      },
      lineStyle: { opacity: 0.65 },
    }],
    animationDuration: 650,
  }
})

function stepBadgeClass(priority) {
  const map = {
    high: 'bg-red-500/15 text-red-600 border border-red-500/30',
    medium: 'bg-yellow-500/15 text-yellow-600 border border-yellow-500/30',
    low: 'bg-green-500/15 text-green-600 border border-green-500/30',
    completed: 'bg-muted text-muted-foreground border border-border',
  }
  return map[priority] || map.medium
}

function actionBtnLabel(action) {
  const map = { study: '去学习', quiz: '去测验', review: '去复习' }
  return map[action] || '去学习'
}

function goToAction(item) {
  if (item.action === 'quiz') {
    router.push({
      path: '/quiz',
      query: buildRouteContextQuery({
        kbId: selectedKbId.value,
        focus: item.text || '',
      }),
    })
    return
  }
  router.push({
    path: '/qa',
    query: buildRouteContextQuery({
      kbId: selectedKbId.value,
      focus: item.text || '',
    }),
  })
}

const syncingRouteContext = ref(false)

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
  } finally {
    syncingRouteContext.value = false
  }
}

onMounted(async () => {
  busy.value.init = true
  try {
    try {
      await appContext.loadKbs()
    } catch {
      // error toast handled globally
    }
    await syncFromRoute({ ensureKbs: false })
    await Promise.all([
      fetchProfile(),
      fetchProgress(),
      fetchActivity(),
      selectedKbId.value
        ? fetchRecommendations({ hydrateLearningPath: true, preferCache: true })
        : Promise.resolve(),
    ])
  } finally {
    busy.value.init = false
  }
})

onActivated(async () => {
  await syncFromRoute({
    ensureKbs: !appContext.kbs.length,
  })
  if (selectedKbId.value && !busy.value.recommendations) {
    const hasRec = Array.isArray(recommendations.value) && recommendations.value.length > 0
    const hasPath = Array.isArray(learningPath.value) && learningPath.value.length > 0
    if (!hasRec || !hasPath) {
      fetchRecommendations({ hydrateLearningPath: true, preferCache: true })
    }
  }
})

watch(selectedKbId, () => {
  if (busy.value.init) return
  if (selectedKbId.value) {
    fetchRecommendations({ hydrateLearningPath: true, preferCache: true })
  } else {
    recommendations.value = []
    nextRecommendation.value = null
    recommendationsUpdatedAt.value = ''
    resetLearningPathState()
  }
})

watch(
  () => route.fullPath,
  async () => {
    if (busy.value.init) return
    await syncFromRoute({ ensureKbs: false })
  }
)
</script>
