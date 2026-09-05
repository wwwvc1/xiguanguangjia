<script setup lang="ts">
/**
 * UsersView — 用户管理 (Phase 2 完整版)
 *
 * 功能:
 * - 列表 + 搜索 + 角色/状态筛选 + 分页
 * - 新建用户(弹窗表单)
 * - 编辑用户(弹窗表单,字段预填)
 * - 删除/封禁/解禁
 * - 重置密码(弹窗)
 * - 重算成就(详情抽屉入口)
 * - 详情抽屉:基础/数据/AI 对话(单删+批删)
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import GlassInput from '@/components/form/GlassInput.vue'
import GlassSelect from '@/components/form/GlassSelect.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UserDetailDrawer from './users/UserDetailDrawer.vue'
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  setUserActive,
  resetUserPassword,
  type UserItem,
  type NewUser,
  type UserPatch
} from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatRelativeTime } from '@/utils/format'

// ────────────── 鉴权 ──────────────
const auth = useAuthStore()
const canManage = computed(() => auth.isSuperAdmin)

// ────────────── 列表状态 ──────────────
const filters = reactive({
  keyword: '',
  is_active: undefined as boolean | undefined,
  is_admin: undefined as boolean | undefined,
  page: 1,
  page_size: 20
})
const users = ref<UserItem[]>([])
const total = ref(0)
const loading = ref(false)
const errorMsg = ref<string | null>(null)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.page_size)))

async function load() {
  loading.value = true
  errorMsg.value = null
  try {
    const resp = await listUsers({
      keyword: filters.keyword || undefined,
      is_active: filters.is_active,
      is_admin: filters.is_admin,
      page: filters.page,
      page_size: filters.page_size
    })
    users.value = resp.items ?? []
    total.value = resp.total ?? 0
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载失败'
    users.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function resetSearch() {
  filters.keyword = ''
  filters.is_active = undefined
  filters.is_admin = undefined
  filters.page = 1
  load()
}

watch(() => [filters.is_active, filters.is_admin], () => {
  filters.page = 1
  load()
})

onMounted(load)

// ────────────── 头像辅助 ──────────────
/** 把后端 avatar 字段变成 <img> 可用的 src:
 *  - 已是 data: URL 或 http(s) → 原样
 *  - 裸 base64 → 拼 data:image/<mime>;base64,
 *  - 空/无效 → undefined,组件降级显示首字母
 */
function avatarSrc(u: { avatar?: string | null } | null | undefined): string | undefined {
  const a = u?.avatar
  if (!a) return undefined
  if (a.startsWith('data:') || a.startsWith('http')) return a
  const mime = a.startsWith('/9j/') ? 'jpeg' : a.startsWith('iVBOR') ? 'png' : 'png'
  return `data:image/${mime};base64,${a}`
}

// ────────────── 新建/编辑用户 ──────────────
interface UserFormState {
  username: string
  password: string
  nickname: string
  email: string
  role: 'super_admin' | 'admin' | 'viewer'
  is_active: boolean
}
const blankForm = (): UserFormState => ({
  username: '',
  password: '',
  nickname: '',
  email: '',
  role: 'viewer',
  is_active: true
})

const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const formSubmitting = ref(false)
const formError = ref('')
const formState = reactive<UserFormState>(blankForm())
const editingId = ref<number | null>(null)

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  Object.assign(formState, blankForm())
  formError.value = ''
  formOpen.value = true
}

function openEdit(u: UserItem) {
  formMode.value = 'edit'
  editingId.value = u.id
  Object.assign(formState, {
    username: u.username ?? '',
    password: '', // 编辑时密码留空,后端不更新密码
    nickname: u.nickname ?? '',
    email: u.email ?? '',
    role: u.role ?? (u.is_admin ? 'super_admin' : 'viewer'),
    is_active: u.is_active
  })
  formError.value = ''
  formOpen.value = true
}

