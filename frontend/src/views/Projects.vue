<template>
  <div class="projects-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title">项目管理</span>
          <el-button type="primary" @click="openCreateDialog">
            <el-icon><Plus /></el-icon>
            新建项目
          </el-button>
        </div>
      </template>

      <el-table :data="projects" v-loading="loading" stripe>
        <el-table-column prop="name" label="项目名称" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="180" />
        <el-table-column prop="updatedAt" label="更新时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/project/${row.id}`)">
              查看
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建项目对话框 -->
    <el-dialog v-model="showCreateDialog" title="新建项目" width="500px" @keydown.enter.prevent>
      <el-form :model="form" label-width="100px" @submit.prevent>
        <el-form-item label="项目名称">
          <el-input
            v-model="form.name"
            :placeholder="namePlaceholder"
            @keydown.enter.prevent="handleCreate"
          />
        </el-form-item>
        <el-form-item label="数据文件">
          <el-upload
            ref="uploadRef"
            action="/api/projects"
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            accept=".xlsx,.xls,.csv"
            :show-file-list="true"
            :file-list="uploadFileList"
            @remove="handleFileRemove"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip">支持 xlsx, xls, csv 格式</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelCreate">取消</el-button>
        <el-button type="primary" @click="handleCreate" :loading="creating">
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getProjects, createProject, deleteProject } from '../api'

const projects = ref([])
const loading = ref(false)
const showCreateDialog = ref(false)
const creating = ref(false)
const uploadRef = ref(null)
const uploadFileList = ref([])
const form = ref({
  name: '',
  file: null,
  fileName: '',
})

const namePlaceholder = computed(() => {
  if (form.value.fileName) {
    return `如不填写，将使用文件名: ${form.value.fileName}`
  }
  return '请先选择数据文件，或手动输入项目名称'
})

const getStatusType = (status) => {
  const map = {
    uploaded: 'info',
    processing: 'warning',
    generating_paper: 'warning',
    completed: 'success',
    failed: 'danger',
  }
  return map[status] || 'info'
}

const getStatusText = (status) => {
  const map = {
    uploaded: '已上传',
    processing: '处理中',
    generating_paper: '论文生成中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

const loadProjects = async () => {
  loading.value = true
  try {
    const res = await getProjects()
    projects.value = res.data.data?.projects || []
  } catch (err) {
    ElMessage.error('加载项目失败')
  } finally {
    loading.value = false
  }
}

const handleFileChange = (file) => {
  form.value.file = file.raw
  form.value.fileName = file.name.replace(/\.[^/.]+$/, '')
  // 同步 uploadFileList（让显示受控）
  uploadFileList.value = [file]
}

const handleFileRemove = () => {
  form.value.file = null
  form.value.fileName = ''
  uploadFileList.value = []
}

const openCreateDialog = () => {
  // 每次打开都重置表单与文件列表，避免上次的残留
  form.value = { name: '', file: null, fileName: '' }
  uploadFileList.value = []
  if (uploadRef.value) {
    // 兜底：直接调用 el-upload 内部 clearFiles
    try { uploadRef.value.clearFiles() } catch (e) {}
  }
  showCreateDialog.value = true
}

const cancelCreate = () => {
  showCreateDialog.value = false
  form.value = { name: '', file: null, fileName: '' }
  uploadFileList.value = []
  if (uploadRef.value) {
    try { uploadRef.value.clearFiles() } catch (e) {}
  }
}

const handleCreate = async () => {
  if (!form.value.file) {
    ElMessage.warning('请选择数据文件')
    return
  }

  // 若用户没填项目名，自动使用文件名（去掉后缀）
  const finalName = form.value.name?.trim() || form.value.fileName
  if (!finalName) {
    ElMessage.warning('请输入项目名称')
    return
  }

  creating.value = true
  try {
    const formData = new FormData()
    formData.append('file', form.value.file)
    formData.append('project_name', finalName)

    const res = await createProject(formData)

    if (res.data.success) {
      ElMessage.success('项目创建成功')
      showCreateDialog.value = false
      form.value = { name: '', file: null, fileName: '' }
      uploadFileList.value = []
      if (uploadRef.value) {
        try { uploadRef.value.clearFiles() } catch (e) {}
      }
      await loadProjects()
    } else {
      ElMessage.error(res.data.message || '创建失败')
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

const handleDelete = async (id) => {
  try {
    await ElMessageBox.confirm('确定删除该项目吗？', '提示', { type: 'warning' })
    await deleteProject(id)
    ElMessage.success('删除成功')
    await loadProjects()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(loadProjects)
</script>

<style scoped>
.projects-container {
  max-width: 1200px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
}
</style>
