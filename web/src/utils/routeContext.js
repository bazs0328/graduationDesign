const DIFFICULTY_SET = new Set(['easy', 'medium', 'hard'])

export function normalizeQueryString(value) {
  if (Array.isArray(value)) {
    return value[0] || ''
  }
  return typeof value === 'string' ? value : ''
}

export function normalizeDifficulty(value) {
  const normalized = normalizeQueryString(value).trim().toLowerCase()
  return DIFFICULTY_SET.has(normalized) ? normalized : ''
}

export function parseRouteContext(query = {}) {
  const kbId = normalizeQueryString(query.kb_id)
  const docId = normalizeQueryString(query.doc_id)
  const focus = normalizeQueryString(query.focus).trim()
  const difficulty = normalizeDifficulty(query.difficulty)
  const keypointText = normalizeQueryString(query.keypoint_text).trim()
  const qaMode = normalizeQueryString(query.qa_mode).trim().toLowerCase()
  const qaAutoSend = normalizeQueryString(query.qa_autosend).trim()
  const qaQuestion = normalizeQueryString(query.qa_question).trim()
  const qaFrom = normalizeQueryString(query.qa_from).trim()

  return {
    kbId,
    docId,
    focus,
    difficulty,
    keypointText,
    qaMode,
    qaAutoSend,
    qaQuestion,
    qaFrom,
  }
}

export function buildRouteContextQuery(context = {}, baseQuery = {}) {
  const query = {}

  for (const [key, value] of Object.entries(baseQuery || {})) {
    const normalized = normalizeQueryString(value)
    if (normalized) {
      query[key] = normalized
    }
  }

  const kbId = normalizeQueryString(context.kbId)
  const docId = normalizeQueryString(context.docId)
  const focus = normalizeQueryString(context.focus).trim()
  const difficulty = normalizeDifficulty(context.difficulty)
  const keypointText = normalizeQueryString(context.keypointText).trim()

  if (kbId) query.kb_id = kbId
  if (docId) query.doc_id = docId
  if (focus) query.focus = focus
  if (difficulty) query.difficulty = difficulty
  if (keypointText) query.keypoint_text = keypointText

  return query
}
