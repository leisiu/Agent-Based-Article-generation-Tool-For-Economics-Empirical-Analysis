<template>
  <div class="academic-table-wrapper">
    <h4 v-if="title" class="academic-table-title">{{ title }}</h4>
    <div v-if="errorMessage" class="academic-table-error">
      <p>⚠️ {{ errorMessage }}</p>
    </div>
    <div v-else-if="columns.length === 0" class="academic-table-empty">
      <p>📊 暂无回归结果</p>
      <p class="empty-hint">请先在「变量配置」中设置变量并运行实证分析</p>
    </div>
    <div v-else-if="!hasAnyData" class="academic-table-empty">
      <p v-if="firstColError" class="empty-hint empty-error">⚠️ {{ firstColError }}</p>
      <p v-else>📊 回归已完成但未生成有效系数</p>
    </div>
    <div v-else class="academic-table-scroll">
      <table class="academic-table">
        <thead>
          <tr class="tbl-head-num">
            <th class="tbl-vars-head" rowspan="2">VARIABLES</th>
            <th
              v-for="(col, idx) in columns"
              :key="`head-${idx}`"
              class="tbl-col-head"
            >
              ({{ idx + 1 }})
            </th>
          </tr>
          <tr class="tbl-head-dep">
            <th
              v-for="(col, idx) in columns"
              :key="`dep-${idx}`"
              class="tbl-col-dep"
            >
              {{ col.dependentLabel || '-' }}
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="varName in orderedVars" :key="`var-${varName}`">
            <!-- 系数行 -->
            <tr class="tbl-coef-row">
              <td class="tbl-var-label">{{ varName }}</td>
              <td
                v-for="(col, idx) in columns"
                :key="`coef-${varName}-${idx}`"
                class="tbl-num-cell"
              >
                <span class="tbl-coef">{{ getCoef(col, varName) }}</span>
                <span class="tbl-sig">{{ getSig(col, varName) }}</span>
              </td>
            </tr>
            <!-- t值行 -->
            <tr class="tbl-t-row">
              <td class="tbl-var-sub"></td>
              <td
                v-for="(col, idx) in columns"
                :key="`t-${varName}-${idx}`"
                class="tbl-num-cell tbl-t-cell"
              >
                {{ getTValue(col, varName) }}
              </td>
            </tr>
            <!-- 标准误行（稳健标准误） -->
            <tr class="tbl-se-row">
              <td class="tbl-var-sub"></td>
              <td
                v-for="(col, idx) in columns"
                :key="`se-${varName}-${idx}`"
                class="tbl-num-cell tbl-se-cell"
              >
                {{ getStdErr(col, varName) }}
              </td>
            </tr>
          </template>

          <!-- 底部元信息 -->
          <tr v-if="hasNobs" class="tbl-meta-row">
            <td class="tbl-meta-label">Observations</td>
            <td
              v-for="(col, idx) in columns"
              :key="`nobs-${idx}`"
              class="tbl-num-cell"
            >
              {{ col.nObs != null ? col.nObs : '' }}
            </td>
          </tr>
          <tr v-if="hasRSquared" class="tbl-meta-row">
            <td class="tbl-meta-label">R-squared</td>
            <td
              v-for="(col, idx) in columns"
              :key="`r2-${idx}`"
              class="tbl-num-cell"
            >
              {{ col.rSquared != null ? formatNum(col.rSquared) : '' }}
            </td>
          </tr>
          <tr v-if="hasAdjR" class="tbl-meta-row">
            <td class="tbl-meta-label">Adj R-squared</td>
            <td
              v-for="(col, idx) in columns"
              :key="`adjr-${idx}`"
              class="tbl-num-cell"
            >
              {{ col.adjRSquared != null ? formatNum(col.adjRSquared) : '' }}
            </td>
          </tr>

          <!-- 固定效应行（按用户传入的 fixed_effects 填写） -->
          <tr
            v-for="(fe, feIdx) in fixedEffectRows"
            :key="`fe-${feIdx}`"
            class="tbl-meta-row"
          >
            <td class="tbl-meta-label">{{ fe.name }}固定效应</td>
            <td
              v-for="(col, idx) in columns"
              :key="`fe-${feIdx}-${idx}`"
              class="tbl-num-cell"
            >
              {{ getFEValue(col, fe.key) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="significance-note">
      <p>系数（标准误为稳健标准误），显著性水平: *** p&lt;0.01, ** p&lt;0.05, * p&lt;0.1</p>
      <p>t statistics in parentheses. Standard errors in parentheses.</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtNum } from '../utils/format.js'

const props = defineProps({
  title: { type: String, default: '' },
  columns: { type: Array, default: () => [] },
  errorMessage: { type: String, default: '' },
  // 固定效应行：[{ key: 'individual', name: '个体' }, ...]
  // 根据各 column 的 fixedEffects 字典判断"是"或"否"
  fixedEffects: { type: Array, default: () => [] },
})

const errorMessage = computed(() => props.errorMessage)

function formatNum(v) {
  return fmtNum(v)
}

const hasNobs = computed(() =>
  props.columns.some(c => c && c.nObs !== null && c.nObs !== undefined && c.nObs !== '')
)
const hasRSquared = computed(() =>
  props.columns.some(c => c && c.rSquared !== null && c.rSquared !== undefined)
)
const hasAdjR = computed(() =>
  props.columns.some(c => c && c.adjRSquared !== null && c.adjRSquared !== undefined)
)

const fixedEffectRows = computed(() => props.fixedEffects || [])

// 1. 汇总所有变量名（按出现顺序），常数项放最末
const orderedVars = computed(() => {
  const set = new Set()
  const order = []
  for (const col of props.columns) {
    for (const row of col.coefficients || []) {
      if (row && row.variable && !set.has(row.variable)) {
        set.add(row.variable)
        order.push(row.variable)
      }
    }
  }
  // 把"常数项"移到最后
  const constIdx = order.indexOf('常数项')
  if (constIdx >= 0) {
    order.splice(constIdx, 1)
    order.push('常数项')
  }
  return order
})

// 检查是否有任何有效数据
const hasAnyData = computed(() => {
  if (!props.columns || props.columns.length === 0) return false
  // 至少有一列包含系数数据
  return props.columns.some(col => col && col.coefficients && col.coefficients.length > 0)
})

// 提取第一列的错误信息（用于"未生成有效系数"分支展示）
const firstColError = computed(() => {
  if (!props.columns || props.columns.length === 0) return ''
  for (const col of props.columns) {
    if (col && col.error) return col.error
  }
  return ''
})

function findRow(col, varName) {
  if (!col || !col.coefficients) return null
  return col.coefficients.find(r => r && r.variable === varName) || null
}

function getCoef(col, varName) {
  if (col.error) return '-'
  const row = findRow(col, varName)
  if (!row) return ''
  const c = row.coef
  if (c === null || c === undefined || c === '') return ''
  return fmtNum(c, 4)
}

function getTValue(col, varName) {
  if (col.error) return '-'
  const row = findRow(col, varName)
  if (!row) return ''
  // 兼容多种字段名：t_value（后端） / tStat（部分早期版本） / t
  const t = row.t_value ?? row.tStat ?? row.t
  if (t === null || t === undefined || t === '') return ''
  const num = typeof t === 'number' ? t : Number(t)
  if (Number.isNaN(num)) return ''
  return `(${num.toFixed(4)})`
}

function getStdErr(col, varName) {
  if (col.error) return '-'
  const row = findRow(col, varName)
  if (!row) return ''
  // 后端字段：std_err
  const se = row.std_err ?? row.stdErr ?? row.se
  if (se === null || se === undefined || se === '') return ''
  const num = typeof se === 'number' ? se : Number(se)
  if (Number.isNaN(num)) return ''
  return `(${num.toFixed(4)})`
}

function getSig(col, varName) {
  if (col.error) return ''
  const row = findRow(col, varName)
  if (!row) return ''
  const p = row.pValueNum
  if (p === null || p === undefined) return ''
  if (p < 0.01) return '***'
  if (p < 0.05) return '**'
  if (p < 0.1) return '*'
  return ''
}

function getFEValue(col, feKey) {
  if (col.error) return '-'
  if (!col.fixedEffects || typeof col.fixedEffects !== 'object') return '否'
  const v = col.fixedEffects[feKey]
  if (v === true || v === 'true' || v === '是' || v === 1) return '是'
  if (v === false || v === 'false' || v === '否' || v === 0) return '否'
  if (typeof v === 'string' && v.trim()) return v
  return '否'
}
</script>

<style scoped>
.academic-table-wrapper {
  margin: 12px 0 20px 0;
}

.academic-table-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 8px 0 10px 0;
}

