<template>
  <div class="descriptive-statistics">
    <el-table :data="tableData" border stripe v-if="tableData.length > 0">
      <el-table-column prop="variable" label="变量" />
      <el-table-column prop="N" label="观测值" />
      <el-table-column prop="mean" label="均值" />
      <el-table-column prop="std" label="标准差" />
      <el-table-column prop="min" label="最小值" />
      <el-table-column prop="p25" label="25分位" />
      <el-table-column prop="median" label="中位数" />
      <el-table-column prop="p75" label="75分位" />
      <el-table-column prop="max" label="最大值" />
    </el-table>
    <el-empty v-else description="暂无数据" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtNum } from '../utils/format.js'

const props = defineProps({
  data: {
    type: Object,
    default: () => ({}),
  },
})

const tableData = computed(() => {
  if (!props.data || typeof props.data !== 'object') return []

  const variables = props.data.variables || props.data.stats || props.data
  if (Array.isArray(variables)) return variables

  return Object.keys(variables).map(variable => {
    const stat = variables[variable]
    if (!stat || typeof stat !== 'object') return { variable, N: '-', mean: '-', std: '-', min: '-', p25: '-', median: '-', p75: '-', max: '-' }
    return {
      variable,
      N: stat.count ?? stat.N ?? '-',
      mean: fmtNum(stat.mean),
      std: fmtNum(stat.std),
      min: fmtNum(stat.min),
      p25: stat['25%'] ?? stat.p25 ?? '-',
      median: stat.median ?? stat['50%'] ?? '-',
      p75: stat['75%'] ?? stat.p75 ?? '-',
      max: fmtNum(stat.max),
    }
  })
})
</script>
