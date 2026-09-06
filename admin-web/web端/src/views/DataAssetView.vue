<script setup lang="ts">
/**
 * DataAssetView — 数据资产下钻(7 个 type 之一)
 * 路由:/data-asset/:type
 *
 * 功能:
 *   - 真实数据表(分页 + 用户过滤)
 *   - 每行显示:用户名 / 创建时间 / 业务字段
 *   - 顶部"AI 分析"按钮 → 系统默认模型分析
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassInput from '@/components/form/GlassInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { dataAssetApi, type DataAssetType, type DataAssetRow } from '@/api/insights'
import { formatDate, formatRelativeTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()

// 预填:URL ?user_id=123 会自动设过滤
const initialUserId = route.query.user_id ? String(route.query.user_id) : ''

const type = computed<DataAssetType>(() => route.params.type as DataAssetType)

const TITLES: Record<DataAssetType, { label: string; icon: string; nameField: string }> = {
  todos:        { label: '待办', icon: '✓', nameField: 'text' },
  goals:        { label: '目标', icon: '◎', nameField: 'name' },
  transactions: { label: '收支', icon: '¥', nameField: 'category' },
  meals:        { label: '饮食', icon: '◔', nameField: 'meal_type' },
  reminders:    { label: '提醒', icon: '◐', nameField: 'type' },
  achievements: { label: '成就', icon: '★', nameField: 'code' },
  reports:      { label: '报告', icon: '⎙', nameField: 'title' }
}
const meta = computed(() => TITLES[type.value])

const loading = ref(false)
const rows = ref<DataAssetRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const userIdFilter = ref<string>(initialUserId)

const aiOpen = ref(false)
const aiLoading = ref(false)
const aiAdvice = ref<string>('')
const aiMeta = ref<{ total: number; sample_size: number } | null>(null)

async function load() {
  if (!type.value) return
  loading.value = true
  try {
    const r = await dataAssetApi.list(
      type.value,
      page.value,
      pageSize,
      userIdFilter.value ? Number(userIdFilter.value) : undefined
    )
    rows.value = r.rows ?? []
    total.value = r.total ?? 0
  } catch (e) {
    console.error('加载失败:', e)
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => type.value, () => { page.value = 1; load() })
watch(userIdFilter, () => { page.value = 1; load() })

function changePage(p: number) {
  if (p < 1) return
  page.value = p
  load()
}

async function onAiAnalyze() {
  if (!type.value) return
  aiOpen.value = true
  aiLoading.value = true
  aiAdvice.value = ''
  aiMeta.value = null
  try {
    const r = await dataAssetApi.aiAnalyze(type.value)
    aiAdvice.value = r.ai_advice || '暂无建议'
    aiMeta.value = { total: r.total, sample_size: r.sample_size }
  } catch (e) {
    aiAdvice.value = `AI 调用失败: ${(e as Error).message || e}`
  } finally {
    aiLoading.value = false
  }
}

function userNameOf(r: DataAssetRow) {
  return r.username || r.nickname || `用户 #${r.user_id}`
}

function onBack() { router.push({ name: 'Dashboard' }) }

onMounted(load)
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar :title="`数据资产 · ${meta?.label || ''}`" />

      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">
              <span class="ic">{{ meta?.icon }}</span> {{ meta?.label }} · 真实数据
            </h2>
            <p class="muted">
              共 <span class="mono">{{ total }}</span> 条 ·
              按创建/发生时间倒序 ·
              {{ userIdFilter ? `已过滤 user_id=${userIdFilter}` : '全部用户' }}
            </p>
          </div>
          <div class="header-actions">
            <GlassInput
              v-model="userIdFilter"
              type="number" placeholder="按用户 ID 过滤"
              style="width: 160px"
            />
            <button class="ghost-btn" @click="load" :disabled="loading">
              <span class="ic">↻</span>{{ loading ? '刷新中' : '刷新' }}
            </button>
            <button class="primary-btn" @click="onAiAnalyze" :disabled="aiLoading">
              <span class="ic">✨</span>AI 分析
            </button>
          </div>
        </header>

        <GlassCard type="middle" class="table-card">
          <div v-if="loading && rows.length === 0" class="loading pad">加载中…</div>
          <EmptyState
            v-else-if="!loading && rows.length === 0"
            icon="◊"
            title="还没有数据"
            hint="该业务表目前没有记录"
          />
          <table v-else class="t">
            <thead>
              <tr>
                <th>ID</th>
                <th>用户名</th>
                <th>用户 ID</th>
                <th>内容</th>
                <th v-if="type === 'transactions'">类型 / 金额</th>
                <th v-if="type === 'todos'">完成</th>
                <th v-if="type === 'goals'">进度</th>
                <th v-if="type === 'achievements'">code / status</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td class="mono">#{{ r.id }}</td>
                <td><strong>{{ userNameOf(r) }}</strong></td>
                <td class="mono">#{{ r.user_id }}</td>
                <td>{{ r.text || r.name || r.code || r.type || r.meal_type || '—' }}</td>
                <td v-if="type === 'transactions'">
                  <span class="tag" :class="r.type === 'income' ? 'tag-success' : 'tag-failed'">
                    {{ r.type === 'income' ? '收入' : '支出' }}
                  </span>
                  <span class="mono" style="margin-left: 6px">¥{{ r.amount }}</span>
                </td>
                <td v-if="type === 'todos'">
                  <span v-if="r.done" class="tag tag-success">已完成</span>
                  <span v-else class="tag">未完成</span>
                </td>
                <td v-if="type === 'goals'">
                  <div class="progress"><span :style="{ width: (r.progress || 0) + '%' }" /></div>
                  <span class="muted sm">{{ r.progress || 0 }}%</span>
                </td>
                <td v-if="type === 'achievements'">
                  <code class="mono">{{ r.code }}</code>
                  <span class="tag" style="margin-left: 6px">{{ r.status }}</span>
                </td>
                <td>
                  <div>{{ r.t ? formatDate(r.t, true) : '—' }}</div>
                  <div class="muted sm">{{ r.t ? formatRelativeTime(r.t) : '' }}</div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="total > pageSize" class="pagination">
            <button class="ghost-btn sm" :disabled="page === 1" @click="changePage(page - 1)">‹ 上一页</button>
            <span class="muted sm">第 {{ page }} / {{ Math.ceil(total / pageSize) }} 页 · 共 {{ total }} 条</span>
            <button class="ghost-btn sm" :disabled="page * pageSize >= total" @click="changePage(page + 1)">下一页 ›</button>
          </div>
        </GlassCard>

        <button class="back-link" @click="onBack">← 返回仪表盘</button>
      </section>

      <!-- AI 分析弹窗 -->
      <div v-if="aiOpen" class="modal-mask" @click.self="aiOpen = false">
        <div class="modal">
          <div class="modal-head">
            <h3 class="serif">✨ AI 分析 · {{ meta?.label }} ({{ aiMeta?.total ?? '?' }} 条)</h3>
            <button class="link" @click="aiOpen = false">✕</button>
          </div>
          <div class="modal-body">
            <p v-if="aiMeta" class="muted sm">基于样本 {{ aiMeta.sample_size }} 条 / 总数 {{ aiMeta.total }} 条,系统默认模型生成</p>
            <div v-if="aiLoading" class="loading pad">AI 思考中…</div>
            <pre v-else class="ai-content">{{ aiAdvice }}</pre>
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
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--c-ink); display: flex; align-items: center; gap: 8px; }
.muted { color: var(--c-ink-3); font-size: 13px; margin-top: 4px; }
.sm { font-size: 11px; margin: 0; }
.mono { font-family: var(--font-mono); }
.serif { font-family: var(--font-serif); }
.header-actions { display: flex; gap: 8px; align-items: end; }

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

.table-card { padding: 0; overflow: hidden; }
.t { width: 100%; border-collapse: collapse; font-size: 13px; }
.t th, .t td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--c-line); vertical-align: top; }
.t th { font-size: 11px; font-weight: 600; color: var(--c-ink-3); text-transform: uppercase; letter-spacing: 0.04em; background: var(--glass-1-bg); }
.t tbody tr:last-child td { border-bottom: none; }
.t tbody tr:hover { background: var(--glass-2-bg); }

.tag {
  display: inline-block; padding: 2px 8px; border-radius: var(--r-pill);
  font-size: 11px; font-weight: 600;
  background: var(--glass-3-bg); color: var(--c-ink-2);
}
.tag-success { background: rgba(52, 211, 153, 0.15); color: #4caf50; }
.tag-failed { background: rgba(248, 113, 113, 0.15); color: #f44336; }

.progress { display: inline-block; width: 80px; height: 6px; background: var(--glass-2-bg); border-radius: 3px; overflow: hidden; }
.progress span { display: block; height: 100%; background: var(--accent-gradient); }

.pagination { display: flex; justify-content: center; align-items: center; gap: 12px; padding: 12px 0; border-top: 1px solid var(--c-line); }
.loading.pad { padding: 60px; text-align: center; color: var(--c-ink-3); }
.back-link {
  background: none; border: none; color: var(--c-ink-3);
  font-size: 13px; cursor: pointer; padding: 8px 0;
}
.back-link:hover { color: var(--c-ink); }

.modal-mask {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.modal {
  background: var(--c-paper, #fff);
  border: 1px solid var(--c-line);
  border-radius: var(--r-md);
  max-width: 720px; width: 100%;
  max-height: 80vh;
  display: flex; flex-direction: column;
  backdrop-filter: blur(16px);
}
.modal-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--c-line); }
.modal-body { padding: 20px; }
.ai-content {
  padding: 14px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--glass-1-bg);
  border-radius: var(--r-sm);
  max-height: 60vh;
  overflow: auto;
}
.link { background: none; border: none; color: var(--c-ink-2); cursor: pointer; font-size: 14px; }
</style>