.academic-table-error {
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  padding: 10px 14px;
  border-radius: 4px;
  color: #c45656;
  font-size: 13px;
}

.academic-table-empty {
  text-align: center;
  padding: 24px 16px;
  color: #909399;
  font-size: 13px;
  background: #fafbfc;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  margin: 8px 0;
}

.academic-table-empty p {
  margin: 6px 0;
}

.academic-table-empty .empty-hint {
  color: #909399;
  font-size: 12px;
  margin: 4px 0;
}

.academic-table-empty .empty-reasons {
  display: inline-block;
  text-align: left;
  margin: 8px auto;
  color: #c45656;
  font-size: 12px;
  line-height: 1.8;
  list-style: disc;
  padding-left: 20px;
}

.academic-table-empty .empty-error {
  color: #c45656;
  font-weight: 500;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 4px;
  padding: 6px 10px;
  display: inline-block;
  margin: 6px 0;
  max-width: 90%;
  word-break: break-all;
}

.academic-table-scroll {
  overflow-x: auto;
}

.academic-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: #fff;
  border-top: 3px double #303133;
  border-bottom: 1px solid #303133;
}

.academic-table th,
.academic-table td {
  padding: 6px 10px;
  text-align: right;
  vertical-align: middle;
  font-variant-numeric: tabular-nums;
  border: none;
}

