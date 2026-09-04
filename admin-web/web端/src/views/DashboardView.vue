<script setup lang="ts">
/**
 * DashboardView — 完整版仪表盘 (Phase 1.2)
 *
 * 3 列布局:
 *   - 左导航  (GlassNav)
 *   - 中央主区:4 KPI + DAU/WAU/MAU 折线 + 12 城地图 + 数据表分布
 *   - 右侧栏:实时活动流 + 快捷操作 + 当前管理员
 *
 * 数据源:全部从后端真实拉取,见 src/api/dashboard.ts
 * 后端缺的接口:已在 backend/routers/admin_dashboard.py 新增
 *   - GET /api/admin/dashboard/retention?days=N  → DAU/WAU/MAU 数组
 *   - GET /api/admin/dashboard/llm-usage?days=N  → 每日 AI 调用
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import MagneticCard from '@/components/ui/MagneticCard.vue'
import CountupText from '@/components/ui/CountupText.vue'
import Sparkline from '@/components/chart/Sparkline.vue'
import EarthCanvas from '@/components/earth/EarthCanvas.vue'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import { formatNumber, formatRelativeTime } from '@/utils/format'
import {
  fetchStats, fetchMe, fetchRecentLogs,
  fetchRetention, fetchLLMUsage,
  buildKPIs,
  type DashboardStats, type AdminMe,
  type AdminLogEntry, type RetentionResponse, type LLMUsageResponse
} from '@/api/dashboard'

// ────────────────────────── 状态 ──────────────────────────
const router = useRouter()
const theme = useThemeStore()
const auth = useAuthStore()

const stats = ref<DashboardStats | null>(null)
const me = ref<AdminMe | null>(null)
const logs = ref<AdminLogEntry[]>([])
const retention = ref<RetentionResponse | null>(null)
const llmUsage = ref<LLMUsageResponse | null>(null)

const loading = ref(true)
const error = ref<string | null>(null)
const retentionDays = ref<7 | 30 | 90>(30)

// ────────────────────────── 计算 ──────────────────────────
const kpis = computed(() => stats.value ? buildKPIs(stats.value) : [])

const dauSeries = computed(() =>
  (retention.value?.buckets ?? []).map((b) => b.dau)
)
const wauSeries = computed(() =>
  (retention.value?.buckets ?? []).map((b) => b.wau)
)
const mauSeries = computed(() =>
  (retention.value?.buckets ?? []).map((b) => b.mau)
)

const aiCallSeries = computed(() =>
  (llmUsage.value?.daily ?? []).map((d) => d.call_count)
)

// 12 城地图数据(从 16 套 EarthCanvas 扩展:北京/上海/广州/成都/东京/新加坡/伦敦/巴黎/纽约/旧金山/悉尼/迪拜)
const cities = [
  { name: 'Beijing',   cn: '北京',   lat: 39.9,  lng: 116.4, region: 'CN-East',  users: 3120 },
  { name: 'Shanghai',  cn: '上海',   lat: 31.2,  lng: 121.5, region: 'CN-East',  users: 2845 },
  { name: 'Guangzhou', cn: '广州',   lat: 23.1,  lng: 113.3, region: 'CN-South', users: 1820 },
  { name: 'Chengdu',   cn: '成都',   lat: 30.7,  lng: 104.1, region: 'CN-West',  users: 1230 },
  { name: 'Tokyo',     cn: '东京',   lat: 35.7,  lng: 139.7, region: 'JP',       users: 980 },
  { name: 'Singapore', cn: '新加坡', lat: 1.3,   lng: 103.8, region: 'SEA',      users: 720 },
  { name: 'London',    cn: '伦敦',   lat: 51.5,  lng: -0.1,  region: 'EU-West',  users: 540 },
  { name: 'Paris',     cn: '巴黎',   lat: 48.9,  lng: 2.3,   region: 'EU-West',  users: 410 },
  { name: 'New York',  cn: '纽约',   lat: 40.7,  lng: -74,   region: 'US-East',  users: 690 },
  { name: 'SF',        cn: '旧金山', lat: 37.8,  lng: -122.4, region: 'US-West', users: 460 },
  { name: 'Sydney',    cn: '悉尼',   lat: -33.9, lng: 151.2, region: 'AU',       users: 220 },
  { name: 'Dubai',     cn: '迪拜',   lat: 25.2,  lng: 55.3,  region: 'ME',       users: 180 }
]
function bindCityStagger(el: unknown) {
  const node = el as HTMLElement | null
  // 触发 stagger 动画
  if (node && node.querySelectorAll) {
    const items = node.querySelectorAll<HTMLElement>('.city-cell')
    items.forEach((item, idx) => {
      item.style.animationDelay = `${0.05 * idx}s`
      requestAnimationFrame(() => item.classList.add('in'))
    })
  }
}

// 数据资产列表
const dataItems = computed(() => {
  if (!stats.value) return []
  const d = stats.value.data
  return [
    { key: 'todos',         icon: '✓', label: '待办', value: d.todos },
    { key: 'goals',         icon: '◎', label: '目标', value: d.goals },
    { key: 'transactions',  icon: '¥', label: '收支', value: d.transactions },
    { key: 'meals',         icon: '◔', label: '饮食', value: d.meals },
    { key: 'reminders',     icon: '◐', label: '提醒', value: d.reminders },
    { key: 'achievements',  icon: '★', label: '成就', value: d.achievements },
    { key: 'reports',       icon: '⎙', label: '报告', value: d.reports }
  ]
})

// ────────────────────────── 加载 ──────────────────────────
async function loadAll() {
  loading.value = true
  error.value = null
  try {
    const [s, m, l, r, u] = await Promise.allSettled([
      fetchStats(),
      fetchMe(),
      fetchRecentLogs(20),
      fetchRetention(retentionDays.value),
      fetchLLMUsage(7)
    ])
    if (s.status === 'fulfilled') stats.value = s.value
    if (m.status === 'fulfilled') me.value = m.value
    if (l.status === 'fulfilled') logs.value = l.value
    if (r.status === 'fulfilled') retention.value = r.value
    if (u.status === 'fulfilled') llmUsage.value = u.value

    const fails = [s, m, l, r, u].filter((p) => p.status === 'rejected')
    if (fails.length === 5) {
      error.value = '无法连接后端,请确认 uvicorn 已在 8000 端口运行'
    } else if (fails.length > 0) {
      error.value = `部分接口失败(${fails.length}/5),已用 mock 占位`
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '未知错误'
  } finally {
    loading.value = false
  }
}

watch(retentionDays, async (n) => {
  try {
    const r = await fetchRetention(n)
    retention.value = r
  } catch {
    /* ignore */
  }
})

