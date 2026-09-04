<script setup lang="ts">
/**
 * InsightsView — 数据洞察 v2 (Phase 5)
 *
 * 4 张图表,纯前端 mock + SVG:
  - 散点图:用户打卡天数 vs 完成率(强正相关)
  - 柱状图:24 时段打卡人数(晚 8-10 点高峰)
  - 折线图:30 日活跃用户 + 7 日移动平均
  - 热力图:周一-周日 × 0-23 时段,密度
 *
 * 每个图表自动解读 (insight) — 基于派生统计
 */
import { ref, computed } from 'vue'
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'

// ────────────────────────── Mock 数据生成器 ──────────────────────────
/** Mulberry32 — 确定性 PRNG,刷新页面数据稳定 */
function mulberry32(seed: number) {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return (((t ^ t >>> 14) >>> 0) / 4294967296)
  }
}

const rng = mulberry32(20251231)

function gauss(mean = 0, std = 1): number {
  // Box-Muller
  const u1 = Math.max(rng(), 1e-9)
  const u2 = rng()
  return mean + std * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
}

// ────────────────────────── 1. 散点图数据 ──────────────────────────
interface ScatterPoint { days: number; completion: number }
const scatter = computed<ScatterPoint[]>(() => {
  const pts: ScatterPoint[] = []
  const N = 220
  for (let i = 0; i < N; i++) {
    const days = Math.round(rng() * 365)
    // 高频用户完成率更高,带高斯噪声
    const completion = 28 + days * 0.18 + gauss(0, 12)
    pts.push({ days, completion: Math.max(3, Math.min(98, completion)) })
  }
  return pts
})

// 线性回归 (y = slope*x + intercept)
const regression = computed(() => {
  const data = scatter.value
  const n = data.length
  const mx = data.reduce((s, p) => s + p.days, 0) / n
  const my = data.reduce((s, p) => s + p.completion, 0) / n
  let num = 0, den = 0
  for (const p of data) {
    num += (p.days - mx) * (p.completion - my)
    den += (p.days - mx) ** 2
  }
  const slope = num / den
  const intercept = my - slope * mx
  // R²
  const ssTot = data.reduce((s, p) => s + (p.completion - my) ** 2, 0)
  const ssRes = data.reduce((s, p) => {
    const yp = slope * p.days + intercept
    return s + (p.completion - yp) ** 2
  }, 0)
  const r2 = 1 - ssRes / ssTot
  return { slope, intercept, r2, mx, my }
})

// 区间均值 — 用于洞察
const bucketStats = computed(() => {
  const buckets: Record<string, { sum: number; count: number }> = {
    '低频(<30天)': { sum: 0, count: 0 },
    '中频(30-200天)': { sum: 0, count: 0 },
    '高频(>200天)': { sum: 0, count: 0 }
  }
  for (const p of scatter.value) {
    const key = p.days < 30 ? '低频(<30天)' : p.days <= 200 ? '中频(30-200天)' : '高频(>200天)'
    buckets[key].sum += p.completion
    buckets[key].count += 1
  }
  return Object.entries(buckets).map(([k, v]) => ({
    label: k,
    avg: v.count > 0 ? v.sum / v.count : 0,
    count: v.count
  }))
})

const scatterInsight = computed(() => {
  const r2 = regression.value.r2
  const high = bucketStats.value[2]
  const low = bucketStats.value[0]
  return `打卡天数与完成率呈强正相关(R² = ${r2.toFixed(2)})。高频用户(${high.count} 人)平均完成率 ${high.avg.toFixed(0)}%,低频(${low.count} 人)仅 ${low.avg.toFixed(0)}%。建议引导新用户养成前 2 周的连续打卡习惯。`
})

// ────────────────────────── 2. 柱状图数据 ──────────────────────────
interface HourBar { hour: number; count: number }
const bars = computed<HourBar[]>(() => {
  const arr: HourBar[] = []
  for (let h = 0; h < 24; h++) {
    let base = 35
    if (h >= 7 && h <= 9) base += 70      // 早高峰
    if (h >= 12 && h <= 14) base += 35     // 午高峰
    if (h >= 17 && h <= 19) base += 50     // 下班
    if (h >= 20 && h <= 22) base += 170    // 晚高峰(主要)
    if (h >= 0 && h <= 5) base -= 25       // 凌晨低谷
    base += gauss(0, 18)
    arr.push({ hour: h, count: Math.max(5, Math.round(base)) })
  }
  return arr
})

