<template>
  <div class="achievements-page">
    <h2 class="page-title">成就定义管理</h2>

    <a-card :bordered="false" class="filter-card">
      <a-space wrap>
        <a-segmented
          v-model:value="filterActive"
          :options="[
            { label: '全部', value: 'all' },
            { label: '已启用', value: 'true' },
            { label: '已停用', value: 'false' }
          ]"
          @change="loadAchievements"
        />
        <a-button type="primary" @click="openCreateModal">
          <template #icon><plus-outlined /></template>
          新增成就
        </a-button>
        <a-button @click="loadAchievements">刷新</a-button>
      </a-space>
    </a-card>

    <a-card :bordered="false">
      <a-table
        :columns="columns"
        :data-source="filteredItems"
        :loading="loading"
        :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        row-key="id"
        :scroll="{ x: 1100 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'name'">
            <a-space>
              <span style="font-size: 24px">{{ record.icon }}</span>
              <span>{{ record.name }}</span>
            </a-space>
          </template>
          <template v-else-if="column.dataIndex === 'code'">
            <code class="ach-code">{{ record.code }}</code>
          </template>
          <template v-else-if="column.dataIndex === 'metric_type'">
            <a-tag color="blue">{{ metricLabel(record.metric_type) }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'target_value'">
            ≥ {{ record.target_value }} {{ metricUnit(record.metric_type) }}
          </template>
          <template v-else-if="column.dataIndex === 'is_active'">
            <a-tag :color="record.is_active ? 'green' : 'default'">
              {{ record.is_active ? '已启用' : '已停用' }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'actions'">
            <a-space wrap>
              <a-button size="small" type="link" @click="openEditModal(record)">编辑</a-button>
              <a-button
                size="small" type="link"
                @click="handleToggleActive(record)"
              >
                {{ record.is_active ? '停用' : '启用' }}
              </a-button>
              <a-popconfirm
                title="确认删除该成就定义?已解锁的用户记录也会被清除"
                @confirm="handleDelete(record)"
              >
                <a-button size="small" type="link" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 新建/编辑弹窗 -->
    <a-modal
      v-model:open="editModalOpen"
      :title="editing ? '编辑成就' : '新增成就'"
      :width="isMobile ? '95%' : 600"
      @ok="handleSave"
      :confirmLoading="saving"
    >
      <a-form layout="vertical" :model="formState" :rules="formRules" ref="formRef">
        <a-form-item label="图标 (emoji)" name="icon">
          <a-input
            v-model:value="formState.icon"
            placeholder="🏅"
            style="width: 120rpx; font-size: 32rpx"
            maxlength="4"
          />
        </a-form-item>
        <a-form-item label="唯一标识 (code)" name="code" v-if="!editing">
          <a-input v-model:value="formState.code" placeholder="如 todo_100" />
          <span style="color: #999; font-size: 12px">创建后不可修改,建议英文+下划线</span>
        </a-form-item>
        <a-form-item label="显示名" name="name">
          <a-input v-model:value="formState.name" placeholder="如 百日筑基" />
        </a-form-item>
        <a-form-item label="达成说明" name="description">
          <a-textarea v-model:value="formState.description" :rows="2" placeholder="如 完成 100 条待办" />
        </a-form-item>
        <a-form-item label="评估规则 (metric_type)" name="metric_type">
          <a-select
            v-model:value="formState.metric_type"
            placeholder="选择评估指标"
            :options="metricOptions"
            show-search
          />
        </a-form-item>
        <a-form-item :label="`达成阈值 (≥ 多少${metricUnit(formState.metric_type) || '个'}解锁)`" name="target_value">
          <a-input-number
            v-model:value="formState.target_value"
            :min="1"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-switch v-model:checked="formState.is_active" />
            <span>启用</span>
            <a-input-number
              v-model:value="formState.sort_order"
              :min="0"
              style="width: 200rpx; margin-left: 24rpx;"
              addon-before="排序"
            />
          </a-space>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import http from '../../api/http'

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const metricOptions = ref([])
const filterActive = ref('all')
const editModalOpen = ref(false)
const editing = ref(null)
const formRef = ref()
const isMobile = ref(false)

const formState = reactive({
  icon: '🏅',
  code: '',
  name: '',
  description: '',
  metric_type: undefined,
  target_value: 1,
  is_active: true,
  sort_order: 0
})

const formRules = {
  code: [{ required: true, message: '请输入 code' }],
  name: [{ required: true, message: '请输入显示名' }],
  metric_type: [{ required: true, message: '请选择评估规则' }],
  target_value: [{ required: true, type: 'number', min: 1, message: '阈值 ≥ 1' }]
}

const columns = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  { title: '成就', dataIndex: 'name', width: 200 },
  { title: 'Code', dataIndex: 'code', width: 140 },
  { title: '说明', dataIndex: 'description', ellipsis: true },
  { title: '评估规则', dataIndex: 'metric_type', width: 160 },
  { title: '阈值', dataIndex: 'target_value', width: 100 },
  { title: '状态', dataIndex: 'is_active', width: 90 },
  { title: '排序', dataIndex: 'sort_order', width: 80 },
  { title: '操作', dataIndex: 'actions', width: 220, fixed: 'right' }
]

const filteredItems = computed(() => {
  if (filterActive.value === 'all') return items.value
  const want = filterActive.value === 'true'
  return items.value.filter(it => Boolean(it.is_active) === want)
})

const metricMap = ref({})
const metricLabel = (k) => metricMap.value[k]?.label || k
const metricUnit = (k) => metricMap.value[k]?.unit || ''

async function loadMetrics() {
  try {
    const r = await http.get('/admin/achievements/metrics')
    metricOptions.value = (r.metrics || []).map(m => ({
      label: `${m.label} (${m.value})`,
      value: m.value
    }))
    const m = {}
    for (const it of r.metrics || []) m[it.value] = it
    metricMap.value = m
  } catch (e) {
    message.error('加载 metric 列表失败: ' + e.message)
  }
}

async function loadAchievements() {
  loading.value = true
  try {
    const r = await http.get('/admin/achievements/')
    items.value = (r.items || []).map(it => ({
      ...it,
      is_active: Boolean(it.is_active)
    }))
  } catch (e) {
    message.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(formState, {
    icon: '🏅', code: '', name: '', description: '',
    metric_type: undefined, target_value: 1,
    is_active: true, sort_order: 0
  })
  editing.value = null
}

function openCreateModal() {
  resetForm()
  editModalOpen.value = true
}

function openEditModal(record) {
  resetForm()
  editing.value = record
  Object.assign(formState, {
    icon: record.icon || '🏅',
    code: record.code,
    name: record.name,
    description: record.description || '',
    metric_type: record.metric_type,
    target_value: Number(record.target_value) || 1,
    is_active: Boolean(record.is_active),
    sort_order: Number(record.sort_order) || 0
  })
  editModalOpen.value = true
}

async function handleSave() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      icon: formState.icon,
      name: formState.name,
      description: formState.description,
      metric_type: formState.metric_type,
      target_value: Number(formState.target_value),
      is_active: formState.is_active ? 1 : 0,
      sort_order: Number(formState.sort_order) || 0
    }
    if (editing.value) {
      await http.put(`/admin/achievements/${editing.value.id}`, payload)
      message.success('已更新')
    } else {
      payload.code = formState.code
      await http.post('/admin/achievements/', payload)
      message.success('已创建')
    }
    editModalOpen.value = false
    loadAchievements()
  } catch (e) {
    const status = e.response?.status
    const detail = e.response?.data?.detail
    if (status === 400 && detail) {
      message.error('参数错误: ' + detail)
    } else if (!status) {
      message.warning('请求未完成,但数据可能已保存,请刷新列表确认')
    } else {
      message.error('保存失败: ' + (detail || e.message))
    }
  } finally {
    saving.value = false
  }
}

async function handleToggleActive(record) {
  try {
    await http.put(`/admin/achievements/${record.id}`, {
      is_active: record.is_active ? 0 : 1
    })
    message.success(record.is_active ? '已停用' : '已启用')
    loadAchievements()
  } catch (e) {
    message.error('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleDelete(record) {
  try {
    await http.delete(`/admin/achievements/${record.id}`)
    message.success('已删除')
    loadAchievements()
  } catch (e) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  isMobile.value = window.innerWidth < 768
  loadMetrics()
  loadAchievements()
})
</script>

<style scoped>
.achievements-page {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}
.filter-card {
  margin-bottom: 0;
}
.ach-code {
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
}
</style>