async function submitForm() {
  formError.value = ''
  if (!formState.username || formState.username.length < 3) {
    formError.value = '账号至少 3 个字符'
    return
  }
  if (formMode.value === 'create') {
    if (!formState.password || formState.password.length < 6) {
      formError.value = '密码至少 6 位'
      return
    }
  }
  formSubmitting.value = true
  try {
    if (formMode.value === 'create') {
      const payload: NewUser = {
        username: formState.username,
        password: formState.password,
        nickname: formState.nickname || undefined,
        email: formState.email || undefined,
        role: formState.role,
        is_active: formState.is_active
      }
      await createUser(payload)
    } else if (editingId.value != null) {
      const patch: UserPatch = {
        nickname: formState.nickname || undefined,
        email: formState.email || undefined,
        role: formState.role,
        is_active: formState.is_active
      }
      await updateUser(editingId.value, patch)
    }
    formOpen.value = false
    await load()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || e?.message || '保存失败'
  } finally {
    formSubmitting.value = false
  }
}

// ────────────── 删除 ──────────────
const confirmOpen = ref(false)
const confirmMode = ref<'delete' | 'toggle' | 'reset'>('delete')
const confirmTarget = ref<UserItem | null>(null)
const newPassword = ref('')

function askDelete(u: UserItem) {
  confirmMode.value = 'delete'
  confirmTarget.value = u
  confirmOpen.value = true
}
function askToggle(u: UserItem) {
  confirmMode.value = 'toggle'
  confirmTarget.value = u
  confirmOpen.value = true
}
function askReset(u: UserItem) {
  confirmMode.value = 'reset'
  confirmTarget.value = u
  newPassword.value = ''
  confirmOpen.value = true
}

const confirmBusy = ref(false)
const confirmError = ref('')
async function runConfirm() {
  if (!confirmTarget.value) return
  confirmError.value = ''
  confirmBusy.value = true
  try {
    if (confirmMode.value === 'delete') {
      await deleteUser(confirmTarget.value.id)
    } else if (confirmMode.value === 'toggle') {
      await setUserActive(confirmTarget.value.id, !confirmTarget.value.is_active)
    } else if (confirmMode.value === 'reset') {
      if (!newPassword.value || newPassword.value.length < 6) {
        confirmError.value = '新密码至少 6 位'
        confirmBusy.value = false
        return
      }
      await resetUserPassword(confirmTarget.value.id, newPassword.value)
    }
    confirmOpen.value = false
    await load()
  } catch (e: any) {
    confirmError.value = e?.response?.data?.detail || e?.message || '操作失败'
  } finally {
    confirmBusy.value = false
  }
}

// ────────────── 详情抽屉 ──────────────
const drawerUser = ref<UserItem | null>(null)
const drawerOpen = computed({
  get: () => drawerUser.value !== null,
  set: (v) => { if (!v) drawerUser.value = null }
})
function openDrawer(u: UserItem) {
  drawerUser.value = u
}
function onDrawerUpdated(u: UserItem) {
  drawerUser.value = u
  load()
}

