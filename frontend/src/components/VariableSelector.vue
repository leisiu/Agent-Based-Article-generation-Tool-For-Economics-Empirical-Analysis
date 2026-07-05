<template>
  <el-card class="variable-selector">
    <template #header>
      <span class="card-title">实证分析配置</span>
    </template>

    <div class="form-container">
      <!-- 模块选择按钮行 -->
      <div class="module-tab-bar">
        <button
          v-for="mod in moduleTabs"
          :key="mod.key"
          class="module-tab-btn"
          :class="{ active: selectedModule === mod.key }"
          @click="selectedModule = mod.key"
        >
          <span class="tab-icon">{{ mod.icon }}</span>
          <span class="tab-title">{{ mod.title }}</span>
          <el-tag v-if="mod.required" size="small" type="danger" class="tab-tag">必选</el-tag>
          <span v-if="mod.summary" class="tab-summary">{{ mod.summary }}</span>
        </button>
      </div>

      <!-- ==================== 模块1: 基准回归（必选） ==================== -->
      <div v-show="selectedModule === 'baseline'" class="module-card module-expanded">
          <div v-for="(model, idx) in baselineModels" :key="model.id" class="model-card" :class="{ 'is-collapsed': isModelCollapsed(model.id) }">
            <div class="model-card-header" @click="toggleModelCollapse(model.id)">
              <span class="model-card-arrow">{{ isModelCollapsed(model.id) ? '▶' : '▼' }}</span>
              <span class="model-card-title">模型 {{ idx + 1 }}</span>
              <span class="model-card-summary" v-if="model.dependentVar">
                {{ model.dependentVar }} ~ {{ model.independentVars.join('+') || '?' }}<span v-if="model.controlVars.length"> + {{ model.controlVars.length }}个控制</span>
              </span>
              <span v-if="baselineModels.length > 1" class="model-card-remove" @click.stop="removeBaselineModel(idx)">✕ 删除</span>
            </div>

            <div v-show="!isModelCollapsed(model.id)" class="model-card-body">
              <!-- 被解释变量 -->
              <div class="form-row">
                <label class="form-label">被解释变量：</label>
                <select v-model="model.dependentVar" class="form-select">
                  <option value="">请选择</option>
                  <option v-for="(col, i) in columns" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>

              <!-- 解释变量 -->
              <div class="form-row">
                <label class="form-label">解释变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in columns" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="model.independentVars.includes(col)"
                      @change="toggleModelIndependent(idx, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ model.independentVars.length }} 个</span>
              </div>

              <!-- 控制变量 -->
              <div class="form-row">
                <label class="form-label">控制变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in getAvailableControlVars(model)" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="model.controlVars.includes(col)"
                      @change="toggleModelControl(idx, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ model.controlVars.length }} 个</span>
              </div>

              <!-- 回归命令 + 子配置（ModelMethodConfig 复用组件） -->
              <ModelMethodConfig
                :modelValue="model.methodConfig"
                :availableCols="columns"
                @update:modelValue="onMethodConfigUpdate(idx, $event)"
              />

              <!-- 聚类标准误 -->
              <div class="form-row">
                <label class="form-label">聚类标准误：</label>
                <select v-model="model.clusterVar" class="form-select">
                  <option value="">不选择</option>
                  <option v-for="(col, i) in getAvailableClusterVars(model)" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>
            </div>
          </div>

          <button type="button" class="add-model-btn" @click="addBaselineModel">+ 添加模型</button>
        </div>

      <!-- ==================== 模块2: 稳健性检验（可选） ==================== -->
      <div v-show="selectedModule === 'robustness'" class="module-card module-expanded">
        <div class="module-body">
          <!-- 参与本检验的基准模型（多选） -->
          <div v-if="baselineModels.length > 1" class="form-row">
            <label class="form-label">参与本检验的基准模型：</label>
            <div class="checkbox-group">
              <label v-for="(m, idx) in baselineModelOptions" :key="m.id" class="checkbox-item baseline-model-item">
                <input type="checkbox" :value="m.id"
                  :checked="selectedRobustnessBaselineIds.includes(m.id)"
                  @change="toggleRobustnessBaseline(m.id)" />
                <span>模型{{ idx + 1 }}<span v-if="m.dependentVar" class="model-dep-hint">（{{ m.dependentVar }}）</span></span>
              </label>
            </div>
            <span class="selected-hint">已选: {{ selectedRobustnessBaselineIds.length }} / {{ baselineModels.length }} 个</span>
          </div>

          <div class="form-row">
            <label class="form-label">检验方法：</label>
            <div class="checkbox-group">
              <label v-for="test in robustnessOptions" :key="test.value" class="checkbox-item robust-item">
                <input type="checkbox" :value="test.value"
                  :checked="selectedRobustnessTests.includes(test.value)"
                  @change="toggleRobustnessTest(test.value)" />
                <span>{{ test.label }}</span>
              </label>
            </div>
          </div>

          <!-- 每个选中的稳健性方法：模型配置 + 方法特有配置 -->
          <div v-for="(rm, ri) in robustnessMethodConfigs" :key="rm.id" class="robust-config" :class="{ 'is-collapsed': isRobustCollapsed(rm.id) }">
            <div class="config-title" @click="toggleRobustCollapse(rm.id)" style="cursor:pointer;">
              <span>
                <span class="collapse-arrow">{{ isRobustCollapsed(rm.id) ? '▶' : '▼' }}</span>
                {{ getRobustnessMethodLabel(rm.method) }}
              </span>
            </div>

            <div v-show="!isRobustCollapsed(rm.id)">
            <!-- 导入自基准模型 -->
            <div class="model-import-row">
              <span class="form-label-sm">导入自模型：</span>
              <select class="form-select form-select-sm" @change="importRobustnessModel(ri, $event.target.value)">
                <option value="">— 选择基准模型 —</option>
                <option v-for="(m, mi) in baselineModelOptions" :key="m.id" :value="m.id">{{ m.name }}（{{ m.dependentVar || '?' }}）</option>
              </select>
              <span class="import-hint">将覆盖下方的变量配置</span>
            </div>

            <!-- 方法特有配置（优先显示，对应检验要求） -->
            <!-- 替换被解释变量 -->
            <div v-if="rm.method === 'replace_dep_var'" class="robust-sub-config">
              <div class="form-row">
                <label class="form-label">新被解释变量：</label>
                <select v-model="rm.newDepVar" class="form-select">
                  <option value="">请选择</option>
                  <option v-for="(col, idx) in replaceDepVarOptions" :key="idx" :value="col">{{ col }}</option>
                </select>
              </div>
            </div>

            <!-- 替换解释变量 -->
            <div v-if="rm.method === 'replace_indep_var'" class="robust-sub-config">
              <div v-for="(target, idx) in (rm.independentVars.length > 0 ? rm.independentVars : ['核心解释变量'])" :key="'rep-'+idx" class="form-row">
                <label class="form-label">{{ target }} →：</label>
                <select v-model="rm.replaceIndepVar[target]" class="form-select">
                  <option value="">不替换</option>
                  <option v-for="col in replaceIndepVarOptions" :key="col" :value="col">{{ col }}</option>
                </select>
              </div>
            </div>

            <!-- 缩短时间窗口 -->
            <div v-if="rm.method === 'shorten_window'" class="robust-sub-config">
              <div class="form-row">
                <label class="form-label">时间列：</label>
                <select v-model="rm.timeCol" class="form-select">
                  <option value="">自动检测</option>
                  <option v-for="(col, idx) in timeColOptions" :key="idx" :value="col">{{ col }}</option>
                </select>
              </div>
              <div class="form-row">
                <label class="form-label">剔除年份：</label>
                <div class="exclude-years">
                  <input type="text" v-model="rm.excludeYearsInput"
                    placeholder="如: 2015,2016,2017" class="form-input" />
                  <span class="hint">多个年份用逗号分隔</span>
                </div>
              </div>
            </div>

            <!-- 缩尾处理 -->
            <div v-if="rm.method === 'winsorize'" class="robust-sub-config">
              <div class="form-row">
                <label class="form-label">缩尾阈值：</label>
                <select v-model="rm.winsorizeThreshold" class="form-select" style="max-width:150px">
                  <option value="0.01">1% (双侧缩尾)</option>
                  <option value="0.025">2.5% (双侧缩尾)</option>
                  <option value="0.05">5% (双侧缩尾)</option>
                  <option value="0.1">10% (双侧缩尾)</option>
                </select>
              </div>
            </div>

            <!-- 剔除异常值 -->
            <div v-if="rm.method === 'remove_outliers'" class="robust-sub-config">
              <div class="form-row">
                <label class="form-label">Z值阈值：</label>
                <select v-model="rm.outlierZThreshold" class="form-select" style="max-width:150px">
                  <option value="2">2σ</option>
                  <option value="3">3σ (常用)</option>
                  <option value="4">4σ</option>
                </select>
              </div>
            </div>

            <!-- 通用模型配置 -->
            <div class="robust-sub-config">
              <div class="form-row">
                <label class="form-label">被解释变量：</label>
                <select v-model="rm.dependentVar" class="form-select">
                  <option value="">请选择</option>
                  <option v-for="(col, i) in columns" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>
              <div class="form-row">
                <label class="form-label">解释变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in columns" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="rm.independentVars.includes(col)"
                      @change="toggleRobustnessIndep(ri, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ rm.independentVars.length }} 个</span>
              </div>
              <div class="form-row">
                <label class="form-label">控制变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in getRobAvailableControlVars(rm)" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="rm.controlVars.includes(col)"
                      @change="toggleRobustnessControl(ri, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ rm.controlVars.length }} 个</span>
              </div>
              <ModelMethodConfig
                :modelValue="rm.methodConfig"
                :availableCols="columns"
                @update:modelValue="onRobMethodConfigUpdate(ri, $event)"
              />
              <div class="form-row">
                <label class="form-label">聚类标准误：</label>
                <select v-model="rm.clusterVar" class="form-select">
                  <option value="">不选择</option>
                  <option v-for="(col, i) in columns" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>
            </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== 模块3: 调节效应检验（可选） ==================== -->
      <div v-show="selectedModule === 'moderation'" class="module-card module-expanded">
        <div class="module-body">
          <!-- 参与本检验的基准模型（多选） -->
          <div v-if="baselineModels.length > 1" class="form-row">
            <label class="form-label">参与本检验的基准模型：</label>
            <div class="checkbox-group">
              <label v-for="(m, idx) in baselineModelOptions" :key="m.id" class="checkbox-item baseline-model-item">
                <input type="checkbox" :value="m.id"
                  :checked="selectedModerationBaselineIds.includes(m.id)"
                  @change="toggleModerationBaseline(m.id)" />
                <span>模型{{ idx + 1 }}<span v-if="m.dependentVar" class="model-dep-hint">（{{ m.dependentVar }}）</span></span>
              </label>
            </div>
            <span class="selected-hint">已选: {{ selectedModerationBaselineIds.length }} / {{ baselineModels.length }} 个</span>
          </div>

          <!-- 导入自基准模型 -->
          <div class="model-import-row">
            <span class="form-label-sm">导入自模型：</span>
            <select class="form-select form-select-sm" @change="importModerationBaseline($event.target.value)">
              <option value="">— 选择基准模型 —</option>
              <option v-for="(m, mi) in baselineModelOptions" :key="m.id" :value="m.id">{{ m.name }}（{{ m.dependentVar || '?' }}）</option>
            </select>
            <span class="import-hint">将覆盖下方的变量配置</span>
          </div>

          <div class="form-row">
            <label class="form-label">调节变量（可多选）：</label>
            <div class="checkbox-group moderation-multi-select">
              <label v-for="(col, i) in otherVarOptions" :key="i" class="checkbox-item">
                <input type="checkbox" :value="col"
                  :checked="moderationVars.includes(col)"
                  @change="toggleModerationVar(col)" />
                <span>{{ col }}</span>
              </label>
            </div>
            <span class="selected-hint">已选: {{ moderationVars.length }} 个</span>
          </div>

          <!-- 变量配置（用于交互项回归） -->
          <div v-if="moderationVars.length > 0" class="method-subconfig">
            <div class="form-row">
              <label class="form-label">被解释变量：</label>
              <select v-model="moderationDepVar" class="form-select">
                <option value="">请选择</option>
                <option v-for="(col, i) in columns" :key="i" :value="col">{{ col }}</option>
              </select>
            </div>
            <div class="form-row">
              <label class="form-label">解释变量：</label>
              <div class="checkbox-group">
                <label v-for="(col, i) in columns" :key="i" class="checkbox-item">
                  <input type="checkbox" :value="col"
                    :checked="moderationIndepVars.includes(col)"
                    @change="toggleModerationIndep(col)" />
                  <span>{{ col }}</span>
                </label>
              </div>
              <span class="selected-hint">已选: {{ moderationIndepVars.length }} 个</span>
            </div>
            <div class="form-row">
              <label class="form-label">控制变量：</label>
              <div class="checkbox-group">
                <label v-for="(col, i) in getModAvailableControlVars()" :key="i" class="checkbox-item">
                  <input type="checkbox" :value="col"
                    :checked="moderationControlVars.includes(col)"
                    @change="toggleModerationControl(col)" />
                  <span>{{ col }}</span>
                </label>
              </div>
              <span class="selected-hint">已选: {{ moderationControlVars.length }} 个</span>
            </div>
            <ModelMethodConfig
              :modelValue="moderationMethodConfig"
              :availableCols="columns"
              @update:modelValue="onModMethodConfigUpdate($event)"
            />
            <div class="form-row">
              <label class="form-label">聚类标准误：</label>
              <select v-model="moderationClusterVar" class="form-select">
                <option value="">不选择</option>
                <option v-for="(col, i) in getModAvailableClusterVars()" :key="i" :value="col">{{ col }}</option>
              </select>
            </div>
          </div>

          <p class="module-desc">将逐一构建各解释变量与各调节变量的交互项（中心化后），检验调节效应。</p>
        </div>
      </div>

      <!-- ==================== 模块4: 异质性分析（可选） ==================== -->
      <div v-show="selectedModule === 'heterogeneity'" class="module-card module-expanded">
        <div class="module-body">
          <!-- 参与本检验的基准模型（多选） -->
          <div v-if="baselineModels.length > 1" class="form-row">
            <label class="form-label">参与本检验的基准模型：</label>
            <div class="checkbox-group">
              <label v-for="(m, idx) in baselineModelOptions" :key="m.id" class="checkbox-item baseline-model-item">
                <input type="checkbox" :value="m.id"
                  :checked="selectedHeterogeneityBaselineIds.includes(m.id)"
                  @change="toggleHeterogeneityBaseline(m.id)" />
                <span>模型{{ idx + 1 }}<span v-if="m.dependentVar" class="model-dep-hint">（{{ m.dependentVar }}）</span></span>
              </label>
            </div>
            <span class="selected-hint">已选: {{ selectedHeterogeneityBaselineIds.length }} / {{ baselineModels.length }} 个</span>
          </div>

          <!-- 方法选择 -->
          <div class="form-row">
            <label class="form-label">选择方法：</label>
            <div class="checkbox-group">
              <label v-for="m in heterogeneityMethodOptions" :key="m.value" class="checkbox-item">
                <input type="checkbox" :value="m.value"
                  :checked="heterogeneityMethods.some(x => x.method === m.value)"
                  @change="toggleHeterogeneityMethod(m.value)" />
                <span>{{ m.label }}</span>
                <el-tag size="small" type="info" effect="plain" class="method-tag">{{ m.hint }}</el-tag>
              </label>
            </div>
          </div>

          <!-- 每种方法的配置 -->
          <div v-for="(mcfg, midx) in heterogeneityMethods" :key="mcfg.id" class="method-config">
            <div class="config-title">
              {{ getHeterogeneityMethodLabel(mcfg.method) }}
              <span class="config-remove" @click="removeHeterogeneityMethod(midx)">✕ 删除</span>
            </div>

            <!-- 分组变量（可多选） -->
            <div v-if="mcfg.method === 'subgroup' || mcfg.method === 'median_split' || mcfg.method === 'interaction'" class="form-row">
              <label class="form-label">{{ mcfg.method === 'interaction' ? '调节变量（可多选）：' : (mcfg.method === 'median_split' ? '切分变量（可多选）：' : '分组变量（可多选）：') }}</label>
              <div class="checkbox-group">
                <label v-for="(col, i) in columns" :key="i" class="checkbox-item">
                  <input type="checkbox" :value="col"
                    :checked="(mcfg.groupVars || []).includes(col)"
                    @change="toggleHetGroupVar(midx, col)" />
                  <span>{{ col }}</span>
                </label>
              </div>
              <span class="selected-hint">已选: {{ (mcfg.groupVars || []).length }} 个</span>
            </div>

            <!-- 共享：本方法的完整变量配置 -->
            <div class="method-subconfig">
              <div class="model-import-row">
                <span class="form-label-sm">导入自模型：</span>
                <select class="form-select form-select-sm" @change="importFromBaseline(mcfg, $event.target.value)">
                  <option value="">— 选择基准模型 —</option>
                  <option v-for="(m, mi) in baselineModelOptions" :key="m.id" :value="m.id">{{ m.name }}（{{ m.dependentVar || '?' }}）</option>
                </select>
                <span class="import-hint">将覆盖下方的变量选择</span>
              </div>
              <div class="form-row">
                <label class="form-label">被解释变量：</label>
                <select v-model="mcfg.dependentVar" class="form-select">
                  <option value="">请选择</option>
                  <option v-for="(col, i) in columns" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>
              <div class="form-row">
                <label class="form-label">解释变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in columns" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="mcfg.independentVars.includes(col)"
                      @change="toggleHeterogeneityIndependent(midx, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ mcfg.independentVars.length }} 个</span>
              </div>
              <div class="form-row">
                <label class="form-label">控制变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in getHetAvailableControlVars(mcfg)" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="mcfg.controlVars.includes(col)"
                      @change="toggleHeterogeneityControl(midx, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ mcfg.controlVars.length }} 个</span>
              </div>
              <!-- 回归命令 + 子配置 -->
              <ModelMethodConfig
                :modelValue="mcfg.methodConfig"
                :availableCols="columns"
                @update:modelValue="onHetMethodConfigUpdate(midx, $event)"
              />
              <div class="form-row">
                <label class="form-label">聚类标准误：</label>
                <select v-model="mcfg.clusterVar" class="form-select">
                  <option value="">不选择</option>
                  <option v-for="(col, i) in getHetAvailableClusterVars(mcfg)" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== 模块5: 机制检验（可选） ==================== -->
      <div v-show="selectedModule === 'mechanism'" class="module-card module-expanded">
        <div class="module-body">
          <!-- 参与本检验的基准模型（多选） -->
          <div v-if="baselineModels.length > 1" class="form-row">
            <label class="form-label">参与本检验的基准模型：</label>
            <div class="checkbox-group">
              <label v-for="(m, idx) in baselineModelOptions" :key="m.id" class="checkbox-item baseline-model-item">
                <input type="checkbox" :value="m.id"
                  :checked="selectedMechanismBaselineIds.includes(m.id)"
                  @change="toggleMechanismBaseline(m.id)" />
                <span>模型{{ idx + 1 }}<span v-if="m.dependentVar" class="model-dep-hint">（{{ m.dependentVar }}）</span></span>
              </label>
            </div>
            <span class="selected-hint">已选: {{ selectedMechanismBaselineIds.length }} / {{ baselineModels.length }} 个</span>
          </div>

          <!-- 方法选择 -->
          <div class="form-row">
            <label class="form-label">选择方法：</label>
            <div class="checkbox-group">
              <label v-for="m in mechanismMethodOptions" :key="m.value" class="checkbox-item">
                <input type="checkbox" :value="m.value"
                  :checked="mechanismMethods.some(x => x.method === m.value)"
                  @change="toggleMechanismMethod(m.value)" />
                <span>{{ m.label }}</span>
                <el-tag size="small" type="info" effect="plain" class="method-tag">{{ m.hint }}</el-tag>
              </label>
            </div>
          </div>

          <!-- 每种方法的配置 -->
          <div v-for="(mcfg, midx) in mechanismMethods" :key="mcfg.id" class="method-config">
            <div class="config-title">
              {{ getMechanismMethodLabel(mcfg.method) }}
              <span class="config-remove" @click="removeMechanismMethod(midx)">✕ 删除</span>
            </div>

            <div class="method-subconfig">
              <div class="model-import-row">
                <span class="form-label-sm">导入自模型：</span>
                <select class="form-select form-select-sm" @change="importFromBaseline(mcfg, $event.target.value)">
                  <option value="">— 选择基准模型 —</option>
                  <option v-for="(m, mi) in baselineModelOptions" :key="m.id" :value="m.id">{{ m.name }}（{{ m.dependentVar || '?' }}）</option>
                </select>
                <span class="import-hint">将覆盖下方的变量选择</span>
              </div>
              <div class="form-row">
                <label class="form-label">被解释变量：</label>
                <select v-model="mcfg.dependentVar" class="form-select">
                  <option value="">请选择</option>
                  <option v-for="(col, i) in columns" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>
              <div class="form-row">
                <label class="form-label">解释变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in columns" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="mcfg.independentVars.includes(col)"
                      @change="toggleMechanismIndependent(midx, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ mcfg.independentVars.length }} 个</span>
              </div>
              <div class="form-row">
                <label class="form-label">中介变量（可多选）：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in columns" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="mcfg.mediatorVars?.includes(col)"
                      @change="toggleMechanismMediator(midx, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ (mcfg.mediatorVars || []).length }} 个</span>
              </div>
              <div class="form-row">
                <label class="form-label">控制变量：</label>
                <div class="checkbox-group">
                  <label v-for="(col, i) in getMechAvailableControlVars(mcfg)" :key="i" class="checkbox-item">
                    <input type="checkbox" :value="col"
                      :checked="mcfg.controlVars.includes(col)"
                      @change="toggleMechanismControl(midx, col)" />
                    <span>{{ col }}</span>
                  </label>
                </div>
                <span class="selected-hint">已选: {{ mcfg.controlVars.length }} 个</span>
              </div>
              <!-- 回归命令 + 子配置 -->
              <ModelMethodConfig
                :modelValue="mcfg.methodConfig"
                :availableCols="columns"
                @update:modelValue="onMechMethodConfigUpdate(midx, $event)"
              />
              <div class="form-row">
                <label class="form-label">聚类标准误：</label>
                <select v-model="mcfg.clusterVar" class="form-select">
                  <option value="">不选择</option>
                  <option v-for="(col, i) in getMechAvailableClusterVars(mcfg)" :key="i" :value="col">{{ col }}</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 提交按钮 -->
      <div class="form-actions">
        <button type="button" class="submit-btn" @click="handleStart" :disabled="starting">
          {{ starting ? '启动中...' : '开始实证分析' }}
        </button>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getProjectColumns, runEmpirical, getSettings } from '../api'
