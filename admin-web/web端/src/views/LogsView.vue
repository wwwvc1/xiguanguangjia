<script setup lang="ts">
/**
 * LogsView — 系统日志 (Phase 4)
 */
import GlassNav from '@/components/glass/GlassNav.vue'
import GlassTopBar from '@/components/glass/GlassTopBar.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <div class="app-shell">
    <GlassNav />
    <div class="app-main">
      <GlassTopBar title="系统日志" />
      <section class="page">
        <header class="page-header">
          <h2 class="serif">系统日志</h2>
          <p class="muted">Phase 4 才接 listLogs / exportLogs</p>
        </header>
        <GlassCard type="middle">
          <EmptyState
            icon="⌖"
            title="日志列表占位"
            hint="Phase 4 会接 listLogs(),支持级别过滤 / 时间范围 / 导出 CSV"
          />
        </GlassCard>
      </section>
    </div>
  </div>
</template>

<style scoped>
.app-shell { display: grid; grid-template-columns: auto 1fr; min-height: 100vh; }
.app-main { min-width: 0; }
.page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--c-ink); }
.muted { color: var(--c-ink-3); font-size: 13px; margin-top: 4px; }
</style>