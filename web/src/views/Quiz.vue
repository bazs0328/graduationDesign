<template>
  <div class="space-y-6 md:space-y-8 max-w-6xl mx-auto">
    <section
      v-if="hasPathContext"
      class="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 space-y-1"
    >
      <p class="text-[10px] font-bold uppercase tracking-widest text-primary">学习路径上下文</p>
      <p class="text-sm text-muted-foreground">
        <span v-if="entryKbContextId">
          当前知识库：<span class="font-semibold text-foreground">{{ entryKbContextName }}</span>
        </span>
        <span v-if="entryDocContextId">
          <span v-if="entryKbContextId"> · </span>
          当前文档：<span class="font-semibold text-foreground">{{ entryDocContextName }}</span>
        </span>
        <span v-if="entryFocusContext">
          <span v-if="entryKbContextId || entryDocContextId"> · </span>
          重点概念：<span class="font-semibold text-foreground">{{ entryFocusContext }}</span>
        </span>
      </p>
    </section>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-8">
      <!-- Left: Quiz Generation -->
      <aside class="space-y-4 md:space-y-6">
        <section class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-6">
          <div class="flex items-center gap-3">
            <PenTool class="w-6 h-6 text-primary" />
            <h2 class="text-lg sm:text-xl font-bold">测验生成</h2>
          </div>

          <div class="space-y-4">
            <KnowledgeScopePicker
              :kb-id="selectedKbId"
              :doc-id="selectedDocId"
              :kbs="kbs"
              :docs="docsInKb"
              :kb-loading="appContext.kbsLoading"
              :docs-loading="busy.docs"
              mode="kb-and-optional-doc"
              kb-label="目标知识库"
              doc-label="限定文档（可选）"
              @update:kb-id="selectedKbId = $event"
              @update:doc-id="selectedDocId = $event"
            >
              <div class="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span>题量/难度默认值来自设置中心，可在此页临时调整。</span>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 font-semibold hover:bg-accent disabled:opacity-50"
                    :disabled="settingsStore.savingUser"
                    @click="saveCurrentQuizDefaults"
                  >
                    {{ settingsStore.savingUser ? '保存中…' : '保存为默认' }}
                  </button>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 font-semibold hover:bg-accent"
                    @click="router.push('/settings')"
                  >
                    <SlidersHorizontal class="w-3 h-3" />
                    设置
                  </button>
                </div>
              </div>
            </KnowledgeScopePicker>

            <div v-if="selectedKbId" class="space-y-2">
              <div class="flex items-center justify-between gap-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">重点聚合知识点（可选）</label>
                <button
                  v-if="quizFocusConcepts.length"
                  type="button"
                  class="text-[10px] text-muted-foreground hover:text-foreground"
                  @click="clearQuizFocusConcepts"
                >
                  清空
                </button>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2">
                <input
                  v-model="quizFocusSearch"
                  type="text"
                  placeholder="搜索聚合知识点（如：牛顿定律）"
                  class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                  @keydown.enter.prevent="addSelectedQuizFocusCandidate"
                />
                <button
                  type="button"
                  class="px-3 py-2 rounded-lg border border-input bg-background text-sm hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="busy.focusKeypoints || !quizFocusCandidate"
                  @click="addSelectedQuizFocusCandidate"
                >
                  添加
                </button>
              </div>
              <select
                v-model="quizFocusCandidate"
                class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                :disabled="busy.focusKeypoints || !filteredQuizFocusOptions.length"
              >
                <option value="">{{ quizFocusSelectPlaceholder }}</option>
                <option v-for="item in filteredQuizFocusOptions" :key="item.id" :value="item.text">
                  {{ item.text }}
                </option>
              </select>
              <p class="text-[10px] text-muted-foreground">
                选项来自“当前范围内已解锁”的聚合知识点；若已选择文档，仅显示该文档相关聚合知识点。基础模式与蓝图模式都受此范围约束。
              </p>
              <p class="text-[10px] text-muted-foreground">
                当前可出题范围：{{ scopeConceptCount }} 个聚合知识点
              </p>
              <div v-if="quizFocusConcepts.length" class="flex flex-wrap gap-2">
                <span
                  v-for="(concept, idx) in quizFocusConcepts"
                  :key="`${concept}-${idx}`"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-primary/20 bg-primary/10 text-primary text-[11px] font-semibold"
                >
                  <span>{{ concept }}</span>
                  <button
                    type="button"
                    class="text-primary/80 hover:text-primary"
                    :aria-label="`移除重点知识点 ${concept}`"
                    @click="removeQuizFocusConcept(idx)"
                  >
                    ×
                  </button>
                </span>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">题目数量</label>
                <input type="number" min="1" max="20" v-model.number="quizCount" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm" />
              </div>
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">自适应模式</label>
                <button
                  class="w-full flex items-center justify-between border border-input rounded-lg px-3 py-2 text-sm transition-colors"
                  :class="autoAdapt ? 'bg-primary/10 text-primary border-primary/30' : 'bg-background text-muted-foreground'"
                  @click="autoAdapt = !autoAdapt"
                >
                  <span>{{ autoAdapt ? '开启' : '关闭' }}</span>
                  <span class="text-xs">{{ autoAdapt ? '系统自动调难度' : '手动选择难度' }}</span>
                </button>
              </div>
            </div>

            <div v-if="!autoAdapt" class="space-y-2">
              <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">难度</label>
              <select v-model="quizDifficulty" class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm">
                <option value="easy">简单</option>
                <option value="medium">中等</option>
                <option value="hard">困难</option>
              </select>
            </div>

            <div class="space-y-3 rounded-xl border border-border bg-accent/20 p-3">
              <div class="flex items-center justify-between gap-2">
                <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">组卷模式</label>
                <button
                  type="button"
                  class="px-2 py-1 rounded-md border border-input text-xs font-semibold transition-colors"
                  :class="usePaperBlueprint ? 'bg-primary/10 text-primary border-primary/30' : 'bg-background text-muted-foreground'"
                  @click="usePaperBlueprint = !usePaperBlueprint"
                >
                  {{ usePaperBlueprint ? '蓝图组卷' : '基础模式' }}
                </button>
              </div>
              <div v-if="usePaperBlueprint" class="space-y-3">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div class="space-y-1">
                    <label class="text-[11px] text-muted-foreground">试卷标题</label>
                    <input
                      v-model="paperTitle"
                      type="text"
                      maxlength="64"
                      class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                    />
                  </div>
                  <div class="space-y-1">
                    <label class="text-[11px] text-muted-foreground">时长（分钟）</label>
                    <input
                      v-model.number="paperDurationMinutes"
                      type="number"
                      min="5"
                      max="240"
                      class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                    />
                  </div>
                </div>
                <div class="space-y-2">
                  <p class="text-[11px] text-muted-foreground">题型蓝图（数量/分值/难度）</p>
                  <div class="space-y-2">
                    <div
                      v-for="section in paperSections"
                      :key="section.type"
                      class="grid grid-cols-12 gap-2 items-center"
                    >
                      <p class="col-span-12 sm:col-span-3 text-xs font-semibold">
                        {{ questionTypeLabel(section.type) }}
                      </p>
                      <input
                        v-model.number="section.count"
                        type="number"
                        min="0"
                        max="20"
                        class="col-span-4 sm:col-span-2 bg-background border border-input rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-primary text-sm"
                        :aria-label="`${questionTypeLabel(section.type)} 数量`"
                      />
                      <input
                        v-model.number="section.score_per_question"
                        type="number"
                        min="0.5"
                        max="20"
                        step="0.5"
                        class="col-span-4 sm:col-span-2 bg-background border border-input rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-primary text-sm"
                        :aria-label="`${questionTypeLabel(section.type)} 分值`"
                      />
                      <select
                        v-model="section.difficulty"
                        class="col-span-4 sm:col-span-5 bg-background border border-input rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-primary text-sm"
                        :aria-label="`${questionTypeLabel(section.type)} 难度`"
                      >
                        <option value="">跟随全局</option>
                        <option value="adaptive">自适应</option>
                        <option value="easy">简单</option>
                        <option value="medium">中等</option>
                        <option value="hard">困难</option>
                      </select>
                    </div>
                  </div>
                </div>
                <p class="text-[11px] text-muted-foreground">
                  当前蓝图总题数：{{ paperSectionTotalCount }}（默认建议不超过 20）
                </p>
              </div>
            </div>

            <Button
              class="w-full"
              size="lg"
              :disabled="!selectedKbId || !canGenerateQuiz"
              :loading="busy.quiz"
              @click="generateQuiz"
            >
              <template #icon>
                <Sparkles class="w-5 h-5" />
              </template>
              {{ busy.quiz ? '正在生成题目…' : '生成新测验' }}
            </Button>
          </div>
        </section>

        <div v-if="quizResult" class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-4 text-center">
          <h3 class="text-sm font-bold uppercase tracking-widest text-muted-foreground">上次结果</h3>
          <div class="relative inline-flex items-center justify-center">
            <svg class="w-24 h-24">
              <circle class="text-muted/20" stroke-width="8" stroke="currentColor" fill="transparent" r="40" cx="48" cy="48" />
              <circle 
                class="text-primary transition-all duration-1000 ease-out" 
                stroke-width="8" 
                :stroke-dasharray="2 * Math.PI * 40" 
                :stroke-dashoffset="2 * Math.PI * 40 * (1 - quizResult.score)" 
                stroke-linecap="round" 
                stroke="currentColor" 
                fill="transparent" 
                r="40" cx="48" cy="48" 
              />
            </svg>
            <span class="absolute text-2xl font-black">{{ Math.round(quizResult.score * 100) }}%</span>
          </div>
          <p class="text-sm font-medium">
            {{ quizResult.correct }} / {{ quizResult.total }} 正确
          </p>
          <p v-if="Number.isFinite(Number(quizResult.earned_score))" class="text-xs text-muted-foreground">
            试卷得分：{{ Number(quizResult.earned_score).toFixed(1) }} / {{ Number(quizResult.total_score || 0).toFixed(1) }}
          </p>
          <div
            v-if="Array.isArray(quizResult.section_scores) && quizResult.section_scores.length"
            class="rounded-lg border border-border bg-background p-3 text-left space-y-2"
          >
            <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">分节得分</p>
            <div class="grid grid-cols-1 gap-1 text-xs">
              <div
                v-for="sectionScore in quizResult.section_scores"
                :key="sectionScore.section_id"
                class="flex items-center justify-between"
              >
                <span class="text-muted-foreground truncate">{{ sectionScore.section_id }}</span>
                <span class="font-semibold">
                  {{ Number(sectionScore.earned || 0).toFixed(1) }} / {{ Number(sectionScore.total || 0).toFixed(1) }}
                </span>
              </div>
            </div>
          </div>
          <div v-if="hasProfileDelta" class="space-y-2 text-left">
            <p class="text-xs font-bold uppercase tracking-widest text-primary">能力变化</p>
            <div class="grid grid-cols-2 gap-3 text-xs font-semibold">
              <div class="bg-accent/40 rounded-lg p-3 space-y-1">
                <p class="text-muted-foreground">准确率</p>
                <p :class="profileDelta.recent_accuracy_delta >= 0 ? 'text-green-600' : 'text-red-600'">
                  <span>{{ profileDelta.recent_accuracy_delta >= 0 ? '+' : '' }}</span>
                  <AnimatedNumber :value="profileDelta.recent_accuracy_delta * 100" :decimals="1" />
                  %
                  <span class="ml-1">{{ profileDelta.recent_accuracy_delta >= 0 ? '↑' : '↓' }}</span>
                </p>
              </div>
              <div class="bg-accent/40 rounded-lg p-3 space-y-1">
                <p class="text-muted-foreground">挫败感</p>
                <p :class="profileDelta.frustration_delta <= 0 ? 'text-green-600' : 'text-red-600'">
                  <span>{{ profileDelta.frustration_delta >= 0 ? '+' : '' }}</span>
                  <AnimatedNumber :value="profileDelta.frustration_delta" :decimals="2" />
                  <span class="ml-1">{{ profileDelta.frustration_delta <= 0 ? '↓' : '↑' }}</span>
                </p>
              </div>
            </div>
            <div v-if="profileDelta.ability_level_changed" class="text-xs font-semibold text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
              能力等级更新！继续保持进步节奏。
            </div>
          </div>
          <div v-if="quizResult.feedback" class="mt-4 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg text-left space-y-2">
            <p class="text-xs font-bold uppercase tracking-widest text-amber-600">学习建议</p>
            <div
              class="quiz-feedback-markdown markdown-content"
              v-html="renderMarkdown(quizResult.feedback.message)"
            ></div>
            <div v-if="quizResult.next_quiz_recommendation" class="text-xs text-amber-700">
              下次建议：{{ quizResult.next_quiz_recommendation.difficulty }} 难度
              <span v-if="quizResult.next_quiz_recommendation.focus_concepts?.length">
                （重点：{{ quizResult.next_quiz_recommendation.focus_concepts.join('、') }}）
              </span>
            </div>
          </div>
        </div>
      </aside>

      <!-- Right: Quiz Content -->
      <section class="lg:col-span-2 space-y-4 md:space-y-6 relative">
        <LoadingOverlay :show="busy.quiz" message="正在根据知识库生成题目…" />
        <div v-if="quiz" class="space-y-6">
          <div v-for="(q, idx) in quiz.questions" :id="`question-${idx + 1}`" :key="idx" class="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-4 transition-all" :class="{ 'border-primary/50 ring-1 ring-primary/20': quizResult }">
            <div class="flex items-start gap-4">
              <div class="flex-shrink-0 w-8 h-8 bg-accent text-accent-foreground rounded-lg flex items-center justify-center font-bold">
                {{ idx + 1 }}
              </div>
              <div class="space-y-4 flex-1">
                <div class="quiz-question-markdown markdown-content" v-html="renderMarkdown(q.question)"></div>

                <div class="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <span class="px-2 py-0.5 rounded-full border border-border bg-accent/40">
                    {{ questionTypeLabel(resolveQuestionType(q)) }}
                  </span>
                  <span class="px-2 py-0.5 rounded-full border border-border bg-accent/40">
                    {{ Number(questionScore(q)).toFixed(1) }} 分
                  </span>
                  <span v-if="q.section_id" class="truncate">Section: {{ q.section_id }}</span>
                </div>

                <div
                  v-if="resolveQuestionType(q) === 'single_choice' || resolveQuestionType(q) === 'multiple_choice'"
                  class="grid grid-cols-1 gap-2"
                >
                  <label
                    v-for="(opt, optIdx) in normalizedQuestionOptions(q)"
                    :key="optIdx"
                    class="flex items-start sm:items-center gap-3 p-3 rounded-lg border border-border cursor-pointer transition-all hover:bg-accent/50"
                    :class="choiceOptionClass(q, idx, optIdx)"
                  >
                    <input
                      v-if="resolveQuestionType(q) === 'single_choice'"
                      type="radio"
                      :name="`q-${idx}`"
                      :value="optIdx"
                      :checked="quizAnswers[idx] === optIdx"
                      class="hidden"
                      :disabled="!!quizResult"
                      @change="setSingleChoiceAnswer(idx, optIdx)"
                    />
                    <input
                      v-else
                      type="checkbox"
                      :name="`q-${idx}`"
                      :value="optIdx"
                      :checked="isMultipleOptionChecked(idx, optIdx)"
                      class="hidden"
                      :disabled="!!quizResult"
                      @change="toggleMultipleOption(idx, optIdx)"
                    />
                    <div
                      class="w-5 h-5 border-2 border-primary flex items-center justify-center flex-shrink-0"
                      :class="resolveQuestionType(q) === 'multiple_choice' ? 'rounded-md' : 'rounded-full'"
                    >
                      <div
                        v-if="isChoiceOptionSelected(q, idx, optIdx)"
                        class="bg-primary"
                        :class="resolveQuestionType(q) === 'multiple_choice' ? 'w-2.5 h-2.5 rounded-sm' : 'w-2.5 h-2.5 rounded-full'"
                      ></div>
                    </div>
                    <span
                      class="quiz-option-markdown min-w-0 flex-1"
                      v-html="renderMarkdownInline(opt)"
                    ></span>
                    <CheckCircle2 v-if="quizResult && isChoiceOptionCorrect(q, optIdx)" class="w-5 h-5 text-green-500 ml-auto" />
                    <XCircle v-if="quizResult && isChoiceOptionWrongSelection(q, idx, optIdx)" class="w-5 h-5 text-destructive ml-auto" />
                  </label>
                </div>

                <div v-else-if="resolveQuestionType(q) === 'true_false'" class="grid grid-cols-1 gap-2">
                  <label
                    v-for="(opt, optIdx) in normalizedQuestionOptions(q)"
                    :key="optIdx"
                    class="flex items-center gap-3 p-3 rounded-lg border border-border cursor-pointer transition-all hover:bg-accent/50"
                    :class="trueFalseOptionClass(q, idx, optIdx)"
                  >
                    <input
                      type="radio"
                      :name="`q-${idx}`"
                      :checked="quizAnswers[idx] === (optIdx === 0)"
                      class="hidden"
                      :disabled="!!quizResult"
                      @change="setTrueFalseAnswer(idx, optIdx === 0)"
                    />
                    <div class="w-5 h-5 rounded-full border-2 border-primary flex items-center justify-center flex-shrink-0">
                      <div v-if="quizAnswers[idx] === (optIdx === 0)" class="w-2.5 h-2.5 bg-primary rounded-full"></div>
                    </div>
                    <span class="quiz-option-markdown min-w-0 flex-1" v-html="renderMarkdownInline(opt)"></span>
                    <CheckCircle2 v-if="quizResult && isTrueFalseOptionCorrect(q, optIdx)" class="w-5 h-5 text-green-500 ml-auto" />
                    <XCircle v-if="quizResult && isTrueFalseOptionWrongSelection(q, idx, optIdx)" class="w-5 h-5 text-destructive ml-auto" />
                  </label>
                </div>

                <div v-else class="space-y-3">
                  <div
                    v-for="blankIdx in blankCountForQuestion(q)"
                    :key="blankIdx"
                    class="space-y-1"
                  >
                    <label class="text-xs text-muted-foreground">填空 {{ blankIdx }}</label>
                    <input
                      type="text"
                      :value="fillBlankValue(idx, blankIdx - 1)"
                      class="w-full bg-background border border-input rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary text-sm"
                      :disabled="!!quizResult"
                      @input="setFillBlankAnswer(idx, blankIdx - 1, $event.target?.value || '')"
                    />
                  </div>
                  <p
                    v-if="quizResult"
                    class="text-xs text-muted-foreground"
                  >
                    参考答案：{{ formatFillBlankAnswers(q) }}
                  </p>
                </div>

                <div v-if="quizResult" class="mt-4 p-4 bg-accent/30 rounded-lg space-y-2">
                  <p class="text-xs font-bold uppercase tracking-widest text-primary">解析</p>
                  <div
                    class="quiz-explanation-markdown markdown-content"
                    v-html="renderMarkdown(quizResult.explanations[idx])"
                  ></div>
                  <div v-if="quizResult.results?.[idx] === false" class="pt-2 flex justify-end">
                    <button
                      class="px-3 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/15 transition-colors"
                      @click="goToQaExplainForWrongQuestion(idx)"
                    >
                      讲解此题
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-center pt-4">
            <Button
              v-if="!quizResult"
              size="lg"
              class="w-full sm:w-auto px-6 sm:px-12 text-base sm:text-lg font-black shadow-lg hover:scale-105"
              @click="submitQuiz"
              :loading="busy.submit"
              :disabled="busy.submit || !!quizResult || !allQuestionsAnswered"
            >
              {{ busy.submit ? '正在批改…' : '提交全部答案' }}
            </Button>
            <button
              v-else
              class="w-full sm:w-auto px-6 sm:px-12 py-4 bg-secondary text-secondary-foreground rounded-xl font-black text-base sm:text-lg shadow-lg hover:scale-105 active:scale-95 transition-all"
              @click="generateQuiz"
            >
              再测一次
            </button>
          </div>
          <div v-if="hasMasteryUpdates" class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
            <h3 class="text-lg font-bold">知识点掌握度变化</h3>
            <p v-if="isKbQuizResultContext" class="text-xs text-muted-foreground">
              以下知识点反馈已按知识库口径去重合并统计。
            </p>
            <div class="grid grid-cols-1 gap-3">
              <div v-for="mu in masteryUpdates" :key="mu.keypoint_id"
                class="flex items-center gap-3 p-3 border rounded-lg"
                :class="masteryBorderClass(mu.new_level)">
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium truncate">{{ mu.text }}</p>
                  <div class="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                    <span>{{ masteryPercent(mu.old_level) }}%</span>
                    <span>→</span>
                    <span class="font-semibold" :class="mu.new_level > mu.old_level ? 'text-green-600' : 'text-red-500'">
                      {{ masteryPercent(mu.new_level) }}%
                    </span>
                  </div>
                </div>
                <span class="px-2 py-1 text-[10px] font-bold rounded-full border" :class="masteryBadgeClass(mu.new_level)">
                  {{ masteryLabel(mu.new_level) }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="hasWrongGroups" class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-lg font-bold">错题知识点归类</h3>
                <p class="text-xs text-muted-foreground">点击题号可跳转到对应题目</p>
                <p v-if="isKbQuizResultContext" class="text-xs text-muted-foreground">
                  概念名称可能与单文档表述不同，但会映射到同一知识点。
                </p>
              </div>
              <button
                class="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity"
                @click="generateTargetedQuiz"
              >
                针对薄弱点再练
              </button>
            </div>
            <div class="grid grid-cols-1 gap-3">
              <div v-for="group in wrongQuestionGroups" :key="group.concept" class="border border-border rounded-lg p-4 bg-accent/20">
                <div
                  class="quiz-concept-markdown text-primary"
                  v-html="renderMarkdownInline(group.concept)"
                ></div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <button
                    v-for="index in group.question_indices"
                    :key="index"
                    class="px-3 py-1 text-xs font-semibold rounded-full bg-background border border-input hover:border-primary hover:text-primary transition-colors"
                    @click="scrollToQuestion(index)"
                  >
                    第 {{ index }} 题
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="bg-card border border-border rounded-xl p-4 sm:p-6 lg:p-8 min-h-[420px] flex items-center justify-center">
          <EmptyState
            :icon="PenTool"
            :title="quizEmptyTitle"
            :description="quizEmptyDescription"
            :hint="quizEmptyHint"
            size="lg"
            :primary-action="quizEmptyPrimaryAction"
            @primary="handleQuizEmptyPrimary"
          />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PenTool, Sparkles, CheckCircle2, XCircle, SlidersHorizontal } from 'lucide-vue-next'
