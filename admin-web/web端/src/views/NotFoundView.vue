<script setup lang="ts">
/**
 * NotFoundView — 404
 */
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <main class="nf-page">
    <div class="big serif">404</div>
    <p class="msg">页面去往了另一个宇宙</p>
    <button class="btn" @click="router.replace('/')">回到首页</button>
  </main>
</template>

<style scoped>
.nf-page {
  min-height: 100vh;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 16px;
  background: var(--c-paper);
  color: var(--c-ink);
  padding: 24px;
}
.big {
  font-size: 96px;
  font-weight: 700;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  line-height: 1;
}
.msg { color: var(--c-ink-3); font-size: 14px; }
.btn {
  padding: 10px 22px;
  border-radius: var(--r-sm);
  background: var(--accent-gradient);
  color: #fff;
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: transform var(--t-fast);
}
.btn:hover { transform: translateY(-1px); }
</style>