<template>
  <div class="dashboard-page">
    <h2 class="page-title">仪表盘</h2>

    <div class="dashboard-grid">
      <div class="stat-card primary">
        <div class="stat-icon"><team-outlined /></div>
        <a-statistic title="总用户数" :value="stats.users?.total ?? 0" />
        <div class="stat-extra">
          <span class="text-success">+{{ stats.users?.new_7d ?? 0 }} 本周新增</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon"><fire-outlined /></div>
        <a-statistic
          title="7 日活跃"
          :value="stats.users?.active_7d ?? 0"
          :suffix="`/ ${stats.users?.total ?? 0}`"
        />
        <div class="stat-extra">
          <span>活跃率 {{ Math.round((stats.users?.active_rate || 0) * 100) }}%</span>
        </div>
      </div>
      <div class="stat-card success">
        <div class="stat-icon"><robot-outlined /></div>
        <a-statistic title="AI 调用(7d)" :value="stats.ai?.calls_7d ?? 0" />
        <div class="stat-extra">
          <span>今日 {{ stats.ai?.calls_today ?? 0 }} / {{ stats.ai?.unique_users_7d ?? 0 }} 独立用户</span>
        </div>
      </div>
      <div class="stat-card warning">
        <div class="stat-icon"><database-outlined /></div>
        <a-statistic title="知识库文档" :value="stats.knowledge?.documents ?? 0" />
        <div class="stat-extra">
          <span>{{ stats.knowledge?.chunks ?? 0 }} chunks</span>
        </div>
      </div>
    </div>

    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="24" :md="12">
        <a-card title="系统数据" :bordered="false">
          <a-descriptions :column="1" size="small">
            <a-descriptions-item label="待办">{{ stats.data?.todos ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="目标">{{ stats.data?.goals ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="收支记录">{{ stats.data?.transactions ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="饮食记录">{{ stats.data?.meals ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="提醒">{{ stats.data?.reminders ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="成就解锁">{{ stats.data?.achievements ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="周月报">{{ stats.data?.reports ?? 0 }}</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-card title="LLM 配置" :bordered="false">
          <a-descriptions :column="1" size="small">
            <a-descriptions-item label="模型总数">
              <a-tag color="blue">{{ stats.llm?.models_total ?? 0 }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="系统默认">
              <a-tag color="gold">{{ stats.llm?.system_default_name || '未设置' }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="7 日操作日志">{{ stats.logs_7d ?? 0 }}</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="24" :md="14">
        <a-card title="7 日操作日志趋势" :bordered="false">
          <div v-if="!logStats.daily?.length" class="empty-tip">
            暂无日志数据
          </div>
          <div v-else class="bar-chart">
            <div
              v-for="d in logStats.daily"
              :key="d.date"
              class="bar-item"
            >
              <div
                class="bar"
                :style="{ height: barHeight(d.count) + 'px' }"
                :title="`${d.date}: ${d.count} 条`"
              >
                <span class="bar-value">{{ d.count }}</span>
              </div>
              <div class="bar-label">{{ formatShortDate(d.date) }}</div>
            </div>
          </div>
        </a-card>
      </a-col>
      <a-col :xs="24" :md="10">
        <a-card title="操作类型分布" :bordered="false">
          <a-empty v-if="!logStats.by_action?.length" description="暂无数据" />
          <a-list
            v-else
            :data-source="logStats.by_action"
            size="small"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-space>
                  <a-tag color="blue">{{ item.action }}</a-tag>
                </a-space>
                <span class="action-count">{{ item.count }}</span>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  TeamOutlined,
  FireOutlined,
  RobotOutlined,
  DatabaseOutlined
} from '@ant-design/icons-vue'
import http from '@/api/http'

const stats = ref({})
const logStats = ref({ daily: [], by_action: [] })

const loadStats = async () => {
  try {
    stats.value = await http.get('/admin/stats')
  } catch (e) { /* handled */ }
}

const loadLogStats = async () => {
  try {
    logStats.value = await http.get('/admin/logs/stats', { params: { days: 7 } })
  } catch (e) { /* handled */ }
}

const maxCount = () => {
  const arr = logStats.value.daily || []
  if (!arr.length) return 1
  return Math.max(...arr.map((d) => d.count), 1)
}

const barHeight = (count) => {
  const max = maxCount()
  return Math.max(8, Math.round((count / max) * 140))
}

const formatShortDate = (d) => {
  if (!d) return ''
  const parts = String(d).split('-')
  return parts.length >= 3 ? `${parts[1]}-${parts[2]}` : d
}

onMounted(() => {
  loadStats()
  loadLogStats()
})
</script>

<style scoped>
.dashboard-page { display: flex; flex-direction: column; }
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 18px 20px;
  border: 1px solid #f0f0f0;
  position: relative;
  transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.stat-card.primary { border-left: 4px solid #1890ff; }
.stat-card.success { border-left: 4px solid #52c41a; }
.stat-card.warning { border-left: 4px solid #faad14; }
.stat-card .stat-icon {
  position: absolute;
  top: 18px;
  right: 20px;
  font-size: 28px;
  color: #d9d9d9;
}
.stat-card.primary .stat-icon { color: #1890ff; }
.stat-card.success .stat-icon { color: #52c41a; }
.stat-card.warning .stat-icon { color: #faad14; }
.stat-extra {
  margin-top: 8px;
  font-size: 12px;
  color: #999;
}
.text-success { color: #52c41a; }
.empty-tip {
  text-align: center;
  color: #999;
  padding: 40px 0;
}
.bar-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 180px;
  padding: 0 8px;
}
.bar-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 0;
}
.bar {
  background: linear-gradient(180deg, #1890ff 0%, #69c0ff 100%);
  width: 70%;
  max-width: 36px;
  border-radius: 4px 4px 0 0;
  position: relative;
  transition: all 0.2s;
  cursor: pointer;
}
.bar:hover { background: linear-gradient(180deg, #40a9ff 0%, #91d5ff 100%); }
.bar-value {
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  color: #666;
}
.bar-label {
  margin-top: 6px;
  font-size: 11px;
  color: #999;
}
.action-count {
  font-weight: bold;
  color: #1890ff;
}
</style>
