<template>
  <div class="project-detail">
    <!-- 页面头部 -->
    <div class="header">
      <button class="back-btn" @click="goBack">
        <span class="arrow">←</span> 返回
      </button>
      <h1>{{ project.name }}</h1>
      <div class="header-actions">
        <button
          v-if="project.status === 'running'"
          class="stop-btn"
          @click="handleStop"
        >
          终止任务
        </button>
      </div>
    </div>

    <!-- 状态指示器 -->
    <div v-if="project.status === 'running'" class="status-bar">
      <div class="status-spinner"></div>
      <span class="status-text">{{ getStatusText() }}</span>
    </div>

    <!-- 错误提示 -->
    <div v-if="project.status === 'failed'" class="error-bar">
      <span class="error-icon">⚠</span>
      <span class="error-text">{{ getErrorMessage() }}</span>
      <button class="retry-btn" @click="handleRetry">重试</button>
      <button 
        v-if="project.empiricalResults?.traceback" 
        class="detail-btn"
        @click="showTraceback = !showTraceback"
      >
        {{ showTraceback ? '隐藏详情' : '查看详情' }}
      </button>
      <pre v-if="showTraceback" class="traceback">{{ getErrorTraceback() }}</pre>
    </div>

    <!-- 步骤1: 数据预览和变量配置 (uploaded 状态) -->
    <div v-if="project.status === 'uploaded'" class="config-section">
      <!-- 数据预览 -->
      <el-card class="data-preview-card">
        <template #header>
          <span class="card-title">数据预览（前5行）</span>
        </template>
        <div class="data-preview">
          <el-table :data="previewData" border stripe max-height="400">
            <el-table-column v-for="col in columns" :key="col" :prop="col" :label="col" min-width="120" />
          </el-table>
        </div>
      </el-card>

      <!-- 变量选择器 -->
      <VariableSelector
        :project-id="projectId"
        @start="handleAnalysisStarted"
      />
    </div>

    <!-- 步骤2: 分析结果展示 (completed 状态，无论文) -->
    <el-card v-if="project.status === 'completed' && !generating && !showPromptForm" class="results-card">
      <template #header>
        <div class="results-header">
          <span class="card-title">分析结果</span>
          <div class="results-actions">
            <el-button type="primary" @click="handleExport">
              <el-icon><Download /></el-icon>
              导出结果
            </el-button>
          </div>
        </div>
      </template>

      <!-- 分析结果区：按顺序展示 描述性 → 相关性 → VIF → 基准回归 → 稳健性 → 异质性 → 调节 → 机制 -->
      <div v-if="resultSectionList.length > 0" class="results-area">
        <div class="result-tabs">
          <button
            v-for="sec in resultSectionList"
            :key="sec.key"
            :class="{ active: activeTab === sec.key }"
            @click="activeTab = sec.key"
            class="result-tab-btn"
          >
            {{ sec.title }}
          </button>
        </div>
        <div class="result-content">
          <template v-if="activeTab === 'descriptive'">
            <DescriptiveStatistics :data="project.empiricalResults?.descriptive" />
          </template>
          <template v-else-if="activeTab === 'correlation'">
            <CorrelationAnalysis :data="project.empiricalResults?.correlation" />
          </template>
          <template v-else-if="activeTab === 'vif'">
            <VIFResults :data="project.empiricalResults?.vif" />
          </template>
          <template v-else-if="activeTab === 'regression'">
            <RegressionResults :data="project.empiricalResults?.regression" />
          </template>
          <template v-else>
            <RobustnessResults :data="activeTabData" :title="activeTabTitle" />
          </template>
        </div>
      </div>

      <!-- 底部导航 -->
      <div class="step-navigation">
        <button class="nav-btn prev-btn" @click="handlePrevStep">
          ← 上一步（重新配置变量）
        </button>
        <button class="nav-btn next-btn" @click="handleNextToPrompt">
          下一步（生成论文）→
        </button>
      </div>
    </el-card>

    <!-- 步骤2.5: 提示词输入 (内嵌表单) -->
    <el-card v-if="project.status === 'completed' && showPromptForm && !generating" class="prompt-card">
      <template #header>
        <div class="results-header">
          <span class="card-title">生成论文 - 请输入研究指令</span>
        </div>
      </template>

      <div class="prompt-form">
        <p class="form-description">
          请输入您的研究指令或自定义提示词，AI将根据您的实证分析结果生成论文。
        </p>
        
        <el-input
          v-model="customPrompt"
          type="textarea"
          :rows="8"
          placeholder="例如：请基于实证分析结果，撰写一篇关于债务融资与企业创新关系的学术论文，重点探讨融资约束的调节作用..."
          class="prompt-textarea"
        ></el-input>

        <!-- 文献综述参考文件上传 -->
        <div class="literature-upload-inline">
          <span class="literature-label">文献综述参考文件（可选）</span>
          <div class="literature-input-wrapper">
            <el-button size="small" @click="$refs.literatureInput.click()" :loading="uploadingLiterature">
              上传文件
            </el-button>
            <span class="literature-file-name">
              {{ literatureFile ? literatureFile.name : '点击上传 .txt 文件' }}
            </span>
            <input
              ref="literatureInput"
              type="file"
              accept=".txt"
              style="display: none"
              @change="handleLiteratureChange"
            />
          </div>
        </div>

        <div class="dialog-tips">
          <p><strong>提示：</strong></p>
          <ul>
            <li>您可以指定论文的研究主题和重点</li>
            <li>可以要求强调某些特定的分析结果</li>
            <li>可以指定论文的风格和目标期刊</li>
          </ul>
        </div>
      </div>

      <!-- 底部导航 -->
      <div class="step-navigation">
        <button class="nav-btn prev-btn" @click="handleBackToResults">
          ← 上一步（查看分析结果）
        </button>
        <button class="nav-btn next-btn" @click="confirmGeneratePaper">
          下一步（生成论文）→
        </button>
      </div>
    </el-card>

    <!-- 步骤3: 论文生成中 -->
    <el-card v-if="generating" class="generating-card">
      <template #header>
        <div class="results-header">
          <span class="card-title">论文生成中</span>
          <el-button size="small" type="danger" plain @click="handleExitGenerating">
            退出（重置状态）
          </el-button>
        </div>
      </template>
      <div class="generating-status">
        <div class="spinner"></div>
        <p>正在根据你的研究指令撰写论文，请稍后...</p>
        <p v-if="pollElapsed > 0" class="poll-hint">
          已等待 {{ Math.floor(pollElapsed / 60) }} 分 {{ pollElapsed % 60 }} 秒
        </p>
      </div>
    </el-card>

    <!-- 步骤4: 论文展示 -->
    <el-card v-if="project.paperContent && !generating && !showPromptForm" class="paper-card">
      <template #header>
        <div class="results-header">
          <span class="card-title">生成的论文</span>
          <div class="results-actions">
            <el-button type="primary" @click="handleExportPaper">
              <el-icon><Download /></el-icon>
              导出论文
            </el-button>
          </div>
        </div>
      </template>

      <div class="paper-view">
        <div class="view-actions">
          <button
            :class="{ active: paperViewMode === 'html' }"
            @click="paperViewMode = 'html'"
          >预览</button>
          <button
            :class="{ active: paperViewMode === 'source' }"
            @click="paperViewMode = 'source'"
          >源码</button>
        </div>
        <div v-if="paperViewMode === 'html'" v-html="formattedPaperContent" class="paper-html-content"></div>
        <pre v-else class="paper-source-content">{{ project.paperContent }}</pre>
      </div>

      <!-- 底部导航 -->
      <div class="step-navigation">
        <button class="nav-btn prev-btn" @click="handleBackToPrompt">
          ← 上一步（重新输入提示词）
        </button>
        <button class="nav-btn prev-btn" @click="handleBackToResults">
          ← 查看分析结果
        </button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { getProject, runEmpirical, exportResults, exportPDF, exportPaperWord, exportExcel, getProjectColumns, generatePaper, uploadLiterature, getSettings, resetProjectFromGenerating } from '../api'
