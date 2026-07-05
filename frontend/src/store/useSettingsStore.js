import { defineStore } from 'pinia'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    apiBase: '/api',
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
  }),
  actions: {
    setSettings(settings) {
      Object.assign(this, settings)
    },
  },
})
