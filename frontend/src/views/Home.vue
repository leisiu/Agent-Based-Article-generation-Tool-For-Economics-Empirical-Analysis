<template>
  <div class="home-container">
    <el-card class="welcome-card">
      <template #header>
        <span class="card-title">欢迎使用经管实证AI自动论文生成工具</span>
      </template>
      <div class="welcome-content">
        <p>本工具可以帮助您：</p>
        <ul>
          <li>上传面板数据文件</li>
          <li>自动进行描述性统计、相关性分析、VIF检验</li>
          <li>执行回归分析（含固定效应模型）</li>
          <li>进行稳健性检验</li>
          <li>自动生成实证论文</li>
        </ul>
        <el-button type="primary" size="large" @click="$router.push('/projects')">
          开始使用
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
</script>

<style scoped>
.home-container {
  max-width: 800px;
  margin: 0 auto;
}

.welcome-card {
  margin-top: 40px;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
}

.welcome-content {
  padding: 20px 0;
}

.welcome-content p {
  font-size: 16px;
  margin-bottom: 15px;
}

.welcome-content ul {
  margin-left: 20px;
  margin-bottom: 20px;
}

.welcome-content li {
  font-size: 14px;
  line-height: 2;
  color: #606266;
}
</style>
