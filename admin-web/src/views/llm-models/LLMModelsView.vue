<template>
  <div class="llm-models-page">
    <h2 class="page-title">AI 模型管理</h2>
    <a-card :bordered="false" class="filter-card">
      <a-space wrap>
        <a-segmented
          v-model:value="filterOwner"
          :options="[
            { label: '全部', value: 'all' },
            { label: '系统预设', value: 'system' },
            { label: '用户自定义', value: 'user' }
          ]"
          @change="loadModels"
        />
        <a-segmented
          v-model:value="filterActive"
          :options="[
            { label: '全部状态', value: 'all' },
            { label: '已启用', value: 'true' },
            { label: '已停用', value: 'false' }
          ]"
          @change="loadModels"
        />
        <a-button type="primary" @click="openCreateModal">
          <template #icon><plus-outlined /></template>
          新增模型
        </a-button>
        <a-button @click="loadModels">刷新</a-button>
      </a-space>
    </a-card>

    <a-card :bordered="false">
      <a-table
        :columns="columns"
        :data-source="filteredModels"
        :loading="loading"
        :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        row-key="id"
        :scroll="{ x: 900 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'name'">
            <a-space>
              <span>{{ record.name }}</span>
              <a-tag v-if="record.is_system_default" color="gold">系统默认</a-tag>
              <a-tag v-if="record.owner_user_id" color="blue">用户</a-tag>
            </a-space>
          </template>
          <template v-else-if="column.dataIndex === 'api_key'">
            <a-space>
              <code class="api-key-masked">{{ record.api_key_masked }}</code>
              <a-tooltip title="复制">
                <a-button type="text" size="small" @click="copyText(record.api_key)">
                  <template #icon><copy-outlined /></template>
                </a-button>
              </a-tooltip>
            </a-space>
          </template>
          <template v-else-if="column.dataIndex === 'is_active'">
            <a-tag :color="record.is_active ? 'green' : 'default'">
              {{ record.is_active ? '已启用' : '已停用' }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'actions'">
            <a-space wrap>
              <a-button
                v-if="!record.is_system_default && !record.owner_user_id"
                size="small"
                type="link"
                @click="handleSetDefault(record)"
              >
                设为默认
              </a-button>
              <a-button size="small" type="link" @click="openTestModal(record)">测试</a-button>
              <a-button size="small" type="link" @click="openEditModal(record)">编辑</a-button>
              <a-button
                size="small"
                type="link"
                :danger="!record.is_active"
                @click="handleToggleActive(record)"
              >
                {{ record.is_active ? '停用' : '启用' }}
              </a-button>
              <a-popconfirm
                :title="record.is_system_default ? '系统默认模型不能删除' : '确认删除该模型?'"
                :disabled="record.is_system_default"
                @confirm="handleDelete(record)"
              >
                <a-button size="small" type="link" danger :disabled="record.is_system_default">
                  删除
                </a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 新建 / 编辑弹窗 -->
    <a-modal
      v-model:open="editModalOpen"
      :title="editing ? '编辑模型' : '新增模型'"
      :width="isMobile ? '95%' : 600"
      @ok="handleSave"
      :confirmLoading="saving"
    >
      <a-form layout="vertical" :model="formState" :rules="formRules" ref="formRef">
        <a-form-item label="展示名" name="name">
          <a-input v-model:value="formState.name" placeholder="如:Agnes 官方 / OpenAI 备用" />
        </a-form-item>
        <a-form-item label="Base URL" name="base_url">
          <a-input v-model:value="formState.base_url" placeholder="https://api.openai.com/v1" />
        </a-form-item>
        <a-form-item label="API Key" name="api_key">
          <a-input-password
            v-model:value="formState.api_key"
            :placeholder="editing ? '留空表示不修改' : 'sk-...'"
          />
        </a-form-item>
        <a-form-item label="模型标识" name="model_name">
          <a-input v-model:value="formState.model_name" placeholder="如:agnes-2.0-flash / gpt-4o-mini" />
        </a-form-item>
        <a-form-item label="所属用户(留空 = 系统预设)">
          <a-input-number
            v-model:value="formState.owner_user_id"
            :min="1"
            style="width: 100%"
            placeholder="系统预设或用户 ID"
          />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-switch v-model:checked="formState.is_system_default" />
            <span>设为系统默认(将自动取消其他默认)</span>
          </a-space>
        </a-form-item>
        <a-form-item v-if="editing">
          <a-space>
            <a-switch v-model:checked="formState.is_active" />
            <span>启用</span>
          </a-space>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 测试弹窗 -->
    <a-modal
      v-model:open="testModalOpen"
      :title="`测试模型 - ${testTarget?.name || ''}`"
      :width="isMobile ? '95%' : 600"
      :footer="null"
    >
      <a-space direction="vertical" style="width: 100%">
        <a-textarea
          v-model:value="testPrompt"
          :rows="3"
          placeholder="请输入测试 prompt"
        />
        <a-button type="primary" :loading="testing" @click="handleTest">
          发送测试
        </a-button>
        <a-alert
          v-if="testResult"
          :type="testResult.success ? 'success' : 'error'"
          :message="testResult.success ? `成功(${testResult.latency_ms}ms)` : `失败(${testResult.latency_ms}ms)`"
          show-icon
        >
          <template #description>
            <pre class="test-result">{{ testResult.success ? testResult.reply : testResult.error }}</pre>
          </template>
        </a-alert>
      </a-space>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { Modal, message } from 'ant-design-vue'
import {
  PlusOutlined,
  CopyOutlined
} from '@ant-design/icons-vue'
import {
  listLLMModels,
  createLLMModel,
  updateLLMModel,
  deleteLLMModel,
  setDefaultLLMModel,
  testLLMModel
} from '../../api/llmModels'

const loading = ref(false)
const models = ref([])
const filterOwner = ref('all')
const filterActive = ref('all')

const columns = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  { title: '名称', dataIndex: 'name', width: 180 },
  { title: '模型标识', dataIndex: 'model_name', width: 200 },
  { title: 'Base URL', dataIndex: 'base_url', ellipsis: true },
  { title: 'API Key', dataIndex: 'api_key', width: 200 },
  { title: '状态', dataIndex: 'is_active', width: 90 },
  { title: '操作', dataIndex: 'actions', width: 280, fixed: 'right' }
]