import VariableSelector from '../components/VariableSelector.vue'
import DescriptiveStatistics from '../components/DescriptiveStatistics.vue'
import CorrelationAnalysis from '../components/CorrelationAnalysis.vue'
import VIFResults from '../components/VIFResults.vue'
import RegressionResults from '../components/RegressionResults.vue'
import RobustnessResults from '../components/RobustnessResults.vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id)

const project = ref({
  id: '',
  name: '',
  description: '',
  status: 'uploaded',
  modelType: 'deepseek',
  dataPath: null,
  resultPath: null,
  createdAt: '',
  updatedAt: '',
  completedAt: null,
  originalCommand: '',
  paperContent: null,
  empiricalResults: null,
})

const columns = ref([])
const previewData = ref([])
const activeTab = ref('descriptive') // 当前激活的结果标签
const paperViewMode = ref('html')
const formattedPaperContent = ref('')
const showTraceback = ref(false)
const generating = ref(false)
const showPromptForm = ref(false)
const oldPaperContent = ref('') // 重新生成时保留旧论文直到新论文完成
const pollElapsed = ref(0)      // 已等待秒数
let refreshTimer = null
let generateTimer = null
let pollTimer = null            // 计时器

// 自定义提示词
const customPrompt = ref('')

// 文献综述参考文件
const literatureFile = ref(null)
const literatureContent = ref('')
const uploadingLiterature = ref(false)

