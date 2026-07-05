<template>
  <div class="settings-container">
    <el-card>
      <template #header>
        <span class="card-title">设置</span>
      </template>
      <el-form :model="settings" label-width="140px" style="max-width: 650px">
        <el-form-item label="AI模型">
          <el-select v-model="settings.modelType" style="width: 100%" @change="onModelChange">
            <el-option v-for="m in modelOptions" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </el-form-item>

        <!-- DeepSeek -->
        <template v-if="settings.modelType === 'deepseek'">
          <el-form-item label="API Key">
            <el-input v-model="settings.deepseekApiKey" type="password" show-password placeholder="请输入DeepSeek API Key" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-select v-model="settings.deepseekModel" style="width: 100%" filterable allow-create>
              <el-option v-for="m in modelNames.deepseek" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </template>

        <!-- 通义千问 -->
        <template v-if="settings.modelType === 'qwen'">
          <el-form-item label="API Key">
            <el-input v-model="settings.qwenApiKey" type="password" show-password placeholder="请输入阿里云百炼平台 API Key (sk-...)" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-select v-model="settings.qwenModel" style="width: 100%" filterable allow-create>
              <el-option v-for="m in modelNames.qwen" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </template>

        <!-- Kimi -->
        <template v-if="settings.modelType === 'kimi'">
          <el-form-item label="API Key">
            <el-input v-model="settings.kimiApiKey" type="password" show-password placeholder="请输入月之暗面 API Key" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-select v-model="settings.kimiModel" style="width: 100%" filterable allow-create>
              <el-option v-for="m in modelNames.kimi" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </template>

        <!-- 智谱GLM -->
        <template v-if="settings.modelType === 'glm'">
          <el-form-item label="API Key">
            <el-input v-model="settings.glmApiKey" type="password" show-password placeholder="请输入智谱 API Key" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-select v-model="settings.glmModel" style="width: 100%" filterable allow-create>
              <el-option v-for="m in modelNames.glm" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </template>

        <!-- 豆包 -->
        <template v-if="settings.modelType === 'doubao'">
          <el-form-item label="API Key">
            <el-input v-model="settings.doubaoApiKey" type="password" show-password placeholder="请输入火山引擎 API Key" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-select v-model="settings.doubaoModel" style="width: 100%" filterable allow-create>
              <el-option v-for="m in modelNames.doubao" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </template>

        <!-- 自定义 -->
        <template v-if="settings.modelType === 'custom'">
          <el-form-item label="API Key">
            <el-input v-model="settings.customApiKey" type="password" show-password placeholder="请输入 API Key" />
          </el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="settings.customBaseUrl" placeholder="https://your-api-endpoint/v1" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-input v-model="settings.customModel" placeholder="模型名称（如 gpt-4o-mini）" />
          </el-form-item>
        </template>

        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getSettings, updateSettings } from '../api'

const modelOptions = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: '通义千问 (阿里云)' },
  { value: 'kimi', label: 'Kimi (月之暗面)' },
  { value: 'glm', label: '智谱GLM' },
  { value: 'doubao', label: '豆包 (字节跳动)' },
  { value: 'custom', label: '自定义 (OpenAI兼容)' },
]

const modelNames = {
  deepseek: ['deepseek-chat', 'deepseek-reasoner', 'deepseek-v4-flash', 'deepseek-v4-pro'],
  qwen: ['qwen-plus', 'qwen-max', 'qwen-turbo', 'qwen3.5-plus', 'qwen3-max', 'qwen3.6-plus'],
  kimi: ['kimi-k2.6', 'kimi-k2.5', 'moonshot-v1-128k'],
  glm: ['glm-4-plus', 'glm-4-air', 'glm-4-flash', 'glm-5.2'],
  doubao: ['doubao-pro-32k', 'doubao-lite-128k'],
}

const settings = ref({
  modelType: 'deepseek',
  deepseekApiKey: '',
  deepseekModel: 'deepseek-chat',
  qwenApiKey: '',
  qwenModel: 'qwen-plus',
  kimiApiKey: '',
  kimiModel: 'kimi-k2.6',
  glmApiKey: '',
  glmModel: 'glm-4-plus',
  doubaoApiKey: '',
  doubaoModel: 'doubao-pro-32k',
  customApiKey: '',
  customModel: '',
  customBaseUrl: '',
})

const saving = ref(false)

const onModelChange = () => {
  // 切换模型时不做额外操作
}

const loadSettings = async () => {
  try {
    const res = await getSettings()
    const data = res.data.data?.settings || res.data.settings || {}
    const aiSettings = data.aiSettings || data
    // 只合并有值的字段，避免覆盖默认值
    Object.keys(settings.value).forEach(key => {
      if (aiSettings[key] !== undefined && aiSettings[key] !== null) {
        settings.value[key] = aiSettings[key]
      }
    })
  } catch (err) {
    console.error('加载设置失败', err)
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    await updateSettings({
      aiSettings: { ...settings.value }
    })
    ElMessage.success('保存成功')
  } catch (err) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.settings-container {
  max-width: 800px;
  margin: 0 auto;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
}
</style>
