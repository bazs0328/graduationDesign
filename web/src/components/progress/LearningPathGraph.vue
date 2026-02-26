<template>
  <VChart :style="chartStyle" :option="option || {}" autoresize />
</template>

<script setup>
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, GraphChart, TooltipComponent, LegendComponent, GraphicComponent])

const props = defineProps({
  option: {
    type: Object,
    default: () => ({}),
  },
  height: {
    type: Number,
    default: 380,
  },
  width: {
    type: Number,
    default: 0,
  },
})

const normalizedHeight = computed(() => Math.max(120, Number(props.height) || 380))
const normalizedWidth = computed(() => Math.max(0, Number(props.width) || 0))
const chartStyle = computed(() => ({
  width: normalizedWidth.value > 0 ? `${normalizedWidth.value}px` : '100%',
  height: `${normalizedHeight.value}px`,
  display: 'block',
}))
</script>