import { apiGet, apiPost } from '../api'
import AnimatedNumber from '../components/ui/AnimatedNumber.vue'
import { useToast } from '../composables/useToast'
import { useAppKnowledgeScope } from '../composables/useAppKnowledgeScope'
import { useSettingsStore } from '../stores/settings'
import Button from '../components/ui/Button.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingOverlay from '../components/ui/LoadingOverlay.vue'
import KnowledgeScopePicker from '../components/context/KnowledgeScopePicker.vue'
import { masteryLabel, masteryPercent, masteryBadgeClass, masteryBorderClass } from '../utils/mastery'
import { renderMarkdown, renderMarkdownInline } from '../utils/markdown'
import { buildRouteContextQuery, normalizeDifficulty, parseRouteContext } from '../utils/routeContext'

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
const quiz = ref(null)
const quizAnswers = ref({})
const quizResult = ref(null)
const quizCount = ref(5)
const quizDifficulty = ref('medium')
const autoAdapt = ref(true)
const usePaperBlueprint = ref(true)
const paperTitle = ref('自动组卷')
const paperDurationMinutes = ref(20)
const paperSections = ref([])
const quizFocusConcepts = ref([])
const quizFocusSearch = ref('')
const quizFocusCandidate = ref('')
const quizFocusOptions = ref([])
const busy = ref({
  quiz: false,
  submit: false,
  docs: false,
  focusKeypoints: false,
})
const QUESTION_TYPE_LABELS = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
}
const DEFAULT_BLUEPRINT_RATIOS = {
  single_choice: 0.5,
  multiple_choice: 0.2,
  true_false: 0.15,
  fill_blank: 0.15,
}