// ────────────── 派生 ──────────────
const roleOptions = [
  { value: 'viewer', label: '普通用户' },
  { value: 'admin', label: '管理员' },
  { value: 'super_admin', label: '超级管理员' }
]
const activeOptions = [
  { value: '', label: '全部状态' },
  { value: '1', label: '正常' },
  { value: '0', label: '已封禁' }
]
const adminOptions = [
  { value: '', label: '全部角色' },
  { value: '1', label: '仅管理员' },
  { value: '0', label: '仅普通用户' }
]
function activeFilter(v: string): boolean | undefined {
  if (v === '') return undefined
  return v === '1'
}
function adminFilter(v: string): boolean | undefined {
  if (v === '') return undefined
  return v === '1'
}
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="用户管理" />
      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">用户管理</h2>
            <p class="muted">共 {{ total }} 位用户 · Phase 2 完整 CRUD</p>
          </div>
          <div class="actions">
            <button v-if="canManage" class="btn-primary" @click="openCreate">
              <span class="ic">＋</span>新建用户
            </button>
          </div>
        </header>

        <!-- 筛选条 -->
        <GlassCard :tier="2" padding="16px">
          <div class="filters">
            <div class="f-search">
              <GlassInput
                v-model="filters.keyword"
                placeholder="搜索账号 / 昵称 / openid / id"
                @keyup.enter="() => { filters.page = 1; load() }"
              />
            </div>
            <div class="f-select">
              <GlassSelect
                :model-value="filters.is_active === undefined ? '' : (filters.is_active ? '1' : '0')"
                :options="activeOptions"
                placeholder="状态"
                @update:model-value="(v: string | number) => (filters.is_active = activeFilter(String(v)))"
              />
            </div>
            <div class="f-select">
              <GlassSelect
                :model-value="filters.is_admin === undefined ? '' : (filters.is_admin ? '1' : '0')"
                :options="adminOptions"
                placeholder="角色"
                @update:model-value="(v: string | number) => (filters.is_admin = adminFilter(String(v)))"
              />
            </div>
            <button class="btn-ghost" @click="resetSearch">重置</button>
          </div>
        </GlassCard>

        <!-- 列表 -->
        <GlassCard :tier="2" padding="0">
          <div v-if="loading" class="loading">加载中…</div>
          <div v-else-if="errorMsg" class="error">{{ errorMsg }}</div>
          <EmptyState
            v-else-if="users.length === 0"
            icon="☉"
            title="暂无用户"
            hint="试着清空筛选条件,或点击右上角「新建用户」"
          />
          <table v-else class="tbl">
            <thead>
              <tr>
                <th class="col-id">ID</th>
                <th>用户 / 账号</th>
                <th>昵称</th>
                <th class="col-role">角色</th>
                <th class="col-status">状态</th>
                <th class="col-quota">AI 配额</th>
                <th class="col-time">注册时间</th>
                <th class="col-time">最后活跃</th>
                <th class="col-op">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td class="mono">#{{ u.id }}</td>
                <td>
                  <div class="user-cell">
                    <img v-if="avatarSrc(u)" :src="avatarSrc(u)" class="avatar avatar-img" alt="" />
                    <span v-else class="avatar">{{ (u.nickname || u.username || '?').slice(0, 1) }}</span>
                    <div class="user-meta">
                      <div class="name">{{ u.nickname || u.username || '—' }}</div>
                      <div class="sub">@{{ u.username || '未设置' }}</div>
                    </div>
                  </div>
                </td>
                <td>{{ u.nickname || '—' }}</td>
                <td>
                  <span class="badge" :class="`role-${u.role}`">
                    {{ u.is_admin ? '管理员' : '普通' }}
                  </span>
                </td>
                <td>
                  <span class="badge" :class="u.is_active ? 'state-ok' : 'state-blocked'">
                    {{ u.is_active ? '正常' : '已封禁' }}
                  </span>
                </td>
                <td class="mono">{{ u.ai_calls_remaining ?? '—' }}</td>
                <td>{{ formatDate(u.created_at) }}</td>
                <td>{{ u.last_login_at ? formatRelativeTime(u.last_login_at) : '—' }}</td>
                <td>
                  <div class="row-ops">
                    <button class="op-btn" title="详情" @click="openDrawer(u)">查看</button>
                    <button v-if="canManage && u.id !== auth.user?.id" class="op-btn" @click="openEdit(u)">编辑</button>
                    <button v-if="canManage && u.id !== auth.user?.id" class="op-btn" @click="askReset(u)">重置密码</button>
                    <button
                      v-if="canManage && u.id !== auth.user?.id && !u.is_admin"
                      class="op-btn"
                      :class="u.is_active ? 'op-warn' : 'op-ok'"
                      @click="askToggle(u)"
                    >
                      {{ u.is_active ? '封禁' : '解禁' }}
                    </button>
                    <button
                      v-if="canManage && u.id !== auth.user?.id && !u.is_admin"
                      class="op-btn op-danger"
                      @click="askDelete(u)"
                    >删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 分页 -->
          <div v-if="users.length > 0" class="pager">
            <button class="pg" :disabled="filters.page <= 1" @click="filters.page--; load()">上一页</button>
            <span class="pg-info">{{ filters.page }} / {{ totalPages }} · 共 {{ total }}</span>
            <button class="pg" :disabled="filters.page >= totalPages" @click="filters.page++; load()">下一页</button>
          </div>
        </GlassCard>
      </section>
    </div>

    <!-- 新建 / 编辑表单 -->
    <GlassModal
      v-model:open="formOpen"
      :title="formMode === 'create' ? '新建用户' : '编辑用户'"
      width="520px"
    >
      <div class="form">
        <div class="field">
          <label>账号 <span class="req">*</span></label>
          <GlassInput v-model="formState.username" :disabled="formMode === 'edit'" placeholder="3-64 位字母/数字/下划线" />
        </div>
        <div class="field">
          <label>
            密码
            <span v-if="formMode === 'create'" class="req">*</span>
            <span v-else class="hint">（留空则不修改）</span>
          </label>
          <GlassInput v-model="formState.password" type="password" placeholder="至少 6 位" />
        </div>
        <div class="field">
          <label>昵称</label>
          <GlassInput v-model="formState.nickname" placeholder="显示用昵称" />
        </div>
        <div class="field">
          <label>邮箱</label>
          <GlassInput v-model="formState.email" placeholder="可选,仅展示" />
        </div>
        <div class="field">
          <label>角色</label>
          <GlassSelect
            :model-value="formState.role"
            :options="roleOptions"
            placeholder="选择角色"
            @update:model-value="(v: string | number) => (formState.role = v as UserFormState['role'])"
          />
        </div>
        <div class="field row">
          <label class="checkbox">
            <input type="checkbox" v-model="formState.is_active" />
            <span>启用账号</span>
          </label>
        </div>
        <div v-if="formError" class="form-err">{{ formError }}</div>
      </div>
      <template #footer>
        <button class="btn ghost" @click="formOpen = false">取消</button>
        <button class="btn primary" :disabled="formSubmitting" @click="submitForm">
          {{ formSubmitting ? '提交中…' : (formMode === 'create' ? '创建' : '保存') }}
        </button>
      </template>
    </GlassModal>

    <!-- 删除 / 封禁 / 重置密码 确认 -->
    <ConfirmDialog
      v-model:open="confirmOpen"
      :title="
        confirmMode === 'delete' ? '删除用户' :
        confirmMode === 'toggle' ? (confirmTarget?.is_active ? '封禁用户' : '解禁用户') :
        '重置密码'
      "
      :message="
        confirmMode === 'delete'
          ? `确定要删除用户「${confirmTarget?.username ?? ''}」?该操作不可恢复,会级联删除该用户的全部数据。`
          : confirmMode === 'toggle'
            ? `确定要${confirmTarget?.is_active ? '封禁' : '解禁'}用户「${confirmTarget?.username ?? ''}」?`
            : `为用户「${confirmTarget?.username ?? ''}」设置新密码:`
      "
      :tone="confirmMode === 'delete' ? 'danger' : 'default'"
      :confirm-text="confirmMode === 'reset' ? '重置' : '确认'"
      @confirm="runConfirm"
    >
      <template v-if="confirmMode === 'reset'">
        <div class="form" style="margin-top: 12px;">
          <GlassInput v-model="newPassword" type="password" placeholder="新密码(至少 6 位)" />
          <div v-if="confirmError" class="form-err" style="margin-top: 8px;">{{ confirmError }}</div>
        </div>
      </template>
    </ConfirmDialog>

    <!-- 详情抽屉 -->
    <UserDetailDrawer
      v-if="drawerUser"
      v-model:open="drawerOpen"
      :user="drawerUser"
      @updated="onDrawerUpdated"
    />
  </div>
