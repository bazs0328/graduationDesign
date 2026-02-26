export const LEARNING_PATH_CHART_LAYOUT = Object.freeze({
  columnGap: 280,
  rowGap: 96,
  leftPadding: 96,
  topPadding: 72,
  bottomPadding: 72,
  rightPadding: 96,
  bandTop: 28,
  bandWidth: 200,
  headerPillTop: 4,
  headerPillHeight: 22,
  separatorBottomPadding: 16,
  minCanvasHeight: 380,
  minCanvasWidth: 980,
  minViewportHeight: 396,
  maxViewportHeight: 640,
  milestoneOffset: 8,
})

const EDGE_CURVE_OFFSETS = [-0.12, -0.06, 0, 0.06, 0.12, 0.18, -0.18]

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function normalizePathLevel(item) {
  return Math.max(0, Number(item?.path_level) || 0)
}

function levelHeaderTitle(level, count) {
  return `${level === 0 ? '先修起点' : `先修层级 ${level}`} · ${count}项`
}

function estimateHeaderPillWidth(title) {
  return Math.max(92, (String(title).length * 8) + 18)
}

function estimateNodeSymbolSize(item) {
  const baseSize = 24 + Math.round((Number(item?.importance) || 0.5) * 18)
  return item?.milestone ? baseSize + 6 : baseSize
}

export function learningPathEdgeKey(fromId, toId) {
  return `${String(fromId || '')}=>${String(toId || '')}`
}