const filteredModels = computed(() => {
  return models.value.filter((m) => {
    if (filterOwner.value === 'system' && m.owner_user_id) return false
    if (filterOwner.value === 'user' && !m.owner_user_id) return false
    if (filterActive.value !== 'all' && String(m.is_active) !== filterActive.value) return false
    return true
  })
})

async function loadModels() {
  loading.value = true
  try {
    const data = await listLLMModels()
    models.value = Array.isArray(data) ? data : []
  } catch (e) {
    message.error('加载失败:' + (e.message || e))
  } finally {
    loading.value = false
  }
}

// 编辑 / 新建
const editModalOpen = ref(false)
const saving = ref(false)
const editing = ref(null)
const formRef = ref()
const formState = reactive({
  name: '',
  base_url: '',
  api_key: '',
  model_name: '',
  is_system_default: false,
  is_active: true,
  owner_user_id: null
})
const formRules = {
  name: [{ required: true, message: '请输入展示名' }],
  base_url: [{ required: true, message: '请输入 Base URL' }],
  api_key: [{ required: true, message: '请输入 API Key' }],
  model_name: [{ required: true, message: '请输入模型标识' }]
}

function resetForm() {
  Object.assign(formState, {
    name: '',
    base_url: '',
    api_key: '',
    model_name: '',
    is_system_default: false,
    is_active: true,
    owner_user_id: null
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
    name: record.name,
    base_url: record.base_url,
    api_key: '',  // 编辑时不回显,留空表示不改
    model_name: record.model_name,
    is_system_default: record.is_system_default,
    is_active: record.is_active,
    owner_user_id: record.owner_user_id
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
    if (editing.value) {
      const data = { ...formState }
      if (!data.api_key) delete data.api_key
      await updateLLMModel(editing.value.id, data)
      message.success('更新成功')
    } else {
      await createLLMModel({
        ...formState,
        owner_user_id: formState.owner_user_id || null
      })
      message.success('创建成功')
    }
    editModalOpen.value = false
    loadModels()
  } catch (e) {
    message.error('保存失败:' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function handleDelete(record) {
  try {
    await deleteLLMModel(record.id)
    message.success('已删除')
    loadModels()
  } catch (e) {
    message.error('删除失败:' + (e.response?.data?.detail || e.message))
  }
}

async function handleSetDefault(record) {
  try {
    await setDefaultLLMModel(record.id)
    message.success('已设为系统默认')
    loadModels()
  } catch (e) {
    message.error('操作失败:' + (e.response?.data?.detail || e.message))
  }
}

async function handleToggleActive(record) {
  try {
    await updateLLMModel(record.id, { is_active: !record.is_active })
    message.success(record.is_active ? '已停用' : '已启用')
    loadModels()
  } catch (e) {
    message.error('操作失败:' + (e.response?.data?.detail || e.message))
  }
}

// 测试
const testModalOpen = ref(false)
const testing = ref(false)
const testTarget = ref(null)
const testPrompt = ref('你好,请用一句话自我介绍。')
const testResult = ref(null)

function openTestModal(record) {
  testTarget.value = record
  testResult.value = null
  testPrompt.value = '你好,请用一句话自我介绍。'
  testModalOpen.value = true
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const r = await testLLMModel(testTarget.value.id, testPrompt.value)
    testResult.value = r
  } catch (e) {
    testResult.value = { success: false, latency_ms: 0, error: e.response?.data?.detail || e.message }
  } finally {
    testing.value = false
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(
    () => message.success('已复制'),
    () => message.warning('复制失败')
  )
}

const isMobile = ref(false)
function checkMobile() {
  isMobile.value = window.innerWidth < 768
}
onMounted(() => {
  loadModels()
  checkMobile()
  window.addEventListener('resize', checkMobile)
})
</script>

<style scoped>
.llm-models-page { display: flex; flex-direction: column; gap: 16px; }
.filter-card { margin-bottom: 0; }
.api-key-masked {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
}
.test-result {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 8px 0 0;
  max-height: 300px;
  overflow-y: auto;
}
</style>
