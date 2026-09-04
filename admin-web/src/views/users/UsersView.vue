<template>
  <div>
    <h2 class="page-title">用户管理</h2>

    <!-- 筛选条 -->
    <a-card :bordered="false" style="margin-bottom: 16px">
      <a-row :gutter="16" align="middle">
        <a-col :xs="24" :sm="12" :md="8">
          <a-input-search
            v-model:value="query.q"
            placeholder="搜索用户名/昵称/openid/ID"
            allow-clear
            @search="reload"
            @press-enter="reload"
          />
        </a-col>
        <a-col :xs="12" :sm="6" :md="4">
          <a-select v-model:value="query.is_active" placeholder="状态" allow-clear style="width: 100%" @change="reload">
            <a-select-option :value="true">正常</a-select-option>
            <a-select-option :value="false">已封禁</a-select-option>
          </a-select>
        </a-col>
        <a-col :xs="12" :sm="6" :md="4">
          <a-select v-model:value="query.is_admin" placeholder="角色" allow-clear style="width: 100%" @change="reload">
            <a-select-option :value="true">管理员</a-select-option>
            <a-select-option :value="false">普通用户</a-select-option>
          </a-select>
        </a-col>
        <a-col :xs="24" :sm="24" :md="8" style="text-align: right">
          <a-button @click="reload">刷新</a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- 表格 -->
    <a-card :bordered="false">
      <a-table
        :columns="columns"
        :data-source="users"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="onTableChange"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'user'">
            <a-space>
              <a-avatar :size="32">{{ record.nickname?.[0] || record.username?.[0] || 'U' }}</a-avatar>
              <div>
                <div>{{ record.nickname || record.username || '未设置' }}</div>
                <div style="font-size: 12px; color: #999">ID: {{ record.id }}</div>
              </div>
            </a-space>
          </template>
          <template v-else-if="column.key === 'role'">
            <a-tag v-if="record.is_admin" color="purple">管理员</a-tag>
            <a-tag v-else>普通用户</a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag v-if="record.is_active" color="success">正常</a-tag>
            <a-tag v-else color="error">已封禁</a-tag>
          </template>
          <template v-else-if="column.key === 'data'">
            <a-popover>
              <template #content>
                <div>待办: {{ record.data_counts?.todos || 0 }}</div>
                <div>目标: {{ record.data_counts?.goals || 0 }}</div>
                <div>收支: {{ record.data_counts?.transactions || 0 }}</div>
                <div>饮食: {{ record.data_counts?.meals || 0 }}</div>
              </template>
              <span style="cursor: pointer; color: #8DA9C4">
                待 {{ record.data_counts?.todos || 0 }} · 目 {{ record.data_counts?.goals || 0 }}
              </span>
            </a-popover>
          </template>
          <template v-else-if="column.key === 'time'">
            <div>注册: {{ formatTime(record.created_at) }}</div>
            <div style="font-size: 12px; color: #999">登录: {{ formatTime(record.last_login_at) || '从未' }}</div>
          </template>
          <template v-else-if="column.key === 'quota'">
            <a-statistic :value="record.ai_calls_remaining" :value-style="{ fontSize: '14px', color: record.ai_calls_remaining < 20 ? '#f5222d' : '#52c41a' }" />
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button type="link" size="small" @click="openDetail(record)">查看</a-button>
              <a-button v-if="record.is_active" type="link" size="small" danger @click="onBan(record)">封禁</a-button>
              <a-button v-else type="link" size="small" @click="onUnban(record)">解禁</a-button>
              <a-dropdown>
                <a-button type="link" size="small">更多</a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item @click="openResetPwd(record)">重置密码</a-menu-item>
                    <a-menu-item @click="openQuota(record)">调整配额</a-menu-item>
                    <a-menu-divider />
                    <a-menu-item danger :disabled="record.is_admin" @click="onDelete(record)">删除用户</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 详情抽屉 -->
    <UserDetailDrawer
      v-model:open="detailOpen"
      :user-id="detailUserId"
      @reset-pwd="openResetPwd"
      @adjust-quota="openQuota"
    />

    <!-- 重置密码弹窗 -->
    <a-modal v-model:open="resetPwdOpen" title="重置密码" @ok="onResetPwdConfirm" :confirm-loading="resetPwdLoading">
      <p>用户: <strong>{{ resetPwdTarget?.nickname || resetPwdTarget?.username }}</strong> (ID: {{ resetPwdTarget?.id }})</p>
      <a-input-password v-model:value="newPassword" placeholder="新密码(至少 6 位)" />
    </a-modal>

    <!-- 配额调整弹窗 -->
    <a-modal v-model:open="quotaOpen" title="调整 AI 配额" @ok="onQuotaConfirm" :confirm-loading="quotaLoading">
      <p>用户: <strong>{{ quotaTarget?.nickname || quotaTarget?.username }}</strong></p>
      <p>当前剩余: <strong>{{ quotaTarget?.ai_calls_remaining }}</strong></p>
      <a-radio-group v-model:value="quotaMode" style="margin-bottom: 12px">
        <a-radio-button value="set">设为</a-radio-button>
        <a-radio-button value="delta">增减</a-radio-button>
      </a-radio-group>
      <a-input-number v-model:value="quotaValue" :min="0" style="width: 100%" />
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Modal, message } from 'ant-design-vue'
import dayjs from 'dayjs'
import {
  listUsers, deleteUser, toggleUserActive, resetUserPassword, updateUserQuota
} from '@/api/users'
import UserDetailDrawer from './UserDetailDrawer.vue'