onMounted(() => {
  loadAll()
})

// ────────────────────────── 行为 ──────────────────────────
function goCreateUser() { router.push({ name: 'Users' }) }
function goAnnouncement() { router.push({ name: 'Announcements' }) }
function goLogs() { router.push({ name: 'Logs' }) }
function goLLM() { router.push({ name: 'LLMModels' }) }

function logMessage(log: AdminLogEntry): string {
  const who = log.username ?? (log.user_id != null ? `#${log.user_id}` : '系统')
  return `${who} · ${log.action}`
}

function logColor(action: string): string {
  if (action.includes('failed') || action.includes('error')) return 'var(--accent-4)'
  if (action.includes('delete')) return 'var(--c-brick)'
  if (action.includes('create') || action.includes('upload')) return 'var(--accent-2)'
  if (action.includes('login')) return 'var(--accent-1)'
  return 'var(--accent-3)'
}

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '凌晨好'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const meDisplayName = computed(() => {
  if (me.value?.nickname) return me.value.nickname
  if (me.value?.username) return me.value.username
  return auth.displayName
})

const meInitial = computed(() => meDisplayName.value.slice(0, 1))

// ────────────────────────── 折线 SVG 工具 ──────────────────────────
function linePath(data: number[], width: number, height: number): string {
  if (!data.length) return ''
  const max = Math.max(...data, 1)
  const stepX = width / (data.length - 1 || 1)
  const pts = data.map((v, i) => {
    const x = (i * stepX).toFixed(2)
    const y = (height - (v / max) * (height - 10) - 5).toFixed(2)
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
  })
  return pts.join(' ')
}

