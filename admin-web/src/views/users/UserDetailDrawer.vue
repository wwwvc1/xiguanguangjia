<template>
  <a-drawer
    :open="open"
    :width="isMobile ? '100%' : 720"
    :title="user ? `用户详情 - ${user.nickname || user.username || 'ID:' + user.id}` : '用户详情'"
    @close="onClose"
  >
    <a-spin :spinning="loading">
      <template v-if="user">
        <a-tabs v-model:active-key="activeTab">
          <!-- 基本信息 -->
          <a-tab-pane key="basic" title="基本信息">
            <a-descriptions :column="1" bordered size="small">
              <a-descriptions-item label="ID">{{ user.id }}</a-descriptions-item>
              <a-descriptions-item label="用户名">{{ user.username || '-' }}</a-descriptions-item>
              <a-descriptions-item label="昵称">{{ user.nickname || '-' }}</a-descriptions-item>
              <a-descriptions-item label="OpenID">
                <a-typography-text copyable :ellipsis="{ tooltip: user.openid }">{{ user.openid }}</a-typography-text>
              </a-descriptions-item>
              <a-descriptions-item label="角色">
                <a-tag v-if="user.is_admin" color="purple">管理员</a-tag>
                <a-tag v-else>普通用户</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="状态">
                <a-tag v-if="user.is_active" color="success">正常</a-tag>
                <a-tag v-else color="error">已封禁</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="AI 配额">
                <span :style="{ color: user.ai_calls_remaining < 20 ? '#f5222d' : '#52c41a', fontWeight: 600 }">
                  {{ user.ai_calls_remaining }}
                </span>
              </a-descriptions-item>
              <a-descriptions-item label="注册时间">{{ formatTime(user.created_at) }}</a-descriptions-item>
              <a-descriptions-item label="最后登录">{{ formatTime(user.last_login_at) || '从未' }}</a-descriptions-item>
            </a-descriptions>

            <a-divider>数据统计</a-divider>
            <a-row :gutter="[12, 12]">
              <a-col v-for="item in dataItems" :key="item.key" :xs="12" :sm="8">
                <div class="data-stat">
                  <div class="num">{{ user.data_counts?.[item.key] || 0 }}</div>
                  <div class="label">{{ item.label }}</div>
                </div>
              </a-col>
            </a-row>
          </a-tab-pane>

          <!-- AI 对话 -->
          <a-tab-pane key="ai" title="AI 对话">
            <a-spin :spinning="chatLoading">
              <a-empty v-if="sessions.length === 0 && !chatLoading" description="暂无 AI 对话记录" />
              <a-list v-else size="small" :data-source="sessions" :pagination="sessionPagination">
                <template #renderItem="{ item }">
                  <a-list-item style="cursor: pointer" @click="openSession(item.session_id)">
                    <a-list-item-meta>
                      <template #title>
                        <a-space>
                          <span>{{ item.first_user?.slice(0, 40) || '(空消息)' }}</span>
                          <a-tag v-if="item.model" color="blue" size="small">{{ item.model }}</a-tag>
                        </a-space>
                      </template>
                      <template #description>
                        <span style="color: #999">{{ item.msg_count }} 条 · {{ formatTime(item.last_at) }}</span>
                      </template>
                    </a-list-item-meta>
                  </a-list-item>
                </template>
              </a-list>
            </a-spin>
          </a-tab-pane>
        </a-tabs>
      </template>
    </a-spin>

    <!-- Session 详情弹窗 -->
    <a-modal v-model:open="sessionOpen" :footer="null" width="700px" :title="`对话 Session - ${currentSession}`">
      <a-spin :spinning="detailLoading">
        <div v-for="m in sessionMessages" :key="m.id" class="chat-msg" :class="m.role">
          <div class="role">{{ roleLabel(m.role) }}</div>
          <div class="content">{{ m.content }}</div>
          <div v-if="m.tool_calls" class="tool-calls">
            <div v-for="tc in (m.tool_calls.tool_calls || m.tool_calls)" :key="tc.id || tc.name" class="tool">
              🔧 {{ tc.name }} <span v-if="tc.function?.arguments">({{ tc.function.arguments }})</span>
            </div>
          </div>
          <div class="meta">
            <a-tag v-if="m.model" size="small">{{ m.model }}</a-tag>
            <span style="color: #999; font-size: 12px">{{ formatTime(m.created_at) }}</span>
          </div>
        </div>
      </a-spin>
    </a-modal>
  </a-drawer>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import dayjs from 'dayjs'
import { getUserDetail, getUserAIChats, getUserAIChatDetail } from '@/api/users'

const props = defineProps({ open: Boolean, userId: [Number, null] })
const emit = defineEmits(['update:open', 'reset-pwd', 'adjust-quota'])

const loading = ref(false)
const user = ref(null)
const activeTab = ref('basic')

const isMobile = ref(window.innerWidth < 768)
const onResize = () => { isMobile.value = window.innerWidth < 768 }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

const dataItems = [
  { key: 'todos', label: '待办' }, { key: 'goals', label: '目标' },
  { key: 'transactions', label: '收支' }, { key: 'meals', label: '饮食' },
  { key: 'reminders', label: '提醒' }, { key: 'achievements', label: '成就' },
  { key: 'reports', label: '周报月报' }
]

const formatTime = (t) => t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'

watch(() => props.open, async (v) => {
  if (v && props.userId) await load()
})

const load = async () => {
  loading.value = true
  try {
    user.value = await getUserDetail(props.userId)
  } finally {
    loading.value = false
  }
}

const onClose = () => { emit('update:open', false) }

// AI 会话
const sessions = ref([])
const chatLoading = ref(false)
const loadSessions = async (page = 1) => {
  chatLoading.value = true
  try {
    const r = await getUserAIChats(props.userId, { page, page_size: 20 })
    sessions.value = r.items
    sessionPagination.value.total = r.total
    sessionPagination.value.current = page
  } finally {
    chatLoading.value = false
  }
}
const sessionPagination = ref({ current: 1, pageSize: 20, total: 0, simple: true, onChange: loadSessions })

watch(() => activeTab.value, (v) => { if (v === 'ai' && sessions.value.length === 0) loadSessions() })

const sessionOpen = ref(false)
const currentSession = ref(null)
const sessionMessages = ref([])
const detailLoading = ref(false)
const openSession = async (sid) => {
  currentSession.value = sid
  sessionOpen.value = true
  detailLoading.value = true
  try {
    const r = await getUserAIChatDetail(props.userId, sid)
    sessionMessages.value = r.messages
  } finally { detailLoading.value = false }
}

const roleLabel = (r) => ({ user: '👤 用户', assistant: '🤖 AI', tool: '🔧 工具', system: '⚙️ 系统' }[r] || r)
</script>

<style scoped>
.data-stat {
  text-align: center;
  background: #fafafa;
  border-radius: 8px;
  padding: 12px;
}
.data-stat .num { font-size: 24px; font-weight: 700; color: #5A6573; }
.data-stat .label { font-size: 12px; color: #999; margin-top: 4px; }
.chat-msg {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 8px;
  background: #fafafa;
}
.chat-msg.user { background: #E8F0F8; }
.chat-msg.assistant { background: #fff; border: 1px solid #f0f0f0; }
.chat-msg .role { font-size: 12px; color: #999; margin-bottom: 4px; }
.chat-msg .content { white-space: pre-wrap; word-break: break-word; }
.chat-msg .meta { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
.tool-calls { margin-top: 8px; }
.tool { font-size: 12px; color: #666; padding: 4px 0; }
</style>
