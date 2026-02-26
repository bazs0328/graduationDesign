import { ref, unref } from 'vue'
import { apiGet } from '../api'

export function useKbDocuments({ userId, kbId }) {
  const docs = ref([])
  const loading = ref(false)
  let requestSeq = 0
  let inFlightKey = ''
  let inFlightPromise = null

  async function refresh(options = {}) {
    const { force = false } = options
    const resolvedUserId = String(unref(userId) || 'default')
    const resolvedKbId = String(unref(kbId) || '').trim()

    if (!resolvedKbId) {
      docs.value = []
      loading.value = false
      inFlightKey = ''
      inFlightPromise = null
      return docs.value
    }

    const requestKey = `${resolvedUserId}::${resolvedKbId}`
    if (!force && inFlightPromise && inFlightKey === requestKey) {
      return inFlightPromise
    }

    requestSeq += 1
    const seq = requestSeq
    inFlightKey = requestKey
    loading.value = true

    const request = apiGet(
      `/api/docs?user_id=${encodeURIComponent(resolvedUserId)}&kb_id=${encodeURIComponent(resolvedKbId)}`
    )
      .then((rows) => {
        if (seq !== requestSeq) return docs.value
        docs.value = Array.isArray(rows) ? rows : []
        return docs.value
      })
      .catch((err) => {
        if (seq === requestSeq) docs.value = []
        throw err
      })
      .finally(() => {
        if (seq === requestSeq) {
          loading.value = false
          inFlightPromise = null
        }
      })

    inFlightPromise = request
    return request
  }

  function reset() {
    requestSeq += 1
    docs.value = []
    loading.value = false
    inFlightKey = ''
    inFlightPromise = null
  }

  return {
    docs,
    loading,
    refresh,
    reset,
  }
}
