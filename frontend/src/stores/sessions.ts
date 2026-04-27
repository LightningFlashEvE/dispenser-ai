import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sessionApi, type SessionListItem, type SessionDetail } from '@/services/sessions'

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref<SessionListItem[]>([])
  const currentSessionId = ref<string | null>(null)
  const isLoading = ref(false)

  async function loadSessions(): Promise<void> {
    isLoading.value = true
    try {
      sessions.value = await sessionApi.list({ limit: 50 })
    } finally {
      isLoading.value = false
    }
  }

  async function createSession(): Promise<string> {
    const res = await sessionApi.create()
    await loadSessions()
    return res.session_id
  }

  async function deleteSession(sessionId: string): Promise<void> {
    await sessionApi.delete(sessionId)
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = null
    }
    await loadSessions()
  }

  async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
    return sessionApi.get(sessionId)
  }

  function setCurrentSession(sessionId: string): void {
    currentSessionId.value = sessionId
  }

  return {
    sessions,
    currentSessionId,
    isLoading,
    loadSessions,
    createSession,
    deleteSession,
    getSessionDetail,
    setCurrentSession,
  }
})
