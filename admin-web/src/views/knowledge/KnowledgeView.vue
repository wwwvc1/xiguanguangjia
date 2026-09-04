<template>
  <div class="knowledge-page">
    <h2 class="page-title">知识库管理</h2>

    <a-card :bordered="false" class="filter-card">
      <a-space wrap>
        <a-segmented
          v-model:value="filterStatus"
          :options="[
            { label: '全部', value: 'all' },
            { label: '已索引', value: 'indexed' },
            { label: '处理中', value: 'pending' },
            { label: '失败', value: 'failed' }
          ]"
          @change="loadDocuments"
        />
        <a-button @click="loadDocuments">刷新</a-button>
        <a-upload
          :before-upload="handleBeforeUpload"
          :show-upload-list="false"
          :accept="'.md,.txt'"
        >
          <a-button type="primary" :loading="uploading">
            <template #icon><upload-outlined /></template>
            上传文档
          </a-button>
        </a-upload>
        <a-button @click="openTestSearchModal">
          <template #icon><search-outlined /></template>
          测试检索
        </a-button>
      </a-space>
    </a-card>

    <a-card :bordered="false">
      <a-table
        :columns="columns"
        :data-source="filteredDocuments"
        :loading="loading"
        :pagination="{ pageSize: 10 }"
        row-key="id"
        :scroll="{ x: 800 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'filename'">
            <a-space>
              <file-text-outlined />
              <span>{{ record.filename }}</span>
            </a-space>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
            <a-tooltip v-if="record.error_msg" :title="record.error_msg">
              <exclamation-circle-outlined style="color: #faad14; margin-left: 4px" />
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'actions'">
            <a-space wrap>
              <a-button size="small" type="link" @click="openPreview(record)">预览</a-button>
              <a-button size="small" type="link" @click="handleReindex(record)">重新索引</a-button>
              <a-popconfirm
                title="确认删除该文档?(向量数据将一并清除)"
                @confirm="handleDelete(record)"
              >
                <a-button size="small" type="link" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
        <template #emptyText>
          <a-empty description="还没有文档,上传一个开始" />
        </template>
      </a-table>
    </a-card>

    <!-- 预览弹窗 -->
    <a-modal
      v-model:open="previewOpen"
      :title="`预览 - ${previewDoc?.filename || ''}`"
      :width="isMobile ? '95%' : 700"
      :footer="null"
    >
      <pre class="preview-content">{{ previewContent }}</pre>
      <a-alert
        v-if="previewTruncated"
        type="info"
        message="已截断显示前 2000 字符,完整内容请下载源文件"
        show-icon
        style="margin-top: 12px"
      />
    </a-modal>

    <!-- 测试检索弹窗 -->
    <a-modal
      v-model:open="testOpen"
      title="测试 RAG 检索"
      :width="isMobile ? '95%' : 700"
      :footer="null"
    >
      <a-space direction="vertical" style="width: 100%">
        <a-input-search
          v-model:value="testQuery"
          placeholder="输入查询语句"
          enter-button="检索"
          @search="runTestSearch"
        />
        <a-spin :spinning="testLoading">
          <a-empty v-if="!testResults.length && !testLoading" description="输入查询后点击检索" />
          <div v-else>
            <div v-for="(r, i) in testResults" :key="i" class="test-result-item">
              <a-space style="margin-bottom: 6px">
                <a-tag color="blue">{{ r.filename || 'unknown' }}</a-tag>
                <a-tag v-if="r.distance !== null" color="default">
                  距离: {{ r.distance?.toFixed(4) }}
                </a-tag>
              </a-space>
              <pre class="test-text">{{ r.text }}</pre>
            </div>
          </div>
        </a-spin>
      </a-space>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  UploadOutlined,
  FileTextOutlined,
  SearchOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons-vue'
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  reindexDocument,
  previewDocument,
  testSearch
} from '../../api/knowledge'

