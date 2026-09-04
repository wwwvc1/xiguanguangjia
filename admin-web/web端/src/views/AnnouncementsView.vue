<script setup lang="ts">
/**
 * AnnouncementsView — 公告完整 CRUD (Phase 4)
 *  - 列表(类型 / 优先级 / 发布人 / 时间 / 状态)
 *  - 筛选(类型 / 状态)
 *  - 创建 / 编辑 / 删除(GlassModal)
 *  - 类型 3 种:系统 / 活动 / 维护,优先级 1-5,有效期 start_at/end_at
 */
import { ref, computed, onMounted, reactive } from 'vue'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import GlassInput from '@/components/form/GlassInput.vue'
import GlassSelect from '@/components/form/GlassSelect.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import {
  listAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  deleteAnnouncement,
  type Announcement,
  type AnnouncementType,
  type AnnouncementStatus,
  type AnnouncementUpsert
} from '@/api/announcements'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatRelativeTime, truncate } from '@/utils/format'

const auth = useAuthStore()

// ────────────────────────── 筛选 ──────────────────────────
const filterType = ref<AnnouncementType | 'all'>('all')
const filterStatus = ref<AnnouncementStatus | 'all'>('all')

const TYPE_LABEL: Record<AnnouncementType, string> = {
  system: '系统',
  activity: '活动',
  maintenance: '维护'
}
const TYPE_COLOR: Record<AnnouncementType, string> = {
  system: 'var(--accent-1)',
  activity: 'var(--accent-2)',
  maintenance: 'var(--c-brick)'
}
const STATUS_LABEL: Record<AnnouncementStatus, string> = {
  draft: '草稿',
  scheduled: '待发布',
  active: '生效中',
  expired: '已过期'
}
const STATUS_COLOR: Record<AnnouncementStatus, string> = {
  draft: 'var(--c-ink-3)',
  scheduled: 'var(--state-info)',
  active: 'var(--state-success)',
  expired: 'var(--c-ink-3)'
}

const typeFilterOptions = [
  { label: '全部类型', value: 'all' },
  { label: '系统公告', value: 'system' },
  { label: '活动公告', value: 'activity' },
  { label: '维护公告', value: 'maintenance' }
]
const statusFilterOptions = [
  { label: '全部状态', value: 'all' },
  { label: '草稿', value: 'draft' },
  { label: '待发布', value: 'scheduled' },
  { label: '生效中', value: 'active' },
  { label: '已过期', value: 'expired' }
]