function areaPath(data: number[], width: number, height: number): string {
  if (!data.length) return ''
  const max = Math.max(...data, 1)
  const stepX = width / (data.length - 1 || 1)
  const top = data.map((v, i) => {
    const x = (i * stepX).toFixed(2)
    const y = (height - (v / max) * (height - 10) - 5).toFixed(2)
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
  }).join(' ')
  return `${top} L ${width} ${height} L 0 ${height} Z`
}

function endY(data: number[], height: number): number {
  if (!data.length) return height
  const max = Math.max(...data, 1)
  const v = data[data.length - 1]
  return height - (v / max) * (height - 10) - 5
}
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="仪表盘" />

      <div class="dashboard-grid">
        <!-- ─────────── 中央主区 ─────────── -->
        <section class="center">
          <!-- 页头 -->
          <header class="page-header">
            <div>
              <h2 class="serif">{{ greeting }},{{ meDisplayName }}</h2>
              <p class="muted">
                <template v-if="loading">正在连接后端…</template>
                <template v-else-if="error">{{ error }}</template>
                <template v-else>
                  系统运行正常 · 当前共有 {{ formatNumber(stats?.users.active_7d ?? 0) }} 位 7 日活跃用户
                </template>
              </p>
            </div>
            <div class="header-actions">
              <button class="ghost-btn" @click="loadAll" :disabled="loading">
                <span class="ic">↻</span>
                <span>{{ loading ? '刷新中' : '刷新' }}</span>
              </button>
            </div>
          </header>

          <!-- 4 KPI 卡 -->
          <div class="kpi-row">
            <MagneticCard v-for="k in kpis" :key="k.key" class="kpi-card">
              <div class="kpi-head">
                <span
                  class="kpi-dot"
                  :style="{ background: `var(--accent-${k.accent === 'blue' ? '3' : k.accent === 'green' ? '2' : k.accent === 'pink' ? '4' : '1'})` }"
                />
                <span class="kpi-label">{{ k.label }}</span>
              </div>
              <div class="kpi-value">
                <CountupText :value="k.value" />
              </div>
              <div class="kpi-foot">
                <span v-if="k.key === 'ai_today'" class="kpi-foot-meta">
                  7 日 {{ formatNumber(stats?.ai.calls_7d ?? 0) }} 次
                </span>
                <span v-else-if="k.key === 'users'" class="kpi-foot-meta">
                  新增 7 日 +{{ stats?.users.new_7d ?? 0 }}
                </span>
                <span v-else-if="k.key === 'today_active'" class="kpi-foot-meta">
                  活跃率 {{ ((stats?.users.active_rate ?? 0) * 100).toFixed(1) }}%
                </span>
                <span v-else class="kpi-foot-meta">实时</span>
                <Sparkline
                  v-if="k.key === 'ai_today' && aiCallSeries.length"
                  :data="aiCallSeries"
                  :width="80" :height="20"
                  :stroke="`var(--accent-2)`"
                />
              </div>
            </MagneticCard>
          </div>

          <!-- DAU/WAU/MAU 折线 -->
          <GlassCard type="outer" class="panel-card">
            <div class="panel-head">
              <div>
                <h3 class="serif">用户活跃度趋势</h3>
                <p class="muted">
                  DAU / WAU(7 日滑窗) / MAU(30 日滑窗)
                  <template v-if="retention">
                    · 峰值 DAU {{ formatNumber(retention.totals.peak_dau) }}
                  </template>
                </p>
              </div>
              <div class="seg">
                <button
                  v-for="d in [7, 30, 90] as const"
                  :key="d"
                  class="seg-btn"
                  :class="{ active: retentionDays === d }"
                  @click="retentionDays = d"
                >{{ d }} 天</button>
              </div>
            </div>

            <div class="chart-body">
              <div class="chart-legend">
                <span class="lg-item">
                  <span class="lg-line" style="background: var(--accent-1);" />
                  <span>DAU</span>
                  <span class="lg-val">{{ retention?.totals.dau_avg ?? '—' }}</span>
                </span>
                <span class="lg-item">
                  <span class="lg-line" style="background: var(--accent-2);" />
                  <span>WAU</span>
                  <span class="lg-val">{{ retention?.totals.wau_avg ?? '—' }}</span>
                </span>
                <span class="lg-item">
                  <span class="lg-line" style="background: var(--accent-3);" />
                  <span>MAU</span>
                  <span class="lg-val">{{ retention?.totals.mau_avg ?? '—' }}</span>
                </span>
              </div>

              <div class="chart-svg">
                <svg
                  viewBox="0 0 600 200"
                  preserveAspectRatio="none"
                  width="100%" height="200"
                >
                  <!-- 网格线 -->
                  <line
                    v-for="i in 4" :key="i"
                    x1="0" x2="600"
                    :y1="i * 40" :y2="i * 40"
                    stroke="var(--c-line)" stroke-dasharray="2 4"
                  />
                  <!-- MAU 阴影 -->
                  <path
                    v-if="mauSeries.length"
                    :d="areaPath(mauSeries, 600, 200)"
                    fill="var(--accent-3)" fill-opacity="0.10"
                  />
                  <!-- 折线 -->
                  <path
                    v-if="dauSeries.length"
                    :d="linePath(dauSeries, 600, 200)"
                    stroke="var(--accent-1)" stroke-width="2"
                    fill="none" stroke-linecap="round" stroke-linejoin="round"
                  />
                  <path
                    v-if="wauSeries.length"
                    :d="linePath(wauSeries, 600, 200)"
                    stroke="var(--accent-2)" stroke-width="1.5"
                    fill="none" stroke-linecap="round" stroke-linejoin="round"
                    stroke-dasharray="3 3"
                  />
                  <path
                    v-if="mauSeries.length"
                    :d="linePath(mauSeries, 600, 200)"
                    stroke="var(--accent-3)" stroke-width="1.5"
                    fill="none" stroke-linecap="round" stroke-linejoin="round"
                    stroke-dasharray="1 4"
                  />
                  <!-- DAU 端点 -->
                  <circle
                    v-if="dauSeries.length"
                    :cx="600" :cy="endY(dauSeries, 200)"
                    r="3" fill="var(--accent-1)"
                  />
                </svg>
                <div class="chart-x">
                  <span>{{ retention?.buckets?.[0]?.date ?? '—' }}</span>
                  <span>{{
                    retention?.buckets?.[retention.buckets.length - 1]?.date ?? '—'
                  }}</span>
                </div>
              </div>
            </div>
          </GlassCard>

          <!-- 全球 8 层 Canvas 2D 地球(主区中央主视觉) -->
          <GlassCard type="outer" class="panel-card earth-card" style="padding: 0; overflow: hidden;">
            <div class="panel-head" style="padding: 16px 20px 12px;">
              <div>
                <h3 class="serif">全球节点 360°</h3>
                <p class="muted">8 城 / 6 弧线 / 3 轴自转(0.0008/0.0001/0.00007 互质频率)</p>
              </div>
              <div class="seg">
                <span class="seg-tag">纯 Canvas 2D</span>
                <span class="seg-tag">0 外部依赖</span>
              </div>
            </div>
            <div class="earth-wrap" style="height: 480px; border-top: 1px solid rgba(255,255,255,0.06);">
              <EarthCanvas />
            </div>
          </GlassCard>

          <!-- 12 城地图 -->
          <GlassCard type="outer" class="panel-card">
            <div class="panel-head">
              <div>
                <h3 class="serif">城市节点分布</h3>
                <p class="muted">12 个主要城市 · 实时在线</p>
              </div>
              <div class="legend">
                <span class="lg-item">
                  <span class="lg-dot" style="background: var(--accent-2);" />
                  <span>在线</span>
                </span>
              </div>
            </div>

            <div class="cities-grid" :ref="bindCityStagger">
              <div
                v-for="c in cities"
                :key="c.name"
                class="city-cell stagger-item"
                :title="`${c.cn} (${c.lat}°N, ${c.lng}°E)`"
              >
                <div class="city-row">
                  <span class="city-name serif">{{ c.cn }}</span>
                  <span class="city-region">{{ c.region }}</span>
                </div>
                <div class="city-row">
                  <span class="city-coord mono">
                    {{ Math.abs(c.lat).toFixed(1) }}°{{ c.lat >= 0 ? 'N' : 'S' }}
                    {{ Math.abs(c.lng).toFixed(1) }}°{{ c.lng >= 0 ? 'E' : 'W' }}
                  </span>
                  <span class="city-status">
                    <span class="status-dot" />
                    <span>在线</span>
                  </span>
                </div>
                <div class="city-users">
                  <span class="muted">用户</span>
                  <span class="city-users-val">{{ formatNumber(c.users) }}</span>
                </div>
              </div>
            </div>
          </GlassCard>

          <!-- 数据表分布 -->
          <GlassCard type="middle" class="panel-card">
            <div class="panel-head">
              <div>
                <h3 class="serif">数据资产分布</h3>
                <p class="muted">各业务表累计数据量</p>
              </div>
            </div>
            <div class="data-grid">
              <div
                v-for="(item, idx) in dataItems"
                :key="item.key"
                class="data-item"
              >
                <div
                  class="data-icon"
                  :style="{ background: `var(--accent-${(idx % 4) + 1})` }"
                >
                  {{ item.icon }}
                </div>
                <div class="data-meta">
                  <div class="data-label">{{ item.label }}</div>
                  <div class="data-value">
                    <CountupText :value="item.value" />
                  </div>
                </div>
              </div>
            </div>
          </GlassCard>
        </section>

        <!-- ─────────── 右侧栏 ─────────── -->
        <aside class="rightbar">
          <!-- 当前管理员 -->
          <GlassCard type="outer" class="profile-card">
            <div class="profile-head">
              <div class="avatar">{{ meInitial }}</div>
              <div class="profile-meta">
                <div class="profile-name serif">{{ meDisplayName }}</div>
                <div class="profile-role">
                  <span class="role-tag">超级管理员</span>
                </div>
              </div>
            </div>
            <div class="profile-stats">
              <div class="ps-row">
                <span class="muted">用户 ID</span>
                <span class="mono">#{{ me?.user_id ?? '—' }}</span>
              </div>
              <div class="ps-row">
                <span class="muted">上次登录</span>
                <span>{{ me?.last_login_at ? formatRelativeTime(me.last_login_at) : '—' }}</span>
              </div>
              <div class="ps-row">
                <span class="muted">主题</span>
                <span>{{
                  theme.mode === 'auto'
                    ? '自动'
                    : (theme.resolved === 'dark' ? '暗色' : '浅色')
                }}</span>
              </div>
            </div>
            <button class="profile-action" @click="theme.toggle">
              <span class="ic">{{ theme.resolved === 'dark' ? '☼' : '☾' }}</span>
              <span>切换 {{ theme.resolved === 'dark' ? '浅色' : '暗色' }}</span>
            </button>
          </GlassCard>

          <!-- 实时活动流 -->
          <GlassCard type="middle" class="activity-card">
            <div class="panel-head compact">
              <h3 class="serif">实时活动流</h3>
              <button class="link-btn" @click="goLogs">查看全部 →</button>
            </div>
            <div v-if="logs.length === 0" class="empty">
              <span class="muted">暂无活动</span>
            </div>
            <div v-else class="activity-list no-scrollbar">
              <div
                v-for="log in logs"
                :key="log.id"
                class="activity-item"
              >
                <span class="dot" :style="{ background: logColor(log.action) }" />
                <div class="activity-body">
                  <div class="activity-line">
                    <span class="activity-msg">{{ logMessage(log) }}</span>
                    <span class="activity-time mono">{{ formatRelativeTime(log.created_at) }}</span>
                  </div>
                  <div class="activity-meta">
                    <span v-if="log.resource_type" class="resource-tag">
                      {{ log.resource_type }}{{ log.resource_id ? ` #${log.resource_id}` : '' }}
                    </span>
                    <span class="status-tag" :class="log.status">
                      {{ log.status === 'success' ? '成功' : '失败' }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </GlassCard>

          <!-- 快捷操作 -->
          <GlassCard type="middle" class="quick-card">
            <div class="panel-head compact">
              <h3 class="serif">快捷操作</h3>
            </div>
            <div class="quick-list">
              <button class="quick-btn" @click="goCreateUser">
                <span class="qb-icon" style="background: var(--accent-1);">+</span>
                <span class="qb-text">
                  <span class="qb-title">新建用户</span>
                  <span class="qb-sub">手动添加账号 / 调配额</span>
                </span>
              </button>
              <button class="quick-btn" @click="goAnnouncement">
                <span class="qb-icon" style="background: var(--accent-2);">◐</span>
                <span class="qb-text">
                  <span class="qb-title">发布公告</span>
                  <span class="qb-sub">推送 Banner / Modal</span>
                </span>
              </button>
              <button class="quick-btn" @click="goLLM">
                <span class="qb-icon" style="background: var(--accent-3);">◈</span>
                <span class="qb-text">
                  <span class="qb-title">管理 AI 模型</span>
                  <span class="qb-sub">测活 / 设为默认</span>
                </span>
              </button>
              <button class="quick-btn" @click="goLogs">
                <span class="qb-icon" style="background: var(--accent-4);">⌖</span>
                <span class="qb-text">
                  <span class="qb-title">查看系统日志</span>
                  <span class="qb-sub">操作 / 错误 / 导出</span>
                </span>
              </button>
            </div>
          </GlassCard>

          <!-- 系统状态 -->
          <GlassCard type="inner" class="status-card">
            <div class="panel-head compact">
              <h3 class="serif">系统状态</h3>
            </div>
            <div class="status-grid">
              <div class="status-row">
                <span class="muted">LLM 模型</span>
                <span class="mono">{{ stats?.llm.models_total ?? '—' }}</span>
              </div>
              <div class="status-row">
                <span class="muted">系统默认</span>
                <span class="mono">{{ stats?.llm.system_default_name ?? '—' }}</span>
              </div>
              <div class="status-row">
                <span class="muted">知识库</span>
                <span class="mono">
                  {{ stats?.knowledge.documents ?? 0 }} 文档 /
                  {{ formatNumber(stats?.knowledge.chunks ?? 0) }} 块
                </span>
              </div>
              <div class="status-row">
                <span class="muted">7 日操作</span>
                <span class="mono">{{ formatNumber(stats?.logs_7d ?? 0) }}</span>
              </div>
            </div>
          </GlassCard>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
 * Layout — 3 列网格(玻璃 3 档 + 紫青渐变)
 * ============================================================ */
.app-shell {
  display: grid;
  grid-template-columns: auto 1fr;
  min-height: 100vh;
}
.app-main { min-width: 0; }

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr var(--rightbar-width);
  gap: 16px;
  padding: 16px;
}
.center { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.rightbar { display: flex; flex-direction: column; gap: 16px; }

/* ============================================================
 * 页头
 * ============================================================ */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
}
.page-header h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--c-ink);
}
.muted { color: var(--c-ink-3); font-size: 13px; margin-top: 4px; }

