const ABILITY_LEVELS = new Set(['beginner', 'intermediate', 'advanced'])

const ABILITY_LEVEL_META = {
  beginner: {
    text: '基础模式',
    code: 'BEGINNER',
    badgeClass: 'text-green-700 bg-green-100 border-green-200',
    description: '当前更适合以通俗讲解和基础巩固为主，先稳住学习节奏。',
  },
  intermediate: {
    text: '进阶模式',
    code: 'INTERMEDIATE',
    badgeClass: 'text-blue-700 bg-blue-100 border-blue-200',
    description: '当前处于能力提升区间，系统会在巩固与挑战之间保持平衡。',
  },
  advanced: {
    text: '专家模式',
    code: 'ADVANCED',
    badgeClass: 'text-amber-700 bg-amber-100 border-amber-200',
    description: '当前具备较高学习稳定性，可增加高难度题目推进进阶。',
  },
}

function toFiniteNumber(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function clampRatio(value, fallback = 0) {
  return clamp(toFiniteNumber(value, fallback), 0, 1)
}

function normalizeConceptList(values) {
  if (!Array.isArray(values)) return []
  const seen = new Set()
  const out = []
  for (const raw of values) {
    const text = String(raw || '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(text)
  }
  return out
}

function ratioToPercent(ratios) {
  const entries = Object.entries(ratios || {})
  const cleaned = entries.map(([key, value]) => ({
    key,
    value: Math.max(0, toFiniteNumber(value, 0)),
  }))
  const sum = cleaned.reduce((acc, item) => acc + item.value, 0)
  if (sum <= 0) {
    return { easy: 30, medium: 50, hard: 20 }
  }

  const normalized = cleaned.map((item) => ({
    ...item,
    value: item.value / sum,
  }))
  const base = {}
  let allocated = 0
  for (const item of normalized) {
    const floor = Math.floor(item.value * 100)
    base[item.key] = floor
    allocated += floor
  }

  let remainder = 100 - allocated
  const ranked = [...normalized].sort((a, b) => {
    const fracA = (a.value * 100) - Math.floor(a.value * 100)
    const fracB = (b.value * 100) - Math.floor(b.value * 100)
    return fracB - fracA
  })
  for (const item of ranked) {
    if (remainder <= 0) break
    base[item.key] = Number(base[item.key] || 0) + 1
    remainder -= 1
  }
  return {
    easy: Number(base.easy || 0),
    medium: Number(base.medium || 0),
    hard: Number(base.hard || 0),
  }
}

function normalizePlan(plan) {
  const easy = Math.max(0, toFiniteNumber(plan?.easy, NaN))
  const medium = Math.max(0, toFiniteNumber(plan?.medium, NaN))
  const hard = Math.max(0, toFiniteNumber(plan?.hard, NaN))
  const valid = Number.isFinite(easy) && Number.isFinite(medium) && Number.isFinite(hard) && (easy + medium + hard) > 0
  if (!valid) return null
  return {
    easy,
    medium,
    hard,
    message: typeof plan?.message === 'string' ? plan.message.trim() : '',
  }
}

function inferPlanByProfile(profile) {
  const abilityLevel = normalizeAbilityLevel(profile?.ability_level)
  const recentAccuracy = clampRatio(profile?.recent_accuracy)
  const frustrationScore = clampRatio(profile?.frustration_score)

  if (abilityLevel === 'beginner' || frustrationScore > 0.7) {
    return { easy: 0.8, medium: 0.2, hard: 0, message: '系统将优先安排基础巩固内容，帮助你先建立稳定感。' }
  }
  if (abilityLevel === 'intermediate') {
    if (recentAccuracy < 0.5) {
      return { easy: 0.5, medium: 0.4, hard: 0.1, message: '系统将适度回稳难度，先提升正确率，再逐步加压。' }
    }
    return { easy: 0.3, medium: 0.5, hard: 0.2, message: '系统将保持中等难度为主，并加入少量挑战题。' }
  }
  return { easy: 0.1, medium: 0.4, hard: 0.5, message: '系统将提高挑战题占比，帮助你持续进阶。' }
}

function resolveReasonText(profile) {
  const abilityLevel = normalizeAbilityLevel(profile?.ability_level)
  const recentAccuracy = clampRatio(profile?.recent_accuracy)
  const frustrationScore = clampRatio(profile?.frustration_score)

  if (abilityLevel === 'beginner' || frustrationScore > 0.7) {
    return '系统判断你当前更适合先巩固基础，以减少连续受挫并逐步恢复学习稳定性。'
  }
  if (abilityLevel === 'intermediate') {
    if (recentAccuracy < 0.5) {
      return '系统判断你正处于回稳阶段，先提升正确率，再逐步恢复更高难度。'
    }
    return '系统判断你已具备稳定基础，因此采用平衡分配以兼顾巩固与挑战。'
  }
  return '系统判断你具备较强学习稳定性，因此提高挑战题比例以促进进阶。'
}

export function normalizeAbilityLevel(level) {
  const normalized = String(level || '').trim().toLowerCase()
  return ABILITY_LEVELS.has(normalized) ? normalized : 'intermediate'
}

export function getAbilityLevelMeta(level) {
  return ABILITY_LEVEL_META[normalizeAbilityLevel(level)] || ABILITY_LEVEL_META.intermediate
}

export function buildAdaptiveInsight({ profile = {}, plan = null } = {}) {
  const abilityLevel = normalizeAbilityLevel(profile?.ability_level)
  const recentAccuracy = clampRatio(profile?.recent_accuracy)
  const frustrationScore = clampRatio(profile?.frustration_score)
  const totalAttempts = Math.max(0, Math.floor(toFiniteNumber(profile?.total_attempts, 0)))
  const weakConcepts = normalizeConceptList(profile?.weak_concepts)
  const resolvedPlan = normalizePlan(plan) || inferPlanByProfile(profile)
  const planPercent = ratioToPercent(resolvedPlan)
  const reasonText = resolveReasonText(profile)

  return {
    level: abilityLevel,
    levelMeta: getAbilityLevelMeta(abilityLevel),
    plan: resolvedPlan,
    planPercent,
    reasonText,
    signals: {
      recentAccuracy,
      frustrationScore,
      totalAttempts,
      recentAccuracyPercent: Math.round(recentAccuracy * 100),
      frustrationPercent: Math.round(frustrationScore * 100),
    },
    weakConceptsTop3: weakConcepts.slice(0, 3),
  }
}

