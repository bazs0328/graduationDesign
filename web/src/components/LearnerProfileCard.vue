<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart, GaugeChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  RadarComponent
} from 'echarts/components'
import VChart from 'vue-echarts'

use([
  CanvasRenderer,
  RadarChart,
  GaugeChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  RadarComponent
])

const props = defineProps({
  profile: {
    type: Object,
    default: null
  }
})

const router = useRouter()
const chartRef = ref(null)

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

// 雷达图四维：理解力、稳定性、活跃度、能力潜质（0–100）
const radarValues = computed(() => {
  if (!props.profile) return [0, 0, 0, 0]
  const p = props.profile
  const understanding = Math.round((p.recent_accuracy ?? 0) * 100)
  const stability = Math.round((1 - (p.frustration_score ?? 0)) * 100)
  const activity = Math.min(100, (p.total_attempts ?? 0) * 10)
  const thetaNorm = Math.max(0, Math.min(100, ((p.theta ?? 0) + 2) / 4 * 100))
  return [understanding, stability, activity, Math.round(thetaNorm)]
})

const radarOption = computed(() => ({
  radar: {
    indicator: [
      { name: '理解力', max: 100 },
      { name: '稳定性', max: 100 },
      { name: '活跃度', max: 100 },
      { name: '能力潜质', max: 100 }
    ],
    radius: '65%',
    axisName: {
      color: 'var(--muted-foreground, #71717a)',
      fontSize: 12
    },
    splitArea: {
      areaStyle: {
        color: ['rgba(59, 130, 246, 0.05)', 'rgba(59, 130, 246, 0.1)']
      }
    },
    axisLine: { lineStyle: { color: 'rgba(59, 130, 246, 0.3)' } },
    splitLine: { lineStyle: { color: 'rgba(59, 130, 246, 0.2)' } }
  },
  series: [
    {
      type: 'radar',
      data: [
        {
          value: radarValues.value,
          name: '当前画像',
          areaStyle: { color: 'rgba(59, 130, 246, 0.35)' },
          lineStyle: { color: 'rgb(59, 130, 246)', width: 2 },
          itemStyle: { color: 'rgb(59, 130, 246)' }
        }
      ]
    }
  ]
}))

const gaugeOption = computed(() => ({
  series: [
    {
      type: 'gauge',
      data: [{ value: frustrationPercent.value, name: '挫败感' }],
      startAngle: 200,
      endAngle: -20,
      min: 0,
      max: 100,
      splitNumber: 5,
      itemStyle: {
        color: frustrationPercent.value >= 70 ? '#f59e0b' : frustrationPercent.value >= 40 ? '#eab308' : '#22c55e'
      },
      progress: {
        show: true,
        width: 10,
        roundCap: true
      },
      pointer: { show: false },
      axisLine: { roundCap: true, lineStyle: { width: 10, color: [[1, 'var(--muted, #e4e4e7)']] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      title: {
        offsetCenter: [0, '80%'],
        fontSize: 11,
        color: 'var(--muted-foreground, #71717a)'
      },
      detail: {
        valueAnimation: true,
        offsetCenter: [0, '35%'],
        fontSize: 18,
        fontWeight: 'bold',
        formatter: '{value}%',
        color: 'inherit'
      }
    }
  ]
}))

const frustrationLabel = computed(() => {
  if (frustrationPercent.value >= 70) return '较高'
  if (frustrationPercent.value >= 40) return '适中'
  return '较低'
})

function goToQuiz(concept) {
  router.push({ name: 'Quiz', query: { focus: concept } })
}

function goToQA(concept) {
  router.push(concept ? { name: 'QA', query: { focus: concept } } : { name: 'QA' })
}
</script>

<template>
  <section
    class="bg-card border border-border rounded-xl p-6 shadow-sm space-y-6"
    aria-labelledby="profile-heading"
  >
    <div class="flex items-center justify-between" id="profile-heading">
      <div class="space-y-1">
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          学习者画像
        </p>
        <p class="text-2xl font-black">{{ abilityLabel }}</p>
      </div>
      <div
        class="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold"
      >
        {{ accuracyPercent }}%
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="min-h-[220px] flex items-center justify-center" aria-hidden="true">
        <VChart
          ref="chartRef"
          class="w-full h-[220px]"
          :option="radarOption"
          autoresize
        />
      </div>
      <div class="space-y-4 flex flex-col">
        <div class="space-y-2">
          <div
            class="flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider"
          >
            <span>最近正确率</span>
            <span>{{ accuracyPercent }}%</span>
          </div>
          <div class="h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full bg-primary transition-all duration-300"
              :style="{ width: `${accuracyPercent}%` }"
            />
          </div>
        </div>
        <div class="space-y-2 flex-1 min-h-[120px]">
          <div
            class="flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider"
          >
            <span>挫败感指数</span>
            <span>{{ frustrationPercent }}% ({{ frustrationLabel }})</span>
          </div>
          <div class="h-[100px] w-full">
            <VChart
              class="w-full h-full"
              :option="gaugeOption"
              autoresize
            />
          </div>
        </div>
      </div>
    </div>

    <div class="space-y-2">
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        薄弱知识点
      </p>
      <div v-if="weakConcepts.length" class="flex flex-wrap gap-2">
        <button
          v-for="concept in weakConcepts"
          :key="concept"
          type="button"
          class="px-2 py-1 bg-primary/10 text-primary text-xs font-semibold rounded-full hover:bg-primary/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 transition-colors"
          :aria-label="`针对「${concept}」去测验`"
          @click="goToQuiz(concept)"
        >
          {{ concept }}
        </button>
        <span class="text-[10px] text-muted-foreground self-center">
          点击可前往测验；或
          <button
            type="button"
            class="underline focus:outline-none focus:ring-2 focus:ring-primary rounded"
            aria-label="前往问答页"
            @click="goToQA()"
          >
            去问答
          </button>
        </span>
      </div>
      <p v-else class="text-sm text-muted-foreground">暂无薄弱知识点记录</p>
    </div>
  </section>
</template>