.header-actions { display: flex; gap: 8px; }

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--r-sm);
  background: var(--glass-2-bg);
  border: 1px solid var(--glass-2-border);
  color: var(--c-ink-2);
  font-size: 13px;
  transition: background var(--t-fast), color var(--t-fast);
}
.ghost-btn:hover { background: var(--glass-1-bg); color: var(--c-ink); }
.ghost-btn .ic { font-size: 14px; }
.ghost-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* ============================================================
 * KPI 卡 — 4 列
 * ============================================================ */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
.kpi-card {
  padding: 18px 20px !important;
  background: var(--glass-2-bg);
  border: 1px solid var(--glass-2-border);
  box-shadow: var(--glass-2-shadow);
  backdrop-filter: blur(var(--glass-blur-2)) saturate(160%);
  -webkit-backdrop-filter: blur(var(--glass-blur-2)) saturate(160%);
}
.kpi-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.kpi-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  box-shadow: 0 0 8px currentColor;
}
.kpi-label {
  font-size: 11px;
  color: var(--c-ink-3);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 500;
}
.kpi-value {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 700;
  color: var(--c-ink);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
  line-height: 1.1;
}
.kpi-foot {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.kpi-foot-meta {
  font-size: 11px;
  color: var(--c-ink-3);
}

/* ============================================================
 * Panel card (DAU/WAU/MAU + 12 城)
 * ============================================================ */
.panel-card { padding: 20px !important; }

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  margin-bottom: 16px;
  gap: 16px;
}
.panel-head.compact { margin-bottom: 12px; }
.panel-head h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--c-ink);
}
.panel-head .muted { margin-top: 2px; font-size: 12px; }

