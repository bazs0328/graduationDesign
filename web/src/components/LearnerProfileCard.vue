<script setup>
import { computed } from 'vue'

const props = defineProps({
  profile: {
    type: Object,
    default: null
  }
})

const abilityLabel = computed(() => {
  if (!props.profile) return '未建立'
  switch (props.profile.ability_level) {
    case 'beginner':
      return '初级'
    case 'advanced':
      return '高级'
    default:
      return '中级'
  }
})

const accuracyPercent = computed(() => {
  if (!props.profile) return 0
  return Math.round((props.profile.recent_accuracy || 0) * 100)
})

const frustrationPercent = computed(() => {
  if (!props.profile) return 0
  return Math.round((props.profile.frustration_score || 0) * 100)
})

const weakConcepts = computed(() => {
  if (!props.profile || !Array.isArray(props.profile.weak_concepts)) return []
  return props.profile.weak_concepts.slice(0, 6)
})
</script>

<template>
  <section class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-6">
    <div class="flex items-center justify-between">
      <div class="space-y-1">
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">学习者画像</p>
        <p class="text-2xl font-black">{{ abilityLabel }}</p>
      </div>
      <div class="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">
        {{ accuracyPercent }}%
      </div>
    </div>

    <div class="space-y-4">
      <div class="space-y-2">
        <div class="flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <span>最近正确率</span>
          <span>{{ accuracyPercent }}%</span>
        </div>
        <div class="h-2 rounded-full bg-muted overflow-hidden">
          <div class="h-full bg-primary transition-all" :style="{ width: `${accuracyPercent}%` }"></div>
        </div>
      </div>

      <div class="space-y-2">
        <div class="flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <span>挫败感指数</span>
          <span>{{ frustrationPercent }}%</span>
        </div>
        <div class="h-2 rounded-full bg-muted overflow-hidden">
          <div class="h-full bg-amber-400 transition-all" :style="{ width: `${frustrationPercent}%` }"></div>
        </div>
      </div>
    </div>

    <div class="space-y-2">
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">薄弱知识点</p>
      <div v-if="weakConcepts.length" class="flex flex-wrap gap-2">
        <span v-for="concept in weakConcepts" :key="concept" class="px-2 py-1 bg-primary/10 text-primary text-xs font-semibold rounded-full">
          {{ concept }}
        </span>
      </div>
      <p v-else class="text-sm text-muted-foreground">暂无薄弱知识点记录</p>
    </div>
  </section>
</template>
