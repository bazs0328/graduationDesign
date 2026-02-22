import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

import { apiSsePost } from '@/api'

function makeReaderFromChunks(chunks) {
  const encoder = new TextEncoder()
  let index = 0
  return {
    async read() {
      if (index >= chunks.length) {
        return { done: true, value: undefined }
      }
      const value = encoder.encode(chunks[index])
      index += 1
      return { done: false, value }
    }
  }
}

describe('apiSsePost', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('gradtutor_access_token', 'test-token')
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('parses SSE events across chunk boundaries', async () => {
    const onStatus = vi.fn()
    const onChunk = vi.fn()
    const onSources = vi.fn()
    const onDone = vi.fn()

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader() {
          return makeReaderFromChunks([
            'event: status\n',
            'data: {"stage":"retrieving","message":"检索中"}\n\n',
            'event: chunk\ndata: {"delta":"Hello"}\n\nev',
            'ent: chunk\ndata: {"delta":" World"}\n\n',
            'event: sources\ndata: {"sources":[{"source":"doc p.1 c.0","snippet":"x"}],"retrieved_count":1}\n\n',
            'event: done\ndata: {"result":"ok","retrieved_count":1,"timings":{"total_ms":12}}\n\n',
          ])
        }
      }
    })

    await apiSsePost('/api/qa/stream', { question: 'Q', kb_id: 'kb-1' }, {
      onStatus,
      onChunk,
      onSources,
      onDone,
    })

    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(onStatus).toHaveBeenCalledWith(expect.objectContaining({ stage: 'retrieving' }))
    expect(onChunk).toHaveBeenNthCalledWith(1, { delta: 'Hello' })
    expect(onChunk).toHaveBeenNthCalledWith(2, { delta: ' World' })
    expect(onSources).toHaveBeenCalledWith(expect.objectContaining({ retrieved_count: 1 }))
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ result: 'ok' }))
  })
})