const profileDelta = computed(() => quizResult.value?.profile_delta || null)
const hasProfileDelta = computed(() => !!profileDelta.value)
const wrongQuestionGroups = computed(() => quizResult.value?.wrong_questions_by_concept || [])
const hasWrongGroups = computed(() => wrongQuestionGroups.value.length > 0)
const masteryUpdates = computed(() => quizResult.value?.mastery_updates || [])
const hasMasteryUpdates = computed(() => masteryUpdates.value.length > 0)
const isKbQuizResultContext = computed(() => Boolean(selectedKbId.value && quizResult.value))
const entryKbContextId = computed(() => parseRouteContext(route.query).kbId)
const entryDocContextId = computed(() => parseRouteContext(route.query).docId)
const entryFocusContext = computed(() => appContext.routeContext.focus)
const hasPathContext = computed(() => Boolean(entryKbContextId.value || entryDocContextId.value || entryFocusContext.value))
const entryKbContextName = computed(() => {
  if (!entryKbContextId.value) return ''
  const kb = kbs.value.find((item) => item.id === entryKbContextId.value)
  if (kb?.name) return kb.name
  return `${entryKbContextId.value.slice(0, 8)}...`
})
const entryDocContextName = computed(() => {
  if (!entryDocContextId.value) return ''
  const doc = docsInKb.value.find((item) => item.id === entryDocContextId.value)
  if (doc?.filename) return doc.filename
  return `${entryDocContextId.value.slice(0, 8)}...`
})
const hasAnyKb = computed(() => kbs.value.length > 0)
const quizEmptyTitle = computed(() => {
  if (!hasAnyKb.value) return '先上传文档再开始测验'
  if (!selectedKbId.value) return '先选择知识库'
  return '准备好检验掌握程度了吗？'
})
const quizEmptyDescription = computed(() => {
  if (!hasAnyKb.value) return '当前还没有知识库，上传并解析文档后才能生成测验。'
  if (!selectedKbId.value) return '在左侧选择目标知识库，并按需设置题量与难度。'
  return '已选知识库后可直接生成专属测验，系统会根据配置生成题目。'
})
const quizEmptyHint = computed(() => {
  if (!hasAnyKb.value) return '上传完成后返回本页即可一键生成题目。'
  if (!selectedKbId.value) return '开启自适应模式后，系统会自动调整题目难度。'
  return '生成后可提交批改，并查看错题归类与能力变化。'
})
const quizEmptyPrimaryAction = computed(() => {
  if (!hasAnyKb.value) return { label: '去上传文档' }
  if (!selectedKbId.value) return null
  return { label: '生成新测验', loading: busy.value.quiz }
})
const scopedQuizFocusOptions = computed(() => {
  const options = Array.isArray(quizFocusOptions.value) ? quizFocusOptions.value : []
  const docId = String(selectedDocId.value || '').trim()
  if (!docId) return options
  return options.filter((item) => {
    const sourceDocIds = Array.isArray(item?.sourceDocIds) ? item.sourceDocIds : []
    return sourceDocIds.includes(docId)
  })
})
const filteredQuizFocusOptions = computed(() => {
  const keyword = String(quizFocusSearch.value || '').trim().toLowerCase()
  const selected = new Set((quizFocusConcepts.value || []).map((item) => String(item || '').trim().toLowerCase()))
  const options = Array.isArray(scopedQuizFocusOptions.value) ? scopedQuizFocusOptions.value : []
  return options
    .filter((item) => {
      const text = String(item?.text || '').trim()
      if (!text) return false
      if (selected.has(text.toLowerCase())) return false
      if (!keyword) return true
      return text.toLowerCase().includes(keyword)
    })
    .slice(0, 80)
})
const quizFocusSelectPlaceholder = computed(() => {
  if (busy.value.focusKeypoints) return '正在加载知识点...'
  if (filteredQuizFocusOptions.value.length) return '请选择知识点'
  return selectedDocId.value ? '该文档暂无可选聚合知识点' : '暂无可选聚合知识点'
})
const scopeConceptCount = computed(() => collectScopeConceptsForGenerate().length)
const canGenerateQuiz = computed(() => {
  if (busy.value.focusKeypoints) return false
  return scopeConceptCount.value > 0
})
const paperSectionTotalCount = computed(() => {
  return (paperSections.value || []).reduce((sum, section) => {
    const count = Number(section?.count || 0)
    return sum + (Number.isFinite(count) ? Math.max(0, count) : 0)
  }, 0)
})
const allQuestionsAnswered = computed(() => {
  const questions = Array.isArray(quiz.value?.questions) ? quiz.value.questions : []
  if (!questions.length) return false
  return questions.every((question, index) => isQuestionAnswered(question, quizAnswers.value[index]))
})
const OPTION_LABELS = ['A', 'B', 'C', 'D']
const effectiveQuizSettings = computed(() => settingsStore.effectiveSettings?.quiz || {})