// 分析结果区段：固定顺序——描述性 → 相关性 → VIF → 基准回归 → 稳健性 → 异质性 → 调节 → 机制
const resultSectionList = computed(() => {
  const results = project.value.empiricalResults
  if (!results) return []
  const sections = []
  // 描述性
  if (results.descriptive && Object.keys(results.descriptive.variables || {}).length > 0) {
    sections.push({ key: 'descriptive', title: '描述性统计', data: null })
  }
  // 相关性
  if (results.correlation && Object.keys(results.correlation.pearson || {}).length > 0) {
    sections.push({ key: 'correlation', title: '相关性分析', data: null })
  }
  // VIF
  if (results.vif && Object.keys(results.vif.vif_values || {}).length > 0) {
    sections.push({ key: 'vif', title: 'VIF检验', data: null })
  }
  // 基准回归
  if (results.regression && Object.keys(results.regression).length > 0) {
    sections.push({ key: 'regression', title: '基准回归', data: null })
  }
  // 稳健性
  if (results.robustness && Object.keys(results.robustness).filter(k => k !== 'tests' && k !== 'count').length > 0) {
    sections.push({ key: 'robustness', title: '稳健性检验', data: results.robustness })
  }
  // 异质性
  if (results.heterogeneity && (results.heterogeneity.tests || (results.heterogeneity.count || 0) > 0 || results.heterogeneity.methods)) {
    sections.push({ key: 'heterogeneity', title: '异质性分析', data: results.heterogeneity })
  }
  // 调节
  if (results.moderation && (results.moderation.tests || (results.moderation.count || 0) > 0 || results.moderation.methods)) {
    sections.push({ key: 'moderation', title: '调节效应', data: results.moderation })
  }
  // 机制
  if (results.mechanism && (results.mechanism.tests || (results.mechanism.count || 0) > 0 || results.mechanism.methods)) {
    sections.push({ key: 'mechanism', title: '机制检验', data: results.mechanism })
  }
  return sections
})

// 当前激活的标签数据
const activeTabData = computed(() => {
  const sec = resultSectionList.value.find(s => s.key === activeTab.value)
  return sec ? sec.data : null
})