const peakHour = computed(() => {
  const max = bars.value.reduce((m, b) => (b.count > m.count ? b : m), { hour: 0, count: 0 })
  return max
})

const totalCount = computed(() => bars.value.reduce((s, b) => s + b.count, 0))
const peakShare = computed(() => {
  // 20-22 这 3 小时占比
  const peakSlice = bars.value.slice(20, 23).reduce((s, b) => s + b.count, 0)
  return peakSlice / totalCount.value
})

const barInsight = computed(() => {
  const peak = peakHour.value
  const slice3 = bars.value.slice(20, 23).reduce((s, b) => s + b.count, 0)
  const share = (slice3 / totalCount.value * 100).toFixed(0)
  return `晚间 ${peak.hour - 1}-${peak.hour + 1} 点为绝对高峰(${peak.count} 次/小时),20-22 点 3 小时合计占全天打卡 ${share}%。建议 AI 推送与提醒任务集中在 19:30-21:00 触发。`
})

// ────────────────────────── 3. 折线图数据 ──────────────────────────
const dauRaw = computed<number[]>(() => {
  const arr: number[] = []
  for (let i = 0; i < 30; i++) {
    const trend = 800 + i * 12                          // 缓增
    const wave = Math.sin(i * 0.45) * 80                // 周期
    const weekend = (i % 7 === 5 || i % 7 === 6) ? -120 : 0  // 周末回落
    const v = trend + wave + weekend + gauss(0, 60)
    arr.push(Math.max(400, Math.round(v)))
  }
  return arr
})

const dauMA = computed<number[]>(() => {
  // 7 日移动平均(中心对齐:取 i-3..i+3)
  const raw = dauRaw.value
  return raw.map((_, i) => {
    const start = Math.max(0, i - 3)
    const end = Math.min(raw.length, i + 4)
    const slice = raw.slice(start, end)
    return Math.round(slice.reduce((s, v) => s + v, 0) / slice.length)
  })
})

