<template>
  <a-config-provider :theme="{ token: { colorPrimary: '#8DA9C4' } }">
    <router-view />
  </a-config-provider>
</template>

<script setup>
// 全局配置
</script>

<style>
html, body, #app {
  height: 100%;
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
</style>
