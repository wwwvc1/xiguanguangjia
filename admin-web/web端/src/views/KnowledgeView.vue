<script setup lang="ts">
/**
 * KnowledgeView — 知识库 (RAG) 管理
 *
 * 功能:
 *   - 文档列表 (R)
 *   - 上传 .md / .txt → 自动切块入向量库
 *   - 重索引 / 删除 / 预览原文
 *   - 搜索预览(模拟一次 RAG 检索,显示召回的 chunks)
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
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  reindexDocument,
  previewDocument,
  testKnowledgeSearch,
  type KnowledgeDoc,
  type KnowledgePreview,
  type KnowledgeSearchHit
} from '@/api/knowledge'
import { formatNumber, formatRelativeTime, truncate } from '@/utils/format'

// ─────────── state ───────────
const loading = ref(true)
const error = ref<string | null>(null)
const docs = ref<KnowledgeDoc[]>([])
const filterStatus = ref<'all' | 'indexed' | 'pending' | 'failed'>('all')
const fileInput = ref<HTMLInputElement | null>(null)
const uploadProgress = ref<number | null>(null)
const reindexingId = ref<number | null>(null)

// 预览 modal
const previewOpen = ref(false)
const previewData = ref<KnowledgePreview | null>(null)
const previewLoading = ref(false)

// 搜索面板
const searchQuery = ref('')
const searchTopK = ref(5)
const searchLoading = ref(false)
const searchHits = ref<KnowledgeSearchHit[]>([])

// 确认弹窗
const confirmOpen = ref(false)
const confirmPayload = ref<{ title: string; message: string; onConfirm: () => void; tone?: 'default' | 'danger' } | null>(null)
function askConfirm(opts: { title: string; message: string; tone?: 'default' | 'danger'; onConfirm: () => void }) {
  confirmPayload.value = { tone: 'default', ...opts }
  confirmOpen.value = true
}

// ─────────── loaders ───────────
async function loadDocs() {
  loading.value = true
  error.value = null
  try {
    docs.value = await listDocuments()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载文档失败'
  } finally {
    loading.value = false
  }
}
onMounted(loadDocs)

// ─────────── derived ───────────
const filteredDocs = computed(() => {
  if (filterStatus.value === 'all') return docs.value
  return docs.value.filter((d) => d.status === filterStatus.value)
})

const stats = computed(() => {
  const total = docs.value.length
  const indexed = docs.value.filter((d) => d.status === 'indexed').length
  const pending = docs.value.filter((d) => d.status === 'pending').length
  const failed = docs.value.filter((d) => d.status === 'failed').length
  const chunks = docs.value.reduce((s, d) => s + (d.chunk_count || 0), 0)
  return { total, indexed, pending, failed, chunks }
})

// 距离 → 相似度(用 1/(1+distance) 映射,后端给的是 distance 越小越相似)
function similarity(distance: number | null | undefined): number {
  if (distance == null) return 0
  return 1 / (1 + distance)
}

function statusLabel(s: string): string {
  return ({ indexed: '已索引', pending: '索引中', failed: '失败' } as Record<string, string>)[s] ?? s
}

// ─────────── handlers ───────────
function pickFile() {
  fileInput.value?.click()
}

async function onFile(e: Event) {
  const t = e.target as HTMLInputElement
  const f = t.files?.[0]
  if (!f) return
  uploadProgress.value = 0
  try {
    await uploadDocument(f, (p) => (uploadProgress.value = p))
    await loadDocs()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploadProgress.value = null
    if (t) t.value = ''
  }
}

async function onReindex(d: KnowledgeDoc) {
  reindexingId.value = d.id
  try {
    await reindexDocument(d.id)
    await loadDocs()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '重索引失败'
  } finally {
    reindexingId.value = null
  }
}

function onDelete(d: KnowledgeDoc) {
  askConfirm({
    title: '删除文档',
    message: `将永久删除「${d.filename}」并从向量库移除,此操作不可撤销。确认?`,
    tone: 'danger',
    onConfirm: async () => {
      try {
        await deleteDocument(d.id)
        await loadDocs()
      } catch (err: unknown) {
        error.value = err instanceof Error ? err.message : '删除失败'
      }
    }
  })
}

async function onPreview(d: KnowledgeDoc) {
  previewOpen.value = true
  previewLoading.value = true
  previewData.value = null
  try {
    previewData.value = await previewDocument(d.id, 2000)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '预览失败'
    previewOpen.value = false
  } finally {
    previewLoading.value = false
  }
}

async function onSearch() {
  if (!searchQuery.value.trim()) return
  searchLoading.value = true
  searchHits.value = []
  try {
    const r = await testKnowledgeSearch(searchQuery.value.trim(), searchTopK.value)
    searchHits.value = r.results ?? []
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '搜索失败'
  } finally {
    searchLoading.value = false
  }
}

watch(searchQuery, (v) => {
  if (!v) searchHits.value = []
})
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="知识库" />

      <section class="page">
        <header class="page-header">
          <div>
            <h2 class="serif">知识库 (RAG)</h2>
            <p class="muted">
              上传 .md / .txt 文档,自动切块后注入向量库 ·
              <span class="status-tag">共 {{ stats.total }} 份 · <span class="mono">{{ formatNumber(stats.chunks) }}</span> chunk · 已索引 {{ stats.indexed }}</span>
            </p>
          </div>
          <div class="header-actions">
            <input ref="fileInput" type="file" accept=".md,.txt" hidden @change="onFile" />
            <button class="primary-btn" @click="pickFile" :disabled="uploadProgress !== null">
              <span class="ic">↑</span>
              {{ uploadProgress !== null ? `上传 ${uploadProgress}%` : '上传文档' }}
            </button>
          </div>
        </header>

        <!-- 顶部 KPI -->
        <div class="kpi-row">
          <MagneticCard class="kpi">
            <div class="k-label">总文档</div>
            <div class="k-value mono">{{ stats.total }}</div>
          </MagneticCard>
          <MagneticCard class="kpi">
            <div class="k-label">已索引</div>
            <div class="k-value mono" style="color: var(--accent-2);">{{ stats.indexed }}</div>
          </MagneticCard>
          <MagneticCard class="kpi">
            <div class="k-label">索引中</div>
            <div class="k-value mono" style="color: var(--accent-1);">{{ stats.pending }}</div>
          </MagneticCard>
          <MagneticCard class="kpi">
            <div class="k-label">失败</div>
            <div class="k-value mono" style="color: var(--state-error);">{{ stats.failed }}</div>
          </MagneticCard>
          <MagneticCard class="kpi">
            <div class="k-label">Chunk 总数</div>
            <div class="k-value mono">{{ formatNumber(stats.chunks) }}</div>
          </MagneticCard>
        </div>

        <!-- 搜索预览 -->
        <GlassCard type="outer" class="search-card">
          <div class="panel-head">
            <div>
              <h3 class="serif">RAG 搜索预览</h3>
              <p class="muted">输入查询词,模拟一次向量检索,显示召回的 chunk</p>
            </div>
            <div class="search-controls">
              <label class="inline">
                <span class="muted sm">Top-K</span>
                <select v-model.number="searchTopK" class="k-select">
                  <option v-for="k in [3, 5, 8, 10]" :key="k" :value="k">{{ k }}</option>
                </select>
              </label>
              <button class="primary-btn" :disabled="!searchQuery.trim() || searchLoading" @click="onSearch">
                {{ searchLoading ? '检索中…' : '检索' }}
              </button>
            </div>
          </div>
          <GlassInput
            v-model="searchQuery"
            placeholder="试试:如何记录饮食 / 早起的好处 / 收支统计…"
            @keyup.enter="onSearch"
          />
          <div v-if="searchLoading" class="loading pad">检索中…</div>
          <div v-else-if="searchHits.length === 0 && searchQuery" class="muted tip">
            未命中任何 chunk,试试更短的关键词
          </div>
          <div v-else-if="searchHits.length === 0" class="muted tip">输入查询词开始检索</div>
          <div v-else class="hit-list">
            <div v-for="(hit, i) in searchHits" :key="i" class="hit">
              <div class="hit-head">
                <span class="rank mono">#{{ i + 1 }}</span>
                <span class="filename">
                  <span class="ic">◊</span>
                  {{ hit.filename ?? '未知文档' }}
                  <span v-if="hit.doc_id != null" class="muted sm">doc#{{ hit.doc_id }}</span>
                </span>
                <span class="sim mono">
                  相似度 {{ (similarity(hit.distance) * 100).toFixed(1) }}%
                </span>
              </div>
              <div class="hit-bar">
                <span
                  class="sim-bar"
                  :style="{
                    width: similarity(hit.distance) * 100 + '%',
                    background: similarity(hit.distance) > 0.7 ? 'var(--accent-2)' :
                                similarity(hit.distance) > 0.5 ? 'var(--accent-1)' : 'var(--accent-3)'
                  }"
                />
              </div>
              <pre class="hit-text">{{ truncate(hit.text, 400) }}</pre>
            </div>
          </div>
        </GlassCard>

        <!-- 文档列表 -->
        <div class="toolbar">
          <div class="left-tools">
            <div class="seg">
              <button
                v-for="f in (['all', 'indexed', 'pending', 'failed'] as const)"
                :key="f"
                class="seg-btn"
                :class="{ active: filterStatus === f }"
                @click="filterStatus = f"
              >{{ f === 'all' ? '全部' : statusLabel(f) }}</button>
            </div>
            <span class="muted count">显示 {{ filteredDocs.length }} 份</span>
          </div>
          <button class="ghost-btn" @click="loadDocs" :disabled="loading">
            <span class="ic">↻</span>{{ loading ? '刷新中' : '刷新' }}
          </button>
        </div>

        <GlassCard type="middle" class="table-card">
          <div v-if="loading && docs.length === 0" class="loading pad">加载中…</div>
          <div v-else-if="filteredDocs.length === 0">
            <EmptyState
              icon="◊"
              :title="filterStatus === 'all' ? '还没有任何文档' : `没有${statusLabel(filterStatus)}的文档`"
              hint="点击右上「上传文档」开始添加 .md / .txt 业务规则"
            />
          </div>
          <table v-else class="t">
            <thead>
              <tr>
                <th>文件名</th>
                <th>状态</th>
                <th>Chunk 数</th>
                <th>上传时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in filteredDocs" :key="d.id">
                <td>
                  <div class="file-cell">
                    <span class="file-icon">◊</span>
                    <div>
                      <div class="file-name">{{ d.filename }}</div>
                      <div v-if="d.error_msg" class="err-line">{{ d.error_msg }}</div>
                      <div v-else class="muted sm">#{{ d.id }} · 上传者 {{ d.uploaded_by }}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <span class="tag" :class="`tag-${d.status}`">
                    <span v-if="d.status === 'pending'" class="spin">◌</span>
                    {{ statusLabel(d.status) }}
                  </span>
                </td>
                <td class="mono">{{ d.chunk_count || 0 }}</td>
                <td>
                  <div>{{ d.created_at ? formatRelativeTime(d.created_at) : '—' }}</div>
                  <div class="muted sm">{{ d.created_at ? d.created_at.slice(0, 10) : '' }}</div>
                </td>
                <td>
                  <div class="ops">
                    <button class="op-btn" @click="onPreview(d)">预览</button>
                    <button
                      class="op-btn"
                      :disabled="reindexingId === d.id"
                      @click="onReindex(d)"
                    >{{ reindexingId === d.id ? '重索中…' : '重索引' }}</button>
                    <button class="op-btn danger" @click="onDelete(d)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </GlassCard>
      </section>
    </div>

    <!-- 预览 modal -->
    <GlassModal
      :open="previewOpen"
      :title="previewData?.filename ?? '预览'"
      width="640px"
      @update:open="(v) => (previewOpen = v)"
    >
      <div v-if="previewLoading" class="loading pad">加载中…</div>
      <pre v-else-if="previewData" class="preview-text">{{ previewData.content }}</pre>
      <div v-if="previewData?.truncated" class="muted sm tip">(已截断,仅显示前 {{ previewData.content.length }} 字符)</div>
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
.tip { margin-top: 8px; }
.mono { font-family: var(--font-mono); }

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
  transition: background var(--t-fast), color var(--t-fast);
}
.ghost-btn:hover:not(:disabled) { background: var(--glass-1-bg); color: var(--c-ink); }
.ghost-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* KPI */
.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.kpi { padding: 16px 18px !important; }
.k-label { font-size: 11px; color: var(--c-ink-3); text-transform: uppercase; letter-spacing: 0.06em; }
.k-value { font-family: var(--font-serif); font-size: 24px; font-weight: 700; color: var(--c-ink); margin-top: 4px; font-variant-numeric: tabular-nums; }

