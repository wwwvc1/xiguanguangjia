<script setup lang="ts">
/**
 * InsightsView — 数据洞察(真实数据版)
 *
 * 4 张图全部从后端 /api/admin/insights/* 拿真实数据:
 *   - 散点图:用户活跃天数 vs 完成率(可点)
 *   - 折线图:每日活跃用户(checkin)
 *   - 柱状图:24 时段打卡
 *   - 热力图:周×小时
 *
 * 顶部"AI 运营建议"按钮 → 系统默认模型解读
 */
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import { insightsApi, type ScatterPoint, type TrendPoint, type HourlyPoint, type HeatmapCell, type InsightOverview } from '@/api/insights'
import { formatNumber } from '@/utils/format'

const router = useRouter()

// ─────────── state ───────────
const loading = ref(false)
const overview = ref<InsightOverview | null>(null)
const scatter = ref<ScatterPoint[]>([])
const trend = ref<TrendPoint[]>([])
const hourly = ref<HourlyPoint[]>([])
const heatmap = ref<HeatmapCell[]>([])

const aiOpen = ref(false)
const aiLoading = ref(false)
const aiAdvice = ref('')

// ─────────── derived ───────────
// 散点回归
const regression = computed(() => {
  const data = scatter.value
  if (data.length < 2) return { slope: 0, intercept: 0, r2: 0 }
  const n = data.length
  const mx = data.reduce((s, p) => s + p.days, 0) / n
  const my = data.reduce((s, p) => s + p.completion, 0) / n
  let num = 0, den = 0
  for (const p of data) {
    num += (p.days - mx) * (p.completion - my)
    den += (p.days - mx) ** 2
  }
  const slope = den === 0 ? 0 : num / den
  const intercept = my - slope * mx
  // R²
  const ssTot = data.reduce((s, p) => s + (p.completion - my) ** 2, 0)
  const ssRes = data.reduce((s, p) => s + (p.completion - (slope * p.days + intercept)) ** 2, 0)
  const r2 = ssTot === 0 ? 0 : 1 - ssRes / ssTot
  return { slope, intercept, r2 }
})

// ─────────── load ───────────
async function loadAll() {
  loading.value = true
  try {
    const [ov, sc, tr, hr, hm] = await Promise.all([
      insightsApi.overview(),
      insightsApi.scatter(30),
      insightsApi.trend(30),
      insightsApi.hourly(),
      insightsApi.heatmap()
    ])
    overview.value = ov
    scatter.value = sc.points
    trend.value = tr.series
    hourly.value = hr.buckets
    heatmap.value = hm.cells
  } catch (e) {
    console.error('加载数据洞察失败:', e)
  } finally {
    loading.value = false
  }
}

async function onAiSummary() {
  aiOpen.value = true
  aiLoading.value = true
  aiAdvice.value = ''
  try {
    const r = await insightsApi.aiSummary()
    aiAdvice.value = r.ai_advice || '暂无建议'
  } catch (e: any) {
    aiAdvice.value = `AI 调用失败: ${e?.response?.data?.detail || e?.message || e}`
  } finally {
    aiLoading.value = false
  }
}

function onScatterClick(p: ScatterPoint) {
  // 跳到该用户的 todo 数据视图(沿用 DataAssetView 复用)
  router.push({ name: 'DataAsset', params: { type: 'todos' }, query: { user_id: p.user_id } })
}

// ─────────── chart helpers ───────────
const HEATMAP_DOWS = ['日', '一', '二', '三', '四', '五', '六']

const scatterChart = computed(() => {
  const data = scatter.value
  if (!data.length) return null
  const W = 600, H = 320, pad = 40
  const xs = data.map((d) => d.days)
  const ys = data.map((d) => d.completion)
  const xMax = Math.max(...xs, 1)
  const yMax = 100
  const xScale = (x: number) => pad + (x / xMax) * (W - pad * 2)
  const yScale = (y: number) => H - pad - (y / yMax) * (H - pad * 2)
  const reg = regression.value
  return {
    W, H, pad, xMax, yMax,
    points: data.map((p) => ({ ...p, cx: xScale(p.days), cy: yScale(p.completion) })),
    line: {
      x1: xScale(0), y1: yScale(reg.intercept),
      x2: xScale(xMax), y2: yScale(reg.slope * xMax + reg.intercept)
    },
    xScale, yScale
  }
})

