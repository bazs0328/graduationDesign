<template>
  <div class="space-y-8 md:space-y-12 pb-12 md:pb-20">
    <!-- Hero Section -->
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-blue-800 to-blue-500 p-6 sm:p-8 lg:p-12 text-white shadow-2xl shadow-blue-900/30 ring-1 ring-white/10">
      <div class="absolute inset-0 bg-gradient-to-t from-black/25 to-transparent"></div>
      <div class="relative z-10 max-w-3xl space-y-6">
        <div class="inline-flex items-center gap-2 px-3 py-1 bg-white/12 border border-white/15 backdrop-blur-md rounded-full text-sm font-bold tracking-wide uppercase">
          <Sparkles class="w-4 h-4" />
          新一代学习
        </div>
        <h1 class="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-black tracking-tight leading-none text-white">
          用 <span class="text-cyan-300">AI</span> 掌握<br/>你的知识
        </h1>
        <p class="text-base sm:text-lg md:text-xl text-blue-50/90 leading-relaxed max-w-2xl font-medium">
          StudyCompass 将你的文档转化为互动学习体验，支持摘要、问答与测验等学习流程。
        </p>
        <div class="flex flex-wrap gap-3 sm:gap-4 pt-2 sm:pt-4">
          <router-link to="/upload" class="px-6 sm:px-8 py-3.5 sm:py-4 bg-white text-slate-900 rounded-2xl font-black text-base sm:text-lg shadow-xl hover:scale-105 active:scale-95 transition-all">
            免费开始
          </router-link>
          <a href="#starter-flow" class="px-6 sm:px-8 py-3.5 sm:py-4 bg-white/8 backdrop-blur-md text-white border-2 border-white/20 rounded-2xl font-black text-base sm:text-lg hover:bg-white/12 transition-all">
            查看使用流程
          </a>
        </div>
      </div>
      
      <!-- Decorative Elements -->
      <div class="absolute top-0 right-0 -translate-y-1/4 translate-x-1/4 w-96 h-96 bg-cyan-300/12 rounded-full blur-3xl"></div>
      <div class="absolute bottom-0 left-0 translate-y-1/2 -translate-x-1/4 w-64 h-64 bg-blue-300/18 rounded-full blur-3xl"></div>
    </section>

    <section id="starter-flow" class="relative overflow-hidden rounded-3xl border border-border bg-card p-6 sm:p-8 shadow-sm">
      <div class="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.08),transparent_48%)]"></div>
      <div class="relative space-y-6">
        <div class="flex flex-wrap items-end justify-between gap-4">
          <div class="space-y-2">
            <div class="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              第一次使用
            </div>
            <h2 class="text-2xl sm:text-3xl font-black tracking-tight">三步开始你的学习流程</h2>
            <p class="text-sm sm:text-base text-muted-foreground max-w-2xl leading-relaxed">
              不需要先研究设置。先上传资料，再生成摘要，最后进入问答或测验巩固理解。
            </p>
          </div>
          <router-link to="/upload" class="inline-flex items-center gap-2 rounded-2xl border border-border bg-background px-4 py-3 text-sm font-semibold hover:bg-accent transition-colors">
            先去上传资料
          </router-link>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <article
            v-for="step in starterSteps"
            :key="step.step"
            class="rounded-2xl border border-border bg-background/70 p-5 space-y-4 shadow-sm"
          >
            <div class="flex items-center justify-between gap-3">
              <span class="inline-flex h-10 w-10 items-center justify-center rounded-2xl font-black text-sm" :class="step.badgeClass">
                {{ step.step }}
              </span>
              <component :is="step.icon" class="w-5 h-5 text-primary" />
            </div>
            <div class="space-y-2">
              <h3 class="text-lg font-bold tracking-tight">{{ step.title }}</h3>
              <p class="text-sm text-muted-foreground leading-relaxed">{{ step.description }}</p>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- Features Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-8">
      <div v-for="feature in features" :key="feature.name" class="group p-6 sm:p-8 bg-card border border-border rounded-3xl shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
        <div class="w-14 h-14 bg-primary/10 text-primary rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
          <component :is="feature.icon" class="w-8 h-8" />
        </div>
        <h3 class="text-xl sm:text-2xl font-bold mb-3 tracking-tight">{{ feature.name }}</h3>
        <p class="text-muted-foreground leading-relaxed font-medium">{{ feature.description }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  Upload,
  FileText,
  MessageSquare,
  PenTool,
  BarChart2,
  Sparkles
} from 'lucide-vue-next'

const starterSteps = [
  {
    step: '01',
    title: '上传资料',
    description: '先创建学习资料库并上传 PDF、讲义或笔记，系统会自动解析内容。',
    icon: Upload,
    badgeClass: 'bg-sky-100 text-sky-700',
  },
  {
    step: '02',
    title: '生成摘要',
    description: '用摘要和重点知识点快速建立全局理解，不用一开始就逐段阅读。',
    icon: FileText,
    badgeClass: 'bg-emerald-100 text-emerald-700',
  },
  {
    step: '03',
    title: '开始问答或测验',
    description: '理解后再进入问答或测验，把疑问和薄弱点集中解决。',
    icon: Sparkles,
    badgeClass: 'bg-amber-100 text-amber-700',
  },
]

const features = [
  {
    name: '文档上传',
    description: '上传 PDF 或文本文件，轻松构建个人学习资料库。',
    icon: Upload
  },
  {
    name: '智能摘要',
    description: '从复杂学习材料中快速提取核心概念与要点。',
    icon: FileText
  },
  {
    name: '学习对话',
    description: '围绕资料内容进行多轮提问、追问与讲解。',
    icon: MessageSquare
  },
  {
    name: '自动测验',
    description: '通过 AI 生成的测验巩固理解、检验掌握程度。',
    icon: PenTool
  },
  {
    name: '进度跟踪',
    description: '可视化学习成长，获得基于数据的学径推荐。',
    icon: BarChart2
  },
  {
    name: '分步讲解',
    description: '用清晰步骤拆解难懂概念、定理与定义。',
    icon: Sparkles
  }
]
</script>