</template>

<style scoped>
.app-shell { display: grid; grid-template-columns: auto 1fr; min-height: 100vh; }
.app-main { min-width: 0; }
.page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.page-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 12px;
}
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--c-ink); }
.muted { color: var(--c-ink-3); font-size: 13px; margin-top: 4px; }

.btn-primary {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 16px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent-gradient);
  color: #fff;
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(124, 92, 255, 0.30);
  transition: transform var(--t-fast), box-shadow var(--t-fast);
}
.btn-primary:hover { transform: translateY(-1px); }
.btn-primary .ic { font-size: 14px; line-height: 1; }

.filters {
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap;
}
.f-search { flex: 1 1 240px; min-width: 200px; }
.f-select { width: 140px; }
.btn-ghost {
  padding: 10px 14px;
  border-radius: var(--r-sm);
  background: var(--glass-1-bg);
  border: 1px solid var(--c-line);
  color: var(--c-ink-2);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--t-fast);
}
.btn-ghost:hover { background: var(--glass-2-bg); }

.loading,
.error {
  padding: 48px 16px;
  text-align: center;
  color: var(--c-ink-3);
  font-size: 13px;
}
.error { color: var(--state-error); }

.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: var(--c-ink);
}
.tbl th, .tbl td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid var(--c-line);
}
.tbl th {
  font-weight: 600;
  font-size: 12px;
  color: var(--c-ink-3);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: var(--glass-1-bg);
  position: sticky; top: 0;
}
.tbl tbody tr { transition: background var(--t-fast); }
.tbl tbody tr:hover { background: var(--glass-1-bg); }
.col-id { width: 60px; }
.col-role { width: 80px; }
.col-status { width: 80px; }
.col-quota { width: 80px; text-align: right; }
.col-time { width: 130px; }
.col-op { width: 260px; }