// ────────────────────────── 列表 ──────────────────────────
const items = ref<Announcement[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const resp = await listAnnouncements({
      type: filterType.value,
      status: filterStatus.value,
      page: 1,
      page_size: 100
    })
    items.value = resp.items
  } catch (e) {
    items.value = []
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 客户端再过滤一次(防止后端忽略)
const filtered = computed(() => items.value)

const counts = computed(() => {
  const all = items.value
  return {
    total: all.length,
    active: all.filter((a) => a.status === 'active').length,
    scheduled: all.filter((a) => a.status === 'scheduled').length,
    high: all.filter((a) => a.priority >= 4).length
  }
})

// ────────────────────────── 创建 / 编辑 Modal ──────────────────────────
interface FormState {
  id: number | null
  title: string
  content: string
  type: AnnouncementType
  priority: 1 | 2 | 3 | 4 | 5
  start_at: string
  end_at: string
  enabled: boolean
}
const form = reactive<FormState>({
  id: null,
  title: '',
  content: '',
  type: 'system',
  priority: 3,
  start_at: '',
  end_at: '',
  enabled: true
})

const modalOpen = ref(false)
const submitting = ref(false)
const formError = ref<string | null>(null)

function resetForm() {
  form.id = null
  form.title = ''
  form.content = ''
  form.type = 'system'
  form.priority = 3
  form.start_at = ''
  form.end_at = ''
  form.enabled = true
  formError.value = null
}

function openCreate() {
  resetForm()
  modalOpen.value = true
}

function openEdit(a: Announcement) {
  form.id = a.id
  form.title = a.title
  form.content = a.content
  form.type = a.type
  form.priority = a.priority
  // 转成 datetime-local 需要的本地时间格式 (YYYY-MM-DDTHH:mm)
  form.start_at = toLocalInput(a.start_at)
  form.end_at = toLocalInput(a.end_at)
  form.enabled = a.enabled
  formError.value = null
  modalOpen.value = true
}

function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function toISO(local: string): string | null {
  if (!local) return null
  const d = new Date(local)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

async function submit() {
  if (!form.title.trim()) {
    formError.value = '标题不能为空'
    return
  }
  if (!form.content.trim()) {
    formError.value = '内容不能为空'
    return
  }
  if (form.start_at && form.end_at) {
    if (new Date(form.end_at) <= new Date(form.start_at)) {
      formError.value = '结束时间需晚于开始时间'
      return
    }
  }

  const payload: AnnouncementUpsert = {
    title: form.title.trim(),
    content: form.content.trim(),
    type: form.type,
    priority: form.priority,
    start_at: toISO(form.start_at),
    end_at: toISO(form.end_at),
    enabled: form.enabled
  }

  submitting.value = true
  formError.value = null
  try {
    if (form.id == null) {
      await createAnnouncement(payload)
    } else {
      await updateAnnouncement(form.id, payload)
    }
    modalOpen.value = false
    await load()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    submitting.value = false
  }
}

// ────────────────────────── 删除 ──────────────────────────
const confirmOpen = ref(false)
const deleteTarget = ref<Announcement | null>(null)

function askDelete(a: Announcement) {
  deleteTarget.value = a
  confirmOpen.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  const id = deleteTarget.value.id
  try {
    await deleteAnnouncement(id)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '删除失败'
  } finally {
    deleteTarget.value = null
  }
}

// ────────────────────────── 辅助 ──────────────────────────
function priorityLabel(p: number): string {
  return '★'.repeat(p) + '☆'.repeat(5 - p)
}

const publisherName = computed(() => auth.displayName)
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="公告" />

      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">公告管理</h2>
            <p class="muted">
              <template v-if="loading">加载中…</template>
              <template v-else-if="error">⚠ {{ error }}</template>
              <template v-else>
                共 {{ counts.total }} 条 · 生效中 {{ counts.active }} · 待发布 {{ counts.scheduled }} · 高优先级 {{ counts.high }}
              </template>
            </p>
          </div>
          <div class="header-actions">
            <button class="ghost-btn" @click="load" :disabled="loading">
              <span class="ic">↻</span>
              <span>刷新</span>
            </button>
            <button class="primary-btn" @click="openCreate">
              <span class="ic">+</span>
              <span>新建公告</span>
            </button>
          </div>
        </header>

        <!-- 筛选条 -->
        <GlassCard type="outer" padding="14px 16px">
          <div class="filter-bar">
            <div class="filter-group">
              <span class="filter-label">类型</span>
              <GlassSelect
                v-model="filterType"
                :options="typeFilterOptions"
                @update:modelValue="load"
              />
            </div>
            <div class="filter-group">
              <span class="filter-label">状态</span>
              <GlassSelect
                v-model="filterStatus"
                :options="statusFilterOptions"
                @update:modelValue="load"
              />
            </div>
          </div>
        </GlassCard>

        <!-- 列表 -->
        <GlassCard type="outer" padding="0">
          <template v-if="loading && items.length === 0">
            <EmptyState icon="◐" title="加载中" hint="正在拉取公告列表…" />
          </template>
          <template v-else-if="filtered.length === 0">
            <EmptyState
              icon="◐"
              title="暂无公告"
              hint="点击右上「新建公告」创建第一条"
            />
          </template>
          <template v-else>
            <div class="list-head">
              <div>类型 / 优先级</div>
              <div>标题 / 内容</div>
              <div>有效期</div>
              <div>发布人 / 时间</div>
              <div class="ta-r">操作</div>
            </div>
            <div class="list-body">
              <div v-for="a in filtered" :key="a.id" class="row">
                <div class="cell-type">
                  <span class="type-tag" :style="{ color: TYPE_COLOR[a.type], borderColor: TYPE_COLOR[a.type] }">
                    {{ TYPE_LABEL[a.type] }}
                  </span>
                  <span class="priority" :title="`优先级 ${a.priority}/5`">{{ priorityLabel(a.priority) }}</span>
                </div>
                <div class="cell-main">
                  <div class="title-row">
                    <span class="title serif">{{ a.title }}</span>
                    <span class="status-pill" :style="{ color: STATUS_COLOR[a.status], background: 'transparent', borderColor: STATUS_COLOR[a.status] }">
                      {{ STATUS_LABEL[a.status] }}
                    </span>
                    <span v-if="!a.enabled" class="status-pill disabled">已停用</span>
                  </div>
                  <div class="preview">{{ truncate(a.content, 90) }}</div>
                </div>
                <div class="cell-range">
                  <div class="range">
                    <span class="muted">起</span>
                    <span class="mono">{{ a.start_at ? formatDate(a.start_at, true) : '即时' }}</span>
                  </div>
                  <div class="range">
                    <span class="muted">止</span>
                    <span class="mono">{{ a.end_at ? formatDate(a.end_at, true) : '永久' }}</span>
                  </div>
                </div>
                <div class="cell-meta">
                  <div class="publisher">{{ a.created_by || publisherName }}</div>
                  <div class="time muted">{{ formatRelativeTime(a.created_at) }}</div>
                </div>
                <div class="cell-actions ta-r">
                  <button class="row-btn" @click="openEdit(a)" title="编辑">✎</button>
                  <button class="row-btn danger" @click="askDelete(a)" title="删除">×</button>
                </div>
              </div>
            </div>
          </template>
        </GlassCard>
      </section>

      <!-- 创建/编辑 Modal -->
      <GlassModal
        :open="modalOpen"
        :title="form.id == null ? '新建公告' : '编辑公告'"
        @update:open="(v) => modalOpen = v"
        width="560px"
      >
        <form class="ann-form" @submit.prevent="submit">
          <div class="form-field">
            <label class="form-label">标题</label>
            <GlassInput v-model="form.title" placeholder="公告标题" />
          </div>

          <div class="form-field">
            <label class="form-label">类型</label>
            <GlassSelect
              v-model="form.type"
              :options="[
                { label: '系统公告', value: 'system' },
                { label: '活动公告', value: 'activity' },
                { label: '维护公告', value: 'maintenance' }
              ]"
            />
          </div>

          <div class="form-field">
            <label class="form-label">优先级</label>
            <div class="priority-picker">
              <button
                v-for="n in 5"
                :key="n"
                type="button"
                class="prio-btn"
                :class="{ active: form.priority >= n }"
                @click="form.priority = n as 1 | 2 | 3 | 4 | 5"
              >★</button>
              <span class="prio-hint">{{ form.priority }} / 5</span>
            </div>
          </div>

          <div class="form-row">
            <div class="form-field">
              <label class="form-label">开始时间</label>
              <GlassInput v-model="form.start_at" type="datetime-local" />
            </div>
            <div class="form-field">
              <label class="form-label">结束时间</label>
              <GlassInput v-model="form.end_at" type="datetime-local" />
            </div>
          </div>

          <div class="form-field">
            <label class="form-label">内容</label>
            <textarea
              v-model="form.content"
              class="g-textarea"
              rows="5"
              placeholder="公告正文…"
            />
          </div>

          <label class="form-toggle">
            <input type="checkbox" v-model="form.enabled" />
            <span>启用</span>
          </label>

          <p v-if="formError" class="form-error">{{ formError }}</p>
        </form>

        <template #footer>
          <button class="btn ghost" @click="modalOpen = false" :disabled="submitting">取消</button>
          <button class="btn primary" @click="submit" :disabled="submitting">
            {{ submitting ? '保存中…' : '保存' }}
          </button>
        </template>
      </GlassModal>

      <ConfirmDialog
        :open="confirmOpen"
        title="删除公告"
        :message="`确定删除「${deleteTarget?.title || ''}」?此操作不可撤销。`"
        confirm-text="删除"
        cancel-text="取消"
        tone="danger"
        @update:open="(v) => confirmOpen = v"
        @confirm="doDelete"
      />
    </div>
  </div>
</template>

<style scoped>
.app-shell { display: grid; grid-template-columns: auto 1fr; min-height: 100vh; }
.app-main { min-width: 0; }
.page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: end; gap: 16px; }
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--c-ink); }
.muted { color: var(--c-ink-3); font-size: 13px; margin-top: 4px; }

