/**
 * Unified mastery thresholds and helpers.
 * Keeps frontend in sync with backend MASTERY_MASTERED / MASTERY_PARTIAL.
 */

export const MASTERY_MASTERED = 0.8
export const MASTERY_PARTIAL = 0.3

export function masteryState(level) {
  if (level >= MASTERY_MASTERED) return 'mastered'
  if (level >= MASTERY_PARTIAL) return 'partial'
  return 'weak'
}

export function masteryLabel(level) {
  const map = { mastered: '已掌握', partial: '部分掌握', weak: '待学习' }
  return map[masteryState(level)]
}

export function masteryPercent(level) {
  return Math.round((level || 0) * 100)
}

export function masteryBadgeClass(level) {
  const state = masteryState(level)
  return {
    mastered: 'bg-green-500/10 text-green-600 border-green-500/30',
    partial: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
    weak: 'bg-red-500/10 text-red-600 border-red-500/30',
  }[state]
}

export function masteryBorderClass(level) {
  const state = masteryState(level)
  return {
    mastered: 'border-green-500/40',
    partial: 'border-amber-500/40',
    weak: 'border-red-500/40',
  }[state]
}

export function isWeakMastery(level) {
  return (level || 0) < MASTERY_PARTIAL
}
