<template>
  <div class="rag-chat">
    <!-- 侧边栏 - 会话历史 -->
    <div class="chat-sidebar">
      <div class="sidebar-header">
        <div class="brand">

          <span class="brand-text"></span>
        </div>
        <ElButton size="small" type="primary" round @click="newChat">
          <i class="iconfont-sys">&#xe608;</i> 新对话
        </ElButton>
      </div>
      <div class="session-list">
        <div v-for="s in sessions" :key="s.session_id"
          :class="['session-item', { active: s.session_id === sessionId }]"
          @click="switchSession(s.session_id)">
          <span class="session-dot" :class="{ active: s.session_id === sessionId }" />
          <span class="session-title">{{ s.title || ragStore.getTitle(s.session_id) }}</span>
          <span class="session-count">{{ (s as any).message_count || 0 }}</span>
          <ElButton class="session-del" size="small" text type="danger" @click.stop="removeSession(s.session_id)">
            &#xe690;
          </ElButton>
        </div>
        <div v-if="sessions.length === 0 && !loading" class="empty-hint">
          <span class="empty-icon">🤖</span>
          <p>开始你的第一次对话</p>
        </div>
      </div>
    </div>

    <!-- 主聊天区 -->
    <div class="chat-main">
      <div class="msg-scroll">
      <!-- 欢迎屏 -->
      <div v-if="messages.length === 0 && !streaming" class="welcome">
        <div class="welcome-bot">🤖</div>
        <h2>你好，我是知源助手</h2>
        <p>基于 RAG 知识库的智能问答系统，可以检索文档内容并生成回答</p>
        <div class="quick-actions">
          <span class="quick-hint">你可以试着问我：</span>
          <div class="quick-items">
            <span class="quick-item" @click="userInput='帮我总结一下上传的文档内容'; handleSend()">帮我总结上传的文档</span>
            <span class="quick-item" @click="userInput='介绍一下RAG技术'; handleSend()">什么是 RAG 技术</span>
            <span class="quick-item" @click="userInput='今天有哪些新闻'; handleSend()">今天有哪些新闻</span>
          </div>
        </div>
      </div>

      <!-- 消息列表 -->
      <template v-for="(msg, i) in messages" :key="i">
        <div :class="['message-row', msg.isUser ? 'user' : 'bot']">
          <div class="msg-avatar">
            <span v-if="msg.isUser" class="avatar-text">{{ msg.isUser ? '我' : '' }}</span>
            <i v-else class="iconfont-sys bot-icon">🤖</i>
          </div>
          <div class="msg-body">
            <div v-if="!msg.isUser && msg.ragSteps?.length" class="trace-lines">
              <div v-for="(s, si) in msg.ragSteps" :key="si" class="trace-line">
                <span class="tl-icon">{{ s.icon }}</span>
                <span class="tl-label">{{ s.label }}</span>
                <span v-if="s.detail" class="tl-detail">{{ s.detail }}</span>
              </div>
            </div>
            <div v-if="msg.text" class="msg-bubble" v-html="renderMd(msg.text)" />
            <div v-if="!msg.isUser && msg.ragTrace" class="trace-toggle">
              <ElButton size="small" text type="primary" @click="msg.showTrace = !msg.showTrace">
                &#xe6df; 检索过程
              </ElButton>
              <div v-if="msg.showTrace" class="trace-panel">
                <div class="tp-grid">
                  <div>检索模式：{{ msg.ragTrace.retrieval_mode || '-' }}</div>
                  <div>候选数：{{ msg.ragTrace.candidate_k || '-' }}</div>
                  <div>叶子层级：L{{ msg.ragTrace.leaf_retrieve_level || '-' }}</div>
                  <div>Auto-merge：{{ msg.ragTrace.auto_merge_enabled ? '✓' : '✗' }}</div>
                  <div>Rerank：{{ msg.ragTrace.rerank_enabled ? '✓' : '✗' }}</div>
                  <div>扩展查询：{{ msg.ragTrace.query || '-' }}</div>
                </div>
                <h4>检索结果</h4>
                <div class="tp-list">
                  <div v-for="(chunk, ci) in traceChunks(msg.ragTrace)" :key="ci" class="tp-chunk">
                    <div class="chunk-hdr">
                      <span class="chunk-file">
                        {{ chunk.filename || '-' }}
                        <span v-if="chunk.page_number">(P{{ chunk.page_number }})</span>
                      </span>
                      <span class="chunk-rank">#{{ chunk.rrf_rank || chunk.final_rank || ci + 1 }}</span>
                    </div>
                    <div class="chunk-txt">{{ formatChunkText(chunk.text) }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- 流式消息 -->
      <div v-if="streaming" class="message-row bot">
        <div class="msg-avatar"><i class="iconfont-sys bot-icon">🤖</i></div>
        <div class="msg-body">
          <div class="thinking-bar">
            <span class="dot-pulse" />
            <span class="thinking-label">{{ ragSteps.length ? ragSteps.at(-1)!.label : 'AI 正在思考...' }}</span>
          </div>
          <div v-if="ragSteps.length" class="trace-lines">
            <div v-for="(s, si) in ragSteps" :key="si" class="trace-line">
              <span class="tl-icon">{{ s.icon }}</span>
              <span class="tl-label">{{ s.label }}</span>
              <span v-if="s.detail" class="tl-detail">{{ s.detail }}</span>
            </div>
          </div>
          <div v-if="streamText" class="msg-bubble" v-html="renderMd(streamText)" />
        </div>
      </div>

      <div ref="msgEndRef" />
      </div>

    <!-- 输入区 -->
    <div class="input-area">
      <div class="input-wrapper">
        <textarea
          ref="inputRef"
          v-model="userInput"
          class="chat-input"
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          rows="1"
          :disabled="streaming"
          @keydown.enter.exact.prevent="handleSend"
          @input="autoGrow"
        />
        <button v-if="streaming" class="send-btn stop" @click="stopStream">
          <span class="stop-icon" />
        </button>
        <button v-else class="send-btn" :disabled="!userInput.trim()" @click="handleSend">
          <i class="iconfont-sys">&#xe630;</i>
        </button>
      </div>
      <div class="input-hint">知源助手基于知识库生成回答，内容可能存在偏差，请仔细甄别</div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchRagSessions, fetchRagSessionMessages, deleteRagSession, streamRagChat, type RagSession } from '@/api/rag'