function applyQuizDefaultsFromSettings() {
  const quizDefaults = effectiveQuizSettings.value || {}
  if (Number.isFinite(Number(quizDefaults.count_default))) {
    quizCount.value = Math.max(1, Math.min(20, Number(quizDefaults.count_default)))
  }
  if (typeof quizDefaults.auto_adapt_default === 'boolean') {
    autoAdapt.value = quizDefaults.auto_adapt_default
  }
  if (['easy', 'medium', 'hard'].includes(quizDefaults.difficulty_default)) {
    quizDifficulty.value = quizDefaults.difficulty_default
  }
}

function splitCounts(total, ratios) {
  const safeTotal = Math.max(0, Number(total) || 0)
  const keys = Object.keys(ratios || {})
  const counts = {}
  let assigned = 0
  for (const key of keys) {
    const value = Math.floor(safeTotal * Number(ratios[key] || 0))
    counts[key] = Math.max(0, value)
    assigned += counts[key]
  }
  let remainder = safeTotal - assigned
  const rankedKeys = [...keys].sort((a, b) => Number(ratios[b] || 0) - Number(ratios[a] || 0))
  for (const key of rankedKeys) {
    if (remainder <= 0) break
    counts[key] += 1
    remainder -= 1
  }
  return counts
}

function createDefaultPaperSections(total, mode = 'adaptive') {
  const counts = splitCounts(total, DEFAULT_BLUEPRINT_RATIOS)
  const sections = [
    { section_id: 'single_choice_1', type: 'single_choice', count: counts.single_choice || 0, score_per_question: 1, difficulty: mode },
    { section_id: 'multiple_choice_1', type: 'multiple_choice', count: counts.multiple_choice || 0, score_per_question: 1, difficulty: mode },
    { section_id: 'true_false_1', type: 'true_false', count: counts.true_false || 0, score_per_question: 1, difficulty: mode },
    { section_id: 'fill_blank_1', type: 'fill_blank', count: counts.fill_blank || 0, score_per_question: 1, difficulty: mode },
  ]
  if (!sections.some((item) => item.count > 0)) {
    sections[0].count = Math.max(1, Number(total) || 1)
  }
  return sections
}

