<script setup lang="ts">
/**
 * UserDetailDrawer — 用户详情侧滑面板
 *
 * Tabs:
 *   - basic:     基本信息 + 重算成就 + 状态/角色
 *   - data:      各业务表数据汇总
 *   - ai-chats:  AI 对话 session 列表(单条删除 + 批量清空)
 */
import { computed, ref, watch } from 'vue'
import {
  recomputeAchievements,
  getUserDataSummary,
  getUserAIChats,
  getUserAIChatDetail,
  deleteAIChat,
  deleteUserAIChats,
  type UserItem,
  type DataSummary,
  type AIChatSession,
  type AIChatDetailResponse
} from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatRelativeTime } from '@/utils/format'

interface Props {
  user: UserItem
  open: boolean
}
const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'updated', u: UserItem): void
}>()

const auth = useAuthStore()
const canManage = computed(() => auth.isSuperAdmin)

const activeTab = ref<'basic' | 'data' | 'ai-chats'>('basic')

// 关闭抽屉
function close() { emit('update:open', false) }

// ────────────── 数据汇总 ──────────────
const summary = ref<DataSummary | null>(null)
const summaryLoading = ref(false)
const summaryError = ref('')
async function loadSummary() {
  if (activeTab.value !== 'data') return
  summaryLoading.value = true
  summaryError.value = ''
  try {
    summary.value = await getUserDataSummary(props.user.id)
  } catch (e: any) {
    summaryError.value = e?.response?.data?.detail || e?.message || '加载失败'
    summary.value = null
  } finally {
    summaryLoading.value = false
  }
}

// ────────────── AI 对话 ──────────────
const aiChats = ref<AIChatSession[]>([])
const aiChatsTotal = ref(0)
const aiChatsLoading = ref(false)
const aiChatsError = ref('')
const expandedSession = ref<string | null>(null)
const sessionDetail = ref<AIChatDetailResponse | null>(null)
const sessionDetailLoading = ref(false)

async function loadAIChats() {
  if (activeTab.value !== 'ai-chats') return
  aiChatsLoading.value = true
  aiChatsError.value = ''
  try {
    const r = await getUserAIChats(props.user.id, { page: 1, page_size: 50 })
    aiChats.value = r.items ?? []
    aiChatsTotal.value = r.total ?? 0
  } catch (e: any) {
    aiChatsError.value = e?.response?.data?.detail || e?.message || '加载失败'
    aiChats.value = []
    aiChatsTotal.value = 0
  } finally {
    aiChatsLoading.value = false
  }
}

async function toggleSession(s: AIChatSession) {
  if (expandedSession.value === s.session_id) {
    expandedSession.value = null
    sessionDetail.value = null
    return
  }
  expandedSession.value = s.session_id
  sessionDetail.value = null
  sessionDetailLoading.value = true
  try {
    sessionDetail.value = await getUserAIChatDetail(props.user.id, s.session_id)
  } catch (e: any) {
    aiChatsError.value = e?.response?.data?.detail || e?.message || '加载会话失败'
  } finally {
    sessionDetailLoading.value = false
  }
}

async function removeSession(s: AIChatSession) {
  if (!confirm(`确定要删除会话「${s.first_user?.slice(0, 30) || s.session_id.slice(0, 8)}…」?这会删除该 session 的全部消息,且不可恢复。`)) return
  try {
    await deleteAIChat(props.user.id, s.session_id)
    if (expandedSession.value === s.session_id) {
      expandedSession.value = null
      sessionDetail.value = null
    }
    await loadAIChats()
  } catch (e: any) {
    alert('删除失败:' + (e?.response?.data?.detail || e?.message || ''))
  }
}

async function clearAllAIChats() {
  if (!confirm(`确定要清空该用户的所有 AI 对话记录(共 ${aiChatsTotal.value} 个 session)?该操作不可恢复。`)) return
  try {
    const r = await deleteUserAIChats(props.user.id)
    expandedSession.value = null
    sessionDetail.value = null
    await loadAIChats()
    alert(`已清理 ${r.deleted} 条消息`)
  } catch (e: any) {
    alert('批量删除失败:' + (e?.response?.data?.detail || e?.message || ''))
  }
}

