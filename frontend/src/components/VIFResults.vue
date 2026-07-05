<template>
  <div class="vif-results">
    <div v-if="tableData.length > 0">
      <el-table :data="tableData" border stripe>
        <el-table-column prop="variable" label="变量" />
        <el-table-column prop="vif" label="VIF值" />
        <el-table-column label="状态">
          <template #default="{ row }">
            <span :class="getStatusClass(row.vif)">
              {{ getStatusText(row.vif) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="meanVif" class="vif-summary">
        <p>平均VIF: {{ fmtNum(meanVif) }} | 最大VIF: {{ fmtNum(maxVif) }}</p>
      </div>
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

const tableData = computed(() => {
  if (!props.data || !props.data.vif_values) return []

  const vifValues = props.data.vif_values
  return Object.keys(vifValues).map(variable => ({
    variable,
    vif: fmtNum(vifValues[variable])
  }))
})

const meanVif = computed(() => {
  return props.data?.mean_vif
})

const maxVif = computed(() => {
  return props.data?.max_vif
})

const getStatusClass = (vif) => {
  const numVif = parseFloat(vif)
  if (numVif > 10) return 'status-danger'
  if (numVif > 5) return 'status-warning'
  return 'status-success'
}

const getStatusText = (vif) => {
  const numVif = parseFloat(vif)
  if (numVif > 10) return '严重共线性'
  if (numVif > 5) return '可能共线性'
  return '正常'
}
</script>

<style scoped>
.vif-results {
  padding: 20px;
}

.vif-summary {
  margin-top: 15px;
  font-size: 14px;
  color: #606266;
}

.status-danger {
  color: #f56c6c;
  font-weight: 500;
}

.status-warning {
  color: #e6a23c;
  font-weight: 500;
}

.status-success {
  color: #67c23a;
  font-weight: 500;
}
</style>