// 当前激活的标签标题
const activeTabTitle = computed(() => {
  const sec = resultSectionList.value.find(s => s.key === activeTab.value)
  return sec ? sec.title : ''
})

// 当结果变化时，如果当前 activeTab 已不存在，自动切到第一个
watch(resultSectionList, (newList) => {
  if (newList.length === 0) return
  if (!newList.find(s => s.key === activeTab.value)) {
    activeTab.value = newList[0].key
  }
}, { immediate: true })

const getStatusText = () => {
  const results = project.value.empiricalResults
  if (!results) return '正在初始化...'

  if (results.regression && results.robustness) {
    return '正在进行稳健性检验...'
  }

  if (results.descriptive && results.correlation && results.vif) {
    return '正在进行回归分析...'
  }

  if (results.descriptive && results.correlation) {
    return '正在进行VIF检验...'
  }

  if (results.descriptive) {
    return '正在进行相关性分析...'
  }

  return '正在预处理数据...'
}

const getErrorMessage = () => {
  const results = project.value.empiricalResults
  if (!results) return '未知错误'

  if (results.error) {
    return results.error
  }

  if (results.regression && results.regression.error) {
    return results.regression.error
  }

  return '未知错误'
}

const getErrorTraceback = () => {
  const results = project.value.empiricalResults
  if (!results) return ''

  if (results.traceback) {
    return results.traceback
  }

  if (results.regression && results.regression.traceback) {
    return results.regression.traceback
  }

  return ''
}

const goBack = () => {
  router.push('/projects')
}

const handleStop = async () => {
  ElMessage.info('终止功能开发中...')
}

const handleRetry = async () => {
  try {
    project.value.status = 'running'
    // 重新发送完整的实证参数（避免丢失用户的选择）
    const payload = { project_id: projectId.value }

    // 从保存的变量配置中还原参数
    const cfg = project.value.variableConfig
    if (cfg) {
      if (cfg.dependent_var) payload.dependent_var = cfg.dependent_var
      if (cfg.independent_vars?.length) payload.independent_vars = cfg.independent_vars
      if (cfg.control_vars?.length) payload.control_vars = cfg.control_vars
      if (cfg.fixed_effects) payload.fixed_effects = cfg.fixed_effects
      if (cfg.cluster_var) payload.cluster_var = cfg.cluster_var
      if (cfg.regression_models?.length) {
        payload.regression_models = cfg.regression_models
        payload.model = cfg.regression_models[0]
      }
      if (cfg.missing_method) payload.missing_method = cfg.missing_method
      if (cfg.outlier_method) payload.outlier_method = cfg.outlier_method
      if (cfg.robustness_tests?.length) payload.robustness_tests = cfg.robustness_tests
      if (cfg.test_types?.length) payload.test_types = cfg.test_types
      if (cfg.moderation_var) payload.moderation_var = cfg.moderation_var
      if (cfg.heterogeneity_var) payload.heterogeneity_var = cfg.heterogeneity_var
      if (cfg.mechanism_var) payload.mechanism_var = cfg.mechanism_var
      // 新结构
      if (cfg.baseline_models?.length) payload.baseline_models = cfg.baseline_models
      if (cfg.heterogeneity_methods?.length) payload.heterogeneity_methods = cfg.heterogeneity_methods
      if (cfg.mechanism_methods?.length) payload.mechanism_methods = cfg.mechanism_methods
    }

    await runEmpirical(payload)
    ElMessage.success('重试已启动')
    startRefreshTimer()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '重试失败')
  }
}

const handleAnalysisStarted = () => {
  project.value.status = 'running'
  startRefreshTimer()
}

// 导航函数
const handlePrevStep = () => {
  // 回到变量配置
  project.value.status = 'uploaded'
  loadColumnsAndPreview()
}

const handleNextToPrompt = () => {
  // 显示提示词输入表单
  showPromptForm.value = true
  customPrompt.value = ''
}