.header-actions { display: flex; gap: 8px; }

.ghost-btn,
.primary {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  border-radius: var(--r-sm);
  font-size: 13px;
  border: 1px solid var(--c-line);
  cursor: pointer;
  transition: opacity var(--t-fast), background var(--t-fast);
}
.ghost-btn { background: var(--glass-2-bg); color: var(--c-ink-2); }
.ghost-btn:hover { background: var(--glass-1-bg); color: var(--c-ink); }
.primary {
  background: var(--accent-gradient);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 4px 12px -4px rgba(124, 92, 255, 0.45);
}
.primary:hover { opacity: 0.92; }
.primary:disabled, .ghost-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.primary .ic, .ghost-btn .ic { font-size: 14px; }

/* ===== Filter bar ===== */
.filter-bar {
  display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
}
.filter-group { display: flex; align-items: center; gap: 8px; min-width: 200px; }
.filter-label {
  font-size: 12px; color: var(--c-ink-3);
  letter-spacing: 0.04em;
}

/* ===== List ===== */
.list-head {
  display: grid;
  grid-template-columns: 130px 1fr 200px 140px 100px;
  gap: 12px;
  padding: 10px 18px;
  font-size: 11px;
  color: var(--c-ink-3);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--c-line);
  background: var(--glass-1-bg);
}
.list-body { display: flex; flex-direction: column; }
.row {
  display: grid;
  grid-template-columns: 130px 1fr 200px 140px 100px;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--c-line);
  align-items: center;
  transition: background var(--t-fast);
}
.row:last-child { border-bottom: none; }
.row:hover { background: var(--glass-1-bg); }