// ────────────── 重算成就 ──────────────
const recomputeLoading = ref(false)
const recomputeResult = ref<{ recomputed: number; newly_unlocked: any[] } | null>(null)
const recomputeError = ref('')
async function runRecompute() {
  if (!confirm(`确定要重算「${props.user.username ?? props.user.id}」的成就?`)) return
  recomputeLoading.value = true
  recomputeError.value = ''
  recomputeResult.value = null
  try {
    const r = await recomputeAchievements(props.user.id)
    recomputeResult.value = { recomputed: r.recomputed, newly_unlocked: r.newly_unlocked ?? [] }
  } catch (e: any) {
    recomputeError.value = e?.response?.data?.detail || e?.message || '重算失败'
  } finally {
    recomputeLoading.value = false
  }
}

// ────────────── watch tab 切换 ──────────────
watch(activeTab, (v) => {
  if (v === 'data') loadSummary()
  if (v === 'ai-chats') loadAIChats()
})

// 抽屉打开时自动重置 tab + 拉第一屏
watch(() => props.open, (v) => {
  if (v) {
    activeTab.value = 'basic'
    recomputeResult.value = null
    recomputeError.value = ''
    summary.value = null
    aiChats.value = []
    aiChatsTotal.value = 0
    expandedSession.value = null
    sessionDetail.value = null
  }
})

