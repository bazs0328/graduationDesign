import { describe, it, expect } from 'vitest'

import {
  LEARNING_PATH_CHART_LAYOUT,
  buildLearningPathChartLayout,
  learningPathEdgeKey,
} from '@/utils/learningPathChartLayout'

function makeItem(id, pathLevel, extra = {}) {
  return {
    keypoint_id: id,
    text: `节点 ${id}`,
    path_level: pathLevel,
    milestone: false,
    ...extra,
  }
}

describe('learningPathChartLayout', () => {
  it('expands canvas width for many levels and keeps last header pill inside canvas', () => {
    const items = Array.from({ length: 10 }, (_, idx) => makeItem(`kp-${idx + 1}`, idx))
    const layout = buildLearningPathChartLayout(items, [])

    expect(layout.canvasWidth).toBeGreaterThan(LEARNING_PATH_CHART_LAYOUT.minCanvasWidth)
    expect(layout.headerPills.length).toBe(10)

    const lastPill = layout.headerPills[layout.headerPills.length - 1]
    expect(lastPill.x + lastPill.width).toBeLessThanOrEqual(layout.canvasWidth)
  })

  it('grows canvas height with dense single column and clamps viewport height', () => {
    const items = Array.from({ length: 8 }, (_, idx) => makeItem(`kp-${idx + 1}`, 0))
    const layout = buildLearningPathChartLayout(items, [])

    expect(layout.canvasHeight).toBeGreaterThan(LEARNING_PATH_CHART_LAYOUT.minCanvasHeight)
    expect(layout.viewportHeight).toBeLessThanOrEqual(LEARNING_PATH_CHART_LAYOUT.maxViewportHeight)
    expect(layout.viewportHeight).toBe(LEARNING_PATH_CHART_LAYOUT.maxViewportHeight)
  })

  it('assigns distinct curveness values to multiple incoming edges of the same target', () => {
    const items = [
      makeItem('src-1', 0),
      makeItem('src-2', 0),
      makeItem('src-3', 0),
      makeItem('target', 1),
    ]
    const edges = [
      { from_id: 'src-1', to_id: 'target' },
      { from_id: 'src-2', to_id: 'target' },
      { from_id: 'src-3', to_id: 'target' },
    ]

    const layout = buildLearningPathChartLayout(items, edges)
    const values = edges.map((edge) => layout.edgeCurvenessByKey[learningPathEdgeKey(edge.from_id, edge.to_id)])

    expect(values.every((value) => typeof value === 'number')).toBe(true)
    expect(new Set(values).size).toBe(values.length)
  })

  it('keeps node y positions ordered within a column and inside visible vertical bounds', () => {
    const items = [
      makeItem('l0-1', 0),
      makeItem('l1-1', 1),
      makeItem('l1-2', 1),
      makeItem('l1-3', 1),
    ]

    const layout = buildLearningPathChartLayout(items, [])
    const level1Ys = ['l1-1', 'l1-2', 'l1-3'].map((id) => layout.nodePositions[id].y)

    expect(level1Ys[0]).toBeLessThan(level1Ys[1])
    expect(level1Ys[1]).toBeLessThan(level1Ys[2])

    for (const pos of Object.values(layout.nodePositions)) {
      expect(pos.y).toBeGreaterThanOrEqual(LEARNING_PATH_CHART_LAYOUT.topPadding)
      expect(pos.y).toBeLessThanOrEqual(
        layout.canvasHeight - LEARNING_PATH_CHART_LAYOUT.bottomPadding + LEARNING_PATH_CHART_LAYOUT.rowGap,
      )
    }
  })
})