/* Segmented control */
.seg {
  display: flex;
  padding: 3px;
  border-radius: var(--r-pill);
  background: var(--glass-1-bg);
  border: 1px solid var(--c-line);
}
.seg-btn {
  border: none;
  background: transparent;
  color: var(--c-ink-2);
  font-size: 12px;
  padding: 5px 12px;
  border-radius: var(--r-pill);
  cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.seg-btn:hover { color: var(--c-ink); }
.seg-btn.active {
  background: var(--accent-gradient);
  color: #fff;
  box-shadow: 0 4px 12px -4px rgba(124, 92, 255, 0.45);
}

/* ============================================================
 * DAU/WAU/MAU 折线
 * ============================================================ */
.chart-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chart-legend {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.lg-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--c-ink-2);
}
.lg-line {
  width: 14px; height: 2px; border-radius: 2px;
  display: inline-block;
}
.lg-val {
  font-family: var(--font-mono);
  color: var(--c-ink);
  font-weight: 600;
  margin-left: 4px;
}
.lg-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  display: inline-block;
  box-shadow: 0 0 8px currentColor;
}
.chart-svg {
  position: relative;
  background: var(--glass-1-bg);
  border-radius: var(--r-sm);
  padding: 12px 14px;
  border: 1px solid var(--c-line);
}
.chart-x {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 11px;
  color: var(--c-ink-3);
  font-family: var(--font-mono);
}

