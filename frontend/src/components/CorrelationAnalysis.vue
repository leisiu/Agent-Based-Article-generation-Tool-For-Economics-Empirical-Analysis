<template>
  <div class="correlation-analysis">
    <div v-if="tableData.length > 0">
      <el-table :data="tableData" border stripe class="correlation-table">
        <el-table-column prop="variable" label="变量" fixed />
        <el-table-column v-for="col in displayColumns" :key="col.key" :prop="col.prop" :label="col.label" />
      </el-table>
    </div>
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

// 将对象格式转换为数组格式
const tableData = computed(() => {
  if (!props.data || !props.data.pearson) return []
  
  const pearson = props.data.pearson
  const variables = Object.keys(pearson)
  
  return variables.map(variable => {
    const row = { variable }
    variables.forEach((v, idx) => {
      row[`col_${idx}`] = fmtNum(pearson[variable]?.[v])
    })
    return row
  })
})

const displayColumns = computed(() => {
  if (!props.data || !props.data.pearson) return []
  
  const variables = Object.keys(props.data.pearson)
  return variables.map((v, idx) => ({
    key: idx,
    prop: `col_${idx}`,
    label: v
  }))
})
</script>

<style scoped>
.correlation-analysis {
  padding: 20px;
}

.correlation-table {
  margin-top: 20px;
}
</style>
