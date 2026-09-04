<template>
  <div class="logs-page">
    <h2 class="page-title">系统日志</h2>

    <a-card :bordered="false" class="filter-card">
      <a-space wrap>
        <a-input-number
          v-model:value="filterUserId"
          placeholder="用户 ID"
          style="width: 120px"
          :min="1"
        />
        <a-select
          v-model:value="filterAction"
          placeholder="操作类型"
          allow-clear
          style="width: 200px"
          :options="actionOptions"
        />
        <a-select
          v-model:value="filterStatus"
          placeholder="状态"
          allow-clear
          style="width: 120px"
          :options="[
            { label: '成功', value: 'success' },
            { label: '失败', value: 'failed' }
          ]"
        />
        <a-range-picker v-model:value="dateRange" />
        <a-button type="primary" @click="handleSearch">查询</a-button>
        <a-button @click="handleReset">重置</a-button>
        <a-button @click="loadActions">刷新 actions</a-button>
        <a-button @click="handleExport" :loading="exporting">导出 CSV</a-button>
      </a-space>
    </a-card>

    <a-card :bordered="false">
      <a-table
        :columns="columns"
        :data-source="logs"
        :loading="loading"
        :pagination="pagination"
        @change="handleTableChange"
        row-key="id"
        :scroll="{ x: 1100 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'username'">
            <span v-if="record.username">{{ record.username }}</span>
            <a-tag v-else color="default">系统</a-tag>
            <span v-if="record.user_id" class="user-id">#{{ record.user_id }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'action'">
            <a-tag color="blue">{{ record.action }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 'success' ? 'green' : 'red'">
              {{ record.status === 'success' ? '成功' : '失败' }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'details'">
            <a-tooltip v-if="record.details" :title="JSON.stringify(record.details, null, 2)">
              <a-button type="link" size="small" @click="showDetails(record)">查看</a-button>
            </a-tooltip>
            <span v-else class="text-muted">-</span>
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            <span class="time-text">{{ formatTime(record.created_at) }}</span>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="detailsOpen"
      title="操作详情"
      :footer="null"
      :width="isMobile ? '95%' : 600"
    >
      <pre class="json-content">{{ detailsContent }}</pre>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { listLogs, listLogActions, exportLogsUrl } from '../../api/logs'
import http from '../../api/http'

const loading = ref(false)
const exporting = ref(false)
const logs = ref([])
const total = ref(0)
const filterUserId = ref(undefined)
const filterAction = ref(undefined)
const filterStatus = ref(undefined)
const dateRange = ref([])
const actionOptions = ref([])

const columns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '时间', dataIndex: 'created_at', width: 160 },
  { title: '用户', dataIndex: 'username', width: 130 },
  { title: '操作', dataIndex: 'action', width: 200 },
  { title: '资源', key: 'resource', width: 130, customRender: ({ record }) => {
    if (record.resource_type) {
      return `${record.resource_type}#${record.resource_id || ''}`
    }
    return '-'
  } },
  { title: '状态', dataIndex: 'status', width: 80 },
  { title: 'IP', dataIndex: 'ip', width: 120 },
  { title: '详情', dataIndex: 'details', width: 80 }
]

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (t) => `共 ${t} 条`
})

async function loadLogs() {
  loading.value = true
  try {
    const params = {
      user_id: filterUserId.value,
      action: filterAction.value,
      status: filterStatus.value,
      page: pagination.current,
      page_size: pagination.pageSize
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.date_from = dayjs(dateRange.value[0]).format('YYYY-MM-DD')
      params.date_to = dayjs(dateRange.value[1]).format('YYYY-MM-DD')
    }
    Object.keys(params).forEach((k) => params[k] === undefined && delete params[k])
    const r = await listLogs(params)
    logs.value = r.items
    total.value = r.total
    pagination.total = r.total
  } catch (e) {
    message.error('加载失败:' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function loadActions() {
  try {
    const r = await listLogActions()
    actionOptions.value = r.actions.map((a) => ({ label: a, value: a }))
  } catch (e) {
    // ignore
  }
}

function handleSearch() {
  pagination.current = 1
  loadLogs()
}

function handleReset() {
  filterUserId.value = undefined
  filterAction.value = undefined
  filterStatus.value = undefined
  dateRange.value = []
  pagination.current = 1
  loadLogs()
}

function handleTableChange(pag) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  loadLogs()
}

function formatTime(t) {
  if (!t) return '-'
  return dayjs(t).format('YYYY-MM-DD HH:mm:ss')
}

const detailsOpen = ref(false)
const detailsContent = ref('')
function showDetails(record) {
  detailsContent.value = JSON.stringify(record.details, null, 2)
  detailsOpen.value = true
}

async function handleExport() {
  exporting.value = true
  try {
    const params = {
      user_id: filterUserId.value,
      action: filterAction.value,
      date_from: dateRange.value?.[0] ? dayjs(dateRange.value[0]).format('YYYY-MM-DD') : undefined,
      date_to: dateRange.value?.[1] ? dayjs(dateRange.value[1]).format('YYYY-MM-DD') : undefined
    }
    Object.keys(params).forEach((k) => params[k] === undefined && delete params[k])
    // 复用 http 实例走认证头
    const r = await http.get(exportLogsUrl(params), { responseType: 'blob' })
    const blob = new Blob([r.data], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `operation_logs_${dayjs().format('YYYYMMDD_HHmmss')}.csv`
    a.click()
    URL.revokeObjectURL(url)
    message.success('已导出')
  } catch (e) {
    message.error('导出失败:' + (e.message || e))
  } finally {
    exporting.value = false
  }
}

const isMobile = ref(false)
function checkMobile() {
  isMobile.value = window.innerWidth < 768
}
onMounted(() => {
  loadLogs()
  loadActions()
  checkMobile()
  window.addEventListener('resize', checkMobile)
})
</script>

<style scoped>
.logs-page { display: flex; flex-direction: column; gap: 16px; }
.filter-card { margin-bottom: 0; }
.user-id { color: #999; margin-left: 4px; font-size: 12px; }
.text-muted { color: #ccc; }
.time-text { font-family: monospace; font-size: 12px; }
.json-content {
  background: #fafafa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 400px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
</style>
