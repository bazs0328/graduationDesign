<template>
  <div class="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
    <p class="text-7xl sm:text-8xl font-black text-muted-foreground/40 select-none">404</p>
    <h1 class="mt-4 text-xl sm:text-2xl font-bold">页面未找到</h1>
    <p class="mt-2 text-sm text-muted-foreground max-w-md">
      您访问的地址不存在或已被移除，请检查链接或返回首页。
    </p>
    <router-link
      to="/"
      class="mt-6 px-6 py-3 rounded-xl bg-primary text-primary-foreground font-semibold hover:opacity-90 transition-opacity"
    >
      返回首页
    </router-link>
  </div>
</template>

<script setup>
// 404 兜底页面，避免访问未知路径时出现空白
</script>
