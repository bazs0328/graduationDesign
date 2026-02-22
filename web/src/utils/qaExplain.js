export const QA_EXPLAIN_SECTION_ORDER = [
  '题意理解',
  '相关知识点',
  '分步解答',
  '易错点',
  '自测问题',
]

const TITLE_ALIASES = {
  题意理解: ['题意理解', '题目理解', '题意分析', '问题理解'],
  相关知识点: ['相关知识点', '知识点', '相关概念', '涉及知识点'],
  分步解答: ['分步解答', '解题步骤', '步骤解答', '分步讲解', '解答过程'],
  易错点: ['易错点', '常见易错点', '常见错误', '易错提醒'],
  自测问题: ['自测问题', '自我检测', '练习问题', '自测题'],
}

const ALIAS_TO_CANONICAL = new Map(
  Object.entries(TITLE_ALIASES).flatMap(([canonical, aliases]) =>
    aliases.map((alias) => [normalizeTitleKey(alias), canonical])
  )
)

function normalizeTitleKey(value) {
  return String(value || '')
    .trim()
    .replace(/^#+\s*/, '')
    .replace(/^\*\*|\*\*$/g, '')
    .replace(/[：:]+$/g, '')
    .replace(/\s+/g, '')
}

function matchCanonicalTitle(line) {
  const candidates = []
  const trimmed = String(line || '').trim()
  if (!trimmed) return null

  const headingMatch = trimmed.match(/^#{1,6}\s+(.+?)\s*$/)
  if (headingMatch) candidates.push(headingMatch[1])

  const boldOnlyMatch = trimmed.match(/^\*\*(.+?)\*\*$/)
  if (boldOnlyMatch) candidates.push(boldOnlyMatch[1])

  const plainMatch = trimmed.match(/^([^\n]{1,20}?)[：:]?\s*$/)
  if (plainMatch) candidates.push(plainMatch[1])

  for (const raw of candidates) {
    const canonical = ALIAS_TO_CANONICAL.get(normalizeTitleKey(raw))
    if (canonical) return canonical
  }
  return null
}

export function parseExplainMarkdownSections(text) {
  const rawText = String(text || '')
  const sectionsByTitle = new Map()
  let currentTitle = null
  let buffer = []

  const flush = () => {
    if (!currentTitle) return
    const content = buffer.join('\n').trim()
    if (sectionsByTitle.has(currentTitle)) {
      const previous = sectionsByTitle.get(currentTitle)
      sectionsByTitle.set(currentTitle, [previous, content].filter(Boolean).join('\n\n').trim())
    } else {
      sectionsByTitle.set(currentTitle, content)
    }
    buffer = []
  }

  for (const line of rawText.split(/\r?\n/)) {
    const maybeTitle = matchCanonicalTitle(line)
    if (maybeTitle) {
      flush()
      currentTitle = maybeTitle
      continue
    }
    if (currentTitle) {
      buffer.push(line)
    }
  }
  flush()

  const sections = QA_EXPLAIN_SECTION_ORDER
    .filter((title) => sectionsByTitle.has(title))
    .map((title) => ({
      key: title,
      title,
      content: sectionsByTitle.get(title) || '',
    }))

  const missing = QA_EXPLAIN_SECTION_ORDER.filter((title) => !sectionsByTitle.has(title))
  const hasStepByStep = sections.some((section) => section.title === '分步解答')
  const isExplainLike = sections.length >= 3 && hasStepByStep

  return {
    sections,
    missing,
    isExplainLike,
  }
}

export function isExplainLikeAnswer(text) {
  return parseExplainMarkdownSections(text).isExplainLike
}
