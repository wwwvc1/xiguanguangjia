<script setup lang="ts">
/**
 * LLMModelsView — AI 模型管理 + 7 日用量统计
 *
 * 标签页:
 *   ① 模型列表 — R + CUD + 测活 + 设为默认
 *   ② 用量统计 — 7/30/90 日 LLM 调用折线 + 总调用/总用户 + top 模型分布
 *
 * 测活成功 → 弹出 7 日用量明细 modal(沿用 dashboard 的 LLMUsageStats)
 */
import { ref, computed, onMounted, reactive, watch } from 'vue'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import GlassInput from '@/components/form/GlassInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import MagneticCard from '@/components/ui/MagneticCard.vue'
import Sparkline from '@/components/chart/Sparkline.vue'
import {
  listModels,
  createModel,
  updateModel,
  deleteModel,
  setDefaultModel,
  testModel,
  getLLMUsage,
  type LLMModel,
  type LLMModelCreate,
  type LLMTestResult,
  type LLMUsageStats
} from '@/api/models'
import { formatNumber, formatDate } from '@/utils/format'

// ─────────── state ───────────
type Tab = 'list' | 'usage'
const tab = ref<Tab>('list')
const loading = ref(true)
const usageLoading = ref(true)
const error = ref<string | null>(null)

const models = ref<LLMModel[]>([])
const usage = ref<LLMUsageStats | null>(null)
const usageDays = ref<7 | 30 | 90>(7)

const filterOwner = ref<'all' | 'system' | 'user'>('all')

// 测活结果
const testResults = reactive<Record<number, LLMTestResult | null>>({})
const testingId = ref<number | null>(null)

// 测活成功的 → 弹用量明细
const usageModalOpen = ref(false)
const usageModalModel = ref<LLMModel | null>(null)
const usageModalData = ref<LLMUsageStats | null>(null)
const usageModalLoading = ref(false)

// 表单弹窗(create / edit)
const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const form = reactive<LLMModelCreate>({
  name: '',
  base_url: '',
  api_key: '',
  model_name: '',
  is_active: true,
  is_system_default: false
})
const formEditingId = ref<number | null>(null)
const formSaving = ref(false)
const formError = ref<string | null>(null)

// 确认弹窗
const confirmOpen = ref(false)
const confirmPayload = ref<{ title: string; message: string; onConfirm: () => void; tone: 'default' | 'danger' } | null>(null)
function askConfirm(opts: { title: string; message: string; tone?: 'default' | 'danger'; onConfirm: () => void }) {
  confirmPayload.value = { tone: 'default', ...opts }
  confirmOpen.value = true
}

// ─────────── loaders ───────────
async function loadModels() {
  loading.value = true
  error.value = null
  try {
    models.value = await listModels(filterOwner.value)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载模型失败'
  } finally {
    loading.value = false
  }
}

async function loadUsage() {
  usageLoading.value = true
  try {
    usage.value = await getLLMUsage(usageDays.value)
  } catch (e: unknown) {
    // 静默,只是折线为空
    console.error('usage load failed', e)
  } finally {
    usageLoading.value = false
  }
}

watch(filterOwner, () => loadModels())
watch(usageDays, () => loadUsage())

onMounted(() => {
  loadModels()
  loadUsage()
})

// ─────────── usage 衍生 ───────────
const callSeries = computed(() => (usage.value?.daily ?? []).map((d) => d.call_count))
const userSeries = computed(() => (usage.value?.daily ?? []).map((d) => d.user_count))
const callTotal = computed(() => usage.value?.total_calls ?? 0)
const userTotal = computed(() => usage.value?.total_users ?? 0)
const dailyAvg = computed(() => (callTotal.value / Math.max(1, usage.value?.days ?? 1)).toFixed(1))
const peakDay = computed(() => {
  const daily = usage.value?.daily ?? []
  if (!daily.length) return null
  return daily.reduce((m, d) => (d.call_count > m.call_count ? d : m), daily[0])
})