// ────────────── 派生 ──────────────
const totalDataPoints = computed(() => {
  if (!summary.value) return 0
  const d = summary.value.data_counts
  return d.todos + d.goals + d.transactions + d.meals + d.reminders + d.achievements + d.reports
})
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="open" class="mask" @click.self="close">
        <aside class="drawer glass-2">
          <header class="d-header">
            <div class="d-id">
              <span class="avatar">{{ (user.nickname || user.username || '?').slice(0, 1) }}</span>
              <div class="d-id-text">
                <h3>{{ user.nickname || user.username || `用户 #${user.id}` }}</h3>
                <p class="sub">@{{ user.username || '未设置' }} · #{{ user.id }}</p>
              </div>
            </div>
            <button class="x" @click="close" aria-label="关闭">×</button>
          </header>

          <nav class="tabs">
            <button
              v-for="t in [
                { key: 'basic', label: '基础' },
                { key: 'data', label: '数据' },
                { key: 'ai-chats', label: 'AI 对话' }
              ]"
              :key="t.key"
              class="tab"
              :class="{ active: activeTab === t.key }"
              @click="activeTab = t.key as any"
            >{{ t.label }}</button>
          </nav>

          <div class="d-body">
            <!-- BASIC TAB -->
            <section v-if="activeTab === 'basic'" class="tab-panel">
              <div class="op-bar">
                <h4 class="sec-title">操作</h4>
                <div class="op-actions">
                  <button
                      class="btn primary"
                      :disabled="recomputeLoading"
                      @click="runRecompute"
                    >
                      {{ recomputeLoading ? '重算中…' : '⟳ 重算成就' }}
                    </button>
                </div>
              </div>

              <div v-if="recomputeError" class="err">{{ recomputeError }}</div>
              <div v-if="recomputeResult" class="result-card">
                <div class="result-line">
                  <span class="result-label">评估定义</span>
                  <span class="result-val mono">{{ recomputeResult.recomputed }}</span>
                </div>
                <div class="result-line">
                  <span class="result-label">新解锁</span>
                  <span class="result-val mono">{{ recomputeResult.newly_unlocked.length }}</span>
                </div>
                <div v-if="recomputeResult.newly_unlocked.length" class="newly">
                  <div v-for="a in recomputeResult.newly_unlocked" :key="a.type" class="newly-item">
                    <span class="newly-icon">{{ a.icon || '🏅' }}</span>
                    <div class="newly-text">
                      <div class="newly-name">{{ a.name }}</div>
                      <div class="newly-desc">{{ a.description }}</div>
                      <div class="newly-progress">
                        {{ a.current_value }} / {{ a.target_value }} {{ a.metric_type }}
                      </div>
                    </div>
                  </div>
                </div>
                <div v-else class="newly-empty">暂无新解锁</div>
              </div>

              <h4 class="sec-title" style="margin-top: 24px;">基本信息</h4>
              <div class="kv">
                <div class="kv-row"><span class="k">用户 ID</span><span class="v mono">#{{ user.id }}</span></div>
                <div class="kv-row"><span class="k">账号</span><span class="v mono">{{ user.username || '—' }}</span></div>
                <div class="kv-row"><span class="k">昵称</span><span class="v">{{ user.nickname || '—' }}</span></div>
                <div class="kv-row"><span class="k">OpenID</span><span class="v mono small">{{ user.openid || '—' }}</span></div>
                <div class="kv-row">
                  <span class="k">角色</span>
                  <span class="v">
                    <span class="badge" :class="`role-${user.role}`">
                      {{ user.is_admin ? '管理员' : '普通用户' }}
                    </span>
                  </span>
                </div>
                <div class="kv-row">
                  <span class="k">状态</span>
                  <span class="v">
                    <span class="badge" :class="user.is_active ? 'state-ok' : 'state-blocked'">
                      {{ user.is_active ? '正常' : '已封禁' }}
                    </span>
                  </span>
                </div>
                <div class="kv-row"><span class="k">AI 配额</span><span class="v mono">{{ user.ai_calls_remaining }}</span></div>
                <div class="kv-row"><span class="k">注册时间</span><span class="v">{{ formatDate(user.created_at, true) }}</span></div>
                <div class="kv-row"><span class="k">最后登录</span><span class="v">{{ user.last_login_at ? formatRelativeTime(user.last_login_at) : '从未' }}</span></div>
              </div>
            </section>

            <!-- DATA TAB -->
            <section v-if="activeTab === 'data'" class="tab-panel">
              <div v-if="summaryLoading" class="loading">加载中…</div>
              <div v-else-if="summaryError" class="err">{{ summaryError }}</div>
              <div v-else-if="summary">
                <div class="summary-head">
                  <div>
                    <h4 class="sec-title">数据汇总</h4>
                    <p class="muted-sm">共 {{ totalDataPoints }} 条业务记录</p>
                  </div>
                  <div class="summary-meta">
                    <div><span class="k">最后登录</span><span class="v">{{ summary.last_login_at ? formatRelativeTime(summary.last_login_at) : '—' }}</span></div>
                    <div><span class="k">最后 AI 调用</span><span class="v">{{ summary.last_ai_chat_at ? formatRelativeTime(summary.last_ai_chat_at) : '—' }}</span></div>
                  </div>
                </div>

                <div class="grid-cards">
                  <div class="g-card" v-for="d in [
                    { key: 'todos', label: '待办', icon: '✓', value: summary.data_counts.todos },
                    { key: 'goals', label: '目标', icon: '◎', value: summary.data_counts.goals },
                    { key: 'transactions', label: '收支', icon: '¥', value: summary.data_counts.transactions },
                    { key: 'meals', label: '饮食', icon: '◔', value: summary.data_counts.meals },
                    { key: 'reminders', label: '提醒', icon: '◐', value: summary.data_counts.reminders },
                    { key: 'achievements', label: '成就', icon: '★', value: summary.data_counts.achievements },
                    { key: 'reports', label: '报告', icon: '◧', value: summary.data_counts.reports },
                    { key: 'ai_chats_sessions', label: 'AI 会话', icon: '◈', value: summary.data_counts.ai_chats_sessions }
                  ]" :key="d.key">
                    <span class="g-icon">{{ d.icon }}</span>
                    <span class="g-label">{{ d.label }}</span>
                    <span class="g-val mono">{{ d.value }}</span>
                  </div>
                </div>

                <div class="ai-msgs-row">
                  <span class="k">AI 消息总数</span>
                  <span class="v mono">{{ summary.data_counts.ai_chats_messages }} 条</span>
                </div>
              </div>
            </section>

            <!-- AI CHATS TAB -->
            <section v-if="activeTab === 'ai-chats'" class="tab-panel">
              <div class="chats-head">
                <div>
                  <h4 class="sec-title">AI 对话记录</h4>
                  <p class="muted-sm">共 {{ aiChatsTotal }} 个 session · 仅展示最近 50 条</p>
                </div>
                <button
                  v-if="canManage && aiChatsTotal > 0"
                  class="btn danger"
                  @click="clearAllAIChats"
                >清空全部</button>
              </div>

              <div v-if="aiChatsLoading" class="loading">加载中…</div>
              <div v-else-if="aiChatsError" class="err">{{ aiChatsError }}</div>
              <div v-else-if="aiChats.length === 0" class="empty-tip">该用户暂无 AI 对话记录</div>
              <ul v-else class="chat-list">
                <li v-for="s in aiChats" :key="s.session_id" class="chat-item">
                  <div class="chat-row" @click="toggleSession(s)">
                    <span class="chat-icon">{{ expandedSession === s.session_id ? '▾' : '▸' }}</span>
                    <div class="chat-meta">
                      <div class="chat-title">{{ s.first_user?.slice(0, 60) || s.session_id.slice(0, 16) }}</div>
                      <div class="chat-sub">
                        <span>{{ s.msg_count ?? 0 }} 条消息</span>
                        <span v-if="s.last_at"> · {{ formatRelativeTime(s.last_at) }}</span>
                        <span v-if="s.model"> · {{ s.model }}</span>
                      </div>
                    </div>
                    <button v-if="canManage" class="op-btn danger" @click.stop="removeSession(s)">删除</button>
                  </div>
                  <div v-if="expandedSession === s.session_id" class="chat-detail">
                    <div v-if="sessionDetailLoading" class="loading sm">加载消息…</div>
                    <div v-else-if="sessionDetail" class="msgs">
                      <div
                        v-for="m in sessionDetail.messages"
                        :key="m.id"
                        class="msg"
                        :class="`role-${m.role}`"
                      >
                        <div class="msg-role">{{ m.role }}</div>
                        <div class="msg-content">{{ m.content }}</div>
                        <div class="msg-time">{{ formatDate(m.created_at, true) }}</div>
                      </div>
                    </div>
                  </div>
                </li>
              </ul>
            </section>
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 100;
  display: flex; justify-content: flex-end;
}
.drawer {
  width: 100%;
  max-width: 560px;
  height: 100vh;
  display: flex; flex-direction: column;
  overflow: hidden;
  border-radius: 0;
  border-left: 1px solid var(--glass-2-border);
}
.d-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid var(--c-line);
}
.d-id { display: flex; align-items: center; gap: 12px; }
.avatar {
  width: 40px; height: 40px;
  border-radius: 50%;
  background: var(--accent-gradient);
  color: #fff;
  display: grid; place-items: center;
  font-size: 16px; font-weight: 600;
}
.d-id-text h3 { font-size: 15px; font-weight: 600; color: var(--c-ink); }
.d-id-text .sub { font-size: 12px; color: var(--c-ink-3); }
.x {
  background: transparent; border: none;
  font-size: 22px; color: var(--c-ink-3);
  width: 32px; height: 32px; border-radius: 50%;
  transition: background var(--t-fast);
}
.x:hover { background: var(--glass-1-bg); color: var(--c-ink); }