function normalizeQuestionType(type) {
  const text = String(type || '').trim()
  if (text in QUESTION_TYPE_LABELS) return text
  return 'single_choice'
}

function questionTypeLabel(type) {
  return QUESTION_TYPE_LABELS[normalizeQuestionType(type)] || '单选题'
}

function resolveQuestionType(question) {
  return normalizeQuestionType(question?.type || (question?.answer_blanks ? 'fill_blank' : 'single_choice'))
}

function resolveQuestionId(question, index) {
  const raw = String(question?.question_id || '').trim()
  if (raw) return raw
  return `q-${index + 1}`
}

function normalizedQuestionOptions(question) {
  const type = resolveQuestionType(question)
  if (type === 'true_false') {
    const opts = Array.isArray(question?.options) ? question.options.slice(0, 2) : []
    if (opts.length === 2 && String(opts[0] || '').trim() && String(opts[1] || '').trim()) {
      return opts
    }
    return ['正确', '错误']
  }
  const options = Array.isArray(question?.options) ? question.options : []
  return options
}

function questionScore(question) {
  const score = Number(question?.score ?? 1)
  if (!Number.isFinite(score) || score <= 0) return 1
  return score
}

function blankCountForQuestion(question) {
  const explicit = Number(question?.blank_count)
  if (Number.isFinite(explicit) && explicit > 0) return Math.min(6, Math.max(1, Math.floor(explicit)))
  const answers = Array.isArray(question?.answer_blanks) ? question.answer_blanks : []
  if (answers.length > 0) return Math.min(6, answers.length)
  return 1
}

function fillBlankValue(questionIndex, blankIndex) {
  const raw = quizAnswers.value?.[questionIndex]
  if (Array.isArray(raw)) return String(raw[blankIndex] ?? '')
  if (blankIndex === 0) return String(raw ?? '')
  return ''
}

function setSingleChoiceAnswer(questionIndex, optionIndex) {
  quizAnswers.value = { ...quizAnswers.value, [questionIndex]: optionIndex }
}

function isMultipleOptionChecked(questionIndex, optionIndex) {
  const current = quizAnswers.value?.[questionIndex]
  return Array.isArray(current) && current.includes(optionIndex)
}

function toggleMultipleOption(questionIndex, optionIndex) {
  const current = Array.isArray(quizAnswers.value?.[questionIndex]) ? [...quizAnswers.value[questionIndex]] : []
  const exists = current.includes(optionIndex)
  const next = exists ? current.filter((item) => item !== optionIndex) : [...current, optionIndex]
  quizAnswers.value = { ...quizAnswers.value, [questionIndex]: next.sort((a, b) => a - b) }
}

function setTrueFalseAnswer(questionIndex, value) {
  quizAnswers.value = { ...quizAnswers.value, [questionIndex]: Boolean(value) }
}

function setFillBlankAnswer(questionIndex, blankIndex, value) {
  const current = Array.isArray(quizAnswers.value?.[questionIndex])
    ? [...quizAnswers.value[questionIndex]]
    : [String(quizAnswers.value?.[questionIndex] ?? '')]
  while (current.length <= blankIndex) current.push('')
  current[blankIndex] = String(value ?? '')
  quizAnswers.value = { ...quizAnswers.value, [questionIndex]: current }
}

function normalizeAnswerForSubmit(question, answer) {
  const type = resolveQuestionType(question)
  if (type === 'multiple_choice') {
    if (!Array.isArray(answer)) return []
    return answer.filter((item) => Number.isInteger(item)).map((item) => Number(item)).sort((a, b) => a - b)
  }
  if (type === 'true_false') {
    return Boolean(answer)
  }
  if (type === 'fill_blank') {
    const expected = blankCountForQuestion(question)
    if (Array.isArray(answer)) {
      return Array.from({ length: expected }, (_, idx) => String(answer[idx] ?? '').trim())
    }
    const text = String(answer ?? '').trim()
    return expected <= 1 ? (text ? [text] : ['']) : [text]
  }
  if (Number.isInteger(answer)) return Number(answer)
  return null
}

