<script setup lang="ts">
/**
 * AchievementsView — 成就定义管理
 *
 * 功能:
 *   - 列表 (R) — 卡片网格:图标 / 名称 / 解锁人数 / 占比
 *   - 创建 / 编辑 / 删除 (CUD)
 *   - 详情弹窗 + 试用 metric (输入 user_id → 当前值 / 目标 / 达成率)
 *   - 重新计算(对指定 user 跑 check_and_unlock)
 */
import { ref, computed, onMounted, reactive, watch } from 'vue'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import GlassInput from '@/components/form/GlassInput.vue'
import GlassSelect from '@/components/form/GlassSelect.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import MagneticCard from '@/components/ui/MagneticCard.vue'
import {
  listAchievements,
  getAchievement,
  createAchievement,
  updateAchievement,
  deleteAchievement,
  getMetricTypes,
  getAchievementStats,
  tryMetric,
  recomputeUserAchievements,
  type Achievement,
  type AchievementCreate,
  type AchievementUpdate,
  type MetricType,
  type AchievementStats,
  type TryMetricResult,
  type RecomputeResp
} from '@/api/achievements'
import { formatNumber, formatPercent, formatDate } from '@/utils/format'

// ─────────── state ───────────
const loading = ref(true)
const error = ref<string | null>(null)
const achievements = ref<Achievement[]>([])
const metrics = ref<MetricType[]>([])
const stats = ref<AchievementStats | null>(null)

const filterActive = ref<'all' | 'active' | 'inactive'>('all')
const searchKw = ref('')

// 表单 modal
const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const formEditingId = ref<number | null>(null)
const form = reactive<AchievementCreate>({
  code: '',
  name: '',
  description: '',
  icon: '🏅',
  metric_type: 'todo_count',
  target_value: 1,
  is_active: 1,
  sort_order: 0
})
const formSaving = ref(false)
const formError = ref<string | null>(null)

// 详情 modal
const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref<Achievement | null>(null)

// 试用 metric
const tryUserId = ref<string>('')
const tryLoading = ref(false)
const tryResult = ref<TryMetricResult | null>(null)
const tryError = ref<string | null>(null)

// 重算
const recomputeLoading = ref(false)
const recomputeResp = ref<RecomputeResp | null>(null)

// 确认
const confirmOpen = ref(false)
const confirmPayload = ref<{ title: string; message: string; onConfirm: () => void; tone?: 'default' | 'danger' } | null>(null)
function askConfirm(opts: { title: string; message: string; tone?: 'default' | 'danger'; onConfirm: () => void }) {
  confirmPayload.value = { tone: 'default', ...opts }
  confirmOpen.value = true
}

// ─────────── loaders ───────────
async function loadAll() {
  loading.value = true
  error.value = null
  try {
    const [list, ms, st] = await Promise.allSettled([
      listAchievements(),
      getMetricTypes(),
      getAchievementStats()
    ])
    if (list.status === 'fulfilled') achievements.value = list.value
    if (ms.status === 'fulfilled') metrics.value = ms.value
    if (st.status === 'fulfilled') stats.value = st.value
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(loadAll)

// ─────────── derived ───────────
const filteredAchievements = computed(() => {
  let list = achievements.value
  if (filterActive.value === 'active') list = list.filter((a) => a.is_active)
  else if (filterActive.value === 'inactive') list = list.filter((a) => !a.is_active)
  const kw = searchKw.value.trim().toLowerCase()
  if (kw) list = list.filter((a) => a.name.toLowerCase().includes(kw) || a.code.toLowerCase().includes(kw))
  return list.slice().sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id))
})

function getStatFor(id: number) {
  return stats.value?.rows?.find((r) => r.id === id)
}

const totalUsers = computed(() => stats.value?.total_users ?? 0)
const totalUnlocks = computed(() => stats.value?.total_unlocks ?? 0)

