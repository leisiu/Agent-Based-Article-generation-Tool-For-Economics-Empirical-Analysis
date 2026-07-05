<template>
  <div class="robustness-results">
    <div v-if="errorMessage" class="error-block">
      <p class="error-title">⚠️ {{ errorMessage }}</p>
    </div>

    <!-- 异质性/机制/调节：所有方法合并到一张表（方法内多 step/subgroup 为 (1)(2) 列） -->
    <div v-else-if="effectiveMode === 'method-grouped'" class="robustness-groups">
      <template v-if="mergedMethodColumns.length > 0">
        <!-- 方法级元信息 -->
        <div v-if="mergedMethodInfo" class="result-info">
          <div v-if="mergedMethodInfo.mediator" class="info-row">
            <span class="info-label">中介变量：</span>
            <span class="info-value">{{ mergedMethodInfo.mediator }}</span>
          </div>
          <div v-if="mergedMethodInfo.groupVar" class="info-row">
            <span class="info-label">分组变量：</span>
            <span class="info-value">{{ mergedMethodInfo.groupVar }}</span>
          </div>
          <div v-if="mergedMethodInfo.median !== null && mergedMethodInfo.median !== undefined" class="info-row">
            <span class="info-label">分组中位数：</span>
            <span class="info-value">{{ mergedMethodInfo.median }}</span>
          </div>
        </div>
        <AcademicTable
          :title="mergedMethodTitle"
          :columns="mergedMethodColumns"
          :fixed-effects="mergedMethodFixedEffectRows"
        />
      </template>
      <template v-else>
        <!-- 方法组存在但无有效列：显示各方法的错误信息 -->
        <div v-for="g in methodGroupsWithErrors" :key="g.key" class="method-error-item">
          <p class="method-error-label">{{ g.label }}</p>
          <p class="method-error-detail">{{ g.error }}</p>
        </div>
        <div v-if="methodGroupsWithErrors.length === 0" class="empty-container">
          <p>暂无数据</p>
        </div>
      </template>
    </div>

    <!-- 稳健性/其他：所有检验方法合并为一张表，各方法为 (1)(2)(3) 列 -->
    <div v-else-if="robustnessMergedColumns.length > 0" class="robustness-groups">
      <AcademicTable
        :title="robustnessTitle"
        :columns="robustnessMergedColumns"
        :fixed-effects="robustnessMergedFixedEffectRows"
      />
    </div>

    <!-- 旧结构兼容：单张表 -->
    <AcademicTable
      v-else-if="legacyColumns.length > 0"
      :title="legacyTitle"
      :columns="legacyColumns"
      :fixed-effects="legacyFixedEffectRows"
    />

    <div v-else class="empty-container">
      <p>暂无数据</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import AcademicTable from './AcademicTable.vue'
import { fmtNum } from '../utils/format.js'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  title: { type: String, default: '' },
  mode: { type: String, default: 'auto' }, // 'auto' | 'robustness' | 'method-grouped' | 'legacy'
})

const activeMethod = ref('')

const errorMessage = computed(() => {
  if (!props.data) return ''
  if (props.data.error) return props.data.error
  return ''
})

// =================== 系数解析（统一） ===================
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
      pValueNum: param.p_value !== undefined ? Number(param.p_value) : null,
    })
  }
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

// 从 fixed_effects 字典推导 [{ key, name }] 行
function deriveFixedEffectRows(feDict) {
  const rows = []
  if (!feDict || typeof feDict !== 'object') return rows
  for (const k of Object.keys(feDict)) {
    rows.push({ key: k, name: k })
  }
  return rows
}

// =================== 稳健性检验：所有检验方法合并为一张表 ===================
const robustnessTitle = computed(() => props.title || '稳健性检验')

const robustnessMergedColumns = computed(() => {
  if (!props.data || typeof props.data !== 'object') return []
  const allCols = []

  // 新结构：{test_type: {label, baselines: {bm_name: {name, methods: {mt: result}}}}}
  for (const [tkey, tval] of Object.entries(props.data)) {
    if (!tval || typeof tval !== 'object') continue

    if (tval.baselines && typeof tval.baselines === 'object') {
      // 多 baseline 结构
      for (const bmVal of Object.values(tval.baselines)) {
        if (!bmVal || typeof bmVal !== 'object') continue
        const methods = bmVal.methods || {}
        for (const mv of Object.values(methods)) {
          if (!mv || typeof mv !== 'object') continue
          allCols.push(buildColumnFromMethod(mv, bmVal.name || ''))
        }
      }
    } else {
      // 旧结构（兼容）：平铺
      for (const sv of Object.values(tval)) {
        if (sv && typeof sv === 'object' && (sv.model_name || sv.model_stats || sv.coefficients)) {
          allCols.push(buildColumnFromMethod(sv, ''))
        }
      }
    }
  }
  return allCols
})