function isQuestionAnswered(question, answer) {
  const type = resolveQuestionType(question)
  if (type === 'multiple_choice') return Array.isArray(answer) && answer.length > 0
  if (type === 'true_false') return typeof answer === 'boolean'
  if (type === 'fill_blank') {
    const expected = blankCountForQuestion(question)
    if (Array.isArray(answer)) {
      if (answer.length < expected) return false
      return answer.slice(0, expected).every((item) => String(item ?? '').trim())
    }
    return expected <= 1 && Boolean(String(answer ?? '').trim())
  }
  return Number.isInteger(answer)
}

function correctOptionIndexes(question) {
  const type = resolveQuestionType(question)
  if (type === 'multiple_choice') {
    const values = Array.isArray(question?.answer_indexes) ? question.answer_indexes : (Array.isArray(question?.answer) ? question.answer : [])
    return values.filter((item) => Number.isInteger(item)).map((item) => Number(item))
  }
  if (type === 'true_false') {
    const answerBool = typeof question?.answer_bool === 'boolean'
      ? question.answer_bool
      : Boolean(question?.answer)
    return [answerBool ? 0 : 1]
  }
  const answerIndex = Number.isInteger(question?.answer_index) ? question.answer_index : null
  return answerIndex === null ? [] : [Number(answerIndex)]
}

function isChoiceOptionSelected(question, questionIndex, optionIndex) {
  const type = resolveQuestionType(question)
  if (type === 'multiple_choice') return isMultipleOptionChecked(questionIndex, optionIndex)
  return quizAnswers.value?.[questionIndex] === optionIndex
}

function isChoiceOptionCorrect(question, optionIndex) {
  return correctOptionIndexes(question).includes(optionIndex)
}

function isChoiceOptionWrongSelection(question, questionIndex, optionIndex) {
  return isChoiceOptionSelected(question, questionIndex, optionIndex) && !isChoiceOptionCorrect(question, optionIndex)
}

function isTrueFalseOptionCorrect(question, optionIndex) {
  return correctOptionIndexes(question).includes(optionIndex)
}

function isTrueFalseOptionWrongSelection(question, questionIndex, optionIndex) {
  return quizAnswers.value?.[questionIndex] === (optionIndex === 0) && !isTrueFalseOptionCorrect(question, optionIndex)
}

function choiceOptionClass(question, questionIndex, optionIndex) {
  const selected = isChoiceOptionSelected(question, questionIndex, optionIndex)
  const correct = isChoiceOptionCorrect(question, optionIndex)
  if (!quizResult.value) {
    return selected ? 'bg-primary/10 border-primary/30' : ''
  }
  if (correct) return 'bg-green-500/10 border-green-500/30'
  if (selected && !correct) return 'bg-destructive/10 border-destructive/30'
  return 'opacity-50 grayscale-[0.5]'
}

function trueFalseOptionClass(question, questionIndex, optionIndex) {
  const selected = quizAnswers.value?.[questionIndex] === (optionIndex === 0)
  const correct = isTrueFalseOptionCorrect(question, optionIndex)
  if (!quizResult.value) {
    return selected ? 'bg-primary/10 border-primary/30' : ''
  }
  if (correct) return 'bg-green-500/10 border-green-500/30'
  if (selected && !correct) return 'bg-destructive/10 border-destructive/30'
  return 'opacity-50 grayscale-[0.5]'
}

function formatFillBlankAnswers(question) {
  const answers = Array.isArray(question?.answer_blanks) ? question.answer_blanks : (Array.isArray(question?.answer) ? question.answer : [])
  if (!answers.length) return '暂无'
  return answers.map((item) => String(item ?? '').trim()).filter(Boolean).join(' / ')
}

paperSections.value = createDefaultPaperSections(quizCount.value, autoAdapt.value ? 'adaptive' : quizDifficulty.value)

async function loadQuizViewSettings(force = false) {
  try {
    await settingsStore.load({
      userId: resolvedUserId.value,
      kbId: selectedKbId.value || '',
      force,
    })
    applyQuizDefaultsFromSettings()
  } catch {
    // error toast handled globally
  }
}

async function saveCurrentQuizDefaults() {
  try {
    if (!settingsStore.systemStatus) {
      await loadQuizViewSettings(true)
    }
    settingsStore.setUserDraftSection('quiz', {
      count_default: Math.max(1, Math.min(20, Number(quizCount.value) || 5)),
      auto_adapt_default: Boolean(autoAdapt.value),
      difficulty_default: ['easy', 'medium', 'hard'].includes(quizDifficulty.value)
        ? quizDifficulty.value
        : 'medium',
    })
    await settingsStore.saveUser(resolvedUserId.value)
    if (selectedKbId.value) {
      await settingsStore.load({
        userId: resolvedUserId.value,
        kbId: selectedKbId.value,
        force: true,
      })
    }
    showToast('已保存当前测验配置为默认设置', 'success')
  } catch {
    // error toast handled globally
  }
}

function goToUpload() {
  router.push({ path: '/upload' })
}

function handleQuizEmptyPrimary() {
  if (!hasAnyKb.value) {
    goToUpload()
    return
  }
  if (!selectedKbId.value) return
  generateQuiz()
}