import { useRagStore } from '@/store/modules/rag'

defineOptions({ name: 'RagChat' })

interface ChatMsg { text: string; isUser: boolean; isThinking: boolean; ragTrace: any; ragSteps: { icon: string; label: string; detail: string }[]; showTrace: boolean }

const ragStore = useRagStore()
const sessions = ref<RagSession[]>([])
const messages = ref<ChatMsg[]>(ragStore.messages || [])
const sessionId = ref(ragStore.sessionId || `session_${Date.now()}`)
const loading = ref(false)
const userInput = ref('')
const streamText = ref('')
const ragSteps = ref<{ icon: string; label: string; detail: string }[]>([])
const ragTrace = ref<any>(null)
const streaming = ref(false)
const msgEndRef = ref<HTMLElement>()
const inputRef = ref<HTMLTextAreaElement>()
let abortCtrl: AbortController | null = null

watch([messages, sessionId], () => { ragStore.setSession(sessionId.value, [...messages.value]) }, { deep: true })

function traceChunks(t: any) { if (!t) return []; return t.retrieved_chunks || t.initial_retrieved_chunks || t.expanded_retrieved_chunks || [] }
function formatChunkText(text: string) {
  if (!text) return '-'
  return text
    .replace(/\r/g, '')
    .replace(/[ \t]*\n[ \t]*/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}
function renderMd(t: string): string {
  if (!t) return ''
  let o = t; o = o.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>'); o = o.replace(/`([^`]+)`/g, '<code>$1</code>')
  o = o.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>'); o = o.replace(/\*(.+?)\*/g, '<em>$1</em>')
  o = o.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>'); return o.replace(/\n/g, '<br>')
}
function autoGrow() { const el = inputRef.value; if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px' } }
function scrollBottom() { nextTick(() => msgEndRef.value?.scrollIntoView({ behavior: 'smooth' })) }
function appendRagStep(i: string, l: string, d: string) { const s = `${i}|${l}|${d}`; const last = ragSteps.value.at(-1); if (!last || `${last.icon}|${last.label}|${last.detail}` !== s) ragSteps.value.push({ icon: i, label: l, detail: d }) }

async function loadSessions() {
  try {
    const res = await fetchRagSessions()
    sessions.value = res.sessions || []
    sessions.value.forEach((session: any) => {
      if (session.title) {
        ragStore.setSessionTitle(session.session_id, session.title)
      }
    })
  } catch {
    /* */
  }
}
async function loadMessages(sid: string) {
  try {
    const res = await fetchRagSessionMessages(sid)
    messages.value = (res.messages || []).map((m: any) => ({ text: m.content || '', isUser: m.role === 'user', isThinking: false, ragTrace: m.rag_trace || null, ragSteps: [], showTrace: false }))
    scrollBottom()
  } catch { messages.value = [] }
}
function newChat() { sessionId.value = `session_${Date.now()}`; messages.value = []; streamText.value = ''; ragSteps.value = []; ragTrace.value = null; ragStore.clearSession(); userInput.value = '' }
async function switchSession(sid: string) { sessionId.value = sid; messages.value = []; await loadMessages(sid); ragStore.setSession(sid, [...messages.value]) }
async function removeSession(sid: string) { try { await deleteRagSession(sid); sessions.value = sessions.value.filter(s => s.session_id !== sid); if (sessionId.value === sid) newChat() } catch { ElMessage.error('删除失败') } }

async function handleSend() {
  const text = userInput.value.trim(); if (!text || streaming.value) return
  messages.value.push({ text, isUser: true, isThinking: false, ragTrace: null, ragSteps: [], showTrace: false })
  userInput.value = ''; autoGrow(); scrollBottom()
  streamText.value = ''; ragSteps.value = []; ragTrace.value = null; streaming.value = true; abortCtrl = new AbortController()
  try {
    const resp = await streamRagChat(text, sessionId.value); const reader = resp.body?.getReader(); if (!reader) throw new Error('No stream')
    const decoder = new TextDecoder(); let buffer = ''
    while (true) {
      const { done, value } = await reader.read(); if (done) break
      buffer += decoder.decode(value, { stream: true }); const events = buffer.split('\n\n'); buffer = events.pop() || ''
      for (const evt of events) { if (!evt.startsWith('data: ')) continue; const data = evt.slice(6); if (data === '[DONE]') continue
        try { const obj = JSON.parse(data); if (obj.type === 'content') { streamText.value += obj.content || ''; scrollBottom() } else if (obj.type === 'rag_step' && obj.step) { appendRagStep(obj.step.icon || '', obj.step.label || '', obj.step.detail || '') } else if (obj.type === 'trace') { ragTrace.value = obj.rag_trace || null } else if (obj.type === 'error') { streamText.value += `\n[错误: ${obj.error || obj.content}]` } } catch { /* */ }
      }
    }
    messages.value.push({ text: streamText.value, isUser: false, isThinking: false, ragTrace: ragTrace.value, ragSteps: [...ragSteps.value], showTrace: false })
    streamText.value = ''; ragSteps.value = []; ragTrace.value = null; loadSessions()
  } catch (e: any) { if (e.name !== 'AbortError') messages.value.push({ text: streamText.value || `请求失败: ${e.message}`, isUser: false, isThinking: false, ragTrace: ragTrace.value, ragSteps: [...ragSteps.value], showTrace: false }); streamText.value = ''; ragSteps.value = []; ragTrace.value = null
  } finally { streaming.value = false; abortCtrl = null; scrollBottom() }
}
function stopStream() { abortCtrl?.abort() }
onMounted(() => { loadSessions(); loadMessages(sessionId.value) })
</script>

<style lang="scss" scoped>
// ── 整体布局 ──
.rag-chat { display:flex; height:calc(100vh - 120px); background:var(--el-bg-color); border-radius:12px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,.05); }

// ── 侧边栏 ──
.chat-sidebar { width:280px; border-right:1px solid var(--el-border-color-lighter); display:flex; flex-direction:column; background:var(--el-fill-color-lighter); }
.sidebar-header { padding:16px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--el-border-color-lighter); }
.brand { display:flex; align-items:center; gap:8px; .brand-icon { font-family:iconfont-sys; font-size:22px; color:var(--el-color-primary); } .brand-text { font-weight:700; font-size:16px; } }
.session-list { flex:1; overflow-y:auto; padding:8px; }
.session-item { display:flex; align-items:center; gap:8px; padding:10px 12px; border-radius:8px; cursor:pointer; margin-bottom:2px; transition:background .15s;
  &:hover { background:var(--el-fill-color); }
  &.active { background:var(--el-color-primary-light-9); }
  .session-dot { width:8px; height:8px; border-radius:50%; background:var(--el-color-info); flex-shrink:0; &.active { background:var(--el-color-primary); box-shadow:0 0 6px var(--el-color-primary); } }
  .session-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:var(--el-text-color-primary); }
  .session-count { font-size:11px; color:var(--el-text-color-placeholder); background:var(--el-fill-color-dark); padding:1px 6px; border-radius:8px; flex-shrink:0; }
  .session-del { opacity:0; transition:opacity .15s; font-family:iconfont-sys; }
  &:hover .session-del { opacity:1; }
}
.empty-hint { text-align:center; padding:40px 20px; color:var(--el-text-color-secondary); .empty-icon { font-family:iconfont-sys; font-size:36px; display:block; margin-bottom:8px; } p { font-size:13px; margin:0; } }