const robustnessMergedFixedEffectRows = computed(() => {
  const rows = []
  const seen = new Set()
  for (const col of robustnessMergedColumns.value) {
    if (!col || !col.fixedEffects) continue
    for (const r of deriveFixedEffectRows(col.fixedEffects)) {
      if (seen.has(r.key)) continue
      seen.add(r.key)
      rows.push(r)
    }
  }
  return rows
})

// =================== 异质性/机制：每个 method 一张表 ===================
// 把任一 test 值（可能是 model / methods-map / 嵌套 baselines / 单步结构）展开成一组列
function flattenTestToColumns(tkey, tval) {
  const cols = []
  if (!tval || typeof tval !== 'object') return cols
  if (tval.error) {
    cols.push({ error: tval.error, label: `${tkey}`, coefficients: [] })
    return cols
  }
  // 单 model
  if (tval.model_name || tval.model_stats || tval.coefficients) {
    cols.push(buildColumnFromMethod(tval, tkey))
    return cols
  }
  // methods 字典
  if (tval.methods && typeof tval.methods === 'object') {
    for (const [mk, mv] of Object.entries(tval.methods)) {
      cols.push(...flattenTestToColumns(`${tkey} - ${mk}`, mv))
    }
    return cols
  }
  // 多 baseline 结构：{baseline_name: {group_key: {mt: result}}}
  // 或 {baseline_name: {mt: result}}  /  {baseline_name: {step: result}}
  let looksLikeBaselineMap = false
  for (const [, bv] of Object.entries(tval)) {
    if (bv && typeof bv === 'object' && !bv.model_name && !bv.model_stats && !bv.coefficients
        && !bv.error && !bv.methods) {
      looksLikeBaselineMap = true
      break
    }
  }
  if (looksLikeBaselineMap) {
    for (const [bmk, bmv] of Object.entries(tval)) {
      cols.push(...flattenTestToColumns(`${tkey} - ${bmk}`, bmv))
    }
    return cols
  }
  // 机制 step* 结构 / 通用 {step_name: model}
  for (const [sk, sv] of Object.entries(tval)) {
    if (sv && typeof sv === 'object') {
      if (sv.model_name || sv.model_stats || sv.coefficients) {
        cols.push(buildColumnFromMethod(sv, `${tkey} - ${sk}`))
      } else if (sv.methods) {
        for (const [mk, mv] of Object.entries(sv.methods)) {
          cols.push(buildColumnFromMethod(mv, `${tkey} - ${sk} - ${mk}`))
        }
      }
    }
  }
  return cols
}

function buildMethodGroup(mkey, mval) {
  if (!mval || typeof mval !== 'object') return null
  // 错误方法
  if (mval.error && !mval.methods) {
    return {
      key: mkey,
      label: mval.method_label || mval.method || mkey,
      methodLabel: mval.method_label || mval.method || '',
      groupVar: mval.group_var || '',
      mediator: mval.mediator || '',
      moderator: mval.moderator || '',
      median: mval.median ?? null,
      error: mval.error,
      columns: [],
      fixedEffectRows: [],
    }
  }
  // mval.tests = {test_key: mval | {methods: {...}} | {step1, step2, ...} | {baseline: {...}}}
  const tests = mval.tests || {}
  const cols = []
  for (const [tkey, tval] of Object.entries(tests)) {
    cols.push(...flattenTestToColumns(tkey, tval))
  }
  // 如果 mval 直接是 {baselines: ...}（无 tests），则展开 baselines
  if (cols.length === 0 && mval.baselines && typeof mval.baselines === 'object') {
    for (const [bmk, bmv] of Object.entries(mval.baselines)) {
      cols.push(...flattenTestToColumns(bmk, bmv))
    }
  }
  // 如果通过 tests / baselines 均未提取到列，检查 mval 自身是否为单模型
  if (cols.length === 0 && (mval.model_name || mval.model_stats || mval.coefficients)) {
    cols.push(buildColumnFromMethod(mval, mkey))
  }
  // 从所有列的 fixedEffects 提取固定效应行
  const feRows = []
  const seen = new Set()
  for (const col of cols) {
    if (!col || !col.fixedEffects) continue
    for (const r of deriveFixedEffectRows(col.fixedEffects)) {
      if (seen.has(r.key)) continue
      seen.add(r.key)
      feRows.push(r)
    }
  }
  const emptyReason = cols.length === 0
    ? (mval.error || '数据格式无法解析，未提取到有效回归列')
    : null
  return {
    key: mkey,
    label: mval.method_label || mval.method || mkey,
    methodLabel: mval.method_label || mval.method || '',
    groupVar: mval.group_var || '',
    mediator: mval.mediator || '',
    moderator: mval.moderator || '',
    median: mval.median ?? null,
    error: emptyReason,
    columns: cols,
    fixedEffectRows: feRows,
  }
}