.academic-table th {
  font-weight: 600;
  color: #303133;
}

.academic-table .tbl-vars-head {
  text-align: left;
  vertical-align: bottom;
  font-weight: 700;
  width: 110px;
  min-width: 110px;
  border-right: 1px solid #303133;
}

.academic-table .tbl-col-head {
  text-align: center;
  font-weight: 600;
  font-size: 13px;
  min-width: 80px;
}

.academic-table .tbl-head-num th {
  border-bottom: 1px solid #303133;
}

.academic-table .tbl-head-dep th {
  font-weight: 500;
  font-style: italic;
  color: #606266;
  text-align: center;
  font-size: 12px;
  border-bottom: 1px solid #303133;
}

.academic-table .tbl-var-label {
  text-align: left;
  font-weight: 500;
  padding-left: 4px;
  padding-right: 12px;
  border-right: 1px solid #c0c4cc;
}

.academic-table .tbl-var-sub {
  text-align: left;
  padding-left: 4px;
  border-right: 1px solid #c0c4cc;
}

.academic-table .tbl-coef-row td,
.academic-table .tbl-t-row td {
  padding-top: 4px;
  padding-bottom: 4px;
}

.academic-table .tbl-t-row td {
  color: #606266;
  font-size: 12px;
  font-style: italic;
  border-bottom: 1px dotted #dcdfe6;
}

.academic-table .tbl-se-row td {
  color: #909399;
  font-size: 12px;
  border-bottom: 1px solid #ebeef5;
}

.academic-table .tbl-se-cell {
  font-style: italic;
}

.academic-table .tbl-meta-row td {
  padding-top: 4px;
  padding-bottom: 4px;
  font-size: 12px;
}

.academic-table .tbl-meta-label {
  text-align: left;
  font-style: italic;
  color: #606266;
  border-right: 1px solid #c0c4cc;
  padding-left: 4px;
}

.academic-table .tbl-num-cell {
  text-align: right;
  font-feature-settings: "tnum";
}

.academic-table .tbl-coef {
  font-weight: 500;
  color: #303133;
}

.academic-table .tbl-sig {
  margin-left: 2px;
  color: #303133;
  font-weight: 600;
}

.academic-table .tbl-t-cell {
  font-style: italic;
  color: #606266;
}

.significance-note {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  text-align: left;
}

.significance-note p {
  margin: 0;
}
</style>