// ─────────── form handlers ───────────
function openCreate() {
  formMode.value = 'create'
  formEditingId.value = null
  Object.assign(form, {
    code: '',
    name: '',
    description: '',
    icon: '🏅',
    metric_type: metrics.value[0]?.value ?? 'todo_count',
    target_value: 1,
    is_active: 1,
    sort_order: 0
  })
  formError.value = null
  formOpen.value = true
}

function openEdit(a: Achievement) {
  formMode.value = 'edit'
  formEditingId.value = a.id
  Object.assign(form, {
    code: a.code,
    name: a.name,
    description: a.description ?? '',
    icon: a.icon || '🏅',
    metric_type: a.metric_type,
    target_value: a.target_value,
    is_active: a.is_active ? 1 : 0,
    sort_order: a.sort_order
  })
  formError.value = null
  formOpen.value = true
}

async function onSaveForm() {
  formSaving.value = true
  formError.value = null
  try {
    if (formMode.value === 'create') {
      await createAchievement({ ...form, is_active: form.is_active ? 1 : 0 })
    } else if (formEditingId.value != null) {
      const patch: AchievementUpdate = {
        name: form.name,
        description: form.description,
        icon: form.icon,
        metric_type: form.metric_type,
        target_value: form.target_value,
        is_active: form.is_active ? 1 : 0,
        sort_order: form.sort_order
      }
      await updateAchievement(formEditingId.value, patch)
    }
    formOpen.value = false
    await loadAll()
  } catch (e: unknown) {
    formError.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    formSaving.value = false
  }
}

function onDelete(a: Achievement) {
  askConfirm({
    title: '删除成就',
    message: `将永久删除「${a.name}」并清空所有用户对该 code 的解锁记录,此操作不可撤销。确认?`,
    tone: 'danger',
    onConfirm: async () => {
      try {
        await deleteAchievement(a.id)
        await loadAll()
      } catch (e: unknown) {
        error.value = e instanceof Error ? e.message : '删除失败'
      }
    }
  })
}

function onToggleActive(a: Achievement) {
  askConfirm({
    title: a.is_active ? '停用成就' : '启用成就',
    message: `${a.is_active ? '停用后该成就不会被新用户解锁' : '启用后将重新参与评估'}(「${a.name}」)。继续?`,
    onConfirm: async () => {
      try {
        await updateAchievement(a.id, { is_active: a.is_active ? 0 : 1 })
        await loadAll()
      } catch (e: unknown) {
        error.value = e instanceof Error ? e.message : '操作失败'
      }
    }
  })
}