const handleBackToResults = () => {
  // 回到分析结果
  showPromptForm.value = false
}

const handleBackToPrompt = () => {
  // 回到提示词输入，重新生成
  showPromptForm.value = true
  customPrompt.value = ''
}

const handleLiteratureChange = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  await uploadLiteratureFile(file)
}

const handleLiteratureDrop = async (event) => {
  const file = event.dataTransfer.files[0]
  if (!file) return
  await uploadLiteratureFile(file)
}

const uploadLiteratureFile = async (file) => {
  if (!file.name.endsWith('.txt')) {
    ElMessage.warning('请上传 .txt 格式的文献文件')
    return
  }
  literatureFile.value = file
  uploadingLiterature.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const response = await uploadLiterature(formData)
    if (response.data.success) {
      literatureContent.value = response.data.data.content
      ElMessage.success('文献文件上传成功')
    } else {
      ElMessage.error(response.data.message || '文献上传失败')
      literatureFile.value = null
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.message || '文献上传失败')
    literatureFile.value = null
  } finally {
    uploadingLiterature.value = false
  }
}

const confirmGeneratePaper = async () => {
  // 验证提示词是否为空
  if (!customPrompt.value || customPrompt.value.trim() === '') {
    ElMessage.warning('请输入研究指令或提示词')
    return
  }

  showPromptForm.value = false
  generating.value = true

  // 立即清空旧论文和格式化内容
  project.value.paperContent = null
  formattedPaperContent.value = ''

  try {
    let apiKey = ''
    let aiModelType = 'deepseek'
    let aiModel = ''
    try {
      const settingsRes = await getSettings()
      const settingsData = settingsRes.data.data || settingsRes.data || {}
      const aiSettings = settingsData.aiSettings || settingsData
      aiModelType = aiSettings.modelType || 'deepseek'
      // 根据 modelType 动态获取对应的 API Key 和模型名称
      const apiKeyMap = {
        deepseek: aiSettings.deepseekApiKey || '',
        qwen: aiSettings.qwenApiKey || '',
        kimi: aiSettings.kimiApiKey || '',
        glm: aiSettings.glmApiKey || '',
        doubao: aiSettings.doubaoApiKey || '',
        custom: aiSettings.customApiKey || '',
      }
      const modelMap = {
        deepseek: aiSettings.deepseekModel || 'deepseek-chat',
        qwen: aiSettings.qwenModel || 'qwen-plus',
        kimi: aiSettings.kimiModel || 'kimi-k2.6',
        glm: aiSettings.glmModel || 'glm-4-plus',
        doubao: aiSettings.doubaoModel || 'doubao-pro-32k',
        custom: aiSettings.customModel || '',
      }
      apiKey = apiKeyMap[aiModelType] || ''
      aiModel = modelMap[aiModelType] || ''
    } catch (e) {
      console.warn('获取设置失败，将使用默认值', e)
    }

    console.log('准备调用 generatePaper API...')
    const response = await generatePaper({
      project_id: projectId.value,
      model_type: aiModelType,
      api_key: apiKey,
      model: aiModel,
      custom_prompt: customPrompt.value,
      literature_content: literatureContent.value,
    })
    console.log('generatePaper API 响应:', response.data)

    if (response.data.success) {
      ElMessage.success('论文生成任务已启动')
      startGeneratePoll()
    } else {
      ElMessage.error(response.data.message || '论文生成启动失败')
      generating.value = false
      showPromptForm.value = true
    }
  } catch (err) {
    console.error('generatePaper 请求异常:', err)
    console.error('错误响应:', err.response?.data)
    ElMessage.error(err.response?.data?.detail || err.response?.data?.message || '论文生成启动失败')
    generating.value = false
    showPromptForm.value = true
  }
}