// ── 主聊天区 ──
.chat-main { flex:1; display:flex; flex-direction:column; overflow:hidden; min-height:0; }
.msg-scroll { flex:1; overflow-y:auto; }
.welcome { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:40px; text-align:center;
  .welcome-bot { font-family:iconfont-sys; font-size:64px; width:96px; height:96px; border-radius:50%; background:linear-gradient(135deg, var(--el-color-primary-light-7), var(--el-color-primary-light-3)); display:flex; align-items:center; justify-content:center; margin-bottom:16px; }
  h2 { font-size:22px; margin:0 0 8px; font-weight:600; }
  p { color:var(--el-text-color-secondary); margin:0 0 24px; font-size:14px; }
  .quick-actions { max-width:440px; }
  .quick-hint { font-size:12px; color:var(--el-text-color-placeholder); display:block; margin-bottom:8px; }
  .quick-items { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
  .quick-item { padding:6px 14px; border:1px solid var(--el-border-color); border-radius:16px; font-size:13px; cursor:pointer; transition:all .15s; color:var(--el-text-color-regular); &:hover { border-color:var(--el-color-primary); color:var(--el-color-primary); background:var(--el-color-primary-light-9); } }
}

// ── 消息 ──
.message-row { display:flex; gap:12px; padding:16px 24px;
  &.user { flex-direction:row-reverse; background:var(--el-fill-color-lighter); }
  &.bot { background:var(--el-bg-color); }
}
.msg-avatar { width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0; background:var(--el-color-primary-light-9); font-size:12px; color:var(--el-color-primary); font-weight:600;
  .bot-icon { font-size:18px; font-family:iconfont-sys; color:var(--el-color-primary); }
}
.message-row.user .msg-avatar { background:var(--el-color-success-light-9); color:var(--el-color-success); }
.msg-body { max-width:72%; min-width:0; }
.message-row.bot .msg-body { max-width: calc(100% - 46px); width: calc(100% - 46px); }
.msg-bubble { padding:10px 16px; border-radius:16px; line-height:1.7; font-size:14px; word-break:break-word;
  :deep(code) { background:var(--el-color-primary-light-9); padding:2px 6px; border-radius:4px; font-size:13px; }
  :deep(pre) { background:var(--el-fill-color-dark); padding:12px; border-radius:8px; overflow-x:auto; margin:8px 0; code { background:none; padding:0; } }
}
.message-row.bot .msg-bubble { background:var(--el-fill-color); border-bottom-left-radius:4px; }
.message-row.user .msg-bubble { background:var(--el-color-primary-light-9); border-bottom-right-radius:4px; }

// ── trace lines ──
.trace-lines { margin-bottom:6px; }
.trace-line { display:flex; align-items:center; gap:4px; padding:1px 0; font-size:12px; color:var(--el-text-color-secondary); .tl-icon { flex-shrink:0; } .tl-label { color:var(--el-text-color-regular); } .tl-detail { color:var(--el-text-color-placeholder); margin-left:4px; font-size:11px; } }
.thinking-bar { display:flex; align-items:center; gap:8px; padding:8px 16px; .dot-pulse { width:8px; height:8px; border-radius:50%; background:var(--el-color-primary); animation:pulse 1.2s infinite; } .thinking-label { font-size:12px; color:var(--el-text-color-secondary); } }
@keyframes pulse { 0%,100%{opacity:.3;transform:scale(.8)} 50%{opacity:1;transform:scale(1.2)} }

// ── trace panel ──
.trace-toggle { margin-top:6px; width:100%; }
.trace-panel { margin-top:6px; width:100%; box-sizing:border-box; padding:12px; background:var(--el-fill-color-light); border-radius:8px; font-size:12px; display:flex; flex-direction:column; }
.tp-grid { display:grid; grid-template-columns:1fr 1fr; gap:2px 12px; margin-bottom:8px; color:var(--el-text-color-regular); }
.tp-list { display:flex; flex-direction:column; gap:8px; width:100%; }
.tp-chunk { width:100%; box-sizing:border-box; padding:10px 12px; background:var(--el-bg-color); border-radius:6px; border-left:3px solid var(--el-color-primary); }
.chunk-hdr { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:4px; font-weight:600; }
.chunk-file { min-width:0; }
.chunk-rank { flex-shrink:0; font-size:11px; color:var(--el-text-color-secondary); }
.chunk-txt { font-size:12px; color:var(--el-text-color-regular); line-height:1.6; max-height:96px; overflow-y:auto; white-space:normal; word-break:break-word; }

// ── 输入区 ──
.input-area { flex-shrink:0; padding:12px 24px 16px; border-top:1px solid var(--el-border-color-lighter); background:var(--el-bg-color); }
.input-wrapper { display:flex; align-items:flex-end; gap:8px; background:var(--el-fill-color); border-radius:16px; padding:8px 16px; border:1px solid var(--el-border-color-light); transition:border-color .2s; &:focus-within { border-color:var(--el-color-primary); } }
.chat-input { flex:1; border:none; outline:none; background:transparent; resize:none; font-size:14px; line-height:1.5; min-height:24px; max-height:160px; font-family:inherit; color:var(--el-text-color-primary); &::placeholder { color:var(--el-text-color-placeholder); } }
.send-btn { width:36px; height:36px; border:none; border-radius:50%; background:var(--el-color-primary); color:#fff; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:all .15s; flex-shrink:0; &:hover:not(:disabled) { transform:scale(1.08); } &:disabled { background:var(--el-color-info-light-5); cursor:not-allowed; }
  i { font-family:iconfont-sys; font-size:16px; }
  &.stop { background:var(--el-color-danger); .stop-icon { width:12px; height:12px; background:#fff; border-radius:2px; } }
}
.input-hint { text-align:center; font-size:11px; color:var(--el-text-color-placeholder); margin-top:8px; }
</style>