// ─────────── detail + try metric ───────────
async function openDetail(a: Achievement) {
  detailOpen.value = true
  detailLoading.value = true
  tryUserId.value = ''
  tryResult.value = null
  tryError.value = null
  recomputeResp.value = null
  try {
    detail.value = await getAchievement(a.id)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载详情失败'
    detailOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

const tryMetricInfo = computed<MetricType | null>(() => {
  if (!detail.value) return null
  return metrics.value.find((m) => m.value === detail.value!.metric_type) ?? null
})

async function onTryMetric() {
  if (!detail.value) return
  const uid = parseInt(tryUserId.value, 10)
  if (!uid || uid <= 0) {
    tryError.value = '请输入有效的 user_id'
    return
  }
  tryLoading.value = true
  tryError.value = null
  tryResult.value = null
  try {
    tryResult.value = await tryMetric({
      user_id: uid,
      metric_type: detail.value.metric_type,
      target_value: detail.value.target_value
    })
  } catch (e: unknown) {
    tryError.value = e instanceof Error ? e.message : '试用失败'
  } finally {
    tryLoading.value = false
  }
}

async function onRecompute() {
  if (!detail.value) return
  const uid = parseInt(tryUserId.value, 10)
  if (!uid || uid <= 0) {
    tryError.value = '请输入有效的 user_id'
    return
  }
  recomputeLoading.value = true
  recomputeResp.value = null
  tryError.value = null
  try {
    recomputeResp.value = await recomputeUserAchievements(uid)
  } catch (e: unknown) {
    tryError.value = e instanceof Error ? e.message : '重算失败'
  } finally {
    recomputeLoading.value = false
  }
}

watch(formOpen, (v) => {
  if (!v) formError.value = null
})
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="成就管理" />

      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">成就管理</h2>
            <p class="muted">
              定义成就 · 配置 metric 评估规则 · 试用查看用户当前进度 ·
              <span class="status-tag" v-if="stats">共 <span class="mono">{{ stats.active_definitions }}</span> 启用 / <span class="mono">{{ stats.total_definitions }}</span> 总 · 已解锁 <span class="mono">{{ formatNumber(totalUnlocks) }}</span></span>
            </p>
          </div>
          <div class="header-actions">
            <button class="ghost-btn" @click="loadAll" :disabled="loading">
              <span class="ic">↻</span>{{ loading ? '刷新中' : '刷新' }}
            </button>
            <button class="primary-btn" @click="openCreate">
              <span class="ic">+</span>新建成就
            </button>
          </div>
        </header>

        <!-- 顶部 KPI -->
        <div class="kpi-row">
          <MagneticCard class="kpi">
            <div class="k-label">总用户</div>
            <div class="k-value mono">{{ formatNumber(totalUsers) }}</div>
          </MagneticCard>
          <MagneticCard class="kpi">
            <div class="k-label">定义数</div>
            <div class="k-value mono">{{ stats?.total_definitions ?? achievements.length }}</div>
            <div class="k-foot muted">启用 {{ stats?.active_definitions ?? achievements.filter((a) => a.is_active).length }}</div>
          </MagneticCard>
          <MagneticCard class="kpi">
            <div class="k-label">总解锁</div>
            <div class="k-value mono">{{ formatNumber(totalUnlocks) }}</div>
          </MagneticCard>
          <MagneticCard class="kpi">
            <div class="k-label">平均达成率</div>
            <div class="k-value mono">
              {{ stats?.rows?.length
                ? formatPercent(stats.rows.reduce((s, r) => s + r.unlock_rate, 0) / stats.rows.length, 1)
                : '—' }}
            </div>
          </MagneticCard>
        </div>

        <!-- 过滤栏 -->
        <div class="toolbar">
          <div class="left-tools">
            <GlassInput v-model="searchKw" placeholder="按名称 / code 搜索" />
            <div class="seg">
              <button
                v-for="f in (['all', 'active', 'inactive'] as const)"
                :key="f"
                class="seg-btn"
                :class="{ active: filterActive === f }"
                @click="filterActive = f"
              >{{ f === 'all' ? '全部' : f === 'active' ? '启用' : '停用' }}</button>
            </div>
          </div>
          <span class="muted count">显示 {{ filteredAchievements.length }} 条</span>
        </div>

        <!-- 卡片网格 -->
        <div v-if="loading && achievements.length === 0" class="loading pad">加载中…</div>
        <GlassCard v-else-if="filteredAchievements.length === 0" type="middle" class="empty-card">
          <EmptyState
            icon="★"
            :title="searchKw ? '没有匹配的成就' : '还没有任何成就'"
            :hint="searchKw ? '试试更短的关键词' : '点击右上「新建成就」开始定义'"
          />
        </GlassCard>
        <div v-else class="ach-grid">
          <article
            v-for="a in filteredAchievements"
            :key="a.id"
            class="ach-card"
            :class="{ inactive: !a.is_active }"
            @click="openDetail(a)"
          >
            <div class="ach-icon">{{ a.icon || '🏅' }}</div>
            <div class="ach-body">
              <div class="ach-head">
                <h4 class="ach-title">{{ a.name }}</h4>
                <span v-if="!a.is_active" class="tag-off">已停用</span>
              </div>
              <p class="ach-desc">{{ a.description || '—' }}</p>
              <div class="ach-meta">
                <span class="muted sm">
                  {{ metrics.find((m) => m.value === a.metric_type)?.label ?? a.metric_type }}
                  · 目标 {{ a.target_value }}{{ metrics.find((m) => m.value === a.metric_type)?.unit ?? '' }}
                </span>
              </div>
              <div class="ach-stats">
                <span class="muted sm">已解锁</span>
                <span class="mono big">{{ formatNumber(getStatFor(a.id)?.unlock_count ?? 0) }}</span>
                <span class="muted sm">/ {{ formatNumber(totalUsers) }} ({{ formatPercent(getStatFor(a.id)?.unlock_rate ?? 0, 1) }})</span>
              </div>
              <div class="ach-bar">
                <span
                  class="ach-bar-fill"
                  :style="{ width: ((getStatFor(a.id)?.unlock_rate ?? 0) * 100) + '%' }"
                />
              </div>
            </div>
            <div class="ach-ops" @click.stop>
              <button class="op-btn" @click="openEdit(a)">编辑</button>
              <button class="op-btn" @click="onToggleActive(a)">
                {{ a.is_active ? '停用' : '启用' }}
              </button>
              <button class="op-btn danger" @click="onDelete(a)">删除</button>
            </div>
          </article>
        </div>
      </section>
    </div>

    <!-- 详情 + 试用 modal -->
    <GlassModal
      :open="detailOpen"
      :title="detail ? `${detail.icon || '🏅'} ${detail.name}` : '成就详情'"
      width="560px"
      @update:open="(v) => (detailOpen = v)"
    >
      <div v-if="detailLoading" class="loading pad">加载中…</div>
      <div v-else-if="detail" class="detail-body">
        <section class="meta-block">
          <div class="meta-row">
            <span class="muted">Code</span>
            <span class="mono">{{ detail.code }}</span>
          </div>
          <div class="meta-row">
            <span class="muted">Metric</span>
            <span>
              {{ tryMetricInfo?.label ?? detail.metric_type }}
              <span v-if="tryMetricInfo" class="muted sm">· {{ tryMetricInfo.desc }}</span>
            </span>
          </div>
          <div class="meta-row">
            <span class="muted">目标值</span>
            <span class="mono">{{ detail.target_value }} {{ tryMetricInfo?.unit ?? '' }}</span>
          </div>
          <div class="meta-row">
            <span class="muted">解锁统计</span>
            <span class="mono">
              {{ formatNumber(getStatFor(detail.id)?.unlock_count ?? 0) }} / {{ formatNumber(totalUsers) }}
              ({{ formatPercent(getStatFor(detail.id)?.unlock_rate ?? 0, 1) }})
            </span>
          </div>
        </section>

        <section class="try-block">
          <h5 class="serif">试用 metric</h5>
          <p class="muted sm">输入 user_id,实时查看该用户的当前值与达成率</p>
          <div class="try-row">
            <GlassInput
              v-model="tryUserId"
              type="number"
              placeholder="user_id,如 1"
              @keyup.enter="onTryMetric"
            />
            <button class="primary-btn" :disabled="tryLoading" @click="onTryMetric">
              {{ tryLoading ? '评估中…' : '试用' }}
            </button>
            <button class="ghost-btn" :disabled="recomputeLoading" @click="onRecompute">
              <span class="ic">↻</span>
              {{ recomputeLoading ? '重算中…' : '重算' }}
            </button>
          </div>
          <div v-if="tryError" class="err">{{ tryError }}</div>
          <div v-if="tryResult" class="try-result">
            <div class="try-line">
              <span class="muted">当前值</span>
              <span class="mono big">
                {{ formatNumber(tryResult.current_value) }}
                <span class="muted sm">/ {{ formatNumber(tryResult.target_value) }} {{ tryMetricInfo?.unit ?? '' }}</span>
              </span>
            </div>
            <div class="try-line">
              <span class="muted">达成率</span>
              <span class="mono big" :style="{ color: tryResult.reached ? 'var(--accent-2)' : 'var(--c-ink)' }">
                {{ formatPercent(tryResult.progress, 1) }}
                <span v-if="tryResult.reached" class="tag-on sm">已达成</span>
                <span v-else class="tag-off sm">未达成</span>
              </span>
            </div>
            <div class="try-bar">
              <span
                class="try-bar-fill"
                :style="{
                  width: Math.min(100, tryResult.progress * 100) + '%',
                  background: tryResult.reached ? 'var(--accent-2)' : 'var(--accent-1)'
                }"
              />
            </div>
          </div>
          <div v-if="recomputeResp" class="try-result">
            <div class="try-line">
              <span class="muted">新解锁</span>
              <span class="mono big">{{ recomputeResp.count }} 条</span>
            </div>
            <div v-if="recomputeResp.count > 0" class="recompute-list">
              <div v-for="u in recomputeResp.newly_unlocked" :key="u.type" class="recompute-row">
                <span>{{ u.icon }} {{ u.name }}</span>
                <span class="muted sm mono">{{ u.current_value }} / {{ u.target_value }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </GlassModal>

    <!-- 新建/编辑表单 modal -->
    <GlassModal
      :open="formOpen"
      :title="formMode === 'create' ? '新建成就' : '编辑成就'"
      width="520px"
      @update:open="(v) => (formOpen = v)"
    >
      <div class="form">
        <div class="form-row">
          <span>图标 (Emoji)</span>
          <GlassInput v-model="form.icon" placeholder="🏅 / 🌱 / 🏆 ..." />
        </div>
        <div class="form-row">
          <span>名称</span>
          <GlassInput v-model="form.name" placeholder="如:执行者" />
        </div>
        <div class="form-row" v-if="formMode === 'create'">
          <span>唯一 code</span>
          <GlassInput v-model="form.code" placeholder="如:todo_10" />
        </div>
        <div v-else class="form-row">
          <span>Code <span class="muted sm">(不可修改)</span></span>
          <input class="readonly mono" :value="form.code" disabled />
        </div>
        <div class="form-row">
          <span>说明</span>
          <GlassInput
            :model-value="form.description ?? ''"
            placeholder="达成条件描述"
            @update:model-value="(v) => (form.description = v)"
          />
        </div>
        <div class="form-row">
          <span>Metric 类型</span>
          <GlassSelect
            v-model="form.metric_type"
            :options="metrics.map((m) => ({ label: `${m.label} (${m.value})`, value: m.value }))"
          />
        </div>
        <div class="form-row">
          <span>目标值 ({{ metrics.find((m) => m.value === form.metric_type)?.unit ?? '' }})</span>
          <input
            class="num-input"
            type="number"
            :value="form.target_value"
            min="1"
            @input="(e) => (form.target_value = Math.max(1, parseInt((e.target as HTMLInputElement).value, 10) || 1))"
          />
        </div>
        <div class="form-row">
          <span>排序</span>
          <input
            class="num-input"
            type="number"
            :value="form.sort_order"
            @input="(e) => (form.sort_order = parseInt((e.target as HTMLInputElement).value, 10) || 0)"
          />
        </div>
        <div class="form-row toggles">
          <label class="toggle">
            <input type="checkbox" :checked="!!form.is_active" @change="(e) => (form.is_active = (e.target as HTMLInputElement).checked ? 1 : 0)" />
            <span>启用</span>
          </label>
        </div>
        <div v-if="formError" class="err">{{ formError }}</div>
      </div>
      <template #footer>
        <button class="btn ghost" @click="formOpen = false">取消</button>
        <button class="btn primary" :disabled="formSaving" @click="onSaveForm">
          {{ formSaving ? '保存中…' : '保存' }}
        </button>
      </template>
    </GlassModal>

    <ConfirmDialog
      v-if="confirmPayload"
      :open="confirmOpen"
      :title="confirmPayload.title"
      :message="confirmPayload.message"
      :tone="confirmPayload.tone"
      @update:open="(v) => (confirmOpen = v)"
      @confirm="confirmPayload.onConfirm"
    />
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
.big { font-size: 15px; font-weight: 700; color: var(--c-ink); }

.status-tag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 8px; border-radius: var(--r-pill);
  background: var(--glass-2-bg); border: 1px solid var(--c-line);
  font-size: 11px; color: var(--c-ink-2);
}

/* header */
.header-actions { display: flex; gap: 8px; }

.primary-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: var(--r-sm);
  background: var(--accent-gradient); color: #fff;
  border: none; font-size: 13px; font-weight: 500; cursor: pointer;
  box-shadow: 0 4px 12px -4px rgba(124, 92, 255, 0.45);
  transition: transform var(--t-fast);
}
.primary-btn:hover:not(:disabled) { transform: translateY(-1px); }
.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.primary-btn .ic { font-size: 15px; }

