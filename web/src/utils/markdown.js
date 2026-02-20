import MarkdownIt from 'markdown-it'
import markdownItKatex from 'markdown-it-katex'

const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
})

md.use(markdownItKatex)

const defaultLinkOpenRenderer = md.renderer.rules.link_open

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  if (defaultLinkOpenRenderer) {
    return defaultLinkOpenRenderer(tokens, idx, options, env, self)
  }
  return self.renderToken(tokens, idx, options)
}

export function renderMarkdown(content) {
  const text = typeof content === 'string' ? content : String(content ?? '')
  if (!text.trim()) return ''
  try {
    return md.render(text)
  } catch {
    const escaped = md.utils.escapeHtml(text).replace(/\n/g, '<br/>')
    return `<p>${escaped}</p>`
  }
}

