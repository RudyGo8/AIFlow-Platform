import { useUserStore } from '@/store/modules/user'

const BASE = '/api/ai'

function getToken() { return useUserStore().accessToken }

function extractError(err: any, status: number): string {
  return (err as any).detail || (err as any).msg || `请求失败 (${status})`
}

async function ragGet<T = any>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!resp.ok) throw new Error(extractError(await resp.json().catch(() => ({})), resp.status))
  return resp.json()
}

async function ragPost<T = any>(path: string, body?: any): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: body ? JSON.stringify(body) : undefined
  })
  if (!resp.ok) throw new Error(extractError(await resp.json().catch(() => ({})), resp.status))
  return resp.json()
}

async function ragDelete<T = any>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${getToken()}` }
  })
  if (!resp.ok) throw new Error(extractError(await resp.json().catch(() => ({})), resp.status))
  return resp.json()
}

export interface RagSession {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface RagMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
}

export interface RagDocument {
  filename: string
  size?: number
  uploaded_at?: string
  chunks_count?: number
}

/** 获取会话列表 */
export function fetchRagSessions(): Promise<{ sessions: RagSession[] }> {
  return ragGet('/chat/sessions')
}

/** 获取会话消息 */
export function fetchRagSessionMessages(sessionId: string): Promise<{ messages: RagMessage[] }> {
  return ragGet(`/chat/sessions/${sessionId}`)
}

/** 删除会话 */
export function deleteRagSession(sessionId: string): Promise<{ message: string }> {
  return ragDelete(`/chat/sessions/${sessionId}`)
}

/** 获取文档列表 */
export function fetchRagDocuments(): Promise<{ documents: RagDocument[] }> {
  return ragGet('/documents')
}

/** 上传单个文档 */
export async function uploadRagDocument(file: File): Promise<any> {
  const fd = new FormData()
  fd.append('file', file)
  const resp = await fetch(`${BASE}/documents/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: fd
  })
  if (!resp.ok) throw new Error(extractError(await resp.json().catch(() => ({})), resp.status))
  return resp.json()
}

/** 批量上传文档 */
export async function batchUploadRagDocuments(files: File[]): Promise<any> {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  const resp = await fetch(`${BASE}/documents/batch-upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: fd
  })
  if (!resp.ok) throw new Error(extractError(await resp.json().catch(() => ({})), resp.status))
  return resp.json()
}

/** SSE 流式聊天 */
export function streamRagChat(message: string, sessionId?: string): Promise<Response> {
  return fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`
    },
    body: JSON.stringify({ message, session_id: sessionId || 'default' })
  })
}

/** 删除文档 */
export function deleteRagDocument(filename: string): Promise<{ message: string }> {
  return ragDelete(`/documents/${encodeURIComponent(filename)}`)
}