.cell-type { display: flex; flex-direction: column; gap: 4px; }
.type-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--r-pill);
  border: 1px solid;
  font-size: 11px;
  font-weight: 600;
  background: rgba(255,255,255,0.04);
  text-align: center;
  width: fit-content;
}
.priority { font-size: 11px; color: var(--c-bone); letter-spacing: 1px; }

.cell-main { min-width: 0; }
.title-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.title { font-size: 14px; font-weight: 600; color: var(--c-ink); }
.status-pill {
  display: inline-block;
  padding: 1px 8px;
  border-radius: var(--r-pill);
  border: 1px solid;
  font-size: 10px;
  font-weight: 500;
}
.status-pill.disabled {
  color: var(--c-ink-3);
  border-color: var(--c-line);
  background: var(--glass-1-bg);
}
.preview {
  font-size: 12px;
  color: var(--c-ink-3);
  margin-top: 4px;
  line-height: 1.5;
}

.cell-meta .publisher {
  font-size: 12px;
  color: var(--c-ink-2);
  font-weight: 500;
}
.cell-meta .time { font-size: 11px; margin-top: 2px; }

.cell-range .range {
  display: flex; gap: 6px; align-items: center;
  font-size: 11px;
}
.cell-range .range + .range { margin-top: 2px; }
.cell-range .mono { font-size: 11px; color: var(--c-ink-2); }

.cell-actions { display: flex; gap: 4px; justify-content: flex-end; }
.row-btn {
  width: 28px; height: 28px;
  display: grid; place-items: center;
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
  background: var(--glass-2-bg);
  color: var(--c-ink-2);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.row-btn:hover { background: var(--glass-1-bg); color: var(--c-ink); }
.row-btn.danger:hover { background: rgba(248, 113, 113, 0.12); color: var(--state-error); border-color: var(--state-error); }

.ta-r { text-align: right; }

/* ===== Form ===== */
.ann-form { display: flex; flex-direction: column; gap: 14px; }
.form-field { display: flex; flex-direction: column; gap: 6px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-label {
  font-size: 12px;
  color: var(--c-ink-3);
  letter-spacing: 0.04em;
}
.g-textarea {
  width: 100%;
  padding: 12px 16px;
  border-radius: var(--r-sm);
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  color: var(--c-ink);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  resize: vertical;
  min-height: 100px;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.g-textarea:focus {
  border-color: var(--accent-1);
  box-shadow: 0 0 0 3px rgba(124, 92, 255, 0.18);
}
.priority-picker { display: flex; align-items: center; gap: 4px; }
.prio-btn {
  border: none; background: transparent;
  color: var(--c-ink-3);
  font-size: 18px;
  width: 28px; height: 28px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: color var(--t-fast), background var(--t-fast);
}
.prio-btn:hover { background: var(--glass-1-bg); }
.prio-btn.active { color: var(--c-bone); }
.prio-hint { margin-left: 8px; font-size: 12px; color: var(--c-ink-3); font-family: var(--font-mono); }

.form-toggle {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--c-ink-2);
  cursor: pointer;
}
.form-toggle input { width: 16px; height: 16px; accent-color: var(--accent-1); }

.form-error {
  color: var(--state-error);
  font-size: 12px;
  padding: 8px 12px;
  background: rgba(248, 113, 113, 0.10);
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
.btn:hover { opacity: 0.85; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 900px) {
  .list-head, .row {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .list-head { display: none; }
  .row { padding: 14px 16px; }
  .ta-r { text-align: left; }
}
</style>