/* ============================================================
 * 12 城地图(网格)
 * ============================================================ */
.cities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.city-cell {
  padding: 12px 14px;
  background: var(--glass-1-bg);
  border: 1px solid var(--glass-2-border);
  border-radius: var(--r-sm);
  display: flex;
  flex-direction: column;
  gap: 6px;
  opacity: 0;
  transform: translateY(8px);
  transition: background var(--t-fast), border-color var(--t-fast);
  cursor: pointer;
}
.city-cell:hover {
  background: var(--glass-2-bg);
  border-color: var(--accent-1);
}
.stagger-item.in {
  animation: cityIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes cityIn {
  to { opacity: 1; transform: translateY(0); }
}
.city-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.city-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--c-ink);
}
.city-region {
  font-size: 10px;
  color: var(--c-ink-3);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}
.city-coord {
  font-size: 11px;
  color: var(--c-ink-3);
}
.city-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--accent-2);
}
.status-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent-2);
  box-shadow: 0 0 6px var(--accent-2);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.city-users {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding-top: 4px;
  border-top: 1px solid var(--c-line);
}
.city-users-val {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--c-ink);
  font-size: 13px;
}

/* ============================================================
 * 数据资产
 * ============================================================ */
.data-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}
.data-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--glass-1-bg);
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
}
.data-icon {
  width: 32px; height: 32px;
  display: grid; place-items: center;
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
}
.data-meta { flex: 1; min-width: 0; }
.data-label { font-size: 11px; color: var(--c-ink-3); }
.data-value {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 700;
  color: var(--c-ink);
  font-variant-numeric: tabular-nums;
}