/* 搜索 */
.search-card { padding: 20px !important; }
.panel-head { display: flex; justify-content: space-between; align-items: end; margin-bottom: 12px; gap: 12px; flex-wrap: wrap; }
.panel-head h3 { font-size: 15px; font-weight: 600; color: var(--c-ink); }
.search-controls { display: flex; align-items: center; gap: 8px; }
.inline { display: inline-flex; align-items: center; gap: 6px; }
.k-select {
  padding: 4px 8px; border-radius: var(--r-sm);
  background: var(--glass-3-bg); border: 1px solid var(--c-line);
  color: var(--c-ink); font-size: 12px; font-family: var(--font-mono);
  outline: none; cursor: pointer;
}

.hit-list { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; max-height: 400px; overflow-y: auto; }
.hit {
  padding: 12px 14px; background: var(--glass-1-bg);
  border: 1px solid var(--c-line); border-radius: var(--r-sm);
  display: flex; flex-direction: column; gap: 8px;
}
.hit-head { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.rank {
  background: var(--accent-gradient); color: #fff;
  width: 24px; height: 24px; border-radius: 50%;
  display: grid; place-items: center; font-size: 11px; font-weight: 700;
}
.filename { display: inline-flex; align-items: center; gap: 4px; color: var(--c-ink-2); font-size: 12px; }
.filename .ic { color: var(--accent-1); }
.sim { margin-left: auto; font-size: 11px; color: var(--c-ink); }
.hit-bar { height: 3px; background: var(--c-line); border-radius: 999px; overflow: hidden; }
.sim-bar { display: block; height: 100%; border-radius: 999px; transition: width 0.4s ease; }
.hit-text {
  margin: 0; padding: 0;
  font-family: 'Georgia', 'PingFang SC', serif;
  font-size: 12px; line-height: 1.7;
  color: var(--c-ink-2);
  white-space: pre-wrap; word-break: break-word;
  max-height: 200px; overflow-y: auto;
}

/* toolbar + table */
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.left-tools { display: flex; align-items: center; gap: 12px; }
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

.table-card { padding: 0 !important; overflow: hidden; }
.loading { text-align: center; color: var(--c-ink-3); }
.loading.pad { padding: 60px 16px; }
.t { width: 100%; border-collapse: collapse; }
.t th, .t td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--c-line); font-size: 13px; color: var(--c-ink); vertical-align: middle; }
.t th { font-weight: 600; font-size: 11px; color: var(--c-ink-3); text-transform: uppercase; letter-spacing: 0.06em; background: var(--glass-1-bg); }
.t tbody tr:hover { background: var(--glass-1-bg); }
.t tbody tr:last-child td { border-bottom: none; }

.file-cell { display: flex; align-items: flex-start; gap: 10px; }
.file-icon { font-size: 18px; color: var(--accent-1); }
.file-name { font-weight: 600; }
.err-line { font-size: 11px; color: var(--state-error); margin-top: 2px; }

.tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: var(--r-pill);
  font-size: 11px; border: 1px solid transparent;
}
.tag-indexed { background: rgba(52, 211, 153, 0.15); color: var(--accent-2); }
.tag-pending { background: rgba(124, 92, 255, 0.15); color: var(--accent-1); }
.tag-failed { background: rgba(248, 113, 113, 0.15); color: var(--state-error); }
.spin { display: inline-block; animation: spin 1.2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

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

/* preview */
.preview-text {
  margin: 0; padding: 12px 14px;
  font-family: 'Georgia', 'PingFang SC', serif;
  font-size: 12px; line-height: 1.7;
  color: var(--c-ink-2);
  background: var(--glass-1-bg);
  border-radius: var(--r-sm); border: 1px solid var(--c-line);
  max-height: 60vh; overflow-y: auto;
  white-space: pre-wrap; word-break: break-word;
}

@media (max-width: 1100px) { .kpi-row { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 720px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } .t th, .t td { padding: 10px 8px; } }
</style>