const startGeneratePoll = () => {
  pollElapsed.value = 0

  // 每秒更新计时器（仅用于显示等待时长）
  pollTimer = setInterval(() => {
    pollElapsed.value++
  }, 1000)

  generateTimer = setInterval(async () => {
    await loadProject()

    // 论文生成完成 → 停止轮询并通知用户
    if (project.value.status === 'completed' && project.value.paperContent) {
      clearInterval(generateTimer)
      generateTimer = null
      clearInterval(pollTimer)
      pollTimer = null
      generating.value = false
      ElMessage.success('论文生成完成')
    }

    // 如果状态变成 failed，停止生成状态，返回前端结果页
    if (project.value.status === 'failed') {
      clearInterval(generateTimer)
      generateTimer = null
      clearInterval(pollTimer)
      pollTimer = null
      generating.value = false
      ElMessage.error('论文生成失败，请查看错误信息后重试')
    }
  }, 2000)
}

const handleExitGenerating = async () => {
  try {
    await resetProjectFromGenerating(projectId.value)
    // 清理所有定时器
    if (generateTimer) { clearInterval(generateTimer); generateTimer = null }
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    generating.value = false
    // 重新加载项目状态
    ElMessage.success('已退出论文生成状态')
    await loadProject()
  } catch (err) {
    console.error('退出生成状态失败:', err)
    // 即使 API 失败，也在前端强制退出
    if (generateTimer) { clearInterval(generateTimer); generateTimer = null }
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    generating.value = false
    ElMessage.warning('已强制退出生成状态')
  }
}

const handleExport = async () => {
  try {
    const response = await exportExcel(projectId.value)
    const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `实证分析结果_${project.value.name}.xlsx`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('Excel导出成功')
  } catch (err) {
    console.error('导出失败:', err)
    ElMessage.error('导出失败')
  }
}

const handleExportPaper = async () => {
  try {
    const response = await exportPaperWord(projectId.value)
    const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `论文_${project.value.name}.docx`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('Word导出成功')
  } catch (err) {
    console.error('导出失败:', err)
    ElMessage.error('导出失败')
  }
}

const startRefreshTimer = () => {
  refreshTimer = setInterval(async () => {
    await loadProject()
    
    if (project.value.status === 'completed' || project.value.status === 'failed') {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }, 3000)
}

const loadColumnsAndPreview = async () => {
  try {
    const res = await getProjectColumns(projectId.value)
    const data = res.data.data || res.data
    columns.value = data.columns || []
    previewData.value = data.preview || []
  } catch (err) {
    console.error('加载数据列失败:', err)
  }
}

const loadProject = async () => {
  try {
    const res = await getProject(projectId.value)
    project.value = res.data.data || res.data

    // 根据后端状态设置 generating 标志
    if (project.value.status === 'generating_paper') {
      generating.value = true
    } else if (project.value.status === 'completed' && project.value.paperContent) {
      generating.value = false
      let cleanedContent = project.value.paperContent
      if (cleanedContent.startsWith('AI')) cleanedContent = cleanedContent.substring(2)
      if (cleanedContent.startsWith('AI ')) cleanedContent = cleanedContent.substring(3)
      formattedPaperContent.value = marked(cleanedContent)
    }
  } catch (err) {
    console.error('加载项目失败:', err)
    const errorMsg = err.response?.data?.message || err.message || '网络请求失败'
    ElMessage.error(`加载项目失败: ${errorMsg}`)
  }
}

onMounted(() => {
  loadProject().then(() => {
    if (project.value.status === 'uploaded') {
      loadColumnsAndPreview()
    }
    if (project.value.status === 'running') {
      startRefreshTimer()
    }
    // 如果项目正在生成论文，启动轮询
    if (project.value.status === 'generating_paper') {
      startGeneratePoll()
    }
  })
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (generateTimer) clearInterval(generateTimer)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.project-detail {
  padding: 20px;
}

.header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
}

.back-btn {
  background: none;
  border: none;
  color: #409eff;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
}

.header-actions {
  margin-left: auto;
}

.stop-btn {
  background: #f56c6c;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 20px;
}

.status-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #409eff;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-text {
  color: #666;
}

.error-bar {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 15px;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 4px;
  margin-bottom: 20px;
}

.error-icon {
  font-size: 20px;
}

.error-text {
  flex: 1;
  color: #f56c6c;
}

.retry-btn, .detail-btn {
  background: #409eff;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.detail-btn {
  background: #67c23a;
}

.traceback {
  width: 100%;
  margin-top: 10px;
  padding: 10px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}

.config-section {
  margin-top: 20px;
}

.data-preview-card {
  margin-bottom: 20px;
}

.data-preview {
  overflow-x: auto;
}

.results-card, .prompt-card, .paper-card, .generating-card {
  margin-top: 20px;
}

.generating-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.generating-status .spinner {
  margin-bottom: 20px;
}

.generating-status p {
  font-size: 16px;
  color: #606266;
  margin: 0;
}

.poll-hint {
  margin-top: 16px !important;
  font-size: 14px !important;
  color: #909399 !important;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 18px;
  font-weight: bold;
}

.results-actions {
  display: flex;
  gap: 10px;
}

.tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid #eee;
}