.ghost-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 12px; border-radius: var(--r-sm);
  background: var(--glass-2-bg); border: 1px solid var(--glass-2-border);
  color: var(--c-ink-2); font-size: 12px; cursor: pointer;
}
.ghost-btn:hover:not(:disabled) { background: var(--glass-1-bg); color: var(--c-ink); }
.ghost-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* KPI */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi { padding: 16px 18px !important; }
.k-label { font-size: 11px; color: var(--c-ink-3); text-transform: uppercase; letter-spacing: 0.06em; }
.k-value { font-family: var(--font-serif); font-size: 26px; font-weight: 700; color: var(--c-ink); margin-top: 4px; font-variant-numeric: tabular-nums; }
.k-foot { font-size: 11px; margin-top: 6px; }

/* toolbar */
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.left-tools { display: flex; align-items: center; gap: 12px; flex: 1; max-width: 540px; }
.count { font-size: 12px; }
.seg { display: flex; padding: 3px; border-radius: var(--r-pill); background: var(--glass-1-bg); border: 1px solid var(--c-line); }
.seg-btn {
  border: none; background: transparent;
  color: var(--c-ink-2); font-size: 12px;
  padding: 6px 14px; border-radius: var(--r-pill); cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.seg-btn:hover { color: var(--c-ink); }
.seg-btn.active { background: var(--accent-gradient); color: #fff; box-shadow: 0 4px 12px -4px rgba(124, 92, 255, 0.45); }

/* card grid */
.ach-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.ach-card {
  position: relative;
  display: grid; grid-template-columns: 56px 1fr;
  gap: 14px;
  padding: 16px 18px;
  background: var(--glass-2-bg);
  border: 1px solid var(--glass-2-border);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1), border-color var(--t-fast);
  backdrop-filter: blur(var(--glass-blur-2)) saturate(160%);
  -webkit-backdrop-filter: blur(var(--glass-blur-2)) saturate(160%);
  box-shadow: var(--glass-2-shadow);
}
.ach-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent-1);
  box-shadow:
    0 16px 36px -10px rgba(124, 92, 255, 0.22),
    inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}