function normalizeQuizFocusConcepts(values = []) {
  const seen = new Set()
  const out = []
  for (const raw of values) {
    const text = String(raw ?? '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(text)
    if (out.length >= 8) break
  }
  return out
}

function normalizeScopeConcepts(values = []) {
  const seen = new Set()
  const out = []
  for (const raw of values) {
    const text = String(raw ?? '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(text)
  }
  return out
}

function collectScopeConceptsForGenerate() {
  const options = Array.isArray(scopedQuizFocusOptions.value) ? scopedQuizFocusOptions.value : []
  return normalizeScopeConcepts(options.map((item) => item?.text))
}

function addQuizFocusConcept(concept) {
  const next = normalizeQuizFocusConcepts([...(quizFocusConcepts.value || []), concept])
  quizFocusConcepts.value = next
}

function addSelectedQuizFocusCandidate() {
  const text = String(quizFocusCandidate.value || '').trim()
  if (!text) return
  addQuizFocusConcept(text)
  quizFocusCandidate.value = ''
}

function clearQuizFocusConcepts() {
  quizFocusConcepts.value = []
  quizFocusSearch.value = ''
  quizFocusCandidate.value = ''
}

function removeQuizFocusConcept(index) {
  if (!Number.isInteger(index) || index < 0 || index >= quizFocusConcepts.value.length) return
  quizFocusConcepts.value = quizFocusConcepts.value.filter((_, idx) => idx !== index)
}

function normalizeQuizFocusOptions(items = []) {
  const seenIndex = new Map()
  const out = []
  for (const item of items) {
    const id = String(item?.id || '').trim()
    const text = String(item?.text || '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    const sourceDocIds = [
      ...new Set(
        (Array.isArray(item?.source_doc_ids) ? item.source_doc_ids : [])
          .map((docId) => String(docId || '').trim())
          .filter(Boolean)
      )
    ]
    if (seenIndex.has(key)) {
      const existingIndex = seenIndex.get(key)
      const existing = out[existingIndex]
      const mergedSourceDocIds = [
        ...new Set([...(existing.sourceDocIds || []), ...sourceDocIds])
      ]
      existing.sourceDocIds = mergedSourceDocIds
      existing.sourceDocCount = mergedSourceDocIds.length
      existing.memberCount = Math.max(
        Number(existing.memberCount || 1),
        Number(item?.member_count || 1),
      )
      continue
    }
    seenIndex.set(key, out.length)
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

function syncQuizFocusCandidateSelection() {
  if (
    quizFocusCandidate.value
    && !filteredQuizFocusOptions.value.some((item) => item.text === quizFocusCandidate.value)
  ) {
    quizFocusCandidate.value = ''
  }
}

function pruneQuizFocusConceptsToCurrentDocScope() {
  if (!selectedDocId.value) return
  if (!Array.isArray(quizFocusOptions.value)) return
  if (!quizFocusOptions.value.length && busy.value.focusKeypoints) return
  const allowedTexts = new Set(
    (Array.isArray(scopedQuizFocusOptions.value) ? scopedQuizFocusOptions.value : [])
      .map((item) => String(item?.text || '').trim())
      .filter(Boolean)
  )
  const next = (Array.isArray(quizFocusConcepts.value) ? quizFocusConcepts.value : [])
    .map((item) => String(item || '').trim())
    .filter((text) => text && allowedTexts.has(text))
  const prev = Array.isArray(quizFocusConcepts.value) ? quizFocusConcepts.value : []
  if (next.length === prev.length && next.every((item, idx) => item === prev[idx])) {
    return
  }
  quizFocusConcepts.value = next
}

async function refreshQuizFocusOptions() {
  if (!selectedKbId.value) {
    quizFocusOptions.value = []
    quizFocusCandidate.value = ''
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
    quizFocusOptions.value = normalizeQuizFocusOptions(Array.isArray(res?.keypoints) ? res.keypoints : [])
  } catch {
    if (selectedKbId.value !== requestKbId) return
    quizFocusOptions.value = []
    // error toast handled globally
  } finally {
    if (selectedKbId.value === requestKbId) {
      busy.value.focusKeypoints = false
    }
  }
  pruneQuizFocusConceptsToCurrentDocScope()
  syncQuizFocusCandidateSelection()
}

function maybeAdoptRouteFocusConcept(focusText) {
  const raw = String(focusText || '').trim()
  if (!raw || quizFocusConcepts.value.length) return ''
  const scopedOptions = Array.isArray(scopedQuizFocusOptions.value) ? scopedQuizFocusOptions.value : []
  const exact = scopedOptions.find((item) => String(item?.text || '').trim() === raw)
  if (exact) {
    addQuizFocusConcept(exact.text)
    return exact.text
  }
  const normalized = raw.toLowerCase()
  const partial = scopedOptions.find((item) => String(item?.text || '').toLowerCase().includes(normalized))
  if (partial) {
    addQuizFocusConcept(partial.text)
    return partial.text
  }
  if (selectedDocId.value) return ''
  // Route-provided focus originates from internal recommendation/learning-path flows; allow as fallback.
  addQuizFocusConcept(raw)
  return raw
}

async function refreshDocsInKb() {
  if (!selectedKbId.value) {
    kbDocs.reset()
    busy.value.docs = false
    if (selectedDocId.value) selectedDocId.value = ''
    return
  }
  try {
    await kbDocs.refresh()
  } catch {
    // error toast handled globally
  }
  if (selectedDocId.value && !docsInKb.value.some((doc) => doc.id === selectedDocId.value)) {
    selectedDocId.value = ''
  }
}

async function generateQuiz(options = {}) {
  if (!selectedKbId.value) return
  const scopeConcepts = collectScopeConceptsForGenerate()
  if (!scopeConcepts.length) {
    showToast('当前范围内暂无可用于出题的已解锁聚合知识点，请先调整范围或完成前置学习。', 'warning')
    return
  }
  busy.value.quiz = true
  quiz.value = null
  quizAnswers.value = {}
  quizResult.value = null
  try {
    const payload = {
      kb_id: selectedKbId.value,
      count: quizCount.value,
      user_id: resolvedUserId.value,
      auto_adapt: autoAdapt.value
    }
    if (selectedDocId.value) {
      payload.doc_id = selectedDocId.value
    }
    payload.scope_concepts = scopeConcepts
    const explicitFocusConcepts = normalizeQuizFocusConcepts(options.focusConcepts || quizFocusConcepts.value)
    if (explicitFocusConcepts.length) {
      payload.focus_concepts = explicitFocusConcepts
    }
    if (!autoAdapt.value) {
      payload.difficulty = quizDifficulty.value
    }
    if (usePaperBlueprint.value) {
      const sections = (paperSections.value || [])
        .map((section, sectionIndex) => {
          const type = normalizeQuestionType(section?.type)
          const count = Math.max(0, Math.min(20, Number(section?.count || 0)))
          if (!count) return null
          const score = Number(section?.score_per_question || 1)
          const difficulty = String(section?.difficulty || '').trim()
          return {
            section_id: String(section?.section_id || `${type}_${sectionIndex + 1}`),
            type,
            count,
            score_per_question: Number.isFinite(score) && score > 0 ? score : 1,
            difficulty: difficulty || (autoAdapt.value ? 'adaptive' : quizDifficulty.value),
          }
        })
        .filter(Boolean)
      if (sections.length) {
        payload.paper_blueprint = {
          title: String(paperTitle.value || '自动组卷').trim() || '自动组卷',
          duration_minutes: Math.max(5, Math.min(240, Number(paperDurationMinutes.value) || 20)),
          sections,
        }
        payload.count = Math.max(1, Math.min(20, Number(paperSectionTotalCount.value || quizCount.value) || 1))
      }
    }
    const res = await apiPost('/api/quiz/generate', payload)
    quiz.value = res
    if (res?.paper_meta?.sections?.length) {
      paperSections.value = res.paper_meta.sections.map((section) => ({
        section_id: section.section_id,
        type: normalizeQuestionType(section.type),
        count: Number(section.generated_count || section.requested_count || 0),
        score_per_question: Number(section.score_per_question || 1),
        difficulty: String(section.difficulty || ''),
      }))
      paperTitle.value = String(res.paper_meta.title || paperTitle.value || '自动组卷')
      paperDurationMinutes.value = Math.max(5, Math.min(240, Number(res.paper_meta.duration_minutes || 20)))
    }
    showToast(`已生成 ${res.questions?.length || 0} 道题目`, 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.quiz = false
  }
}

async function submitQuiz() {
  if (!quiz.value || quizResult.value) return
  busy.value.submit = true
  try {
    const questions = Array.isArray(quiz.value?.questions) ? quiz.value.questions : []
    const answers = questions.map((question, idx) => ({
      question_id: resolveQuestionId(question, idx),
      answer: normalizeAnswerForSubmit(question, quizAnswers.value[idx]),
    }))
    const res = await apiPost('/api/quiz/submit', {
      quiz_id: quiz.value.quiz_id,
      answers,
      user_id: resolvedUserId.value
    })
    quizResult.value = res
    showToast(`测验已批改，得分 ${Math.round(res.score * 100)}%`, 'success')
  } catch {
    // error toast handled globally
  } finally {
    busy.value.submit = false
  }
}

function generateTargetedQuiz() {
  const concepts = [
    ...new Set(
      wrongQuestionGroups.value
        .map((group) => group.concept)
        .filter((concept) => concept && String(concept).trim())
    )
  ]
  if (!concepts.length) {
    generateQuiz()
    return
  }
  generateQuiz({ focusConcepts: concepts })
}

function formatQuizOptionLabel(optionIndex, options) {
  if (!Number.isInteger(optionIndex) || optionIndex < 0 || optionIndex >= OPTION_LABELS.length) {
    return '未作答'
  }
  const label = OPTION_LABELS[optionIndex] || `选项${optionIndex + 1}`
  const text = Array.isArray(options) ? String(options[optionIndex] ?? '').trim() : ''
  return text ? `${label}. ${text}` : label
}

function buildWrongQuestionExplainPrompt(questionIndex) {
  const q = quiz.value?.questions?.[questionIndex]
  if (!q) return ''
  const type = resolveQuestionType(q)
  const selectedAnswer = quizAnswers.value?.[questionIndex]
  const options = normalizedQuestionOptions(q)
  const optionLines = options
    .map((opt, idx) => `${OPTION_LABELS[idx] || `选项${idx + 1}`}. ${String(opt ?? '').trim()}`)
    .join('\n')
  const expectedIndexes = correctOptionIndexes(q)
  const expectedLabels = expectedIndexes.map((idx) => formatQuizOptionLabel(idx, options)).join('；')
  let myAnswerLine = '未作答'
  if (type === 'multiple_choice') {
    const picked = Array.isArray(selectedAnswer) ? selectedAnswer : []
    myAnswerLine = picked.length
      ? picked.map((idx) => formatQuizOptionLabel(idx, options)).join('；')
      : '未作答'
  } else if (type === 'true_false') {
    if (typeof selectedAnswer === 'boolean') {
      myAnswerLine = selectedAnswer ? '正确' : '错误'
    }
  } else if (type === 'fill_blank') {
    const lines = Array.isArray(selectedAnswer) ? selectedAnswer : [selectedAnswer]
    myAnswerLine = lines.map((item) => String(item ?? '').trim()).filter(Boolean).join(' / ') || '未作答'
  } else {
    myAnswerLine = Number.isInteger(selectedAnswer)
      ? formatQuizOptionLabel(selectedAnswer, options)
      : '未作答'
  }

  const expectedAnswerText = type === 'fill_blank'
    ? formatFillBlankAnswers(q)
    : (expectedLabels || '未提供')

  return [
    '请用讲解模式解析这道题，并重点解释我为什么会错、如何避免再次出错。',
    '',
    `题型：${questionTypeLabel(type)}`,
    `题干：${String(q.question || '').trim()}`,
    ...(type === 'fill_blank' ? [] : ['选项：', optionLines]),
    `我的答案：${myAnswerLine}`,
    `正确答案：${expectedAnswerText}`,
    '额外要求：请总结易错点，并给出 1-2 个自测变式问题。',
  ].join('\n')
}

function goToQaExplainForWrongQuestion(questionIndex) {
  const q = quiz.value?.questions?.[questionIndex]
  if (!q || !selectedKbId.value) return
  const explainPrompt = buildWrongQuestionExplainPrompt(questionIndex)
  if (!explainPrompt) return

  const focusConcept = Array.isArray(q.concepts)
    ? q.concepts.find((concept) => concept && String(concept).trim())
    : ''

  const query = buildRouteContextQuery(
    {
      kbId: selectedKbId.value,
      focus: focusConcept ? String(focusConcept).trim() : '',
    },
    {
      qa_mode: 'explain',
      qa_autosend: '1',
      qa_question: explainPrompt,
      qa_from: 'quiz_wrong',
    }
  )

  router.push({ path: '/qa', query })
}

function scrollToQuestion(index) {
  const target = document.getElementById(`question-${index}`)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const lastAutoContextKey = ref('')
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

    const queryDifficulty = appContext.routeContext.difficulty
    if (queryDifficulty) {
      autoAdapt.value = false
      quizDifficulty.value = queryDifficulty
    }

    const queryFocus = entryFocusContext.value
    const queryDocId = entryDocContextId.value
    if (!options.autoGenerate) return
    if ((!queryFocus && !queryDifficulty) || !selectedKbId.value) return

    const contextKey = `${selectedKbId.value}|${queryDocId}|${queryFocus}|${queryDifficulty}`
    if (lastAutoContextKey.value === contextKey) return
    lastAutoContextKey.value = contextKey

    const generateOptions = {}
    let adoptedFocus = ''
    if (queryFocus) {
      adoptedFocus = maybeAdoptRouteFocusConcept(queryFocus)
    }
    if (adoptedFocus) {
      generateOptions.focusConcepts = [adoptedFocus]
    }
    await generateQuiz(generateOptions)
  } finally {
    syncingRouteContext.value = false
  }
}

onMounted(async () => {
  try {
    await appContext.loadKbs()
  } catch {
    // error toast handled globally
  }
  await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions(), loadQuizViewSettings(true)])
  await syncFromRoute({ autoGenerate: true })
})

onActivated(async () => {
  await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions(), loadQuizViewSettings()])
  await syncFromRoute({
    ensureKbs: !appContext.kbs.length,
    autoGenerate: true,
  })
})

