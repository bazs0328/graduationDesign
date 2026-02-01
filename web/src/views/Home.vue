<template>
  <div class="max-w-4xl mx-auto space-y-8">
    <section class="text-center py-12 space-y-4">
      <h1 class="text-4xl font-bold tracking-tight sm:text-6xl">Welcome to GradTutor</h1>
      <p class="text-xl text-muted-foreground max-w-2xl mx-auto">
        Your personalized AI learning assistant. Upload documents, generate summaries, take quizzes, and track your progress.
      </p>
      <div class="flex justify-center gap-4 pt-4">
        <router-link to="/upload" class="px-6 py-3 bg-primary text-primary-foreground rounded-lg font-semibold hover:opacity-90 transition-opacity">
          Get Started
        </router-link>
        <router-link to="/qa" class="px-6 py-3 bg-secondary text-secondary-foreground rounded-lg font-semibold hover:bg-secondary/80 transition-colors">
          Ask a Question
        </router-link>
      </div>
    </section>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div v-for="feature in features" :key="feature.name" class="p-6 bg-card border border-border rounded-xl space-y-3">
        <div class="w-10 h-10 bg-primary/10 text-primary rounded-lg flex items-center justify-center">
          <component :is="feature.icon" class="w-6 h-6" />
        </div>
        <h3 class="text-xl font-bold">{{ feature.name }}</h3>
        <p class="text-muted-foreground">{{ feature.description }}</p>
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
    description: 'Upload PDF or text files to build your personal knowledge base.',
    icon: Upload
  },
  {
    name: 'Smart Summaries',
    description: 'Get concise summaries and key points from your learning materials.',
    icon: FileText
  },
  {
    name: 'Interactive Q&A',
    description: 'Chat with an AI tutor that knows your documents inside out.',
    icon: MessageSquare
  },
  {
    name: 'Auto-generated Quizzes',
    description: 'Test your knowledge with AI-generated questions based on your content.',
    icon: PenTool
  },
  {
    name: 'Progress Tracking',
    description: 'Monitor your learning journey and get personalized recommendations.',
    icon: BarChart2
  },
  {
    name: 'AI Insights',
    description: 'Leverage advanced AI to simplify complex concepts and theorems.',
    icon: Sparkles
  }
]
</script>