const trendChart = computed(() => {
  const data = trend.value
  if (!data.length) return null
  const W = 600, H = 240, pad = 36
  const xs = data.map((_, i) => i)
  const ys = data.map((d) => d.value)
  const yMax = Math.max(...ys, 5) * 1.1
  const xScale = (x: number) => pad + (x / Math.max(xs.length - 1, 1)) * (W - pad * 2)
  const yScale = (y: number) => H - pad - (y / yMax) * (H - pad * 2)
  const path = data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(d.value)}`).join(' ')
  return { W, H, pad, yMax, data, path, xScale, yScale }
})

const hourlyChart = computed(() => {
  const data = hourly.value
  if (!data.length) return null
  const W = 600, H = 220, pad = 30
  const yMax = Math.max(...data.map((d) => d.value), 1)
  const bw = (W - pad * 2) / data.length
  const yScale = (y: number) => H - pad - (y / yMax) * (H - pad * 2)
  return { W, H, pad, yMax, data, bw, yScale }
})

const heatmapChart = computed(() => {
  const data = heatmap.value
  if (!data.length) return null
  const W = 560, H = 200, pad = 30
  const cellW = (W - pad * 2) / 24
  const cellH = (H - pad * 2) / 7
  const vMax = Math.max(...data.map((d) => d.value), 1)
  const map = new Map(data.map((d) => [`${d.dow}-${d.hour}`, d.value]))
  // 扁平化 7×24 = 168 个格子,单层 v-for
  const cells: { dow: number; hour: number; value: number; x: number; y: number }[] = []
  for (let di = 0; di < 7; di++) {
    for (let h = 0; h < 24; h++) {
      cells.push({
        dow: di, hour: h,
        value: map.get(`${di}-${h}`) || 0,
        x: pad + h * cellW,
        y: pad + di * cellH
      })
    }
  }
  return { W, H, pad, cellW, cellH, vMax, cells }
})

onMounted(loadAll)
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="数据洞察" />

      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">数据洞察</h2>
            <p class="muted">
              全部数据来自真实业务表 · {{ overview ? `共 ${overview.total_users} 个用户` : '加载中…' }}
            </p>
          </div>
          <div class="header-actions">
            <button class="ghost-btn" @click="loadAll" :disabled="loading">
              <span class="ic">↻</span>{{ loading ? '刷新中' : '刷新' }}
            </button>
            <button class="primary-btn" @click="onAiSummary" :disabled="aiLoading">
              <span class="ic">✨</span>AI 运营建议
            </button>
          </div>
        </header>

        <!-- 总览 KPI(从 overview 拿) -->
        <div class="kpi-row" v-if="overview">
          <GlassCard type="middle" class="kpi">
            <div class="k-label">注册用户</div>
            <div class="k-value mono">{{ overview.total_users }}</div>
          </GlassCard>
          <GlassCard type="middle" class="kpi">
            <div class="k-label">7 日活跃</div>
            <div class="k-value mono" style="color: var(--accent-2)">
              {{ overview.dau_7d }}
            </div>
          </GlassCard>
          <GlassCard type="middle" class="kpi">
            <div class="k-label">活跃率</div>
            <div class="k-value mono">{{ overview.active_rate_7d }}%</div>
          </GlassCard>
          <GlassCard type="middle" class="kpi">
            <div class="k-label">近 30 天新增</div>
            <div class="k-value mono">{{ overview.new_users_30d }}</div>
          </GlassCard>
          <GlassCard type="middle" class="kpi">
            <div class="k-label">7 日 AI 调用</div>
            <div class="k-value mono" style="color: var(--accent-1)">
              {{ overview.data_totals.ai_calls || 0 }}
            </div>
          </GlassCard>
        </div>

        <!-- 4 张图 -->
        <div class="chart-grid">
          <GlassCard type="middle" class="chart-card">
            <div class="chart-head">
              <h3 class="serif">① 散点:用户活跃天数 vs 完成率</h3>
              <span class="muted sm">基于最近 30 天真实数据 · 点可下钻</span>
            </div>
            <div v-if="!scatterChart" class="loading pad">加载中…</div>
            <svg v-else :viewBox="`0 0 ${scatterChart.W} ${scatterChart.H}`" class="svg-chart">
              <line :x1="scatterChart.pad" :y1="scatterChart.H - scatterChart.pad" :x2="scatterChart.W - scatterChart.pad" :y2="scatterChart.H - scatterChart.pad" stroke="var(--c-line)" />
              <line :x1="scatterChart.pad" :y1="scatterChart.pad" :x2="scatterChart.pad" :y2="scatterChart.H - scatterChart.pad" stroke="var(--c-line)" />
              <line :x1="scatterChart.line.x1" :y1="scatterChart.line.y1" :x2="scatterChart.line.x2" :y2="scatterChart.line.y2" stroke="var(--accent-1)" stroke-dasharray="4 3" />
              <circle
                v-for="(p, i) in scatterChart.points" :key="i"
                :cx="p.cx" :cy="p.cy" r="3"
                fill="var(--accent-2)" opacity="0.7"
                @click="onScatterClick(p)" style="cursor: pointer"
              >
                <title>{{ p.username }} · 活跃 {{ p.days }} 天 · 完成率 {{ p.completion }}%</title>
              </circle>
              <text v-for="i in 5" :key="`y${i}`"
                :x="scatterChart.pad - 6" :y="scatterChart.H - scatterChart.pad - (i - 1) * (scatterChart.H - scatterChart.pad * 2) / 4"
                font-size="9" fill="var(--c-ink-3)" text-anchor="end">
                {{ Math.round((i - 1) * 25) }}%
              </text>
              <text v-for="i in 5" :key="`x${i}`"
                :x="scatterChart.pad + (i - 1) * (scatterChart.W - scatterChart.pad * 2) / 4"
                :y="scatterChart.H - scatterChart.pad + 14"
                font-size="9" fill="var(--c-ink-3)" text-anchor="middle">
                {{ Math.round((i - 1) * scatterChart.xMax / 4) }}d
              </text>
            </svg>
            <div class="muted sm insight">
              回归斜率 <span class="mono">{{ regression.slope.toFixed(2) }}</span> / 100% 完成率 · R² = <span class="mono">{{ regression.r2.toFixed(3) }}</span>
            </div>
          </GlassCard>

          <GlassCard type="middle" class="chart-card">
            <div class="chart-head">
              <h3 class="serif">② 折线:30 日活跃用户(checkin)</h3>
              <span class="muted sm">每日独立用户数</span>
            </div>
            <div v-if="!trendChart" class="loading pad">加载中…</div>
            <svg v-else :viewBox="`0 0 ${trendChart.W} ${trendChart.H}`" class="svg-chart">
              <line :x1="trendChart.pad" :y1="trendChart.H - trendChart.pad" :x2="trendChart.W - trendChart.pad" :y2="trendChart.H - trendChart.pad" stroke="var(--c-line)" />
              <path :d="trendChart.path" fill="none" stroke="var(--accent-2)" stroke-width="1.5" />
            </svg>
            <div class="muted sm insight">
              区间 <span class="mono">{{ trendChart.yMax.toFixed(0) }}</span> 用户
            </div>
          </GlassCard>

          <GlassCard type="middle" class="chart-card">
            <div class="chart-head">
              <h3 class="serif">③ 柱状:24 时段打卡人数</h3>
              <span class="muted sm">过去 30 天</span>
            </div>
            <div v-if="!hourlyChart" class="loading pad">加载中…</div>
            <svg v-else :viewBox="`0 0 ${hourlyChart.W} ${hourlyChart.H}`" class="svg-chart">
              <line :x1="hourlyChart.pad" :y1="hourlyChart.H - hourlyChart.pad" :x2="hourlyChart.W - hourlyChart.pad" :y2="hourlyChart.H - hourlyChart.pad" stroke="var(--c-line)" />
              <rect
                v-for="(b, i) in hourlyChart.data" :key="i"
                :x="hourlyChart.pad + i * hourlyChart.bw"
                :y="hourlyChart.yScale(b.value)"
                :width="hourlyChart.bw * 0.8"
                :height="hourlyChart.H - hourlyChart.pad - hourlyChart.yScale(b.value)"
                fill="var(--accent-1)" opacity="0.7"
              />
              <text v-for="i in hourlyChart.data" :key="`l${i.hour}`"
                v-show="i % 3 === 0"
                :x="hourlyChart.pad + i * hourlyChart.bw + hourlyChart.bw * 0.4"
                :y="hourlyChart.H - hourlyChart.pad + 14"
                font-size="9" fill="var(--c-ink-3)" text-anchor="middle">
                {{ i.hour }}h
              </text>
            </svg>
            <div class="muted sm insight">
              峰值时段:<span class="mono">{{ Math.max(...hourlyChart.data.map(d => d.value)) }}</span> 次
            </div>
          </GlassCard>

          <GlassCard type="middle" class="chart-card">
            <div class="chart-head">
              <h3 class="serif">④ 热力:周×小时 活跃度</h3>
              <span class="muted sm">过去 30 天,格子越亮越活跃</span>
            </div>
            <div v-if="!heatmapChart" class="loading pad">加载中…</div>
            <svg v-else :viewBox="`0 0 ${heatmapChart.W} ${heatmapChart.H}`" class="svg-chart">
              <rect
                v-for="(c, i) in heatmapChart.cells" :key="`c${i}`"
                :x="c.x" :y="c.y"
                :width="heatmapChart.cellW - 1"
                :height="heatmapChart.cellH - 1"
                :fill="`rgba(124, 92, 255, ${(c.value / heatmapChart.vMax) * 0.9 + 0.05})`"
              >
                <title>{{ HEATMAP_DOWS[c.dow] }} {{ c.hour }}时 · {{ c.value }} 次</title>
              </rect>
              <text v-for="(label, di) in HEATMAP_DOWS" :key="`dow${di}`"
                :x="heatmapChart.pad - 4"
                :y="heatmapChart.pad + di * heatmapChart.cellH + heatmapChart.cellH * 0.6"
                font-size="9" fill="var(--c-ink-3)" text-anchor="end">
                {{ label }}
              </text>
            </svg>
          </GlassCard>
        </div>
      </section>

      <!-- AI 运营建议 modal -->
      <div v-if="aiOpen" class="modal-mask" @click.self="aiOpen = false">
        <div class="modal">
          <div class="modal-head">
            <h3 class="serif">✨ AI 运营建议(系统默认模型)</h3>
            <button class="link" @click="aiOpen = false">✕</button>
          </div>
          <div class="modal-body">
            <p v-if="overview" class="muted sm">
              依据:用户 {{ overview.total_users }} · 7 日活跃 {{ overview.dau_7d }} · AI 调用 {{ overview.data_totals.ai_calls || 0 }}
            </p>
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
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--c-ink); }
.muted { color: var(--c-ink-3); font-size: 13px; margin-top: 4px; }
.sm { font-size: 11px; margin: 0; }
.mono { font-family: var(--font-mono); }
.serif { font-family: var(--font-serif); }

.header-actions { display: flex; gap: 8px; }
.primary-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: var(--r-sm);
  background: var(--accent-gradient); color: #fff;
  border: none; font-size: 13px; font-weight: 500; cursor: pointer;
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

.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.kpi { padding: 14px; text-align: center; }
.k-label { font-size: 11px; color: var(--c-ink-3); margin-bottom: 6px; }
.k-value { font-size: 22px; font-weight: 700; color: var(--c-ink); }

.chart-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.chart-card { padding: 16px; }
.chart-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; gap: 8px; flex-wrap: wrap; }
.chart-head h3 { font-size: 14px; font-weight: 600; color: var(--c-ink); }

.svg-chart { width: 100%; height: auto; max-height: 320px; }

.insight { margin-top: 8px; }

.loading.pad { padding: 60px; text-align: center; color: var(--c-ink-3); }

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
  margin: 0;
}
.link { background: none; border: none; color: var(--c-ink-2); cursor: pointer; font-size: 14px; }
</style>
