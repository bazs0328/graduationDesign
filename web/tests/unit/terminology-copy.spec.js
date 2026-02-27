import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8')
}

describe('terminology copy updates', () => {
  it('upload page uses simplified system capability wording', () => {
    const source = readSource('src/views/Upload.vue')
    expect(source).toContain('系统级文档识别能力与解析策略由管理员维护')
    expect(source).not.toContain('OCR / PDF 解析')
  })

  it('qa page uses simplified retrieval wording', () => {
    const source = readSource('src/views/QA.vue')
    expect(source).toContain('正在查找相关参考内容...')
    expect(source).toContain("UX_TEXT.retrievalInProgress")
    expect(source).not.toContain('正在检索相关片段...')
  })
})
