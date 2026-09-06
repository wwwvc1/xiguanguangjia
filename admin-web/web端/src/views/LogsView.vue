<script setup lang="ts">
/**
 * LogsView — 系统日志(已对接后端 /api/admin/logs)
 *
 * 功能:
 *   - 列表(分页 + 筛选:用户ID/操作类型/状态/时间范围)
 *   - 详情查看(原始 details JSON)
 *   - 导出 CSV
 */
import { ref, reactive, computed, onMounted } from 'vue'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassInput from '@/components/form/GlassInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { listLogs, listLogActions, exportLogs, type LogEntry } from '@/api/logs'
import { logAiApi } from '@/api/insights'
import { formatDate, formatRelativeTime } from '@/utils/format'

// ─────────── 状态 ───────────
const loading = ref(false)
const error = ref<string | null>(null)
const logs = ref<LogEntry[]>([])
const total = ref(0)
const actionOptions = ref<string[]>([])

const filter = reactive({
  user_id: undefined as number | undefined,
  action: '' as string,
  status: '' as '' | 'success' | 'failed',
  date_from: '' as string,
  date_to: '' as string,
  page: 1,
  page_size: 20
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filter.page_size)))

// ─────────── 加载 ───────────
async function load() {
  loading.value = true
  error.value = null
  try {
    const resp = await listLogs({
      user_id: filter.user_id,
      action: filter.action || undefined,
      status: filter.status || undefined,
      date_from: filter.date_from || undefined,
      date_to: filter.date_to || undefined,
      page: filter.page,
      page_size: filter.page_size
    })
    logs.value = resp.items ?? []
    total.value = resp.total ?? 0
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载日志失败'
    logs.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadActions() {
  try {
    const r = await listLogActions()
    actionOptions.value = r.actions ?? []
  } catch {
    actionOptions.value = []
  }
}
onMounted(() => {
  load()
  loadActions()
})

// ─────────── 操作 ───────────
function applyFilters() {
  filter.page = 1
  load()
}
function resetFilters() {
  filter.user_id = undefined
  filter.action = ''
  filter.status = ''
  filter.date_from = ''
  filter.date_to = ''
  filter.page = 1
  load()
}
function changePage(p: number) {
  if (p < 1 || p > totalPages.value) return
  filter.page = p
  load()
}
async function onExport() {
  try {
    const blob = await exportLogs({
      user_id: filter.user_id,
      action: filter.action || undefined,
      date_from: filter.date_from || undefined,
      date_to: filter.date_to || undefined
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `operation_logs_${formatDate(new Date(), true).replace(/[: ]/g, '-')}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '导出失败'
  }
}

// 详情
const detailOpen = ref(false)
const detailEntry = ref<LogEntry | null>(null)
function showDetail(row: LogEntry) {
  detailEntry.value = row
  detailOpen.value = true
}

// AI 解读
const aiOpen = ref(false)
const aiLoading = ref(false)
const aiInsight = ref('')
const aiPreview = ref<{ by_action: any[]; by_hour: any[]; recent_logs: any[] } | null>(null)
async function onAiSummary() {
  aiOpen.value = true
  aiLoading.value = true
  aiInsight.value = ''
  aiPreview.value = null
  try {
    const r = await logAiApi.run(50)
    aiInsight.value = r.ai_insight || ''
    aiPreview.value = r.preview
  } catch (e: any) {
    aiInsight.value = `AI 调用失败: ${e?.response?.data?.detail || e?.message || e}`
  } finally {
    aiLoading.value = false
  }
}

// 工具
function statusTone(s: string) {
  if (s === 'failed') return 'tag-failed'
  if (s === 'success') return 'tag-success'
  return 'tag-default'
}
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="系统日志" />

      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">系统日志</h2>
            <p class="muted">
              操作审计 + RAG 检索记录 ·
              <span class="status-tag">共 {{ total }} 条</span>
            </p>
          </div>
          <div class="header-actions">
            <button class="ghost-btn" @click="load" :disabled="loading">
              <span class="ic">↻</span>{{ loading ? '刷新中' : '刷新' }}
            </button>
            <button class="primary-btn" @click="onAiSummary" :disabled="aiLoading">
              <span class="ic">✨</span>AI 解读
            </button>
            <button class="primary-btn" @click="onExport">
              <span class="ic">↓</span>导出 CSV
            </button>
          </div>
        </header>

        <!-- 筛选条 -->
        <GlassCard type="middle" class="filter-card">
          <div class="filters">
            <div class="filter-item">
              <label class="muted sm">用户 ID</label>
              <GlassInput v-model.number="filter.user_id" type="number" placeholder="不限" />
            </div>
            <div class="filter-item">
              <label class="muted sm">操作类型</label>
              <select v-model="filter.action" class="native-select">
                <option value="">全部</option>
                <option v-for="a in actionOptions" :key="a" :value="a">{{ a }}</option>
              </select>
            </div>
            <div class="filter-item">
              <label class="muted sm">状态</label>
              <select v-model="filter.status" class="native-select">
                <option value="">全部</option>
                <option value="success">成功</option>
                <option value="failed">失败</option>
              </select>
            </div>
            <div class="filter-item">
              <label class="muted sm">开始日期</label>
              <input v-model="filter.date_from" type="date" class="native-input" />
            </div>
            <div class="filter-item">
              <label class="muted sm">结束日期</label>
              <input v-model="filter.date_to" type="date" class="native-input" />
            </div>
            <div class="filter-actions">
              <button class="primary-btn" @click="applyFilters" :disabled="loading">查询</button>
              <button class="ghost-btn" @click="resetFilters" :disabled="loading">重置</button>
            </div>
          </div>
        </GlassCard>

        <!-- 错误提示 -->
        <div v-if="error" class="err-banner">
          <span class="ic">⚠</span>{{ error }}
          <button class="link" @click="error = null">×</button>
        </div>

        <!-- 列表 -->
        <GlassCard type="middle" class="table-card">
          <div v-if="loading && logs.length === 0" class="loading pad">加载中…</div>
          <div v-else-if="logs.length === 0">
            <EmptyState icon="⌖" title="还没有日志" hint="用户在系统中的操作会出现在这里" />
          </div>
          <table v-else class="t">
            <thead>
              <tr>
                <th>时间</th>
                <th>用户</th>
                <th>操作</th>
                <th>资源</th>
                <th>状态</th>
                <th>IP</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in logs" :key="row.id">
                <td>
                  <div>{{ formatDate(row.created_at, true) }}</div>
                  <div class="muted sm">{{ formatRelativeTime(row.created_at) }}</div>
                </td>
                <td>
                  <span v-if="row.username">{{ row.username }}</span>
                  <span v-else-if="row.user_id">#{{ row.user_id }}</span>
                  <span v-else class="muted">系统</span>
                </td>
                <td><span class="mono">{{ row.action }}</span></td>
                <td class="muted">
                  <span v-if="row.resource_type">{{ row.resource_type }}<span v-if="row.resource_id">#{{ row.resource_id }}</span></span>
                  <span v-else>—</span>
                </td>
                <td>
                  <span class="tag" :class="statusTone(row.status)">{{ row.status }}</span>
                </td>
                <td class="mono sm">{{ row.ip || '—' }}</td>
                <td>
                  <button v-if="row.details" class="op-btn" @click="showDetail(row)">查看</button>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 分页 -->
          <div v-if="total > filter.page_size" class="pagination">
            <button class="ghost-btn sm" :disabled="filter.page === 1" @click="changePage(filter.page - 1)">‹ 上一页</button>
            <span class="muted sm">第 {{ filter.page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
            <button class="ghost-btn sm" :disabled="filter.page >= totalPages" @click="changePage(filter.page + 1)">下一页 ›</button>
          </div>
        </GlassCard>
      </section>

      <!-- 详情 modal -->
      <div v-if="detailOpen" class="modal-mask" @click.self="detailOpen = false">
        <div class="modal">
          <div class="modal-head">
            <h3 class="serif">日志详情 - #{{ detailEntry?.id }}</h3>
            <button class="link" @click="detailOpen = false">✕</button>
          </div>
          <pre class="json-block">{{ JSON.stringify(detailEntry, null, 2) }}</pre>
        </div>
      </div>

      <!-- AI 解读 modal -->
      <div v-if="aiOpen" class="modal-mask" @click.self="aiOpen = false">
        <div class="modal">
          <div class="modal-head">
            <h3 class="serif">✨ AI 解读(系统默认模型 · 基于最近 50 条日志)</h3>
            <button class="link" @click="aiOpen = false">✕</button>
          </div>
          <div class="modal-body">
            <div v-if="aiLoading" class="loading pad">AI 思考中…</div>
            <pre v-else class="json-block">{{ aiInsight }}</pre>
            <div v-if="aiPreview" style="margin-top: 12px; font-size: 11px; color: var(--c-ink-3)">
              依据:近 7 天 {{ aiPreview.by_action.length }} 种 action · {{ aiPreview.recent_logs.length }} 条明细
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-shell { display: grid; grid-template-columns: auto 1fr; min-height: 100vh; }
.app-main { min-width: 0; }
.page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: end; gap: 16px; flex-wrap: wrap; }
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--c-ink); }
.muted { color: var(--c-ink-3); font-size: 13px; margin-top: 4px; }
.sm { font-size: 11px; margin: 0; }
.mono { font-family: var(--font-mono); }
.serif { font-family: var(--font-serif); }

.status-tag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 8px; border-radius: var(--r-pill);
  background: var(--glass-2-bg); border: 1px solid var(--c-line);
  font-size: 11px; color: var(--c-ink-2);
}

.primary-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: var(--r-sm);
  background: var(--accent-gradient); color: #fff;
  border: none; font-size: 13px; font-weight: 500; cursor: pointer;
  transition: transform var(--t-fast);
}
.primary-btn:hover:not(:disabled) { transform: translateY(-1px); }
.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.primary-btn .ic { font-size: 15px; }
.ghost-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: var(--r-sm);
  background: var(--glass-2-bg); color: var(--c-ink);
  border: 1px solid var(--c-line); cursor: pointer;
  font-size: 13px;
}
.ghost-btn:hover:not(:disabled) { background: var(--glass-3-bg); }
.ghost-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ghost-btn.sm { padding: 4px 10px; font-size: 12px; }

.header-actions { display: flex; gap: 8px; }

/* 筛选条 */
.filter-card { padding: 16px; }
.filters {
  display: flex; gap: 12px; flex-wrap: wrap; align-items: end;
}
.filter-item { display: flex; flex-direction: column; gap: 4px; min-width: 130px; }
.filter-actions { display: flex; gap: 6px; }
.native-input, .native-select {
  background: var(--glass-2-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  padding: 8px 10px;
  color: var(--c-ink);
  font-size: 13px;
  outline: none;
  transition: border-color var(--t-fast);
  height: 38px;
  box-sizing: border-box;
}
.native-input:focus, .native-select:focus { border-color: var(--accent-1); }

/* 错误 */
.err-banner {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; border-radius: var(--r-sm);
  background: rgba(255, 100, 100, 0.1); color: var(--state-error);
  border: 1px solid rgba(255, 100, 100, 0.3);
}
.err-banner .ic { font-size: 16px; }
.err-banner .link { margin-left: auto; background: none; border: none; cursor: pointer; color: inherit; }

/* 表格 */
.table-card { padding: 0; overflow: hidden; }
.t { width: 100%; border-collapse: collapse; font-size: 13px; }
.t th, .t td {
  padding: 10px 14px; text-align: left;
  border-bottom: 1px solid var(--c-line);
  vertical-align: top;
}
.t th {
  font-size: 11px; font-weight: 600; color: var(--c-ink-3);
  text-transform: uppercase; letter-spacing: 0.04em;
  background: var(--glass-1-bg);
}
.t tbody tr:last-child td { border-bottom: none; }
.t tbody tr:hover { background: var(--glass-2-bg); }

.tag {
  display: inline-block; padding: 2px 8px; border-radius: var(--r-pill);
  font-size: 11px; font-weight: 600;
  background: var(--glass-3-bg); color: var(--c-ink-2);
}
.tag-success { background: rgba(120, 200, 140, 0.15); color: #4caf50; }
.tag-failed { background: rgba(255, 100, 100, 0.15); color: #f44336; }
.tag-default { background: var(--glass-3-bg); color: var(--c-ink-2); }

.op-btn {
  padding: 4px 10px; border-radius: var(--r-sm);
  background: var(--glass-2-bg); border: 1px solid var(--c-line);
  color: var(--c-ink-2); font-size: 12px; cursor: pointer;
}
.op-btn:hover { background: var(--glass-3-bg); }

.link { background: none; border: none; color: var(--c-ink-2); cursor: pointer; font-size: 14px; }

/* 分页 */
.pagination {
  display: flex; justify-content: center; align-items: center; gap: 12px;
  padding: 12px 0; border-top: 1px solid var(--c-line);
}

/* 加载/空 */
.loading.pad { padding: 60px; text-align: center; color: var(--c-ink-3); }

/* 详情 modal */
.modal-mask {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.modal {
  background: var(--glass-3-bg, #fff);
  border: 1px solid var(--c-line);
  border-radius: var(--r-md);
  max-width: 720px; width: 100%;
  max-height: 80vh;
  display: flex; flex-direction: column;
  backdrop-filter: blur(16px);
}
.modal-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid var(--c-line);
}
.modal-body { padding: 20px; }
.json-block {
  padding: 16px 20px;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 60vh;
  overflow: auto;
  color: var(--c-ink);
  background: var(--glass-1-bg);
}
</style>