const loading = ref(false)
const uploading = ref(false)
const documents = ref([])
const filterStatus = ref('all')

const columns = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  { title: '文件名', dataIndex: 'filename' },
  { title: 'Chunks', dataIndex: 'chunk_count', width: 80 },
  { title: '状态', dataIndex: 'status', width: 120 },
  { title: '上传时间', dataIndex: 'created_at', width: 170 },
  { title: '操作', dataIndex: 'actions', width: 220, fixed: 'right' }
]

const filteredDocuments = computed(() => {
  if (filterStatus.value === 'all') return documents.value
  return documents.value.filter((d) => d.status === filterStatus.value)
})

function statusColor(s) {
  return { indexed: 'green', pending: 'blue', failed: 'red' }[s] || 'default'
}
function statusLabel(s) {
  return { indexed: '已索引', pending: '处理中', failed: '失败' }[s] || s
}

async function loadDocuments() {
  loading.value = true
  try {
    const d = await listDocuments()
    documents.value = d.documents || []
  } catch (e) {
    message.error('加载失败:' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function handleBeforeUpload(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!['.md', '.txt'].includes(ext)) {
    message.error('只支持 .md / .txt 文件')
    return false
  }
  if (file.size > 5 * 1024 * 1024) {
    message.error('文件超过 5MB')
    return false
  }
  uploadFile(file)
  return false  // 阻止默认上传
}

async function uploadFile(file) {
  uploading.value = true
  try {
    const result = await uploadDocument(file)
    message.success(`上传成功,生成 ${result.chunk_count} 个 chunks`)
    loadDocuments()
  } catch (e) {
    message.error('上传失败:' + (e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
  }
}

async function handleDelete(record) {
  try {
    await deleteDocument(record.id)
    message.success('已删除')
    loadDocuments()
  } catch (e) {
    message.error('删除失败:' + (e.response?.data?.detail || e.message))
  }
}

async function handleReindex(record) {
  message.loading('正在重新索引...', 0)
  try {
    await reindexDocument(record.id)
    message.destroy()
    message.success('重新索引完成')
    loadDocuments()
  } catch (e) {
    message.destroy()
    message.error('失败:' + (e.response?.data?.detail || e.message))
  }
}

// 预览
const previewOpen = ref(false)
const previewDoc = ref(null)
const previewContent = ref('')
const previewTruncated = ref(false)
async function openPreview(record) {
  previewDoc.value = record
  try {
    const r = await previewDocument(record.id)
    previewContent.value = r.content
    previewTruncated.value = r.truncated
    previewOpen.value = true
  } catch (e) {
    message.error('预览失败:' + (e.response?.data?.detail || e.message))
  }
}

// 测试检索
const testOpen = ref(false)
const testQuery = ref('')
const testResults = ref([])
const testLoading = ref(false)
function openTestSearchModal() {
  testOpen.value = true
  testQuery.value = ''
  testResults.value = []
}
async function runTestSearch() {
  if (!testQuery.value.trim()) {
    message.warning('请输入查询')
    return
  }
  testLoading.value = true
  try {
    const r = await testSearch(testQuery.value, 3)
    testResults.value = r.results || []
  } catch (e) {
    message.error('检索失败:' + (e.response?.data?.detail || e.message))
  } finally {
    testLoading.value = false
  }
}

const isMobile = ref(false)
function checkMobile() {
  isMobile.value = window.innerWidth < 768
}
onMounted(() => {
  loadDocuments()
  checkMobile()
  window.addEventListener('resize', checkMobile)
})
</script>

<style scoped>
.knowledge-page { display: flex; flex-direction: column; gap: 16px; }
.filter-card { margin-bottom: 0; }
.preview-content {
  background: #fafafa;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 500px;
  overflow-y: auto;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
}
.test-result-item {
  background: #fafafa;
  border-left: 3px solid #1890ff;
  padding: 10px 12px;
  border-radius: 0 4px 4px 0;
  margin-bottom: 12px;
}
.test-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}
</style>
