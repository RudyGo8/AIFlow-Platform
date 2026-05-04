import { defineStore } from 'pinia'
import { ref } from 'vue'

/** RAG 对话状态持久化 — 主题切换等触发的 RouterView refresh 不会丟失对话 */
export const useRagStore = defineStore(
  'ragStore',
  () => {
    const sessionId = ref('')
    const messages = ref<any[]>([])
    const sessionTitles = ref<Record<string, string>>({})

    function setSession(sid: string, msgs: any[]) {
      sessionId.value = sid
      messages.value = msgs
      // 自动用第一条用户消息作为标题
      if (!sessionTitles.value[sid]) {
        const firstUser = msgs.find((m: any) => m.isUser)
        if (firstUser?.text) {
          sessionTitles.value[sid] = firstUser.text.slice(0, 30)
        }
      }
    }

    function getTitle(sid: string): string {
      return sessionTitles.value[sid] || sid?.replace('session_', '') || '新对话'
    }

    function clearSession() {
      sessionId.value = `session_${Date.now()}`
      messages.value = []
    }

    return { sessionId, messages, sessionTitles, setSession, getTitle, clearSession }
  },
  { persist: { storage: sessionStorage } }
)
