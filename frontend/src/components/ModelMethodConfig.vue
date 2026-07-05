<template>
  <div class="model-method-config">
    <!-- Step 1: 回归命令选择（互斥单选） -->
    <div class="form-row">
      <label class="form-label">回归命令：</label>
      <div class="radio-method-group">
        <label
          v-for="opt in methodOptions"
          :key="opt.value"
          class="radio-method-item"
          :class="{ active: modelValue.method === opt.value }"
        >
          <input
            type="radio"
            :value="opt.value"
            :checked="modelValue.method === opt.value"
            @change="onMethodChange(opt.value)"
          />
          <span class="radio-method-label">{{ opt.label }}</span>
          <span v-if="opt.desc" class="radio-method-desc">{{ opt.desc }}</span>
        </label>
      </div>
    </div>

    <!-- Step 2: xtreg → 效应类型 + 面板数据声明 -->
    <template v-if="modelValue.method === 'xtreg'">
      <div class="sub-config">
        <div class="sub-config-header">效应类型 & 面板数据</div>
        <div class="form-row">
          <label class="form-label">效应类型：</label>
          <div class="radio-group">
            <label class="radio-item">
              <input
                type="radio"
                value="fe"
                :checked="modelValue.effectType === 'fe'"
                @change="onEffectTypeChange('fe')"
              />
              <span>固定效应 (FE)</span>
            </label>
            <label class="radio-item">
              <input
                type="radio"
                value="re"
                :checked="modelValue.effectType === 're'"
                @change="onEffectTypeChange('re')"
              />
              <span>随机效应 (RE)</span>
            </label>
          </div>
        </div>
        <div class="panel-declare">
          <div class="form-row">
            <label class="form-label">个体变量：</label>
            <select
              :value="modelValue.entityCol"
              @change="onEntityColChange(($event.target).value)"
              class="form-select"
            >
              <option value="">请选择</option>
              <option v-for="col in availableCols" :key="col" :value="col">{{ col }}</option>
            </select>
            <span class="selected-hint mandatory">* 必选（面板个体维度）</span>
          </div>
          <div class="form-row">
            <label class="form-label">时间变量：</label>
            <select
              :value="modelValue.timeCol"
              @change="onTimeColChange(($event.target).value)"
              class="form-select"
            >
              <option value="">请选择</option>
              <option v-for="col in availableCols" :key="col" :value="col">{{ col }}</option>
            </select>
            <span class="selected-hint mandatory">* 必选（面板时间维度）</span>
          </div>
        </div>
      </div>
    </template>

    <!-- Step 2b: reghdfe → 个体和时间固定效应 -->
    <template v-if="modelValue.method === 'reghdfe'">
      <div class="sub-config">
        <div class="sub-config-header">固定效应变量</div>
        <div class="form-row">
          <label class="form-label">个体变量：</label>
          <select
            :value="modelValue.entityCol"
            @change="onEntityColChange(($event.target).value)"
            class="form-select"
          >
            <option value="">不选择</option>
            <option v-for="col in availableCols" :key="col" :value="col">{{ col }}</option>
          </select>
          <span class="selected-hint">个体固定效应（可选，建议选）</span>
        </div>
        <div class="form-row">
          <label class="form-label">时间变量：</label>
          <select
            :value="modelValue.timeCol"
            @change="onTimeColChange(($event.target).value)"
            class="form-select"
          >
            <option value="">不选择</option>
            <option v-for="col in availableCols" :key="col" :value="col">{{ col }}</option>
          </select>
          <span class="selected-hint">时间固定效应（可选）</span>
        </div>
      </div>
    </template>

    <!-- reg / logit / probit 无额外选项 -->
    <p v-if="['reg', 'logit', 'probit'].includes(modelValue.method)" class="method-hint">
      {{ getMethodHint(modelValue.method) }}
    </p>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({
      method: '',
      effectType: 'fe',
      entityCol: '',
      timeCol: '',
    }),
  },
  availableCols: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:modelValue'])

const methodOptions = [
  { value: 'reg', label: 'reg', desc: '普通最小二乘回归' },
  { value: 'xtreg', label: 'xtreg', desc: '面板数据回归（FE/RE）' },
  { value: 'reghdfe', label: 'reghdfe', desc: '高维固定效应回归' },
  { value: 'logit', label: 'Logit', desc: '二元Logit回归' },
  { value: 'probit', label: 'Probit', desc: '二元Probit回归' },
]

function getMethodHint(method) {
  const map = {
    reg: '使用 statsmodels 执行普通最小二乘 (OLS) 回归，无需额外配置。',
    logit: '使用 statsmodels 执行二元 Logit 回归，无需额外配置。',
    probit: '使用 statsmodels 执行二元 Probit 回归，无需额外配置。',
  }
  return map[method] || ''
}

function emitUpdate(partial) {
  emit('update:modelValue', { ...props.modelValue, ...partial })
}

function onMethodChange(val) {
  // 切换方法时重置子选项
  const reset = {
    method: val,
    effectType: 'fe',
    entityCol: '',
    timeCol: '',
  }
  emit('update:modelValue', reset)
}

function onEffectTypeChange(val) {
  emitUpdate({ effectType: val })
}

function onEntityColChange(val) {
  emitUpdate({ entityCol: val })
}

function onTimeColChange(val) {
  emitUpdate({ timeCol: val })
}
</script>

<style scoped>
.model-method-config {
  margin: 8px 0;
}

/* ====== 方法按钮组（类 Stata 风格） ====== */
.radio-method-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.radio-method-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  background: #fff;
  transition: all 0.2s;
  user-select: none;
}

.radio-method-item:hover {
  border-color: #409eff;
  color: #409eff;
}

.radio-method-item.active {
  border-color: #409eff;
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}

.radio-method-item input[type="radio"] {
  display: none;
}

.radio-method-label {
  font-size: 14px;
  font-weight: 500;
}

.radio-method-desc {
  font-size: 11px;
  color: #909399;
  margin-left: 4px;
}

.radio-method-item.active .radio-method-desc {
  color: #8cc5ff;
}

/* ====== 效应类型（FE/RE 互斥单选） ====== */
.radio-group {
  display: flex;
  gap: 16px;
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 13px;
}

.radio-item input[type="radio"] {
  accent-color: #409eff;
}

/* ====== 子配置区域 ====== */
.sub-config {
  margin-top: 12px;
  padding: 12px 16px;
  background: #f8f9fb;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  border-left: 3px solid #409eff;
}

.sub-config-header {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #e4e7ed;
}

.panel-declare {
  margin-top: 4px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.form-label {
  font-size: 13px;
  color: #606266;
  min-width: 70px;
  flex-shrink: 0;
}

.form-select {
  padding: 6px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
  background: #fff;
  min-width: 160px;
  color: #303133;
}

.form-select:focus {
  outline: none;
  border-color: #409eff;
}

.selected-hint {
  font-size: 12px;
  color: #909399;
}

.selected-hint.mandatory {
  color: #e68a2e;
}

.method-hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #909399;
  padding: 6px 10px;
  background: #fafbfc;
  border-radius: 4px;
}
</style>
