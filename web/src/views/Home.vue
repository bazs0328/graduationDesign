<template>
  <div class="space-y-12 pb-20">
    <!-- Hero Section -->
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary via-primary/90 to-blue-600 p-12 text-white shadow-2xl shadow-primary/20">
      <div class="relative z-10 max-w-3xl space-y-6">
        <div class="inline-flex items-center gap-2 px-3 py-1 bg-white/20 backdrop-blur-md rounded-full text-sm font-bold tracking-wide uppercase">
          <Sparkles class="w-4 h-4" />
          Next-Gen Learning
        </div>
        <h1 class="text-5xl md:text-7xl font-black tracking-tight leading-none">
          Master Your <br/> Knowledge with <span class="text-blue-200">AI</span>
        </h1>
        <p class="text-xl text-blue-50/90 leading-relaxed max-w-2xl font-medium">
          GradTutor transforms your documents into interactive learning experiences. Summarize, quiz, and chat with your personal AI tutor.
        </p>
        <div class="flex flex-wrap gap-4 pt-4">
          <router-link to="/upload" class="px-8 py-4 bg-white text-primary rounded-2xl font-black text-lg shadow-xl hover:scale-105 active:scale-95 transition-all">
            Get Started Free
          </router-link>
          <router-link to="/qa" class="px-8 py-4 bg-primary-foreground/10 backdrop-blur-md text-white border-2 border-white/20 rounded-2xl font-black text-lg hover:bg-white/10 transition-all">
            Try AI Chat
          </router-link>
        </div>
      </div>
      
      <!-- Decorative Elements -->
      <div class="absolute top-0 right-0 -translate-y-1/4 translate-x-1/4 w-96 h-96 bg-white/10 rounded-full blur-3xl"></div>
      <div class="absolute bottom-0 left-0 translate-y-1/2 -translate-x-1/4 w-64 h-64 bg-blue-400/20 rounded-full blur-3xl"></div>
    </section>

    <!-- Features Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
      <div v-for="feature in features" :key="feature.name" class="group p-8 bg-card border border-border rounded-3xl shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
        <div class="w-14 h-14 bg-primary/10 text-primary rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
          <component :is="feature.icon" class="w-8 h-8" />
        </div>
        <h3 class="text-2xl font-bold mb-3 tracking-tight">{{ feature.name }}</h3>
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

const features = [
  {
    name: 'Document Upload',
    description: 'Build your personal knowledge base by uploading PDF or text files seamlessly.',
    icon: Upload
  },
  {
    name: 'Smart Summaries',
    description: 'Instantly extract core concepts and key points from complex learning materials.',
    icon: FileText
  },
  {
    name: 'Interactive Q&A',
    description: 'Engage in deep conversations with an AI tutor that understands every detail of your docs.',
    icon: MessageSquare
  },
  {
    name: 'Auto-Quizzes',
    description: 'Challenge yourself with AI-generated tests designed to reinforce your understanding.',
    icon: PenTool
  },
  {
    name: 'Progress Tracking',
    description: 'Visualize your growth and receive data-driven recommendations for your study path.',
    icon: BarChart2
  },
  {
    name: 'AI Insights',
    description: 'Break down difficult theorems and definitions with advanced simplified explanations.',
    icon: Sparkles
  }
]
</script>