.tabs {
  display: flex;
  padding: 0 20px;
  border-bottom: 1px solid var(--c-line);
  gap: 4px;
}
.tab {
  padding: 12px 14px;
  background: transparent;
  border: none;
  color: var(--c-ink-3);
  font-size: 13px; font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color var(--t-fast), border-color var(--t-fast);
}
.tab:hover { color: var(--c-ink-2); }
.tab.active {
  color: var(--c-ink);
  border-bottom-color: var(--accent-1);
}

.d-body { flex: 1; overflow: auto; padding: 20px; }
.tab-panel { display: flex; flex-direction: column; gap: 12px; }

.op-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.op-actions { display: flex; gap: 8px; }
.sec-title { font-size: 13px; font-weight: 600; color: var(--c-ink-2); letter-spacing: 0.04em; text-transform: uppercase; }
.muted-sm { font-size: 12px; color: var(--c-ink-3); margin-top: 2px; }

.btn {
  padding: 8px 14px;
  border-radius: var(--r-sm);
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--t-fast);
}
.btn.primary { background: var(--accent-gradient); color: #fff; }
.btn.primary:hover { opacity: 0.9; }
.btn.danger { background: var(--state-error); color: #fff; }
.btn.danger:hover { opacity: 0.9; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.err {
  font-size: 12px; color: var(--state-error);
  background: rgba(248, 113, 113, 0.10);
  padding: 8px 12px; border-radius: var(--r-sm);
}
.result-card {
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  padding: 14px;
}
.result-line {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px;
}
.result-label { color: var(--c-ink-3); }
.result-val { color: var(--c-ink); font-weight: 600; font-size: 14px; }
.newly {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--c-line);
  display: flex; flex-direction: column; gap: 10px;
}
.newly-item { display: flex; gap: 10px; }
.newly-icon { font-size: 22px; }
.newly-text { flex: 1; }
.newly-name { font-size: 13px; font-weight: 600; color: var(--c-ink); }
.newly-desc { font-size: 12px; color: var(--c-ink-3); margin-top: 2px; }
.newly-progress {
  margin-top: 4px;
  font-size: 11px; color: var(--c-ink-3);
  font-family: var(--font-mono);
}
.newly-empty { margin-top: 12px; font-size: 12px; color: var(--c-ink-3); text-align: center; padding: 8px; }

.kv {
  display: flex; flex-direction: column;
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.kv-row {
  display: grid; grid-template-columns: 100px 1fr;
  padding: 10px 14px;
  border-bottom: 1px solid var(--c-line);
  font-size: 13px;
}
.kv-row:last-child { border-bottom: none; }
.kv-row .k { color: var(--c-ink-3); font-size: 12px; }
.kv-row .v { color: var(--c-ink); }
.kv-row .v.small { font-size: 11px; word-break: break-all; }

.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: var(--r-pill);
  font-size: 11px; font-weight: 600;
  background: var(--glass-1-bg);
  color: var(--c-ink-2);
  border: 1px solid var(--c-line);
}
.badge.role-super_admin,
.badge.role-admin {
  background: rgba(124, 92, 255, 0.12);
  color: var(--accent-1);
  border-color: rgba(124, 92, 255, 0.30);
}
.badge.state-ok {
  background: rgba(34, 197, 94, 0.10);
  color: var(--state-success);
  border-color: rgba(34, 197, 94, 0.30);
}
.badge.state-blocked {
  background: rgba(248, 113, 113, 0.10);
  color: var(--state-error);
  border-color: rgba(248, 113, 113, 0.30);
}

.summary-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.summary-meta {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12px; color: var(--c-ink-3);
  text-align: right;
}
.summary-meta .k { margin-right: 4px; color: var(--c-ink-3); }
.summary-meta .v { color: var(--c-ink-2); font-weight: 500; }

.grid-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.g-card {
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  padding: 12px;
  display: grid;
  grid-template-columns: 24px 1fr auto;
  gap: 8px;
  align-items: center;
}
.g-icon { font-size: 18px; color: var(--accent-1); }
.g-label { font-size: 12px; color: var(--c-ink-3); }
.g-val { font-size: 18px; font-weight: 700; color: var(--c-ink); }

.ai-msgs-row {
  margin-top: 16px;
  display: flex; justify-content: space-between;
  padding: 12px 14px;
  background: var(--glass-3-bg);
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
}
.ai-msgs-row .k { font-size: 12px; color: var(--c-ink-3); }
.ai-msgs-row .v { font-size: 14px; font-weight: 600; }

.chats-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}
.chat-list { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.chat-item {
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.chat-row {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 12px 14px;
  cursor: pointer;
  transition: background var(--t-fast);
}
.chat-row:hover { background: var(--glass-1-bg); }
.chat-icon { color: var(--c-ink-3); font-size: 12px; }
.chat-title { font-size: 13px; color: var(--c-ink); font-weight: 500; }
.chat-sub { font-size: 11px; color: var(--c-ink-3); margin-top: 2px; }
.op-btn {
  padding: 4px 10px;
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
  background: transparent;
  color: var(--c-ink-2);
  font-size: 12px;
  cursor: pointer;
}
.op-btn.danger { color: var(--state-error); border-color: rgba(248, 113, 113, 0.35); }
.op-btn.danger:hover { background: rgba(248, 113, 113, 0.12); }

.chat-detail {
  padding: 12px 14px;
  border-top: 1px solid var(--c-line);
  background: var(--glass-1-bg);
}
.msgs { display: flex; flex-direction: column; gap: 10px; }
.msg {
  padding: 10px 12px;
  border-radius: var(--r-sm);
  font-size: 13px;
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
}
.msg.role-user {
  border-left: 3px solid var(--accent-1);
}
.msg.role-assistant {
  border-left: 3px solid var(--accent-2);
}
.msg.role-tool {
  border-left: 3px solid var(--accent-3);
  background: rgba(96, 165, 250, 0.08);
}
.msg-role {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--c-ink-3);
  margin-bottom: 4px;
  letter-spacing: 0.06em;
}
.msg-content {
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--c-ink);
  line-height: 1.5;
}
.msg-time {
  margin-top: 4px;
  font-size: 10px;
  color: var(--c-ink-3);
  text-align: right;
}

.loading { padding: 24px; text-align: center; color: var(--c-ink-3); font-size: 13px; }
.loading.sm { padding: 12px; font-size: 12px; }
.empty-tip { padding: 24px; text-align: center; color: var(--c-ink-3); font-size: 12px; }

.drawer-enter-active,
.drawer-leave-active { transition: opacity 0.2s ease; }
.drawer-enter-active .drawer,
.drawer-leave-active .drawer { transition: transform 0.32s cubic-bezier(0.16, 1, 0.3, 1); }
.drawer-enter-from,
.drawer-leave-to { opacity: 0; }
.drawer-enter-from .drawer,
.drawer-leave-to .drawer { transform: translateX(20px); }
</style>