.user-cell { display: flex; align-items: center; gap: 10px; }
.avatar {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--accent-gradient);
  color: #fff;
  display: grid; place-items: center;
  font-size: 12px; font-weight: 600;
  flex-shrink: 0;
}
.avatar.avatar-img {
  object-fit: cover;
  background: var(--glass-2-bg);
  border: 1px solid var(--c-line);
}
.user-meta .name { font-size: 13px; font-weight: 600; color: var(--c-ink); }
.user-meta .sub { font-size: 11px; color: var(--c-ink-3); }

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
.badge.role-viewer { color: var(--c-ink-3); }
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

.row-ops { display: flex; flex-wrap: wrap; gap: 4px; }
.op-btn {
  padding: 4px 10px;
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
  background: transparent;
  color: var(--c-ink-2);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--t-fast);
}
.op-btn:hover { background: var(--glass-1-bg); color: var(--c-ink); }
.op-btn.op-warn { color: var(--state-warning); border-color: rgba(234, 179, 8, 0.35); }
.op-btn.op-warn:hover { background: rgba(234, 179, 8, 0.12); }
.op-btn.op-ok { color: var(--state-success); border-color: rgba(34, 197, 94, 0.35); }
.op-btn.op-ok:hover { background: rgba(34, 197, 94, 0.12); }
.op-btn.op-danger { color: var(--state-error); border-color: rgba(248, 113, 113, 0.35); }
.op-btn.op-danger:hover { background: rgba(248, 113, 113, 0.12); }

.pager {
  display: flex; align-items: center; justify-content: flex-end;
  gap: 12px;
  padding: 12px 16px;
  border-top: 1px solid var(--c-line);
}
.pg {
  padding: 6px 12px;
  border-radius: var(--r-sm);
  background: var(--glass-1-bg);
  border: 1px solid var(--c-line);
  color: var(--c-ink-2);
  font-size: 12px;
  cursor: pointer;
}
.pg:hover:not(:disabled) { background: var(--glass-2-bg); color: var(--c-ink); }
.pg:disabled { opacity: 0.5; cursor: not-allowed; }
.pg-info { font-size: 12px; color: var(--c-ink-3); }

.form { display: flex; flex-direction: column; gap: 14px; }
.field label {
  display: block;
  font-size: 12px; font-weight: 600;
  color: var(--c-ink-2);
  margin-bottom: 6px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.field label .req { color: var(--state-error); margin-left: 2px; }
.field label .hint { font-weight: 400; color: var(--c-ink-3); text-transform: none; letter-spacing: 0; margin-left: 4px; }
.field.row { flex-direction: row; align-items: center; }
.checkbox { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; color: var(--c-ink-2); text-transform: none; letter-spacing: 0; font-weight: 400; }
.checkbox input { width: 16px; height: 16px; accent-color: var(--accent-1); }

.form-err {
  font-size: 12px; color: var(--state-error);
  background: rgba(248, 113, 113, 0.10);
  padding: 8px 12px;
  border-radius: var(--r-sm);
}

.btn {
  padding: 8px 16px;
  border-radius: var(--r-sm);
  font-size: 13px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: opacity var(--t-fast);
}
.btn.primary { background: var(--accent-gradient); color: #fff; }
.btn.ghost { background: var(--glass-1-bg); color: var(--c-ink-2); }
.btn:hover:not(:disabled) { opacity: 0.85; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>