// 折线 SVG 工具
function linePath(data: number[], w: number, h: number): string {
  if (!data.length) return ''
  const max = Math.max(...data, 1)
  const stepX = w / (data.length - 1 || 1)
  return data
    .map((v, i) => {
      const x = (i * stepX).toFixed(2)
      const y = (h - (v / max) * (h - 10) - 5).toFixed(2)
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
}
function areaPath(data: number[], w: number, h: number): string {
  if (!data.length) return ''
  const max = Math.max(...data, 1)
  const stepX = w / (data.length - 1 || 1)
  const top = data
    .map((v, i) => {
      const x = (i * stepX).toFixed(2)
      const y = (h - (v / max) * (h - 10) - 5).toFixed(2)
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
  return `${top} L ${w} ${h} L 0 ${h} Z`
}
function endY(data: number[], h: number): number {
  if (!data.length) return h
  const max = Math.max(...data, 1)
  return h - (data[data.length - 1] / max) * (h - 10) - 5
}

// ─────────── handlers ───────────
async function onTest(m: LLMModel) {
  testingId.value = m.id
  testResults[m.id] = null
  try {
    const r = await testModel(m.id)
    testResults[m.id] = r
    if (r.success) {
      // 弹用量明细
      usageModalModel.value = m
      usageModalOpen.value = true
      usageModalLoading.value = true
      try {
        usageModalData.value = await getLLMUsage(7)
      } catch (e) {
        console.error('usage load failed', e)
      } finally {
        usageModalLoading.value = false
      }
    }
  } catch (e: unknown) {
    testResults[m.id] = { success: false, latency_ms: 0, error: e instanceof Error ? e.message : '测活失败' }
  } finally {
    testingId.value = null
  }
}

async function onSetDefault(m: LLMModel) {
  askConfirm({
    title: '设为系统默认',
    message: `将「${m.name}」设为系统默认模型,所有用户的 AI 调用将优先使用。确认?`,
    onConfirm: async () => {
      try {
        await setDefaultModel(m.id)
        await loadModels()
      } catch (e: unknown) {
        error.value = e instanceof Error ? e.message : '设置失败'
      }
    }
  })
}

function openCreate() {
  formMode.value = 'create'
  formEditingId.value = null
  Object.assign(form, {
    name: '',
    base_url: '',
    api_key: '',
    model_name: '',
    is_active: true,
    is_system_default: false
  })
  formError.value = null
  formOpen.value = true
}
function openEdit(m: LLMModel) {
  formMode.value = 'edit'
  formEditingId.value = m.id
  Object.assign(form, {
    name: m.name,
    base_url: m.base_url,
    api_key: '',  // 不回显,留空 = 不更新
    model_name: m.model_name,
    is_active: m.is_active,
    is_system_default: m.is_system_default
  })
  formError.value = null
  formOpen.value = true
}
async function onSaveForm() {
  formSaving.value = true
  formError.value = null
  try {
    if (formMode.value === 'create') {
      await createModel({ ...form })
    } else if (formEditingId.value != null) {
      const patch: Record<string, unknown> = {
        name: form.name,
        base_url: form.base_url,
        model_name: form.model_name,
        is_active: form.is_active
      }
      if (form.api_key) patch.api_key = form.api_key
      await updateModel(formEditingId.value, patch)
    }
    formOpen.value = false
    await loadModels()
  } catch (e: unknown) {
    formError.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    formSaving.value = false
  }
}

function onDelete(m: LLMModel) {
  askConfirm({
    title: '删除模型',
    message: `将永久删除「${m.name}」,此操作不可撤销。确认?`,
    tone: 'danger',
    onConfirm: async () => {
      try {
        await deleteModel(m.id)
        await loadModels()
      } catch (e: unknown) {
        error.value = e instanceof Error ? e.message : '删除失败'
      }
    }
  })
}

function onToggleActive(m: LLMModel) {
  askConfirm({
    title: m.is_active ? '停用模型' : '启用模型',
    message: `${m.is_active ? '停用后该模型将不再响应请求' : '启用后该模型将恢复响应'}(「${m.name}」)。继续?`,
    onConfirm: async () => {
      try {
        await updateModel(m.id, { is_active: !m.is_active })
        await loadModels()
      } catch (e: unknown) {
        error.value = e instanceof Error ? e.message : '操作失败'
      }
    }
  })
}
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="AI 模型" />

      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">AI 模型管理</h2>
            <p class="muted">
              维护系统级 / 用户私有 LLM 模型 ·
              测活 7 日用量明细 ·
              <span class="status-tag">调用 <span class="mono">{{ formatNumber(callTotal) }}</span> 次 / <span class="mono">{{ formatNumber(userTotal) }}</span> 用户</span>
            </p>
          </div>
          <div class="seg">
            <button
              v-for="t in (['list', 'usage'] as const)"
              :key="t"
              class="seg-btn"
              :class="{ active: tab === t }"
              @click="tab = t"
            >
              {{ t === 'list' ? '模型列表' : '用量统计' }}
            </button>
          </div>
        </header>

        <!-- ============== 标签页 1: 模型列表 ============== -->
        <div v-if="tab === 'list'" class="list-pane">
          <div class="toolbar">
            <div class="left-tools">
              <div class="seg seg-sm">
                <button
                  v-for="o in (['all', 'system', 'user'] as const)"
                  :key="o"
                  class="seg-btn"
                  :class="{ active: filterOwner === o }"
                  @click="filterOwner = o"
                >{{ o === 'all' ? '全部' : o === 'system' ? '系统' : '用户私有' }}</button>
              </div>
              <span class="muted count">共 {{ models.length }} 个</span>
            </div>
            <button class="primary-btn" @click="openCreate">
              <span class="ic">+</span>新建模型
            </button>
          </div>

          <GlassCard type="middle" class="table-card">
            <div v-if="loading" class="loading">加载中…</div>
            <div v-else-if="models.length === 0">
              <EmptyState
                icon="◈"
                title="还没有模型"
                hint="点击右上「新建模型」开始添加 LLM 提供商"
              />
            </div>
            <table v-else class="t">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>模型标识</th>
                  <th>Base URL</th>
                  <th>归属</th>
                  <th>状态</th>
                  <th>测活</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in models" :key="m.id">
                  <td>
                    <div class="name-cell">
                      <span class="dot" :style="{ background: m.is_active ? 'var(--accent-2)' : 'var(--c-line)' }" />
                      <div>
                        <div class="name-text">{{ m.name }}</div>
                        <div class="muted sm">#{{ m.id }} · {{ formatDate(m.created_at) }}</div>
                      </div>
                    </div>
                  </td>
                  <td><span class="mono cell-mono">{{ m.model_name }}</span></td>
                  <td><span class="mono cell-mono cell-trunc" :title="m.base_url">{{ m.base_url }}</span></td>
                  <td>
                    <span v-if="m.is_system_default" class="tag tag-default">系统默认</span>
                    <span v-else-if="m.owner_user_id" class="tag tag-user">用户 #{{ m.owner_user_id }}</span>
                    <span v-else class="tag">系统</span>
                  </td>
                  <td>
                    <span class="tag" :class="m.is_active ? 'tag-on' : 'tag-off'">
                      {{ m.is_active ? '启用' : '停用' }}
                    </span>
                  </td>
                  <td>
                    <div class="test-cell">
                      <button
                        class="mini-btn"
                        :disabled="testingId === m.id"
                        @click="onTest(m)"
                      >
                        {{ testingId === m.id ? '测活中…' : '测活' }}
                      </button>
                      <span
                        v-if="testResults[m.id]"
                        class="test-res"
                        :class="testResults[m.id]?.success ? 'ok' : 'fail'"
                        :title="testResults[m.id]?.error ?? testResults[m.id]?.reply ?? ''"
                      >
                        {{ testResults[m.id]?.success ? `${testResults[m.id]?.latency_ms}ms` : '✕' }}
                      </span>
                    </div>
                  </td>
                  <td>
                    <div class="ops">
                      <button
                        v-if="!m.is_system_default && m.owner_user_id === null"
                        class="op-btn"
                        :disabled="!m.is_active"
                        :title="!m.is_active ? '启用后才能设为默认' : '设为系统默认'"
                        @click="onSetDefault(m)"
                      >设默认</button>
                      <button class="op-btn" @click="openEdit(m)">编辑</button>
                      <button class="op-btn" @click="onToggleActive(m)">
                        {{ m.is_active ? '停用' : '启用' }}
                      </button>
                      <button
                        v-if="!m.is_system_default"
                        class="op-btn danger"
                        @click="onDelete(m)"
                      >删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </GlassCard>
        </div>

        <!-- ============== 标签页 2: 用量统计 ============== -->
        <div v-else class="usage-pane">
          <div class="toolbar">
            <div class="left-tools">
              <div class="seg seg-sm">
                <button
                  v-for="d in ([7, 30, 90] as const)"
                  :key="d"
                  class="seg-btn"
                  :class="{ active: usageDays === d }"
                  @click="usageDays = d"
                >{{ d }} 天</button>
              </div>
              <button class="ghost-btn" @click="loadUsage" :disabled="usageLoading">
                <span class="ic">↻</span>{{ usageLoading ? '刷新中' : '刷新' }}
              </button>
            </div>
            <span class="muted range">
              {{ usage?.daily?.[0]?.date ?? '—' }} → {{ usage?.daily?.[usage.daily.length - 1]?.date ?? '—' }}
            </span>
          </div>

          <div class="kpi-row">
            <MagneticCard class="kpi">
              <div class="k-label">区间总调用</div>
              <div class="k-value"><span class="mono">{{ formatNumber(callTotal) }}</span></div>
              <div class="k-foot muted">日均 {{ dailyAvg }} 次</div>
            </MagneticCard>
            <MagneticCard class="kpi">
              <div class="k-label">独立用户</div>
              <div class="k-value"><span class="mono">{{ formatNumber(userTotal) }}</span></div>
              <div class="k-foot muted">区间内不重复</div>
            </MagneticCard>
            <MagneticCard class="kpi">
              <div class="k-label">峰值日</div>
              <div class="k-value"><span class="mono">{{ formatNumber(peakDay?.call_count ?? 0) }}</span></div>
              <div class="k-foot muted">{{ peakDay?.date ?? '—' }}</div>
            </MagneticCard>
            <MagneticCard class="kpi">
              <div class="k-label">模型数</div>
              <div class="k-value"><span class="mono">{{ models.length }}</span></div>
              <div class="k-foot muted">启用中</div>
            </MagneticCard>
          </div>

          <GlassCard type="outer" class="chart-card">
            <div class="panel-head">
              <div>
                <h3 class="serif">每日 LLM 调用</h3>
                <p class="muted">柱:调用次数 · 线:独立用户数</p>
              </div>
              <div class="legend">
                <span class="lg-item">
                  <span class="lg-bar" style="background: var(--accent-1);" />调用
                </span>
                <span class="lg-item">
                  <span class="lg-line" style="background: var(--accent-2);" />用户
                </span>
              </div>
            </div>

            <div v-if="usageLoading" class="loading pad">加载中…</div>
            <div v-else-if="!usage?.daily?.length" class="loading pad muted">该区间暂无调用</div>
            <div v-else class="chart-svg">
              <svg viewBox="0 0 800 260" preserveAspectRatio="none" width="100%" height="260">
                <!-- 网格 -->
                <line v-for="i in 4" :key="i" x1="0" x2="800" :y1="i * 52" :y2="i * 52"
                      stroke="var(--c-line)" stroke-dasharray="2 4" />
                <!-- 柱 -->
                <g v-if="callSeries.length">
                  <rect
                    v-for="(v, i) in callSeries" :key="`b-${i}`"
                    :x="i * (800 / callSeries.length) + 6"
                    :y="240 - (v / Math.max(...callSeries, 1)) * 200 - 4"
                    :width="(800 / callSeries.length) - 12"
                    :height="(v / Math.max(...callSeries, 1)) * 200 + 4"
                    fill="var(--accent-1)"
                    fill-opacity="0.75"
                    rx="3"
                  >
                    <title>{{ usage?.daily?.[i]?.date }} · {{ v }} 次 · {{ usage?.daily?.[i]?.user_count }} 人</title>
                  </rect>
                </g>
                <!-- 用户折线 -->
                <path v-if="userSeries.length"
                      :d="linePath(userSeries, 800, 240)"
                      stroke="var(--accent-2)" stroke-width="2"
                      fill="none" stroke-linecap="round" stroke-linejoin="round" />
                <path v-if="userSeries.length"
                      :d="areaPath(userSeries, 800, 240)"
                      fill="var(--accent-2)" fill-opacity="0.08" />
                <circle v-if="userSeries.length"
                        :cx="800" :cy="endY(userSeries, 240)"
                        r="4" fill="var(--accent-2)" />
              </svg>
              <div class="x-axis">
                <span v-if="usage?.daily?.length">
                  <template v-for="(d, i) in usage.daily" :key="d.date">
                    <span v-if="i === 0 || i === usage.daily.length - 1 || i === Math.floor(usage.daily.length / 2)" class="mono">
                      {{ d.date.slice(5) }}
                    </span>
                  </template>
                </span>
              </div>
            </div>
          </GlassCard>
        </div>
      </section>
    </div>

    <!-- ============== 测活成功后的用量明细 modal ============== -->
    <GlassModal
      :open="usageModalOpen"
      :title="`${usageModalModel?.name ?? ''} · 7 日用量`"
      width="640px"
      @update:open="(v) => (usageModalOpen = v)"
    >
      <div v-if="usageModalLoading" class="loading pad">加载用量中…</div>
      <div v-else-if="!usageModalData?.daily?.length" class="muted">近 7 日暂无调用</div>
      <div v-else>
        <div class="kpi-row small">
          <div class="mini-kpi">
            <div class="muted">总调用</div>
            <div class="mini-val mono">{{ formatNumber(usageModalData.total_calls) }}</div>
          </div>
          <div class="mini-kpi">
            <div class="muted">总用户</div>
            <div class="mini-val mono">{{ formatNumber(usageModalData.total_users) }}</div>
          </div>
          <div class="mini-kpi">
            <div class="muted">日均</div>
            <div class="mini-val mono">
              {{ (usageModalData.total_calls / 7).toFixed(1) }}
            </div>
          </div>
        </div>
        <Sparkline
          :data="usageModalData.daily.map((d) => d.call_count)"
          :width="540" :height="60"
          stroke="var(--accent-1)"
        />
        <div class="day-list">
          <div v-for="d in usageModalData.daily" :key="d.date" class="day-row">
            <span class="mono">{{ d.date }}</span>
            <span class="muted">{{ d.user_count }} 人</span>
            <span class="mono strong">{{ d.call_count }} 次</span>
          </div>
        </div>
      </div>
    </GlassModal>

    <!-- ============== 新建/编辑表单 modal ============== -->
    <GlassModal
      :open="formOpen"
      :title="formMode === 'create' ? '新建模型' : '编辑模型'"
      width="520px"
      @update:open="(v) => (formOpen = v)"
    >
      <div class="form">
        <label class="form-row">
          <span>显示名</span>
          <GlassInput v-model="form.name" placeholder="如:GPT-4o 主力" />
        </label>
        <label class="form-row">
          <span>Base URL</span>
          <GlassInput v-model="form.base_url" placeholder="https://api.openai.com/v1" />
        </label>
        <label class="form-row">
          <span>
            API Key
            <span v-if="formMode === 'edit'" class="muted sm">(留空则不更新)</span>
          </span>
          <GlassInput
            v-model="form.api_key"
            :type="formMode === 'edit' ? 'password' : 'text'"
            :placeholder="formMode === 'edit' ? '••••••(留空保持不变)' : 'sk-...'"
          />
        </label>
        <label class="form-row">
          <span>模型标识</span>
          <GlassInput v-model="form.model_name" placeholder="gpt-4o / claude-3-5-sonnet-..." />
        </label>
        <div class="form-row toggles">
          <label class="toggle">
            <input type="checkbox" v-model="form.is_active" />
            <span>启用</span>
          </label>
          <label class="toggle">
            <input
              type="checkbox"
              v-model="form.is_system_default"
              :disabled="formMode === 'edit'"
            />
            <span>设为系统默认</span>
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
.sm { font-size: 11px; }
.mono { font-family: var(--font-mono); }

.status-tag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 8px; border-radius: var(--r-pill);
  background: var(--glass-2-bg); border: 1px solid var(--c-line);
  font-size: 11px; color: var(--c-ink-2);
}

.seg {
  display: flex; padding: 3px; border-radius: var(--r-pill);
  background: var(--glass-1-bg); border: 1px solid var(--c-line);
}
.seg-sm { padding: 2px; }
.seg-btn {
  border: none; background: transparent;
  color: var(--c-ink-2); font-size: 12px;
  padding: 6px 14px; border-radius: var(--r-pill); cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.seg-btn:hover { color: var(--c-ink); }
.seg-btn.active {
  background: var(--accent-gradient); color: #fff;
  box-shadow: 0 4px 12px -4px rgba(124, 92, 255, 0.45);
}

/* toolbar */
.toolbar {
  display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
}
.left-tools { display: flex; align-items: center; gap: 12px; }
.count { font-size: 12px; }
.range { font-size: 12px; font-family: var(--font-mono); }

.primary-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: var(--r-sm);
  background: var(--accent-gradient); color: #fff;
  border: none; font-size: 13px; font-weight: 500; cursor: pointer;
  box-shadow: 0 4px 12px -4px rgba(124, 92, 255, 0.45);
  transition: transform var(--t-fast), box-shadow var(--t-fast);
}
.primary-btn:hover { transform: translateY(-1px); }
.primary-btn .ic { font-size: 15px; }

.ghost-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 12px; border-radius: var(--r-sm);
  background: var(--glass-2-bg); border: 1px solid var(--glass-2-border);
  color: var(--c-ink-2); font-size: 12px; cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.ghost-btn:hover:not(:disabled) { background: var(--glass-1-bg); color: var(--c-ink); }
.ghost-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* table */
.table-card { padding: 0 !important; overflow: hidden; }
.loading { padding: 24px; text-align: center; color: var(--c-ink-3); }
.loading.pad { padding: 60px 16px; }
.t { width: 100%; border-collapse: collapse; }
.t th, .t td {
  padding: 12px 16px; text-align: left;
  border-bottom: 1px solid var(--c-line);
  font-size: 13px; color: var(--c-ink);
  vertical-align: middle;
}
.t th {
  font-weight: 600; font-size: 11px;
  color: var(--c-ink-3); text-transform: uppercase; letter-spacing: 0.06em;
  background: var(--glass-1-bg);
}
.t tbody tr:hover { background: var(--glass-1-bg); }
.t tbody tr:last-child td { border-bottom: none; }

.name-cell { display: flex; align-items: center; gap: 10px; }
.name-cell .dot { width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 6px currentColor; flex-shrink: 0; }
.name-text { font-weight: 600; }
.cell-mono { font-size: 12px; color: var(--c-ink-2); }
.cell-trunc { display: inline-block; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }

.tag {
  display: inline-block; padding: 2px 8px; border-radius: var(--r-pill);
  font-size: 11px; background: var(--glass-1-bg); color: var(--c-ink-2);
  border: 1px solid var(--c-line);
}
.tag-on { background: rgba(52, 211, 153, 0.15); color: var(--accent-2); border-color: transparent; }
.tag-off { background: var(--glass-1-bg); color: var(--c-ink-3); }
.tag-default { background: var(--accent-gradient); color: #fff; border-color: transparent; }
.tag-user { background: rgba(124, 92, 255, 0.15); color: var(--accent-1); border-color: transparent; }

.test-cell { display: inline-flex; align-items: center; gap: 6px; }
.mini-btn {
  padding: 4px 10px; border-radius: var(--r-sm);
  background: var(--glass-2-bg); border: 1px solid var(--c-line);
  color: var(--c-ink-2); font-size: 11px; cursor: pointer;
}
.mini-btn:hover:not(:disabled) { background: var(--glass-1-bg); color: var(--c-ink); }
.mini-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.test-res { font-size: 11px; font-family: var(--font-mono); }
.test-res.ok { color: var(--accent-2); }
.test-res.fail { color: var(--state-error); }

.ops { display: flex; gap: 4px; flex-wrap: wrap; }
.op-btn {
  padding: 4px 10px; border-radius: var(--r-sm);
  background: transparent; border: 1px solid var(--c-line);
  color: var(--c-ink-2); font-size: 11px; cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.op-btn:hover:not(:disabled) { background: var(--glass-2-bg); color: var(--c-ink); }
.op-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.op-btn.danger:hover:not(:disabled) { background: rgba(248, 113, 113, 0.12); color: var(--state-error); border-color: var(--state-error); }

/* usage */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi-row.small { grid-template-columns: repeat(3, 1fr); }
.kpi { padding: 16px 18px !important; }
.k-label { font-size: 11px; color: var(--c-ink-3); text-transform: uppercase; letter-spacing: 0.06em; }
.k-value { font-family: var(--font-serif); font-size: 26px; font-weight: 700; color: var(--c-ink); margin-top: 4px; font-variant-numeric: tabular-nums; }
.k-foot { font-size: 11px; margin-top: 6px; }

.chart-card { padding: 20px !important; }
.panel-head { display: flex; justify-content: space-between; align-items: end; margin-bottom: 16px; }
.panel-head h3 { font-size: 15px; font-weight: 600; color: var(--c-ink); }
.legend { display: flex; gap: 16px; }
.lg-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--c-ink-2); }
.lg-bar { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.lg-line { width: 14px; height: 2px; border-radius: 2px; display: inline-block; }

.chart-svg { background: var(--glass-1-bg); border-radius: var(--r-sm); padding: 16px; border: 1px solid var(--c-line); }
.x-axis { display: flex; justify-content: space-between; margin-top: 8px; font-size: 11px; color: var(--c-ink-3); font-family: var(--font-mono); }

/* modal mini kpi */
.mini-kpi { padding: 10px 12px; background: var(--glass-1-bg); border: 1px solid var(--c-line); border-radius: var(--r-sm); }
.mini-kpi .muted { font-size: 11px; margin: 0; }
.mini-val { font-size: 18px; font-weight: 700; color: var(--c-ink); margin-top: 2px; }
.day-list { margin-top: 12px; max-height: 220px; overflow-y: auto; }
.day-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed var(--c-line); font-size: 12px; }
.day-row:last-child { border-bottom: none; }
.day-row .strong { color: var(--c-ink); font-weight: 600; }

/* form */
.form { display: flex; flex-direction: column; gap: 14px; }
.form-row { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--c-ink-2); }
.form-row.toggles { flex-direction: row; gap: 24px; align-items: center; }
.toggle { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.toggle input { accent-color: var(--accent-1); }
.err { font-size: 12px; color: var(--state-error); padding: 8px 10px; background: rgba(248, 113, 113, 0.08); border-radius: var(--r-sm); }
.btn {
  padding: 8px 16px; border-radius: var(--r-sm);
  font-size: 13px; font-weight: 500; border: none;
  transition: opacity var(--t-fast); cursor: pointer;
}
.btn.primary { background: var(--accent-gradient); color: #fff; }
.btn.ghost { background: var(--glass-1-bg); color: var(--c-ink-2); }
.btn:hover:not(:disabled) { opacity: 0.85; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 1100px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px) { .kpi-row { grid-template-columns: 1fr; } .t th, .t td { padding: 10px 8px; } }
</style>
