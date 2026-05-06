import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useRagStore = defineStore(
  'ragStore',
  () => {
    const sessionId = ref('')
    const messages = ref<any[]>([])
    const sessionTitles = ref<Record<string, string>>({})

    function setSession(sid: string, msgs: any[]) {
      sessionId.value = sid
      messages.value = msgs

      if (!sessionTitles.value[sid]) {
        const firstUser = msgs.find((m: any) => m.isUser)
        if (firstUser?.text) {
          sessionTitles.value[sid] = firstUser.text.slice(0, 30)
        }
      }
    }

    function setSessionTitle(sid: string, title: string) {
      if (sid && title?.trim()) {
        sessionTitles.value[sid] = title.trim().slice(0, 30)
      }
    }

    function getTitle(sid: string): string {
      return sessionTitles.value[sid] || sid?.replace('session_', '') || '新对话'
    }

    function clearSession() {
      sessionId.value = `session_${Date.now()}`
      messages.value = []
    }

    return {
      sessionId,
      messages,
      sessionTitles,
      setSession,
      setSessionTitle,
      getTitle,
      clearSession
    }
  },
  { persist: { storage: sessionStorage } }
)
