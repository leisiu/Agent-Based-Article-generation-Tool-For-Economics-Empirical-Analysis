<template>
  <div class="regression-results">
    <div v-if="errorMessage" class="error-block">
      <p class="error-title">⚠️ 回归模型执行失败：</p>
      <p>{{ errorMessage }}</p>
    </div>

    <AcademicTable
      v-else-if="columns.length > 0"
      :title="title"
      :columns="columns"
      :fixed-effects="fixedEffectRows"
    />

    <div v-else class="empty-container">
      <p>暂无回归分析数据</p>
      <details v-if="rawDebug">
        <summary>调试信息</summary>
        <pre>{{ JSON.stringify(rawDebug, null, 2) }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtNum } from '../utils/format.js'
import AcademicTable from './AcademicTable.vue'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  title: { type: String, default: '基准回归结果' },
  // 当前模型使用的固定效应定义 [{ key, name }]
  fixedEffects: { type: Array, default: () => [] },
})

function formatNum(v) {
  return fmtNum(v)
}

const rawDebug = computed(() => {
  if (!props.data || typeof props.data !== 'object') return null
  return {
    keys: Object.keys(props.data),
    first: Object.values(props.data)[0] || null,
  }
})

// 把模型的 coefficients 字典统一转换为 [{variable, coef, std_err, t_value, p_value, significance}] 形式
function buildCoefficients(wrapper) {
  if (!wrapper) return []
  const coefs = wrapper.coefficients || wrapper.params || {}
  if (typeof coefs !== 'object' || Object.keys(coefs).length === 0) return []

  const result = []
  for (const [variable, param] of Object.entries(coefs)) {
    if (!param || typeof param !== 'object') continue
    if (variable === 'Intercept' || variable === 'const') continue
    result.push({
      variable,
      coef: param.coef !== undefined ? param.coef : null,
      std_err: param.std_err !== undefined ? param.std_err : null,
      t_value: param.t_value !== undefined ? param.t_value : null,
      p_value: param.p_value !== undefined ? param.p_value : null,
      significance: param.significance || '',
      pValueNum: param.p_value !== undefined ? Number(param.p_value) : null,
    })
  }
  // 把截距/常数项放到最末并改名为"常数项"
  const interceptKey = Object.keys(coefs).find(k => k === 'Intercept' || k === 'const')
  if (interceptKey) {
    const param = coefs[interceptKey]
    if (param && typeof param === 'object') {
      result.push({
        variable: '常数项',
        coef: param.coef !== undefined ? param.coef : null,
        std_err: param.std_err !== undefined ? param.std_err : null,
        t_value: param.t_value !== undefined ? param.t_value : null,
        p_value: param.p_value !== undefined ? param.p_value : null,
        significance: param.significance || '',
        pValueNum: param.p_value !== undefined ? Number(param.p_value) : null,
      })
    }
  }
  return result
}

function buildColumnFromMethod(mval, fallbackLabel) {
  if (!mval) {
    return { error: '无数据', coefficients: [] }
  }
  if (mval.error) {
    return {
      error: mval.error,
      label: fallbackLabel,
      coefficients: [],
      nObs: null,
      rSquared: null,
      adjRSquared: null,
    }
  }
  const stats = mval.model_stats || {}
  return {
    label: fallbackLabel,
    dependentLabel: mval.dependent_var || fallbackLabel,
    modelName: mval.model_name || fallbackLabel,
    nObs: stats.n_obs ?? null,
    rSquared: stats.r_squared ?? null,
    adjRSquared: stats.adj_r_squared ?? null,
    fixedEffects: stats.fe_info || {},
    coefficients: buildCoefficients(mval),
  }
}

// 把回归数据扁平化为 AcademicTable 的列
const columns = computed(() => {
  if (!props.data || typeof props.data !== 'object') return []
  const cols = []
  for (const [modelKey, modelVal] of Object.entries(props.data)) {
    if (!modelVal || typeof modelVal !== 'object') continue
    // 新结构：{model_name, methods: {fe: {...}, ols: {...}}}
    if (modelVal.methods && typeof modelVal.methods === 'object') {
      for (const [mkey, mval] of Object.entries(modelVal.methods)) {
        if (!mval || typeof mval !== 'object') continue
        const label = mval.model_name || `${modelKey} - ${mkey}`
        cols.push(buildColumnFromMethod(mval, label))
      }
    } else if (modelVal.error && !modelVal.methods) {
      // 模型级错误
      cols.push({ error: modelVal.error, label: modelKey, coefficients: [] })
    } else if (modelVal.coefficients || modelVal.params) {
      // 单模型（旧结构）
      cols.push(buildColumnFromMethod(modelVal, modelVal.model_name || modelKey))
    }
  }
  return cols
})

const errorMessage = computed(() => {
  if (!props.data || typeof props.data !== 'object') return ''
  // 检查模型级错误
  for (const v of Object.values(props.data)) {
    if (v && typeof v === 'object' && v.error && !v.methods) return v.error
  }
  return ''
})

const fixedEffectRows = computed(() => {
  // 优先使用 props.fixedEffects；否则从所有 column 的 fixedEffects 合并去重 keys
  // 展示时用原 key 作为行名（用户传入什么变量名就显示什么）
  if (props.fixedEffects && props.fixedEffects.length > 0) return props.fixedEffects
  const keys = new Set()
  const rows = []
  for (const col of columns.value) {
    if (!col || !col.fixedEffects) continue
    for (const k of Object.keys(col.fixedEffects)) {
      if (keys.has(k)) continue
      keys.add(k)
      rows.push({ key: k, name: k })
    }
  }
  return rows
})
</script>

<style scoped>
.regression-results {
  padding: 0;
}

.error-block {
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 16px;
  color: #c45656;
}

.error-block .error-title {
  font-weight: 600;
  margin: 0 0 6px 0;
}

.empty-container {
  text-align: center;
  padding: 40px;
  color: #909399;
}

.empty-container details {
  margin-top: 12px;
  text-align: left;
}
</style>