import ModelMethodConfig from './ModelMethodConfig.vue'

const props = defineProps({
  projectId: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['start'])

const columns = ref([])
const starting = ref(false)

// 计算基准回归模块的概要信息
function getBaselineSummary() {
  const models = baselineModels.value
  if (models.length === 0) return ''
  const allVars = new Set()
  let modelCount = 0
  for (const m of models) {
    if (!m.dependentVar && m.independentVars.length === 0 && m.controlVars.length === 0) continue
    modelCount++
    if (m.dependentVar) allVars.add(m.dependentVar)
    for (const v of (m.independentVars || [])) allVars.add(v)
    for (const v of (m.controlVars || [])) allVars.add(v)
  }
  if (modelCount === 0) return ''
  return `共 ${allVars.size} 个变量`
}

// 模块展开状态
const selectedModule = ref('baseline') // 当前选中的模块
const moduleTabs = computed(() => [
  { key: 'baseline', icon: '📊', title: '基准回归', required: true, summary: getBaselineSummary() },
  { key: 'robustness', icon: '🔒', title: '稳健性检验', required: false, summary: selectedRobustnessTests.value.length > 0 ? `${selectedRobustnessTests.value.length} 种方法` : '' },
  { key: 'moderation', icon: '🔁', title: '调节效应', required: false, summary: moderationVars.value.length > 0 ? `${moderationVars.value.length} 个变量` : '' },
  { key: 'heterogeneity', icon: '📂', title: '异质性分析', required: false, summary: heterogeneityMethods.value.length > 0 ? `${heterogeneityMethods.value.length} 种方法` : '' },
  { key: 'mechanism', icon: '🔗', title: '机制检验', required: false, summary: mechanismMethods.value.length > 0 ? `${mechanismMethods.value.length} 种方法` : '' },
])


const robustnessOptions = [
  { value: 'replace_dep_var', label: '替换被解释变量' },
  { value: 'replace_indep_var', label: '替换解释变量' },
  { value: 'shorten_window', label: '缩短时间窗口' },
  { value: 'winsorize', label: '缩尾处理' },
  { value: 'remove_outliers', label: '剔除异常值' },
]

const heterogeneityMethodOptions = [
  { value: 'subgroup', label: '分组回归', hint: '按分类变量分样本' },
  { value: 'median_split', label: '中位数分组', hint: '按中位数切分为高/低两组' },
  { value: 'interaction', label: '交互项模型', hint: '构建 X×M 检验调节效应' },
]

const mechanismMethodOptions = [
  { value: 'baron_kenny', label: '逐步回归法', hint: 'Baron & Kenny 三步法' },
  { value: 'jiang_ting', label: '两步法', hint: '江艇 (2022)' },
]

// ==================== 基准回归：多模型列表 ====================
let _idCounter = 0
const nextId = () => `cfg_${++_idCounter}_${Date.now()}`

const baselineModels = ref([
  {
    id: nextId(),
    dependentVar: '',
    independentVars: [],
    controlVars: [],
    methodConfig: {
      method: '',
      effectType: 'fe',
      entityCol: '',
      timeCol: '',
    },
    clusterVar: '',
  },
])

// 跟踪每个模型卡片的折叠状态（true=已折叠）
const collapsedModels = ref(new Set())

// ==================== 稳健性检验 ====================
const selectedRobustnessTests = ref([])
const robustnessMethodConfigs = ref([])
const robustCollapsedIds = ref(new Set())

function isRobustCollapsed(id) {
  return robustCollapsedIds.value.has(id)
}

function toggleRobustCollapse(id) {
  if (robustCollapsedIds.value.has(id)) {
    robustCollapsedIds.value.delete(id)
  } else {
    robustCollapsedIds.value.add(id)
  }
  // force reactivity
  robustCollapsedIds.value = new Set(robustCollapsedIds.value)
}

function createRobustnessMethod(testType) {
  return {
    id: nextId(),
    method: testType,
    // 模型配置
    dependentVar: '',
    independentVars: [],
    controlVars: [],
    methodConfig: {
      method: '',
      effectType: 'fe',
      entityCol: '',
      timeCol: '',
    },
    clusterVar: '',
    // 替换被解释变量
    newDepVar: '',
    // 替换解释变量
    replaceIndepVar: {},
    // 缩短时间窗口
    timeCol: '',
    excludeYearsInput: '',
    // 缩尾处理
    winsorizeThreshold: '0.01',
    // 剔除异常值
    outlierZThreshold: '3',
  }
}

function syncRobustnessMethodConfigs() {
  // 当 selectedRobustnessTests 变化时，同步 robustnessMethodConfigs
  const existing = new Map(robustnessMethodConfigs.value.map(m => [m.method, m]))
  const newList = []
  for (const test of selectedRobustnessTests.value) {
    if (existing.has(test)) {
      newList.push(existing.get(test))
    } else {
      newList.push(createRobustnessMethod(test))
    }
  }
  robustnessMethodConfigs.value = newList
}

watch(selectedRobustnessTests, syncRobustnessMethodConfigs, { deep: true })

// 手动调用一次以初始化
syncRobustnessMethodConfigs()

// ==================== 调节效应 ====================
const moderationVars = ref([])
const moderationDepVar = ref('')
const moderationIndepVars = ref([])
const moderationControlVars = ref([])
const moderationMethodConfig = ref({
  method: '',
  effectType: 'fe',
  entityCol: '',
  timeCol: '',
})
const moderationClusterVar = ref('')

// ==================== 异质性分析：多方法 ====================
const heterogeneityMethods = ref([])

// ==================== 机制检验：多方法 ====================
const mechanismMethods = ref([])

// ==================== 共享：基准模型选项 & 各检验的"参与本检验的基准模型"多选 ====================
// 列出所有 baseline model，附带 id/name/dependentVar/independentVars/controlVars/methodConfig/clusterVar
const baselineModelOptions = computed(() =>
  baselineModels.value.map((m, idx) => {
    const mc = m.methodConfig || { method: 'reg', effectType: 'fe', entityCol: '', timeCol: '' }
    return {
      id: m.id,
      name: `模型${idx + 1}`,
      idx,
      dependentVar: m.dependentVar,
      independentVars: [...m.independentVars],
      controlVars: [...m.controlVars],
      entityCol: mc.entityCol,
      timeCol: mc.timeCol,
      clusterVar: m.clusterVar,
      regressionMethods: [mc.method],
    }
  })
)

function getBaselineModelById(id) {
  return baselineModels.value.find(m => m.id === id) || null
}

function getBaselineModelNameById(id) {
  const opt = baselineModelOptions.value.find(o => o.id === id)
  return opt ? opt.name : null
}

// 各检验模块的"参与本检验的基准模型"多选（默认全选）
const selectedRobustnessBaselineIds = ref([])
const selectedModerationBaselineIds = ref([])
const selectedHeterogeneityBaselineIds = ref([])
const selectedMechanismBaselineIds = ref([])

// 同步：当 baselineModels 变化时，把新增的 id 加进去（默认全选），删除的 id 移除
watch(baselineModels, (newModels) => {
  const newIds = new Set(newModels.map(m => m.id))
  for (const arr of [selectedRobustnessBaselineIds, selectedModerationBaselineIds,
                     selectedHeterogeneityBaselineIds, selectedMechanismBaselineIds]) {
    for (let i = arr.value.length - 1; i >= 0; i--) {
      if (!newIds.has(arr.value[i])) arr.value.splice(i, 1)
    }
    for (const m of newModels) {
      if (!arr.value.includes(m.id)) arr.value.push(m.id)
    }
  }
}, { deep: true, immediate: true })

// 把选中的 id 转成 baseline model 的完整配置（name + 变量）
function getAppliedBaselineModelsPayload(selectedIds) {
  if (!selectedIds || selectedIds.length === 0) return []
  return baselineModelOptions.value
    .filter(o => selectedIds.includes(o.id))
    .map(o => {
      // 由 entity_col + time_col 自动汇总 fixed_effects
      const feAcc = {}
      if (o.entityCol) feAcc[o.entityCol] = 'true'
      if (o.timeCol) feAcc[o.timeCol] = 'true'
      return {
        name: o.name,
        dependent_var: o.dependentVar,
        independent_vars: o.independentVars,
        control_vars: o.controlVars,
        fixed_effects: feAcc,
        entity_col: o.entityCol || null,
        time_col: o.timeCol || null,
        cluster_var: o.clusterVar || null,
        regression_methods: o.regressionMethods,
      }
    })
}

// 各检验的多选切换
function toggleSelectedId(arr, id) {
  const i = arr.value.indexOf(id)
  if (i > -1) arr.value.splice(i, 1)
  else arr.value.push(id)
}

const toggleRobustnessBaseline = (id) => toggleSelectedId(selectedRobustnessBaselineIds, id)
const toggleModerationBaseline = (id) => toggleSelectedId(selectedModerationBaselineIds, id)
const toggleHeterogeneityBaseline = (id) => toggleSelectedId(selectedHeterogeneityBaselineIds, id)
const toggleMechanismBaseline = (id) => toggleSelectedId(selectedMechanismBaselineIds, id)

// ==================== 共用：列选项 ====================
// 调节变量候选：所有列中排除第一个模型中已被使用的被解释/解释变量
const otherVarOptions = computed(() => {
  const firstModel = baselineModels.value[0] || {}
  const used = new Set([
    ...(firstModel.independentVars || []),
    ...(firstModel.controlVars || []),
  ])
  if (firstModel.dependentVar) used.add(firstModel.dependentVar)
  return columns.value.filter(c => !used.has(c))
})
const replaceDepVarOptions = computed(() => columns.value.slice())
const replaceIndepVarOptions = computed(() => columns.value.slice())
const timeColOptions = computed(() => {
  const candidates = ['年度', '年份', '时间', 'year', 'Year', 'date', 'DATE', 'quarter', 'month']
  const found = columns.value.filter(col => candidates.includes(col))
  return found.length > 0 ? found : columns.value
})

// ==================== 基准模型工具函数 ====================
function createEmptyModel() {
  return {
    id: nextId(),
    dependentVar: '',
    independentVars: [],
    controlVars: [],
    methodConfig: {
      method: '',
      effectType: 'fe',
      entityCol: '',
      timeCol: '',
    },
    clusterVar: '',
  }
}

function addBaselineModel() {
  baselineModels.value.push(createEmptyModel())
}

function removeBaselineModel(idx) {
  if (baselineModels.value.length <= 1) {
    ElMessage.warning('至少需要保留 1 个模型')
    return
  }
  // 同时清理该模型的折叠状态
  const removedId = baselineModels.value[idx].id
  collapsedModels.value.delete(removedId)
  baselineModels.value.splice(idx, 1)
}

function isModelCollapsed(modelId) {
  return collapsedModels.value.has(modelId)
}

function toggleModelCollapse(modelId) {
  if (collapsedModels.value.has(modelId)) {
    collapsedModels.value.delete(modelId)
  } else {
    collapsedModels.value.add(modelId)
  }
  // 触发响应式更新（Set 的变更可能不被 Vue 3 深度追踪）
  collapsedModels.value = new Set(collapsedModels.value)
}

function toggleModelIndependent(modelIdx, col) {
  const arr = baselineModels.value[modelIdx].independentVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleModelControl(modelIdx, col) {
  const arr = baselineModels.value[modelIdx].controlVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleModelFixedEffect(modelIdx, col) {
  const arr = baselineModels.value[modelIdx].fixedEffects
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

// ====== ModelMethodConfig 回调 ======
function onMethodConfigUpdate(modelIdx, val) {
  baselineModels.value[modelIdx].methodConfig = val
}

function onHetMethodConfigUpdate(midx, val) {
  heterogeneityMethods.value[midx].methodConfig = val
}

function onMechMethodConfigUpdate(midx, val) {
  mechanismMethods.value[midx].methodConfig = val
}

function getAvailableControlVars(model) {
  return columns.value.filter(c =>
    c !== model.dependentVar && !model.independentVars.includes(c)
  )
}

function getAvailableFixedEffectVars(model) {
  return columns.value.filter(c =>
    c !== model.dependentVar &&
    !model.independentVars.includes(c) &&
    !model.controlVars.includes(c)
  )
}

function getAvailableClusterVars(model) {
  return columns.value.filter(c =>
    c !== model.dependentVar && !model.independentVars.includes(c)
  )
}

// ==================== 异质性方法工具 ====================
function getHeterogeneityMethodLabel(method) {
  const m = heterogeneityMethodOptions.find(x => x.value === method)
  return m ? m.label : method
}

function toggleHeterogeneityMethod(method) {
  const existing = heterogeneityMethods.value.findIndex(x => x.method === method)
  if (existing >= 0) {
    heterogeneityMethods.value.splice(existing, 1)
  } else {
    heterogeneityMethods.value.push({
      id: nextId(),
      method,
      groupVars: [],
      dependentVar: '',
      independentVars: [],
      controlVars: [],
      methodConfig: {
        method: 'reg',
        effectType: 'fe',
        entityCol: '',
        timeCol: '',
      },
      clusterVar: '',
    })
  }
}

function toggleHetGroupVar(midx, col) {
  const mcfg = heterogeneityMethods.value[midx]
  if (!mcfg.groupVars) mcfg.groupVars = []
  const arr = mcfg.groupVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function removeHeterogeneityMethod(idx) {
  heterogeneityMethods.value.splice(idx, 1)
}

function toggleHeterogeneityIndependent(midx, col) {
  const arr = heterogeneityMethods.value[midx].independentVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleHeterogeneityControl(midx, col) {
  const arr = heterogeneityMethods.value[midx].controlVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleHeterogeneityFixedEffect(midx, col) {
  const arr = heterogeneityMethods.value[midx].fixedEffects
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleHeterogeneityMethod2(midx, method) {
  const arr = heterogeneityMethods.value[midx].regressionMethods
  const idx = arr.indexOf(method)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(method)
}

function getHetAvailableControlVars(mcfg) {
  const groupVars = mcfg.groupVars || []
  return columns.value.filter(c =>
    !groupVars.includes(c) &&
    c !== mcfg.dependentVar &&
    !mcfg.independentVars.includes(c)
  )
}

function getHetAvailableFixedEffectVars(mcfg) {
  const groupVars = mcfg.groupVars || []
  return columns.value.filter(c =>
    !groupVars.includes(c) &&
    c !== mcfg.dependentVar &&
    !mcfg.independentVars.includes(c) &&
    !mcfg.controlVars.includes(c)
  )
}

function getHetAvailableClusterVars(mcfg) {
  return columns.value.filter(c =>
    c !== mcfg.dependentVar && !mcfg.independentVars.includes(c)
  )
}

// ==================== 从基准模型导入配置（通用） ====================
function applyBaselineModelToMethod(mcfg, baselineModel) {
  if (!baselineModel) return
  mcfg.dependentVar = baselineModel.dependentVar || ''
  mcfg.independentVars = [...(baselineModel.independentVars || [])]
  mcfg.controlVars = [...(baselineModel.controlVars || [])]
  if (baselineModel.methodConfig) {
    mcfg.methodConfig = { ...baselineModel.methodConfig }
  }
  mcfg.clusterVar = baselineModel.clusterVar || ''
}

function importFromBaseline(targetMethod, modelId) {
  const model = baselineModelOptions.value.find(m => m.id === modelId)
  if (model) applyBaselineModelToMethod(targetMethod, model)
}

// ==================== 机制方法工具 ====================
function getMechanismMethodLabel(method) {
  const m = mechanismMethodOptions.find(x => x.value === method)
  return m ? m.label : method
}

function toggleMechanismMethod(method) {
  const existing = mechanismMethods.value.findIndex(x => x.method === method)
  if (existing >= 0) {
    mechanismMethods.value.splice(existing, 1)
  } else {
    mechanismMethods.value.push({
      id: nextId(),
      method,
      mediatorVars: [],
      dependentVar: '',
      independentVars: [],
      controlVars: [],
      methodConfig: {
        method: 'reg',
        effectType: 'fe',
        entityCol: '',
        timeCol: '',
      },
      clusterVar: '',
    })
  }
}

function removeMechanismMethod(idx) {
  mechanismMethods.value.splice(idx, 1)
}

function toggleMechanismIndependent(midx, col) {
  const arr = mechanismMethods.value[midx].independentVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleMechanismControl(midx, col) {
  const arr = mechanismMethods.value[midx].controlVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleMechanismMediator(midx, col) {
  const mcfg = mechanismMethods.value[midx]
  if (!mcfg.mediatorVars) mcfg.mediatorVars = []
  const arr = mcfg.mediatorVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleMechanismFixedEffect(midx, col) {
  const arr = mechanismMethods.value[midx].fixedEffects
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleMechanismMethod2(midx, method) {
  const arr = mechanismMethods.value[midx].regressionMethods
  const idx = arr.indexOf(method)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(method)
}

function getMechAvailableControlVars(mcfg) {
  const mediators = mcfg.mediatorVars || []
  return columns.value.filter(c =>
    !mediators.includes(c) &&
    c !== mcfg.dependentVar &&
    !mcfg.independentVars.includes(c)
  )
}

function getMechAvailableFixedEffectVars(mcfg) {
  const mediators = mcfg.mediatorVars || []
  return columns.value.filter(c =>
    !mediators.includes(c) &&
    c !== mcfg.dependentVar &&
    !mcfg.independentVars.includes(c) &&
    !mcfg.controlVars.includes(c)
  )
}

function getMechAvailableClusterVars(mcfg) {
  return columns.value.filter(c =>
    c !== mcfg.dependentVar && !mcfg.independentVars.includes(c)
  )
}

// ==================== 稳健性检验函数 ====================
const toggleRobustnessTest = (test) => {
  const idx = selectedRobustnessTests.value.indexOf(test)
  if (idx > -1) selectedRobustnessTests.value.splice(idx, 1)
  else selectedRobustnessTests.value.push(test)
}

function getRobustnessMethodLabel(method) {
  const m = robustnessOptions.find(x => x.value === method)
  return m ? m.label : method
}

function toggleRobustnessIndep(ri, col) {
  const arr = robustnessMethodConfigs.value[ri].independentVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function toggleRobustnessControl(ri, col) {
  const arr = robustnessMethodConfigs.value[ri].controlVars
  const idx = arr.indexOf(col)
  if (idx > -1) arr.splice(idx, 1)
  else arr.push(col)
}

function getRobAvailableControlVars(rm) {
  return columns.value.filter(c =>
    c !== rm.dependentVar && !rm.independentVars.includes(c)
  )
}

function importRobustnessModel(ri, modelId) {
  const model = baselineModelOptions.value.find(m => m.id === modelId)
  if (!model) return
  const rm = robustnessMethodConfigs.value[ri]
  rm.dependentVar = model.dependentVar || ''
  rm.independentVars = [...(model.independentVars || [])]
  rm.controlVars = [...(model.controlVars || [])]
  rm.methodConfig = {
    method: model.regressionMethods?.[0] || '',
    effectType: 'fe',
    entityCol: model.entityCol || '',
    timeCol: model.timeCol || '',
  }
  rm.clusterVar = model.clusterVar || ''
}

function onRobMethodConfigUpdate(ri, val) {
  robustnessMethodConfigs.value[ri].methodConfig = val
}

function buildRobustnessTestsPayload() {
  const tests = []
  // 当前选中的 baseline models 完整配置
  const appliedBaselines = getAppliedBaselineModelsPayload(selectedRobustnessBaselineIds.value)
  for (const rm of robustnessMethodConfigs.value) {
    const mc = rm.methodConfig || { method: 'reg', effectType: 'fe', entityCol: '', timeCol: '' }
    const feAcc = {}
    if (mc.entityCol) feAcc[mc.entityCol] = 'true'
    if (mc.timeCol) feAcc[mc.timeCol] = 'true'
    const baseConfig = {
      dependent_var: rm.dependentVar,
      independent_vars: rm.independentVars,
      control_vars: rm.controlVars,
      fixed_effects: feAcc,
      entity_col: mc.entityCol || null,
      time_col: mc.timeCol || null,
      effect_type: mc.effectType || 'fe',
      cluster_var: rm.clusterVar || null,
      regression_methods: [mc.method],
      model: mc.method,
      applied_baseline_models: appliedBaselines,
    }
    if (rm.method === 'replace_dep_var' && rm.newDepVar) {
      tests.push({
        type: 'replace_dep_var',
        config: { new_dep_var: rm.newDepVar },
        ...baseConfig,
      })
    } else if (rm.method === 'replace_indep_var') {
      const replacements = {}
      Object.entries(rm.replaceIndepVar || {}).forEach(([oldVar, newVar]) => {
        if (newVar) replacements[oldVar] = newVar
      })
      if (Object.keys(replacements).length > 0) {
        tests.push({
          type: 'replace_indep_var',
          config: { replacements },
          ...baseConfig,
        })
      }
    } else if (rm.method === 'shorten_window') {
      const cfg = { time_col: rm.timeCol || undefined }
      if (rm.excludeYearsInput?.trim()) {
        const years = rm.excludeYearsInput.split(',').map(y => {
          const n = Number(y.trim())
          return isNaN(n) ? y.trim() : n
        })
        cfg.exclude_years = years
      }
      if (cfg.time_col || cfg.exclude_years?.length > 0) {
        tests.push({
          type: 'shorten_window',
          config: cfg,
          ...baseConfig,
        })
      }
    } else if (rm.method === 'winsorize') {
      tests.push({
        type: 'winsorize',
        config: { threshold: parseFloat(rm.winsorizeThreshold || '0.01') },
        ...baseConfig,
      })
    } else if (rm.method === 'remove_outliers') {
      tests.push({
        type: 'remove_outliers',
        config: { z_threshold: parseFloat(rm.outlierZThreshold || '3') },
        ...baseConfig,
      })
    }
  }
  return tests
}

// ==================== 加载列 ====================
const loadColumns = async () => {
  try {
    const res = await getProjectColumns(props.projectId)
    let data = res.data
    if (data.data) data = data.data
    columns.value = (data.columns || []).map(col => String(col))
  } catch (err) {
    console.error('加载数据列失败:', err)
    ElMessage.error('加载数据列失败')
  }
}

// ==================== 调节效应工具函数 ====================
function toggleModerationVar(col) {
  const idx = moderationVars.value.indexOf(col)
  if (idx > -1) moderationVars.value.splice(idx, 1)
  else moderationVars.value.push(col)
}

function toggleModerationIndep(col) {
  const idx = moderationIndepVars.value.indexOf(col)
  if (idx > -1) moderationIndepVars.value.splice(idx, 1)
  else moderationIndepVars.value.push(col)
}

function toggleModerationControl(col) {
  const idx = moderationControlVars.value.indexOf(col)
  if (idx > -1) moderationControlVars.value.splice(idx, 1)
  else moderationControlVars.value.push(col)
}

function getModAvailableControlVars() {
  return columns.value.filter(c =>
    c !== moderationDepVar.value &&
    !moderationIndepVars.value.includes(c)
  )
}

function getModAvailableClusterVars() {
  return columns.value.filter(c =>
    c !== moderationDepVar.value && !moderationIndepVars.value.includes(c)
  )
}

function importModerationBaseline(modelId) {
  const model = baselineModelOptions.value.find(m => m.id === modelId)
  if (!model) return
  moderationDepVar.value = model.dependentVar || ''
  moderationIndepVars.value = [...(model.independentVars || [])]
  moderationControlVars.value = [...(model.controlVars || [])]
  moderationMethodConfig.value = {
    method: model.regressionMethods?.[0] || '',
    effectType: 'fe',
    entityCol: model.entityCol || '',
    timeCol: model.timeCol || '',
  }
  moderationClusterVar.value = model.clusterVar || ''
}

function onModMethodConfigUpdate(val) {
  moderationMethodConfig.value = val
}

// ==================== 启动分析 ====================
const handleStart = async () => {
  // 校验
  for (let i = 0; i < baselineModels.value.length; i++) {
    const m = baselineModels.value[i]
    if (!m.dependentVar) {
      ElMessage.warning(`模型 ${i + 1}：请选择被解释变量`)
      return
    }
    if (m.independentVars.length === 0) {
      ElMessage.warning(`模型 ${i + 1}：请至少选择一个解释变量`)
      return
    }
    if (!m.methodConfig || !m.methodConfig.method) {
      ElMessage.warning(`模型 ${i + 1}：请选择一个回归命令`)
      return
    }
    if (m.methodConfig.method === 'xtreg') {
      if (!m.methodConfig.entityCol) {
        ElMessage.warning(`模型 ${i + 1}：xtreg 需要选择个体变量`)
        return
      }
      if (!m.methodConfig.timeCol) {
        ElMessage.warning(`模型 ${i + 1}：xtreg 需要选择时间变量`)
        return
      }
    }
  }
  for (let i = 0; i < heterogeneityMethods.value.length; i++) {
    const m = heterogeneityMethods.value[i]
    if (!m.groupVars || m.groupVars.length === 0) {
      ElMessage.warning(`异质性方法 ${i + 1}：请至少选择一个分组/调节变量`)
      return
    }
    if (!m.dependentVar || m.independentVars.length === 0) {
      ElMessage.warning(`异质性方法 ${i + 1}：请配置被解释变量和解释变量`)
      return
    }
  }
  for (let i = 0; i < mechanismMethods.value.length; i++) {
    const m = mechanismMethods.value[i]
    if (!m.mediatorVars || m.mediatorVars.length === 0) {
      ElMessage.warning(`机制方法 ${i + 1}：请至少选择一个中介变量`)
      return
    }
    if (!m.dependentVar || m.independentVars.length === 0) {
      ElMessage.warning(`机制方法 ${i + 1}：请配置被解释变量和解释变量`)
      return
    }
  }

  starting.value = true
  try {
    let apiKey = ''
    let aiModelType = 'deepseek'
    try {
      const settingsRes = await getSettings()
      const settingsData = settingsRes.data.data || settingsRes.data || {}
      const aiSettings = settingsData.aiSettings || settingsData
      apiKey = aiSettings.deepseekApiKey || ''
      aiModelType = aiSettings.modelType || 'deepseek'
    } catch (e) {
      console.warn('获取设置失败，将使用默认值', e)
    }

    const robustnessTests = buildRobustnessTestsPayload()

    // 构建 test_types
    const testTypes = ['descriptive', 'correlation', 'vif', 'regression']
    if (robustnessTests.length > 0) testTypes.push('robustness')
    if (moderationVars.value.length > 0 && moderationDepVar.value) testTypes.push('moderation')
    if (heterogeneityMethods.value.length > 0) testTypes.push('heterogeneity')
    if (mechanismMethods.value.length > 0) testTypes.push('mechanism')

    // 将 baselineModels 序列化为 baseline_models 列表
    const baselineModelsPayload = baselineModels.value.map((m, idx) => {
      const mc = m.methodConfig || { method: 'reg', effectType: 'fe', entityCol: '', timeCol: '' }
      const feAcc = {}
      if (mc.entityCol) feAcc[mc.entityCol] = 'true'
      if (mc.timeCol) feAcc[mc.timeCol] = 'true'
      return {
        name: `模型${idx + 1}`,
        dependent_var: m.dependentVar,
        independent_vars: m.independentVars,
        control_vars: m.controlVars,
        fixed_effects: feAcc,
        entity_col: mc.entityCol || null,
        time_col: mc.timeCol || null,
        effect_type: mc.effectType || 'fe',
        cluster_var: m.clusterVar || null,
        regression_methods: [mc.method],
        model: mc.method,
      }
    })

    // 异质性方法
    const hetAppliedBaselines = getAppliedBaselineModelsPayload(selectedHeterogeneityBaselineIds.value)
    const heterogeneityMethodsPayload = heterogeneityMethods.value.map(m => {
      const mc = m.methodConfig || { method: 'reg', effectType: 'fe', entityCol: '', timeCol: '' }
      const feAcc = {}
      if (mc.entityCol) feAcc[mc.entityCol] = 'true'
      if (mc.timeCol) feAcc[mc.timeCol] = 'true'
      return {
        method: m.method,
        group_vars: m.groupVars || [],
        dependent_var: m.dependentVar,
        independent_vars: m.independentVars,
        control_vars: m.controlVars,
        fixed_effects: feAcc,
        entity_col: mc.entityCol || null,
        time_col: mc.timeCol || null,
        effect_type: mc.effectType || 'fe',
        cluster_var: m.clusterVar || null,
        regression_methods: [mc.method],
        model: mc.method,
        applied_baseline_models: hetAppliedBaselines,
      }
    })

    // 机制方法
    const mechAppliedBaselines = getAppliedBaselineModelsPayload(selectedMechanismBaselineIds.value)
    const mechanismMethodsPayload = mechanismMethods.value.map(m => {
      const mc = m.methodConfig || { method: 'reg', effectType: 'fe', entityCol: '', timeCol: '' }
      const feAcc = {}
      if (mc.entityCol) feAcc[mc.entityCol] = 'true'
      if (mc.timeCol) feAcc[mc.timeCol] = 'true'
      return {
        method: m.method,
        mediator_vars: m.mediatorVars || [],
        dependent_var: m.dependentVar,
        independent_vars: m.independentVars,
        control_vars: m.controlVars,
        fixed_effects: feAcc,
        entity_col: mc.entityCol || null,
        time_col: mc.timeCol || null,
        effect_type: mc.effectType || 'fe',
        cluster_var: m.clusterVar || null,
        regression_methods: [mc.method],
        model: mc.method,
        applied_baseline_models: mechAppliedBaselines,
      }
    })

    // 兼容字段（从第一个模型提取，兼容旧后端）
    const firstModel = baselineModelsPayload[0] || {}

    const response = await runEmpirical({
      project_id: props.projectId,
      model_type: aiModelType,
      api_key: apiKey,
      // 兼容旧字段（第一个模型）
      ...firstModel,
      // 新结构
      baseline_models: baselineModelsPayload,
      heterogeneity_methods: heterogeneityMethodsPayload,
      mechanism_methods: mechanismMethodsPayload,
      // 调节效应：多选调节变量 + 自配置变量 + 多选基准模型
      moderation_methods: moderationVars.value.length > 0
        ? [{
            method: 'interaction',
            moderator_vars: moderationVars.value,
            dependent_var: moderationDepVar.value || baselineModelsPayload[0]?.dependent_var || '',
            independent_vars: moderationIndepVars.value.length > 0 ? moderationIndepVars.value : (baselineModelsPayload[0]?.independent_vars || []),
            control_vars: moderationControlVars.value.length > 0 ? moderationControlVars.value : (baselineModelsPayload[0]?.control_vars || []),
            fixed_effects: (() => {
              const fe = {}
              if (moderationMethodConfig.value.entityCol) fe[moderationMethodConfig.value.entityCol] = 'true'
              if (moderationMethodConfig.value.timeCol) fe[moderationMethodConfig.value.timeCol] = 'true'
              return fe
            })(),
            entity_col: moderationMethodConfig.value.entityCol || null,
            time_col: moderationMethodConfig.value.timeCol || null,
            effect_type: moderationMethodConfig.value.effectType || 'fe',
            cluster_var: moderationClusterVar.value || null,
            regression_methods: [moderationMethodConfig.value.method || 'reg'],
            model: moderationMethodConfig.value.method || 'reg',
            applied_baseline_models: getAppliedBaselineModelsPayload(selectedModerationBaselineIds.value),
          }]
        : [],
      // 稳健性
      outlier_method: 'none',
      robustness_tests: robustnessTests,
      test_types: testTypes,
      moderation_var: moderationVars.value.length > 0 ? moderationVars.value.join(',') : null,
    })

    if (response.data.success) {
      ElMessage.success('实证分析任务已启动')
      await new Promise(resolve => setTimeout(resolve, 2000))
      emit('start', props.projectId)
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '启动失败')
  } finally {
    starting.value = false
  }
}

onMounted(loadColumns)
</script>

<style scoped>
.variable-selector {
  margin-top: 20px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.form-container {
  padding: 10px;
}

/* ==================== 模块卡片样式 ==================== */
.module-card {
  margin-bottom: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.module-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.module-expanded {
  border-color: #409eff;
}

.module-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  background: #fafbfc;
  user-select: none;
  transition: background 0.2s;
}

.module-header:hover {
  background: #f0f2f5;
}

.module-icon {
  font-size: 18px;
  margin-right: 8px;
}

.module-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  flex: 1;
}

.module-tag {
  margin-right: 8px;
}

.module-arrow {
  font-size: 12px;
  color: #909399;
  transition: transform 0.2s;
}

.module-body {
  padding: 16px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
}

.module-desc {
  font-size: 13px;
  color: #909399;
  margin: 8px 0 0 132px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  line-height: 1.5;
}

/* ==================== 模块标题栏 summary ==================== */
.module-summary {
  font-size: 12px;
  color: #909399;
  margin-right: 8px;
  padding: 2px 8px;
  background: #ecf5ff;
  border-radius: 10px;
}

/* ==================== 多模型卡片样式 ==================== */
.model-card {
  margin-bottom: 16px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fafbfc;
  overflow: hidden;
}

.model-card-header {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  background: #f0f4fa;
  border-bottom: 1px solid #dcdfe6;
  gap: 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.model-card-header:hover {
  background: #e6ecf6;
}

.model-card.is-collapsed .model-card-header {
  border-bottom: none;
}

.model-card-arrow {
  font-size: 12px;
  color: #909399;
  transition: transform 0.2s;
  flex-shrink: 0;
}

.model-card-title {
  font-size: 14px;
  font-weight: 600;
  color: #409eff;
}

.model-card-summary {
  flex: 1;
  font-size: 12px;
  color: #909399;
  font-family: 'Consolas', 'Monaco', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-card-remove {
  font-size: 12px;
  color: #f56c6c;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 3px;
  transition: background 0.2s;
}

.model-card-remove:hover {
  background: #fef0f0;
}

.model-card-body {
  padding: 14px 16px;
  background: #fff;
}

.add-model-btn {
  width: 100%;
  padding: 10px;
  margin-top: 8px;
  border: 2px dashed #dcdfe6;
  border-radius: 6px;
  background: #fff;
  color: #409eff;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.add-model-btn:hover {
  border-color: #409eff;
  background: #ecf5ff;
}

/* ==================== 多方法配置样式 ==================== */
.method-tag {
  margin-left: 4px;
  font-size: 11px !important;
  height: 18px !important;
  line-height: 16px !important;
}

.method-config {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fafbfc;
}

.config-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-remove {
  font-size: 12px;
  color: #f56c6c;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: normal;
}

.config-remove:hover {
  background: #fef0f0;
}

.method-subconfig {
  background: #fff;
  padding: 12px;
  border-radius: 4px;
  border: 1px dashed #e4e7ed;
}

/* ==================== 原有表单样式 ==================== */
.form-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 14px;
  gap: 12px;
}

.form-label {
  min-width: 120px;
  font-size: 14px;
  color: #606266;
  font-weight: 500;
  padding-top: 5px;
}

.form-select {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  background: #fff;
  color: #606266;
  outline: none;
  transition: border-color 0.2s;
}

.form-select:focus {
  border-color: #409eff;
}

.form-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.form-input:focus {
  border-color: #409eff;
}

.checkbox-group {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  max-height: 120px;
  overflow-y: auto;
  padding: 5px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  font-size: 14px;
  color: #606266;
  padding: 3px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.checkbox-item:hover {
  background-color: #f5f7fa;
}

.robust-item {
  font-weight: 500;
}

.checkbox-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.selected-hint {
  font-size: 12px;
  color: #909399;
  padding-top: 5px;
}

.fe-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 5px;
}

.fe-hint {
  font-size: 12px;
  color: #c0c4cc;
  font-style: italic;
}

.robust-config {
  margin: 10px 0 10px 0;
  padding: 12px;
  background: #fafbfc;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}

.robust-sub-config {
  margin-top: 12px;
  padding: 12px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
}

.config-title {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 10px;
}

.exclude-years {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hint {
  font-size: 12px;
  color: #909399;
}

.form-actions {
  margin-top: 24px;
  padding-left: 0;
  text-align: center;
}

.submit-btn {
  padding: 12px 48px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #66b1ff;
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 导入自模型行 */
.model-import-row {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 8px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
  border: 1px solid #e1f3d8;
}

.form-label-sm {
  font-size: 13px;
  color: #606266;
  font-weight: 500;
  white-space: nowrap;
}

.form-select-sm {
  max-width: 240px;
  padding: 4px 8px;
  font-size: 13px;
}

.import-hint {
  font-size: 12px;
  color: #67c23a;
}

/* 多选调节变量 */
.moderation-multi-select {
  margin-bottom: 14px;
}

/* ==================== 模块选择按钮行 ==================== */
.module-tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  padding: 4px;
  background: #f0f2f5;
  border-radius: 8px;
  overflow-x: auto;
}

.module-tab-btn {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
  transition: all 0.2s;
}

.module-tab-btn:hover {
  background: #e4e7ed;
  color: #303133;
}

.module-tab-btn.active {
  background: #fff;
  color: #409eff;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.tab-icon {
  font-size: 16px;
}

.tab-title {
  font-size: 13px;
}

.tab-tag {
  margin-left: 2px;
  transform: scale(0.85);
}

.tab-summary {
  font-size: 11px;
  color: #909399;
  margin-left: 4px;
}
</style>
