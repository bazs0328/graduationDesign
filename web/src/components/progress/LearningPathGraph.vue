<template>
  <VChart class="w-full" :style="{ height: `${normalizedHeight}px`, display: 'block' }" :option="option || {}" autoresize />
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
})

const normalizedHeight = computed(() => Math.max(120, Number(props.height) || 380))
</script>