watch(
  () => route.fullPath,
  async () => {
    await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions(), loadQuizViewSettings()])
    await syncFromRoute({ autoGenerate: true })
  }
)

watch(selectedKbId, async () => {
  clearQuizFocusConcepts()
  quizFocusOptions.value = []
  quizFocusSearch.value = ''
  quizFocusCandidate.value = ''
  await Promise.all([refreshDocsInKb(), refreshQuizFocusOptions(), loadQuizViewSettings(true)])
})

watch(docsInKbLoading, (loading) => {
  busy.value.docs = !!loading
}, { immediate: true })

watch(selectedDocId, () => {
  pruneQuizFocusConceptsToCurrentDocScope()
  syncQuizFocusCandidateSelection()
})

watch(quizFocusOptions, () => {
  pruneQuizFocusConceptsToCurrentDocScope()
  syncQuizFocusCandidateSelection()
})

watch(quizFocusSearch, () => {
  syncQuizFocusCandidateSelection()
})

watch(quizFocusConcepts, () => {
  syncQuizFocusCandidateSelection()
})

watch(quizCount, (value) => {
  const target = Math.max(1, Math.min(20, Number(value) || 1))
  if (target !== value) {
    quizCount.value = target
    return
  }
  if (!usePaperBlueprint.value) return
  paperSections.value = createDefaultPaperSections(target, autoAdapt.value ? 'adaptive' : quizDifficulty.value)
})

watch([autoAdapt, quizDifficulty], () => {
  if (!usePaperBlueprint.value) return
  paperSections.value = paperSections.value.map((section) => ({
    ...section,
    difficulty: section?.difficulty || (autoAdapt.value ? 'adaptive' : quizDifficulty.value),
  }))
})
</script>