.ach-card.inactive { opacity: 0.55; }
.ach-icon {
  font-size: 36px; line-height: 1;
  display: grid; place-items: center;
  background: var(--glass-1-bg);
  border-radius: 14px; padding: 10px;
  border: 1px solid var(--c-line);
}
.ach-body { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.ach-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ach-title { font-size: 14px; font-weight: 600; color: var(--c-ink); }
.ach-desc { font-size: 12px; color: var(--c-ink-3); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ach-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.ach-stats { display: flex; align-items: baseline; gap: 4px; margin-top: 4px; }
.ach-bar { height: 4px; background: var(--c-line); border-radius: 999px; overflow: hidden; }
.ach-bar-fill { display: block; height: 100%; background: var(--accent-gradient); border-radius: 999px; transition: width 0.4s ease; }
.ach-ops {
  position: absolute; top: 8px; right: 8px;
  display: none; gap: 4px;
}
.ach-card:hover .ach-ops { display: flex; }

.op-btn {
  padding: 3px 8px; border-radius: var(--r-sm);
  background: var(--glass-3-bg); border: 1px solid var(--c-line);
  color: var(--c-ink-2); font-size: 10px; cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.op-btn:hover:not(:disabled) { background: var(--glass-1-bg); color: var(--c-ink); }
.op-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.op-btn.danger:hover:not(:disabled) { background: rgba(248, 113, 113, 0.12); color: var(--state-error); border-color: var(--state-error); }

.tag-on { background: rgba(52, 211, 153, 0.15); color: var(--accent-2); padding: 1px 6px; border-radius: var(--r-pill); font-size: 10px; }
.tag-off { background: var(--glass-1-bg); color: var(--c-ink-3); padding: 1px 6px; border-radius: var(--r-pill); font-size: 10px; }

.empty-card { padding: 24px !important; }
.loading { text-align: center; color: var(--c-ink-3); }
.loading.pad { padding: 60px 16px; }

/* detail modal */
.detail-body { display: flex; flex-direction: column; gap: 18px; }
.meta-block { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; background: var(--glass-1-bg); border: 1px solid var(--c-line); border-radius: var(--r-sm); }
.meta-row { display: flex; justify-content: space-between; font-size: 12px; }

.try-block { display: flex; flex-direction: column; gap: 8px; }
.try-block h5 { font-size: 14px; font-weight: 600; color: var(--c-ink); }
.try-row { display: flex; gap: 8px; align-items: center; }
.try-row > :first-child { flex: 1; }

.try-result {
  display: flex; flex-direction: column; gap: 8px;
  padding: 12px 14px; background: var(--glass-1-bg);
  border: 1px solid var(--c-line); border-radius: var(--r-sm);
}
.try-line { display: flex; justify-content: space-between; align-items: center; font-size: 12px; gap: 6px; }
.try-bar { height: 6px; background: var(--c-line); border-radius: 999px; overflow: hidden; }
.try-bar-fill { display: block; height: 100%; border-radius: 999px; transition: width 0.4s ease; }

.recompute-list { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.recompute-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px dashed var(--c-line); font-size: 12px; }
.recompute-row:last-child { border-bottom: none; }
.err { font-size: 12px; color: var(--state-error); padding: 8px 10px; background: rgba(248, 113, 113, 0.08); border-radius: var(--r-sm); }

/* form */
.form { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--c-ink-2); }
.form-row.toggles { flex-direction: row; gap: 24px; align-items: center; }
.toggle { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.toggle input { accent-color: var(--accent-1); }
.readonly {
  width: 100%; padding: 12px 16px;
  border-radius: var(--r-sm);
  background: var(--glass-1-bg);
  border: 1px solid var(--c-line);
  color: var(--c-ink-3); font-size: 14px; font-family: var(--font-mono);
  outline: none; cursor: not-allowed;
}
.num-input {
  width: 100%; padding: 12px 16px;
  border-radius: var(--r-sm);
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  color: var(--c-ink); font-size: 14px; font-family: var(--font-mono);
  outline: none;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.num-input:focus {
  border-color: var(--accent-1);
  box-shadow: 0 0 0 3px rgba(124, 92, 255, 0.18);
}
.btn {
  padding: 8px 16px; border-radius: var(--r-sm);
  font-size: 13px; font-weight: 500; border: none;
  transition: opacity var(--t-fast); cursor: pointer;
}
.btn.primary { background: var(--accent-gradient); color: #fff; }
.btn.ghost { background: var(--glass-1-bg); color: var(--c-ink-2); }
.btn:hover:not(:disabled) { opacity: 0.85; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 1100px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } .ach-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 720px) { .kpi-row { grid-template-columns: 1fr; } .ach-grid { grid-template-columns: 1fr; } }
</style>