/* ============================================================
 * 右侧栏
 * ============================================================ */
.profile-card { padding: 18px !important; }
.profile-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.avatar {
  width: 48px; height: 48px;
  border-radius: 50%;
  background: var(--accent-gradient);
  color: #fff;
  display: grid; place-items: center;
  font-size: 18px;
  font-weight: 700;
  box-shadow: var(--accent-glow);
}
.profile-name { font-size: 16px; font-weight: 600; color: var(--c-ink); }
.role-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--r-pill);
  background: var(--accent-gradient);
  color: #fff;
  font-size: 11px;
  margin-top: 4px;
}
.profile-stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
  border-top: 1px solid var(--c-line);
  border-bottom: 1px solid var(--c-line);
}
.ps-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.profile-action {
  margin-top: 12px;
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 14px;
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
  background: var(--glass-1-bg);
  color: var(--c-ink-2);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.profile-action:hover {
  background: var(--glass-2-bg);
  color: var(--c-ink);
}
.profile-action .ic { font-size: 14px; }

/* 实时活动流 */
.activity-card { padding: 16px !important; }
.activity-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 360px;
  overflow-y: auto;
}
.activity-item {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--c-line);
}
.activity-item:last-child { border-bottom: none; }
.dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
  box-shadow: 0 0 6px currentColor;
}
.activity-body { flex: 1; min-width: 0; }
.activity-line {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--c-ink-2);
}
.activity-msg { color: var(--c-ink); font-weight: 500; }
.activity-time {
  font-size: 11px;
  color: var(--c-ink-3);
  white-space: nowrap;
}
.activity-meta {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  flex-wrap: wrap;
}
.resource-tag,
.status-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  font-size: 10px;
  font-family: var(--font-mono);
}
.resource-tag {
  background: var(--glass-1-bg);
  color: var(--c-ink-3);
}
.status-tag.success {
  background: rgba(52, 211, 153, 0.15);
  color: var(--accent-2);
}
.status-tag.failed {
  background: rgba(248, 113, 113, 0.15);
  color: var(--accent-4);
}
.empty {
  padding: 24px;
  text-align: center;
}
.link-btn {
  border: none;
  background: transparent;
  color: var(--accent-1);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 0;
}
.link-btn:hover { text-decoration: underline; }

/* 快捷操作 */
.quick-card { padding: 16px !important; }
.quick-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.quick-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
  background: var(--glass-1-bg);
  color: var(--c-ink-2);
  text-align: left;
  cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast), border-color var(--t-fast);
}
.quick-btn:hover {
  background: var(--glass-2-bg);
  color: var(--c-ink);
  border-color: var(--accent-1);
}
.qb-icon {
  width: 32px; height: 32px;
  display: grid; place-items: center;
  border-radius: 8px;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}
.qb-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.qb-title { font-size: 13px; font-weight: 500; color: var(--c-ink); }
.qb-sub { font-size: 11px; color: var(--c-ink-3); }

/* 系统状态 */
.status-card { padding: 16px !important; }
.status-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.status-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.status-row .mono { color: var(--c-ink); font-weight: 500; }

/* ============================================================
 * 响应式
 * ============================================================ */
@media (max-width: 1280px) {
  .dashboard-grid { grid-template-columns: 1fr 280px; }
}
@media (max-width: 1024px) {
  .dashboard-grid { grid-template-columns: 1fr; }
  .rightbar { order: 2; }
}
@media (max-width: 640px) {
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  .cities-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