const dauDates = computed<string[]>(() => {
  const arr: string[] = []
  const now = new Date()
  for (let i = 29; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 24 * 3600 * 1000)
    arr.push(`${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
  }
  return arr
})

const dauDelta = computed(() => {
  const ma = dauMA.value
  if (ma.length < 14) return 0
  const recent = ma.slice(-7).reduce((s, v) => s + v, 0) / 7
  const prior = ma.slice(-14, -7).reduce((s, v) => s + v, 0) / 7
  return ((recent - prior) / prior) * 100
})

const lineInsight = computed(() => {
  const ma = dauMA.value
  const avg = Math.round(ma.reduce((s, v) => s + v, 0) / ma.length)
  const peak = Math.max(...ma)
  const delta = dauDelta.value
  const sign = delta >= 0 ? '+' : ''
  return `近 30 日 DAU 7 日均值 ${avg} 人,峰值 ${peak} 人,周环比 ${sign}${delta.toFixed(1)}%。可见周末回落 + 工作日恢复的稳定节律,趋势线整体温和上行。`
})

// ────────────────────────── 4. 热力图数据 ──────────────────────────
const heatmap = computed<number[][]>(() => {
  const matrix: number[][] = []
  for (let d = 0; d < 7; d++) {
    const row: number[] = []
    for (let h = 0; h < 24; h++) {
      let v = 8
      if (h >= 7 && h <= 9) v += 60
      if (h >= 12 && h <= 13) v += 30
      if (h >= 18 && h <= 19) v += 50
      if (h >= 20 && h <= 22) v += 100
      // 工作日 vs 周末
      const isWeekend = d === 5 || d === 6
      if (!isWeekend) {
        if (h >= 19 && h <= 22) v += 60
      } else {
        v -= Math.round(v * 0.4)
        if (h >= 10 && h <= 12) v += 30
      }
      v += gauss(0, 15)
      row.push(Math.max(0, Math.round(v)))
    }
    matrix.push(row)
  }
  return matrix
})

const heatmapMax = computed(() => {
  let max = 1
  for (const row of heatmap.value) for (const v of row) if (v > max) max = v
  return max
})

const dayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const peakCell = computed(() => {
  let best = { d: 0, h: 0, v: 0 }
  for (let d = 0; d < 7; d++) {
    for (let h = 0; h < 24; h++) {
      if (heatmap.value[d][h] > best.v) best = { d, h, v: heatmap.value[d][h] }
    }
  }
  return best
})

const heatmapInsight = computed(() => {
  const p = peakCell.value
  const weekdaySum = heatmap.value.slice(0, 5).reduce((s, r) => s + r.reduce((a, b) => a + b, 0), 0)
  const weekendSum = heatmap.value.slice(5).reduce((s, r) => s + r.reduce((a, b) => a + b, 0), 0)
  const ratio = (weekdaySum / 5) / Math.max(weekendSum / 2, 1)
  return `${dayLabels[p.d]} ${String(p.h).padStart(2, '0')}:00 段打卡密度最高(${p.v})。工作日打卡强度为周末的 ${ratio.toFixed(1)}×,核心时段集中在 20-22 点,周末向 10-12 点轻度迁移。`
})

// ────────────────────────── 视图切换 ──────────────────────────
const viewMode = ref<'all' | 'scatter' | 'bar' | 'line' | 'heatmap'>('all')

// ────────────────────────── SVG 工具 ──────────────────────────
const scatterW = { w: 560, h: 280 }
const scatterPad = { top: 20, right: 16, bottom: 28, left: 40 }

function scatterX(d: number): number {
  const inner = scatterW.w - scatterPad.left - scatterPad.right
  return scatterPad.left + (d / 365) * inner
}
function scatterY(c: number): number {
  const inner = scatterW.h - scatterPad.top - scatterPad.bottom
  return scatterPad.top + (1 - c / 100) * inner
}

// 折线 path
function linePath(data: number[], width: number, height: number, padding: { top: number; right: number; bottom: number; left: number }): string {
  if (!data.length) return ''
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom
  const stepX = innerW / (data.length - 1 || 1)
  return data.map((v, i) => {
    const x = padding.left + i * stepX
    const y = padding.top + (1 - (v - min) / range) * innerH
    return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
  }).join(' ')
}

function areaPath(data: number[], width: number, height: number, padding: { top: number; right: number; bottom: number; left: number }): string {
  if (!data.length) return ''
  const top = linePath(data, width, height, padding)
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  void innerH
  void range
  const baseY = padding.top + innerH
  return `${top} L ${padding.left + innerW} ${baseY} L ${padding.left} ${baseY} Z`
}

function endPoint(data: number[], width: number, height: number, padding: { top: number; right: number; bottom: number; left: number }): { x: number; y: number } {
  if (!data.length) return { x: 0, y: 0 }
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom
  return {
    x: padding.left + innerW,
    y: padding.top + (1 - (data[data.length - 1] - min) / range) * innerH
  }
}

const lineW = { w: 560, h: 240 }
const linePad = { top: 16, right: 16, bottom: 28, left: 40 }
const rawLineD = computed(() => linePath(dauRaw.value, lineW.w, lineW.h, linePad))
const maLineD = computed(() => linePath(dauMA.value, lineW.w, lineW.h, linePad))
const maAreaD = computed(() => areaPath(dauMA.value, lineW.w, lineW.h, linePad))
const maEnd = computed(() => endPoint(dauMA.value, lineW.w, lineW.h, linePad))

// 柱状图
const barW = { w: 560, h: 240 }
const barPad = { top: 16, right: 16, bottom: 28, left: 36 }
const barMax = computed(() => Math.max(...bars.value.map((b) => b.count)))
function barX(i: number): number {
  const innerW = barW.w - barPad.left - barPad.right
  const slotW = innerW / 24
  return barPad.left + i * slotW + slotW * 0.15
}
function barWidth(): number {
  const innerW = barW.w - barPad.left - barPad.right
  return (innerW / 24) * 0.7
}
function barY(v: number): number {
  const innerH = barW.h - barPad.top - barPad.bottom
  return barPad.top + (1 - v / barMax.value) * innerH
}
function barHeight(v: number): number {
  const innerH = barW.h - barPad.top - barPad.bottom
  return (v / barMax.value) * innerH
}

// 热力图
const heatW = { w: 720, h: 280 }
const heatPad = { top: 20, right: 16, bottom: 28, left: 40 }
function heatCellX(d: number): number {
  const innerW = heatW.w - heatPad.left - heatPad.right
  const cellW = innerW / 7
  return heatPad.left + d * cellW
}
function heatCellY(h: number): number {
  const innerH = heatW.h - heatPad.top - heatPad.bottom
  const cellH = innerH / 24
  return heatPad.top + (23 - h) * cellH
}
function heatCellSize(): { w: number; h: number } {
  const innerW = heatW.w - heatPad.left - heatPad.right
  const innerH = heatW.h - heatPad.top - heatPad.bottom
  return { w: innerW / 7 - 2, h: innerH / 24 - 1 }
}
function heatColor(v: number): string {
  const t = v / heatmapMax.value
  if (v === 0) return 'rgba(124, 92, 255, 0.04)'
  if (t < 0.25) return `rgba(124, 92, 255, ${0.15 + t * 0.6})`
  if (t < 0.6) return `rgba(124, 92, 255, ${0.4 + t * 0.4})`
  return `rgba(52, 211, 153, ${0.5 + t * 0.4})`
}

// 数值格式化
const fmtPct = (n: number) => `${n.toFixed(0)}%`
const fmtNum = (n: number) => n.toLocaleString('zh-CN')
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
              4 张可视化 · 纯前端 mock · 自动派生结论 — 接入后端后可直接替换 data source
            </p>
          </div>
          <div class="seg">
            <button
              v-for="m in [
                { key: 'all', label: '全部' },
                { key: 'scatter', label: '散点' },
                { key: 'bar', label: '时段' },
                { key: 'line', label: 'DAU' },
                { key: 'heatmap', label: '热力' }
              ]"
              :key="m.key"
              class="seg-btn"
              :class="{ active: viewMode === m.key }"
              @click="viewMode = m.key as any"
            >{{ m.label }}</button>
          </div>
        </header>

        <div class="charts-grid">
          <!-- ─────────── 散点图 ─────────── -->
          <GlassCard
            v-if="viewMode === 'all' || viewMode === 'scatter'"
            type="outer"
            class="chart-card"
          >
            <div class="chart-head">
              <div>
                <h3 class="serif">打卡天数 vs 完成率</h3>
                <p class="muted">{{ scatter.length }} 位用户 · 强正相关</p>
              </div>
              <div class="kpi-mini">
                <span class="kpi-num serif">r² = {{ regression.r2.toFixed(2) }}</span>
                <span class="kpi-sub">拟合度</span>
              </div>
            </div>

            <div class="chart-svg-wrap">
              <svg :viewBox="`0 0 ${scatterW.w} ${scatterW.h}`" preserveAspectRatio="xMidYMid meet" class="chart-svg">
                <!-- 网格 -->
                <g class="grid">
                  <line
                    v-for="y in [0, 25, 50, 75, 100]"
                    :key="y"
                    :x1="scatterPad.left" :x2="scatterW.w - scatterPad.right"
                    :y1="scatterY(y)" :y2="scatterY(y)"
                    stroke="var(--c-line)" stroke-dasharray="2 4"
                  />
                  <line
                    v-for="x in [0, 60, 120, 180, 240, 300, 365]"
                    :key="`gx-${x}`"
                    :x1="scatterX(x)" :x2="scatterX(x)"
                    :y1="scatterPad.top" :y2="scatterW.h - scatterPad.bottom"
                    stroke="var(--c-line)" stroke-dasharray="2 4"
                  />
                </g>
                <!-- 回归线 -->
                <line
                  :x1="scatterX(0)" :y1="scatterY(regression.intercept)"
                  :x2="scatterX(365)"
                  :y2="scatterY(regression.slope * 365 + regression.intercept)"
                  stroke="var(--accent-1)" stroke-width="1.6" stroke-dasharray="4 4"
                />
                <!-- 数据点 -->
                <circle
                      v-for="(p, i) in scatter" :key="i"
                      :cx="scatterX(p.days)" :cy="scatterY(p.completion)"
                      r="3.5"
                      fill="var(--accent-2)"
                      fill-opacity="0.45"
                    >
                      <title>打卡 {{ p.days }} 天 · 完成率 {{ p.completion.toFixed(0) }}%</title>
                    </circle>
                <!-- Y 轴标签 -->
                <g class="axis-labels">
                  <text v-for="y in [0, 25, 50, 75, 100]" :key="`yl-${y}`"
                        :x="scatterPad.left - 6" :y="scatterY(y) + 4"
                        text-anchor="end" class="axis-text">{{ y }}%</text>
                  <text v-for="x in [0, 60, 120, 180, 240, 300, 365]" :key="`xl-${x}`"
                        :x="scatterX(x)" :y="scatterW.h - 8"
                        text-anchor="middle" class="axis-text">{{ x }}</text>
                </g>
              </svg>
            </div>

            <div class="insight">
              <span class="insight-mark">◐</span>
              <span>{{ scatterInsight }}</span>
            </div>
          </GlassCard>

          <!-- ─────────── 柱状图 ─────────── -->
          <GlassCard
            v-if="viewMode === 'all' || viewMode === 'bar'"
            type="outer"
            class="chart-card"
          >
            <div class="chart-head">
              <div>
                <h3 class="serif">24 小时打卡分布</h3>
                <p class="muted">总打卡 {{ fmtNum(totalCount) }} 次 · 晚间高峰</p>
              </div>
              <div class="kpi-mini">
                <span class="kpi-num serif">{{ peakHour.hour }}:00</span>
                <span class="kpi-sub">峰值小时</span>
              </div>
            </div>

            <div class="chart-svg-wrap">
              <svg :viewBox="`0 0 ${barW.w} ${barW.h}`" preserveAspectRatio="xMidYMid meet" class="chart-svg">
                <!-- 网格 -->
                <g class="grid">
                  <line
                    v-for="t in 5"
                    :key="t"
                    :x1="barPad.left" :x2="barW.w - barPad.right"
                    :y1="barPad.top + ((barW.h - barPad.top - barPad.bottom) / 4) * (t - 1)"
                    :y2="barPad.top + ((barW.h - barPad.top - barPad.bottom) / 4) * (t - 1)"
                    stroke="var(--c-line)" stroke-dasharray="2 4"
                  />
                </g>
                <!-- 柱 -->
                <rect
                  v-for="(b, i) in bars" :key="i"
                  :x="barX(i)" :y="barY(b.count)"
                  :width="barWidth()" :height="barHeight(b.count)"
                  :fill="b.hour >= 20 && b.hour <= 22 ? 'var(--accent-2)' : 'var(--accent-1)'"
                  :fill-opacity="b.hour >= 20 && b.hour <= 22 ? 0.9 : 0.55"
                  rx="2"
                >
                  <title>{{ b.hour }}:00 · {{ b.count }} 次</title>
                </rect>
                <!-- Y 轴标签 -->
                <text
                  v-for="t in 5"
                  :key="`yl-${t}`"
                  :x="barPad.left - 6"
                  :y="barPad.top + ((barW.h - barPad.top - barPad.bottom) / 4) * (t - 1) + 4"
                  text-anchor="end" class="axis-text"
                >{{ Math.round((barMax / 4) * (t - 1)) }}</text>
                <!-- X 轴标签(每 4 小时一标) -->
                <text
                  v-for="h in [0, 4, 8, 12, 16, 20]"
                  :key="`xl-${h}`"
                  :x="barPad.left + (h / 24) * (barW.w - barPad.left - barPad.right)"
                  :y="barW.h - 8"
                  text-anchor="middle" class="axis-text"
                >{{ h }}</text>
              </svg>
            </div>

            <div class="insight">
              <span class="insight-mark">◐</span>
              <span>{{ barInsight }}</span>
            </div>
          </GlassCard>

          <!-- ─────────── 折线图 ─────────── -->
          <GlassCard
            v-if="viewMode === 'all' || viewMode === 'line'"
            type="outer"
            class="chart-card"
          >
            <div class="chart-head">
              <div>
                <h3 class="serif">DAU 趋势</h3>
                <p class="muted">近 30 日 · 7 日移动平均</p>
              </div>
              <div class="kpi-mini">
                <span class="kpi-num serif">{{ dauDelta >= 0 ? '+' : '' }}{{ dauDelta.toFixed(1) }}%</span>
                <span class="kpi-sub">周环比</span>
              </div>
            </div>

            <div class="chart-svg-wrap">
              <svg :viewBox="`0 0 ${lineW.w} ${lineW.h}`" preserveAspectRatio="xMidYMid meet" class="chart-svg">
                <!-- 网格 -->
                <g class="grid">
                  <line
                    v-for="t in 4"
                    :key="t"
                    :x1="linePad.left" :x2="lineW.w - linePad.right"
                    :y1="linePad.top + ((lineW.h - linePad.top - linePad.bottom) / 3) * (t - 1)"
                    :y2="linePad.top + ((lineW.h - linePad.top - linePad.bottom) / 3) * (t - 1)"
                    stroke="var(--c-line)" stroke-dasharray="2 4"
                  />
                </g>
                <!-- MA 面积 -->
                <path :d="maAreaD" fill="var(--accent-1)" fill-opacity="0.10" />
                <!-- 原始 DAU -->
                <path
                  :d="rawLineD"
                  stroke="var(--accent-3)" stroke-width="1.2"
                  fill="none" stroke-linecap="round" stroke-linejoin="round"
                  stroke-opacity="0.55"
                />
                <!-- 7 日 MA -->
                <path
                  :d="maLineD"
                  stroke="var(--accent-1)" stroke-width="2"
                  fill="none" stroke-linecap="round" stroke-linejoin="round"
                />
                <!-- 末端点 -->
                <circle :cx="maEnd.x" :cy="maEnd.y" r="3.5" fill="var(--accent-1)" />
                <!-- X 轴标签 -->
                <text
                  v-for="i in [0, 7, 14, 21, 29]"
                  :key="`xl-${i}`"
                  :x="linePad.left + (i / 29) * (lineW.w - linePad.left - linePad.right)"
                  :y="lineW.h - 8"
                  text-anchor="middle" class="axis-text"
                >{{ dauDates[i] }}</text>
              </svg>
            </div>

            <div class="legend-row">
              <span class="lg-item">
                <span class="lg-line" style="background: var(--accent-3); opacity: 0.6;" />
                <span>DAU 日值</span>
              </span>
              <span class="lg-item">
                <span class="lg-line" style="background: var(--accent-1);" />
                <span>7 日 MA</span>
              </span>
            </div>

            <div class="insight">
              <span class="insight-mark">◐</span>
              <span>{{ lineInsight }}</span>
            </div>
          </GlassCard>

          <!-- ─────────── 热力图 ─────────── -->
          <GlassCard
            v-if="viewMode === 'all' || viewMode === 'heatmap'"
            type="outer"
            class="chart-card chart-card-wide"
          >
            <div class="chart-head">
              <div>
                <h3 class="serif">打卡密度热力</h3>
                <p class="muted">周一-周日 × 0-23 时段 · 越亮越密</p>
              </div>
              <div class="kpi-mini">
                <span class="kpi-num serif">{{ dayLabels[peakCell.d] }} {{ String(peakCell.h).padStart(2, '0') }}:00</span>
                <span class="kpi-sub">峰值单元格</span>
              </div>
            </div>

            <div class="chart-svg-wrap">
              <svg :viewBox="`0 0 ${heatW.w} ${heatW.h}`" preserveAspectRatio="xMidYMid meet" class="chart-svg">
                <!-- 单元格 -->
                <g>
                  <template v-for="(row, d) in heatmap" :key="`row-${d}`">
                    <rect
                      v-for="(v, h) in row"
                      :key="`cell-${d}-${h}`"
                      :x="heatCellX(d) + 1"
                      :y="heatCellY(h)"
                      :width="heatCellSize().w"
                      :height="heatCellSize().h"
                      :fill="heatColor(v)"
                      :stroke="v === peakCell.v && d === peakCell.d && h === peakCell.h ? 'var(--accent-1)' : 'transparent'"
                      :stroke-width="v === peakCell.v && d === peakCell.d && h === peakCell.h ? 1.5 : 0"
                      rx="2"
                    >
                      <title>{{ dayLabels[d] }} {{ String(h).padStart(2, '0') }}:00 · {{ v }} 次</title>
                    </rect>
                  </template>
                </g>
                <!-- Y 轴:0/6/12/18/23 -->
                <text
                  v-for="h in [0, 6, 12, 18, 23]"
                  :key="`yl-${h}`"
                  :x="heatPad.left - 6"
                  :y="heatCellY(h) + heatCellSize().h / 2 + 4"
                  text-anchor="end" class="axis-text"
                >{{ String(h).padStart(2, '0') }}</text>
                <!-- X 轴:周一-周日 -->
                <text
                  v-for="(label, d) in dayLabels"
                  :key="`xl-${d}`"
                  :x="heatCellX(d) + heatCellSize().w / 2 + 1"
                  :y="heatW.h - 8"
                  text-anchor="middle" class="axis-text"
                >{{ label }}</text>
              </svg>
            </div>

            <div class="legend-row">
              <span class="muted">密度</span>
              <div class="heat-legend">
                <div class="heat-cell" style="background: rgba(124, 92, 255, 0.10);" />
                <div class="heat-cell" style="background: rgba(124, 92, 255, 0.30);" />
                <div class="heat-cell" style="background: rgba(124, 92, 255, 0.55);" />
                <div class="heat-cell" style="background: rgba(124, 92, 255, 0.85);" />
                <div class="heat-cell" style="background: rgba(52, 211, 153, 0.85);" />
              </div>
              <span class="muted">高</span>
            </div>

            <div class="insight">
              <span class="insight-mark">◐</span>
              <span>{{ heatmapInsight }}</span>
            </div>
          </GlassCard>
        </div>
      </section>
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

/* segmented control */
.seg {
  display: flex; padding: 3px;
  border-radius: var(--r-pill);
  background: var(--glass-1-bg);
  border: 1px solid var(--c-line);
}
.seg-btn {
  border: none; background: transparent;
  color: var(--c-ink-2); font-size: 12px;
  padding: 5px 12px; border-radius: var(--r-pill);
  cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.seg-btn:hover { color: var(--c-ink); }
.seg-btn.active {
  background: var(--accent-gradient);
  color: #fff;
  box-shadow: 0 4px 12px -4px rgba(124, 92, 255, 0.45);
}

/* ===== Charts grid ===== */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.chart-card {
  padding: 18px !important;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chart-card-wide {
  grid-column: span 2;
}

/* chart header */
.chart-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 12px;
}
.chart-head h3 { font-size: 14px; font-weight: 600; color: var(--c-ink); }
.chart-head .muted { font-size: 11px; }
.kpi-mini { text-align: right; display: flex; flex-direction: column; align-items: flex-end; }
.kpi-num {
  font-size: 18px; font-weight: 700; color: var(--c-ink);
  font-variant-numeric: tabular-nums;
}
.kpi-sub {
  font-size: 10px; color: var(--c-ink-3);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* chart svg */
.chart-svg-wrap {
  position: relative;
  width: 100%;
  background: var(--glass-1-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  padding: 8px;
}
.chart-svg { width: 100%; height: auto; display: block; }
.axis-text {
  font-size: 10px;
  fill: var(--c-ink-3);
  font-family: var(--font-mono);
}

/* legend */
.legend-row {
  display: flex; align-items: center; gap: 12px;
  font-size: 11px; color: var(--c-ink-2);
}
.lg-item { display: inline-flex; align-items: center; gap: 4px; }
.lg-line { width: 14px; height: 2px; border-radius: 2px; display: inline-block; }

/* heatmap legend */
.heat-legend { display: flex; gap: 2px; }
.heat-cell { width: 14px; height: 10px; border-radius: 2px; }

/* insight box */
.insight {
  display: flex; gap: 8px; align-items: flex-start;
  padding: 10px 12px;
  background: linear-gradient(135deg, rgba(124, 92, 255, 0.08), rgba(52, 211, 153, 0.06));
  border-radius: var(--r-sm);
  border: 1px solid var(--c-line);
  font-size: 12px; color: var(--c-ink-2);
  line-height: 1.6;
}
.insight-mark {
  color: var(--accent-1);
  font-size: 14px;
  flex-shrink: 0;
}

@media (max-width: 1024px) {
  .charts-grid { grid-template-columns: 1fr; }
  .chart-card-wide { grid-column: span 1; }
}
</style>