const loading = ref(false)
const users = ref([])
const total = ref(0)
const query = reactive({ q: '', is_active: undefined, is_admin: undefined })

const pagination = reactive({ current: 1, pageSize: 20, total: 0, showSizeChanger: true, showTotal: (t) => `共 ${t} 个用户` })

const columns = [
  { title: '用户', key: 'user', width: 200 },
  { title: '角色', key: 'role', width: 90 },
  { title: '状态', key: 'status', width: 80 },
  { title: '数据', key: 'data', width: 180 },
  { title: 'AI 配额', key: 'quota', width: 80 },
  { title: '时间', key: 'time', width: 200 },
  { title: '操作', key: 'actions', width: 220, fixed: 'right' }
]

const formatTime = (t) => t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'

const reload = async (page = pagination.current, pageSize = pagination.pageSize) => {
  loading.value = true
  try {
    const r = await listUsers({ page, page_size: pageSize, ...query })
    users.value = r.items
    total.value = r.total
    pagination.current = r.page
    pagination.pageSize = r.page_size
    pagination.total = r.total
  } finally {
    loading.value = false
  }
}

const onTableChange = (pag) => reload(pag.current, pag.pageSize)

onMounted(reload)

// 详情
const detailOpen = ref(false)
const detailUserId = ref(null)
const openDetail = (u) => { detailUserId.value = u.id; detailOpen.value = true }

// 封禁/解禁
const onBan = (u) => {
  Modal.confirm({
    title: '确认封禁',
    content: `封禁后 ${u.nickname || u.username} 将无法登录`,
    okType: 'danger',
    onOk: async () => {
      await toggleUserActive(u.id, false)
      message.success('已封禁')
      reload()
    }
  })
}
const onUnban = async (u) => { await toggleUserActive(u.id, true); message.success('已解禁'); reload() }

// 删除
const onDelete = (u) => {
  Modal.confirm({
    title: '确认删除',
    content: `将永久删除 ${u.nickname || u.username} 及其所有数据,不可恢复!`,
    okType: 'danger',
    onOk: async () => {
      await deleteUser(u.id)
      message.success('已删除')
      reload()
    }
  })
}

// 重置密码
const resetPwdOpen = ref(false)
const resetPwdTarget = ref(null)
const newPassword = ref('')
const resetPwdLoading = ref(false)
const openResetPwd = (u) => { resetPwdTarget.value = u; newPassword.value = ''; resetPwdOpen.value = true }
const onResetPwdConfirm = async () => {
  if (newPassword.value.length < 6) { message.error('密码至少 6 位'); return }
  resetPwdLoading.value = true
  try {
    await resetUserPassword(resetPwdTarget.value.id, newPassword.value)
    message.success('密码已重置')
    resetPwdOpen.value = false
  } finally { resetPwdLoading.value = false }
}

// 配额
const quotaOpen = ref(false)
const quotaTarget = ref(null)
const quotaMode = ref('set')
const quotaValue = ref(100)
const quotaLoading = ref(false)
const openQuota = (u) => { quotaTarget.value = u; quotaMode.value = 'set'; quotaValue.value = u.ai_calls_remaining; quotaOpen.value = true }
const onQuotaConfirm = async () => {
  quotaLoading.value = true
  try {
    const payload = quotaMode.value === 'set' ? { set: quotaValue.value } : { delta: quotaValue.value }
    await updateUserQuota(quotaTarget.value.id, payload)
    message.success('已更新')
    quotaOpen.value = false
    reload()
  } finally { quotaLoading.value = false }
}
</script>
