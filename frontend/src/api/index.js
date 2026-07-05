import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 1800000, // 30分钟超时，适应论文生成长时间需求
})

// ==================== 项目管理 ====================

// 获取所有项目
export const getProjects = () => api.get('/projects')

// 获取最近项目
export const getRecentProjects = () => api.get('/projects/recent')

// 创建项目（上传数据时自动创建）
export const createProject = (formData) => api.post('/upload-data', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
})

// 获取项目详情
export const getProject = (id) => api.get(`/project/${id}`)

// 刷新项目数据
export const refreshProject = (id) => api.get(`/project/${id}/refresh`)

// 删除项目
export const deleteProject = (id) => api.delete(`/project/${id}`)

// 重试项目
export const retryProject = (id, data) => api.post(`/project/${id}/retry`, data)

// 获取项目数据列
export const getProjectColumns = (id) => api.get(`/project/${id}/columns`)

// ==================== 实证分析 ====================

// 启动实证分析
export const runEmpirical = (data) => api.post('/run-empirical', data)

// 重新运行实证分析
export const rerunEmpirical = (data) => api.post('/rerun-empirical', data)

// 生成论文
export const generatePaper = (data) => api.post('/generate-paper', data)
export const resetProjectFromGenerating = (id) => api.post(`/project/${id}/reset-from-generating`)

// 上传文献综述参考文件
export const uploadLiterature = (formData) => api.post('/upload-literature', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
})

// ==================== 导出 ====================

// 导出结果
export const exportResults = (id) => api.get(`/export/${id}`, { responseType: 'blob' })

export const exportPDF = (id) => api.get(`/export-pdf/${id}`, { responseType: 'blob' })

export const exportPaperWord = (id) => api.get(`/export-paper-word/${id}`, { responseType: 'blob' })

export const exportExcel = (id) => api.get(`/export-excel/${id}`, { responseType: 'blob' })

// ==================== 设置 ====================

// 获取设置
export const getSettings = () => api.get('/settings')

// 更新AI设置
export const updateAISettings = (data) => api.post('/settings/ai', data)

// 更新实证设置
export const updateEmpiricalSettings = (data) => api.post('/settings/empirical', data)

// 更新系统设置
export const updateSystemSettings = (data) => api.post('/settings/system', data)

// 更新设置（兼容旧接口）
export const updateSettings = (data) => api.post('/settings', data)

// 获取设置统计
export const getSettingsStats = () => api.get('/settings/stats')

// ==================== 统计 ====================

// 获取统计信息
export const getStats = () => api.get('/stats')

export default api