.tabs button {
  background: none;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  color: #666;
}

.tabs button.active {
  background: #409eff;
  color: white;
}

.tab-content {
  min-height: 400px;
}

/* ==================== 回归区段（按钮标签） ==================== */
.results-area {
  margin-top: 20px;
  padding: 16px 18px 20px 18px;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  background: linear-gradient(180deg, #fafbfc 0%, #ffffff 100%);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.06);
}

.result-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px dashed #e4e7ed;
}

.result-tab-btn {
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  color: #606266;
  padding: 8px 18px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.result-tab-btn:hover {
  background: #ecf5ff;
  color: #409eff;
  border-color: #b3d8ff;
}

.result-tab-btn.active {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
  box-shadow: 0 2px 6px rgba(64, 158, 255, 0.3);
}

.result-content {
  min-height: 400px;
}

/* 提示词表单 */
.prompt-form {
  padding: 10px;
}

.form-description {
  margin-bottom: 15px;
  color: #666;
}

.prompt-textarea {
  width: 100%;
  margin-bottom: 15px;
}

.dialog-tips {
  background: #f5f7fa;
  padding: 15px;
  border-radius: 4px;
}

.dialog-tips ul {
  margin: 10px 0 0 20px;
  padding: 0;
}

.dialog-tips li {
  margin-bottom: 5px;
  color: #666;
}

/* 生成中 */
.generating-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px;
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #409eff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

.generating-content p {
  color: #666;
  font-size: 16px;
}

/* 论文展示 */
.paper-view {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.view-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.view-actions button {
  background: none;
  border: 1px solid #ddd;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.view-actions button.active {
  background: #409eff;
  color: white;
  border-color: #409eff;
}

.paper-html-content {
  line-height: 1.8;
  min-height: 400px;
  max-height: none;
  overflow: visible;
  padding: 30px;
  background: white;
  border: 1px solid #eee;
  border-radius: 4px;
  font-size: 15px;
  color: #333;
}

/* 论文标题样式 */
.paper-html-content h1 {
  font-size: 22px;
  font-weight: bold;
  text-align: center;
  margin: 20px 0 15px;
  color: #222;
}

.paper-html-content h2 {
  font-size: 18px;
  font-weight: bold;
  margin: 25px 0 12px;
  color: #333;
  border-bottom: 2px solid #409eff;
  padding-bottom: 8px;
}

.paper-html-content h3 {
  font-size: 16px;
  font-weight: bold;
  margin: 20px 0 10px;
  color: #444;
}

/* 表格样式优化 */
.paper-html-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 20px 0;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border-radius: 4px;
  overflow: hidden;
}

.paper-html-content table thead {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.paper-html-content table th {
  padding: 12px 15px;
  text-align: center;
  font-weight: 600;
  border: none;
}

.paper-html-content table td {
  padding: 10px 15px;
  text-align: center;
  border-bottom: 1px solid #eee;
}

.paper-html-content table tbody tr:hover {
  background-color: #f5f7fa;
}

.paper-html-content table tbody tr:last-child td {
  border-bottom: none;
}

/* 三线表样式（学术论文标准） */
.paper-html-content table.academic-table {
  border-top: 2px solid #333;
  border-bottom: 2px solid #333;
  box-shadow: none;
}

.paper-html-content table.academic-table thead {
  background: transparent;
  color: #333;
  border-bottom: 1px solid #333;
}

.paper-html-content table.academic-table th {
  padding: 8px 12px;
  font-weight: bold;
}

.paper-html-content table.academic-table td {
  padding: 6px 12px;
}

/* 公式样式优化 */
.paper-html-content .formula {
  background: #f8f9fa;
  padding: 15px 20px;
  margin: 15px 0;
  border-left: 4px solid #409eff;
  border-radius: 4px;
  font-family: 'Times New Roman', serif;
  font-size: 16px;
  text-align: center;
  overflow-x: auto;
}

.paper-html-content p:has(> .formula) {
  margin: 20px 0;
}

/* 代码块样式 */
.paper-html-content pre {
  background: #f5f5f5;
  padding: 15px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.6;
}

.paper-html-content code {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
  color: #e83e8c;
}

/* 引用块样式 */
.paper-html-content blockquote {
  border-left: 4px solid #409eff;
  padding: 10px 15px;
  margin: 15px 0;
  background: #f8f9fa;
  color: #666;
  border-radius: 0 4px 4px 0;
}

/* 列表样式 */
.paper-html-content ul,
.paper-html-content ol {
  padding-left: 25px;
  margin: 10px 0;
}

.paper-html-content li {
  margin: 5px 0;
  line-height: 1.6;
}

/* 显著性标记样式 */
.paper-html-content .significance {
  font-size: 12px;
  vertical-align: super;
  color: #e74c3c;
}

.paper-source-content {
  white-space: pre-wrap;
  word-break: break-all;
  background: #f5f5f5;
  padding: 15px;
  border-radius: 4px;
  min-height: 400px;
  max-height: none;
  overflow: visible;
  font-family: monospace;
  font-size: 14px;
  line-height: 1.6;
}

/* 步骤导航 */
.step-navigation {
  display: flex;
  justify-content: space-between;
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.nav-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 6px;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.2s;
}

.prev-btn {
  background: #f5f7fa;
  color: #606266;
  border: 1px solid #dcdfe6;
}

.prev-btn:hover {
  background: #e6e8eb;
}

.next-btn {
  background: #409eff;
  color: white;
}

.next-btn:hover {
  background: #66b1ff;
}

/* 文献上传 - 行内布局 */
.literature-upload-inline {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
  padding: 10px 16px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.literature-label {
  font-weight: 500;
  color: #606266;
  font-size: 14px;
  white-space: nowrap;
}

.literature-input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.literature-file-name {
  color: #909399;
  font-size: 13px;
}

/* 文献上传 - 旧样式（保留兼容） */
.literature-upload {
  margin: 20px 0;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.upload-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.title-text {
  font-weight: 600;
  color: #303133;
}

.optional-badge {
  padding: 2px 8px;
  background: #e6a23c;
  color: white;
  font-size: 12px;
  border-radius: 4px;
}

.upload-drop-zone {
  border: 2px dashed #c0c4cc;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
}

.upload-drop-zone:hover {
  border-color: #409eff;
  background: #f5f7fa;
}

.upload-icon {
  font-size: 32px;
  margin-bottom: 10px;
}

.upload-text {
  color: #606266;
  margin: 0 0 8px;
  font-size: 14px;
}

.upload-hint {
  color: #909399;
  font-size: 12px;
  margin: 0;
}
</style>
