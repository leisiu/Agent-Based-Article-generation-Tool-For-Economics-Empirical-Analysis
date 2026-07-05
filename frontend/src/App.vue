<template>
  <div class="app-container">
    <el-header class="app-header">
      <div class="header-content">
        <h1 class="app-title">经管实证AI自动论文生成工具</h1>
        <el-menu
          :default-active="activeMenu"
          mode="horizontal"
          :router="true"
          class="app-menu"
        >
          <el-menu-item index="/">首页</el-menu-item>
          <el-menu-item index="/projects">项目管理</el-menu-item>
          <el-menu-item index="/settings">设置</el-menu-item>
        </el-menu>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background-color: #f5f7fa;
}

.app-header {
  background-color: #fff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 0;
  height: 60px;
}

.header-content {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 20px;
}

.app-title {
  font-size: 18px;
  color: #303133;
  margin: 0;
  margin-right: 40px;
}

.app-menu {
  flex: 1;
  border-bottom: none;
}

.app-main {
  padding: 20px;
}
</style>
