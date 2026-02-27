import { computed } from 'vue'
import { useAppContextStore } from '../stores/appContext'
import { useKbDocuments } from './useKbDocuments'

export function useAppKnowledgeScope(options = {}) {
  const { withDocs = false } = options

  const appContext = useAppContextStore()
  appContext.hydrate()

  const resolvedUserId = computed(() => appContext.resolvedUserId || 'default')
  const kbs = computed(() => appContext.kbs)
  const selectedKbId = computed({
    get: () => appContext.selectedKbId,
    set: (value) => appContext.setSelectedKbId(value),
  })
  const selectedDocId = computed({
    get: () => appContext.selectedDocId,
    set: (value) => appContext.setSelectedDocId(value),
  })

  const scope = {
    appContext,
    resolvedUserId,
    kbs,
    selectedKbId,
    selectedDocId,
  }

  if (withDocs) {
    const kbDocs = useKbDocuments({ userId: resolvedUserId, kbId: selectedKbId })
    scope.kbDocs = kbDocs
    scope.docsInKb = kbDocs.docs
    scope.docsInKbLoading = kbDocs.loading
  }

  return scope
}