export function buildLearningPathChartLayout(items = [], edges = []) {
  const sourceItems = Array.isArray(items) ? items : []
  const sourceEdges = Array.isArray(edges) ? edges : []

  if (!sourceItems.length) {
    return {
      canvasWidth: LEARNING_PATH_CHART_LAYOUT.minCanvasWidth,
      canvasHeight: LEARNING_PATH_CHART_LAYOUT.minCanvasHeight,
      viewportHeight: LEARNING_PATH_CHART_LAYOUT.minViewportHeight,
      maxRowsPerLevel: 0,
      levelValues: [],
      levelCounts: {},
      headerPills: [],
      nodePositions: {},
      edgeCurvenessByKey: {},
    }
  }

  const levelValues = [...new Set(sourceItems.map((item) => normalizePathLevel(item)))]
    .sort((a, b) => a - b)

  const levelCounts = {}
  for (const item of sourceItems) {
    const level = normalizePathLevel(item)
    levelCounts[level] = (levelCounts[level] || 0) + 1
  }

  const maxRowsPerLevel = Math.max(1, ...Object.values(levelCounts))
  const canvasHeight = Math.max(
    LEARNING_PATH_CHART_LAYOUT.minCanvasHeight,
    LEARNING_PATH_CHART_LAYOUT.topPadding
      + ((maxRowsPerLevel - 1) * LEARNING_PATH_CHART_LAYOUT.rowGap)
      + LEARNING_PATH_CHART_LAYOUT.bottomPadding,
  )
  const viewportHeight = clamp(
    canvasHeight + 16,
    LEARNING_PATH_CHART_LAYOUT.minViewportHeight,
    LEARNING_PATH_CHART_LAYOUT.maxViewportHeight,
  )

  const levelIndexMap = {}
  levelValues.forEach((level, idx) => {
    levelIndexMap[level] = idx
  })

  const headerPills = levelValues.map((level, idx) => {
    const centerX = LEARNING_PATH_CHART_LAYOUT.leftPadding + (idx * LEARNING_PATH_CHART_LAYOUT.columnGap)
    const title = levelHeaderTitle(level, levelCounts[level] || 0)
    const width = estimateHeaderPillWidth(title)
    return {
      level,
      idx,
      title,
      width,
      centerX,
      x: centerX - (width / 2),
    }
  })

  const pillRightMax = headerPills.reduce((max, pill) => Math.max(max, pill.x + pill.width), 0)
  const columnRightFallback = LEARNING_PATH_CHART_LAYOUT.leftPadding
    + ((Math.max(levelValues.length, 1) - 1) * LEARNING_PATH_CHART_LAYOUT.columnGap)
  const canvasWidth = Math.max(
    LEARNING_PATH_CHART_LAYOUT.minCanvasWidth,
    Math.ceil(Math.max(
      columnRightFallback + LEARNING_PATH_CHART_LAYOUT.rightPadding,
      pillRightMax + LEARNING_PATH_CHART_LAYOUT.rightPadding,
    )),
  )

  const itemsByLevel = {}
  for (const item of sourceItems) {
    const level = normalizePathLevel(item)
    if (!itemsByLevel[level]) itemsByLevel[level] = []
    itemsByLevel[level].push(item)
  }

  const nodePositions = {}
  const nodeAreaTop = LEARNING_PATH_CHART_LAYOUT.topPadding
  const nodeAreaBottom = canvasHeight - LEARNING_PATH_CHART_LAYOUT.bottomPadding
  const nodeAreaCenterY = (nodeAreaTop + nodeAreaBottom) / 2

  for (const level of levelValues) {
    const columnItems = itemsByLevel[level] || []
    if (!columnItems.length) continue

    const levelCount = columnItems.length
    const levelIdx = levelIndexMap[level] ?? 0
    const columnCenterX = LEARNING_PATH_CHART_LAYOUT.leftPadding + (levelIdx * LEARNING_PATH_CHART_LAYOUT.columnGap)
    const firstSize = estimateNodeSymbolSize(columnItems[0])
    const lastSize = estimateNodeSymbolSize(columnItems[levelCount - 1])
    const rowSpan = (levelCount - 1) * LEARNING_PATH_CHART_LAYOUT.rowGap
    const rawStartY = nodeAreaCenterY - (rowSpan / 2) - ((lastSize - firstSize) / 4)
    const minStartY = nodeAreaTop + (firstSize / 2)
    const maxStartY = nodeAreaBottom - (lastSize / 2) - rowSpan
    const columnStartY = clamp(rawStartY, minStartY, maxStartY)

    columnItems.forEach((item, rowIdx) => {
      const keypointId = String(item?.keypoint_id || '').trim()
      if (!keypointId) return
      nodePositions[keypointId] = {
        level,
        levelIdx,
        rowIdx,
        x: columnCenterX,
        y: columnStartY + (rowIdx * LEARNING_PATH_CHART_LAYOUT.rowGap),
      }
    })
  }

  const edgeCurvenessByKey = {}
  const groupedByTarget = {}
  for (const edge of sourceEdges) {
    const fromId = String(edge?.from_id || '').trim()
    const toId = String(edge?.to_id || '').trim()
    if (!fromId || !toId) continue
    if (!groupedByTarget[toId]) groupedByTarget[toId] = []
    groupedByTarget[toId].push(edge)
  }

  for (const targetId of Object.keys(groupedByTarget)) {
    const group = groupedByTarget[targetId]
      .filter((edge) => nodePositions[String(edge?.from_id || '').trim()] && nodePositions[String(edge?.to_id || '').trim()])
      .sort((a, b) => {
        const aFrom = nodePositions[String(a?.from_id || '').trim()]
        const bFrom = nodePositions[String(b?.from_id || '').trim()]
        const rowDiff = (aFrom?.rowIdx ?? 0) - (bFrom?.rowIdx ?? 0)
        if (rowDiff) return rowDiff
        const aId = String(a?.from_id || '')
        const bId = String(b?.from_id || '')
        return aId.localeCompare(bId)
      })

    for (let idx = 0; idx < group.length; idx += 1) {
      const edge = group[idx]
      const fromId = String(edge?.from_id || '').trim()
      const toId = String(edge?.to_id || '').trim()
      const sourceMeta = nodePositions[fromId]
      const targetMeta = nodePositions[toId]
      if (!sourceMeta || !targetMeta) continue

      const baseOffset = group.length === 1 ? 0 : EDGE_CURVE_OFFSETS[idx % EDGE_CURVE_OFFSETS.length]
      const rowDeltaAdjust = clamp((targetMeta.rowIdx - sourceMeta.rowIdx) * 0.03, -0.12, 0.12)
      edgeCurvenessByKey[learningPathEdgeKey(fromId, toId)] = clamp(baseOffset + rowDeltaAdjust, -0.28, 0.28)
    }
  }

  return {
    canvasWidth,
    canvasHeight,
    viewportHeight,
    maxRowsPerLevel,
    levelValues,
    levelCounts,
    headerPills,
    nodePositions,
    edgeCurvenessByKey,
  }
}
