import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/api', () => ({
  apiGet: vi.fn(),
}))

import { apiGet } from '../../src/api'
import { useKbDocuments } from '../../src/composables/useKbDocuments'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useKbDocuments', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('deduplicates in-flight requests for the same user/kb key', async () => {
    const d = deferred()
    apiGet.mockReturnValueOnce(d.promise)

    const userId = ref('user-a')
    const kbId = ref('kb-1')
    const store = useKbDocuments({ userId, kbId })

    const p1 = store.refresh()
    const p2 = store.refresh()

    expect(await Promise.race([p1.then(() => 'done'), Promise.resolve('pending')])).toBe('pending')
    expect(await Promise.race([p2.then(() => 'done'), Promise.resolve('pending')])).toBe('pending')
    expect(apiGet).toHaveBeenCalledTimes(1)

    d.resolve([{ id: 'doc-1', filename: 'a.txt' }])
    await p1

    expect(store.docs.value).toEqual([{ id: 'doc-1', filename: 'a.txt' }])
    expect(store.loading.value).toBe(false)
  })

  it('prevents stale response from overriding newer kb selection results', async () => {
    const d1 = deferred()
    const d2 = deferred()
    apiGet.mockImplementationOnce(() => d1.promise).mockImplementationOnce(() => d2.promise)

    const userId = ref('user-a')
    const kbId = ref('kb-1')
    const store = useKbDocuments({ userId, kbId })

    const p1 = store.refresh()
    kbId.value = 'kb-2'
    const p2 = store.refresh()

    d2.resolve([{ id: 'doc-2', filename: 'new.txt' }])
    await p2
    expect(store.docs.value).toEqual([{ id: 'doc-2', filename: 'new.txt' }])

    d1.resolve([{ id: 'doc-1', filename: 'old.txt' }])
    await p1
    expect(store.docs.value).toEqual([{ id: 'doc-2', filename: 'new.txt' }])
    expect(store.loading.value).toBe(false)
  })
})