const methodGroups = computed(() => {
  if (!props.data || typeof props.data !== 'object') return []
  // 新结构：{methods: {mkey: mval}}
  if (props.data.methods && typeof props.data.methods === 'object') {
    const groups = []
    for (const [mk, mv] of Object.entries(props.data.methods)) {
      const g = buildMethodGroup(mk, mv)
      if (g) groups.push(g)
    }
    // 默认选中第一个
    if (groups.length > 0 && !activeMethod.value) {
      activeMethod.value = groups[0].key
    }
    return groups
  }
  return []
})

// =================== 合并所有方法到一张表（机制/异质性/调节） ===================
const mergedMethodColumns = computed(() => {
  const groups = methodGroups.value
  if (groups.length === 0) return []
  const allCols = []
  for (const g of groups) {
    for (const c of (g.columns || [])) {
      allCols.push(c)
    }
  }
  return allCols
})

const mergedMethodFixedEffectRows = computed(() => {
  const rows = []
  const seen = new Set()
  for (const col of mergedMethodColumns.value) {
    if (!col || !col.fixedEffects) continue
    for (const r of deriveFixedEffectRows(col.fixedEffects)) {
      if (seen.has(r.key)) continue
      seen.add(r.key)
      rows.push(r)
    }
  }
  return rows
})

const mergedMethodInfo = computed(() => {
  const groups = methodGroups.value
  if (groups.length === 0) return null
  // 从第一个有中介变量/分组变量的方法组提取元信息
  for (const g of groups) {
    if (g.mediator || g.groupVar || g.median !== null) {
      return { mediator: g.mediator, groupVar: g.groupVar, median: g.median }
    }
  }
  return null
})

// 在 method-grouped 模式下，收集有错误信息的方法组用于展示
const methodGroupsWithErrors = computed(() => {
  const groups = methodGroups.value
  if (groups.length === 0) return []
  return groups.filter(g => g.error).map(g => ({
    key: g.key,
    label: g.label,
    error: g.error,
  }))
})

const mergedMethodTitle = computed(() => {
  const groups = methodGroups.value
  if (groups.length === 0) return props.title || ''
  // 用第一个方法的 label
  return groups[0].label || props.title || ''
})

// =================== 旧结构（兼容）：把 tests 平铺 ===================
const legacyTitle = computed(() => props.title || '检验结果')

const legacyColumns = computed(() => {
  if (!props.data || typeof props.data !== 'object') return []
  const cols = []
  // 旧结构可能为 {tests: {test_key: mval, ...}}
  const tests = props.data.tests || props.data
  for (const [k, v] of Object.entries(tests)) {
    if (['count', 'error', 'methods'].includes(k)) continue
    if (v && typeof v === 'object') {
      if (v.model_name || v.model_stats || v.coefficients) {
        cols.push(buildColumnFromMethod(v, k))
      } else if (v.methods) {
        for (const [mk, mv] of Object.entries(v.methods)) {
          cols.push(buildColumnFromMethod(mv, `${k} - ${mk}`))
        }
      }
    }
  }
  return cols
})

const legacyFixedEffectRows = computed(() => {
  const rows = []
  const seen = new Set()
  for (const col of legacyColumns.value) {
    if (!col || !col.fixedEffects) continue
    for (const r of deriveFixedEffectRows(col.fixedEffects)) {
      if (seen.has(r.key)) continue
      seen.add(r.key)
      rows.push(r)
    }
  }
  return rows
})

// 自动选择 mode
const effectiveMode = computed(() => {
  if (props.mode && props.mode !== 'auto') return props.mode
  if (!props.data || typeof props.data !== 'object') return 'legacy'
  if (props.data.methods) return 'method-grouped'
  if (props.data.tests && Object.keys(props.data.tests).length > 0) return 'legacy'
  return 'legacy'
})
</script>

<style scoped>
.robustness-results {
  padding: 0;
}

.result-info {
  background: #f5f7fa;
  padding: 12px 16px;
  border-radius: 4px;
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  margin-bottom: 6px;
  font-size: 13px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-label {
  display: inline-block;
  width: 110px;
  font-weight: 500;
  color: #606266;
}

.info-value {
  color: #303133;
}

.error-block {
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 16px;
  color: #c45656;
  font-size: 13px;
}

.robustness-group {
  margin-bottom: 24px;
}

.robustness-group:last-child {
  margin-bottom: 0;
}

.empty-container {
  text-align: center;
  padding: 40px;
  color: #909399;
}

.method-error-item {
  background: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 8px;
}

.method-error-label {
  font-weight: 600;
  color: #f56c6c;
  margin: 0 0 4px;
  font-size: 14px;
}

.method-error-detail {
  color: #606266;
  margin: 0;
  font-size: 13px;
}
</style>
