<template>
  <div class="manual-view">
    <div class="page-header">
      <h2>手动控制</h2>
      <el-tag type="warning" size="large">绕过 AI，直接下发合法指令</el-tag>
    </div>

    <div class="manual-layout">
      <!-- 左侧：表单区 -->
      <div class="form-col">
        <!-- 指令类型选择 -->
        <el-card class="form-card">
          <div class="section-title">指令类型</div>
          <el-radio-group v-model="commandType" size="large" @change="onTypeChange">
            <el-radio-button value="dispense">单步称量</el-radio-button>
            <el-radio-button value="aliquot">等量分装</el-radio-button>
            <el-radio-button value="mix">混合配料</el-radio-button>
            <el-radio-button value="restock">库存录入</el-radio-button>
            <el-radio-button value="cancel">取消任务</el-radio-button>
            <el-radio-button value="emergency_stop">急停</el-radio-button>
            <el-radio-button value="device_status">查询状态</el-radio-button>
          </el-radio-group>
        </el-card>

        <!-- ── dispense：单步称量 ─────────────────────────────── -->
        <el-card v-if="commandType === 'dispense'" class="form-card">
          <div class="section-title">称量参数</div>
          <el-form :model="dispenseForm" label-width="110px" size="large">
            <el-form-item label="药品编号" required>
              <el-input v-model="dispenseForm.reagent_code" placeholder="如 NaCl-AR" />
            </el-form-item>
            <el-form-item label="药品中文名" required>
              <el-input v-model="dispenseForm.reagent_name_cn" placeholder="如 氯化钠" />
            </el-form-item>
            <el-form-item label="所在工位">
              <el-input v-model="dispenseForm.station_id" placeholder="如 station_3" />
            </el-form-item>
            <el-form-item label="目标质量(mg)" required>
              <el-input-number v-model="dispenseForm.target_mass_mg" :min="1" :step="10" style="width:100%" />
            </el-form-item>
            <el-form-item label="允许误差(mg)" required>
              <el-input-number v-model="dispenseForm.tolerance_mg" :min="0" :step="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="目标容器" required>
              <el-input v-model="dispenseForm.target_vessel" placeholder="如 A1" />
            </el-form-item>
            <el-form-item label="纯度等级">
              <el-input v-model="dispenseForm.purity_grade" placeholder="如 AR" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="dispenseForm.notes" />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ── aliquot：等量分装 ──────────────────────────────── -->
        <el-card v-if="commandType === 'aliquot'" class="form-card">
          <div class="section-title">分装参数</div>
          <el-form :model="aliquotForm" label-width="130px" size="large">
            <el-form-item label="药品编号" required>
              <el-input v-model="aliquotForm.reagent_code" placeholder="如 NaCl-AR" />
            </el-form-item>
            <el-form-item label="药品中文名" required>
              <el-input v-model="aliquotForm.reagent_name_cn" />
            </el-form-item>
            <el-form-item label="所在工位">
              <el-input v-model="aliquotForm.station_id" />
            </el-form-item>
            <el-form-item label="份数(2~30)" required>
              <el-input-number v-model="aliquotForm.portions" :min="2" :max="30" style="width:100%" @change="syncVessels" />
            </el-form-item>
            <el-form-item label="每份质量(mg)" required>
              <el-input-number v-model="aliquotForm.mass_per_portion_mg" :min="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="每份误差(mg)" required>
              <el-input-number v-model="aliquotForm.tolerance_mg" :min="0" style="width:100%" />
            </el-form-item>
            <el-form-item label="目标容器列表" required>
              <div class="vessel-list">
                <el-input
                  v-for="(_, i) in aliquotForm.target_vessels"
                  :key="i"
                  v-model="aliquotForm.target_vessels[i]"
                  :placeholder="`容器 ${i + 1}，如 A${i + 1}`"
                  size="default"
                  style="margin-bottom:4px"
                />
              </div>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ── mix：混合配料 ───────────────────────────────────── -->
        <el-card v-if="commandType === 'mix'" class="form-card">
          <div class="section-title">混合参数</div>
          <el-form :model="mixForm" label-width="110px" size="large">
            <el-form-item label="配方名称">
              <el-input v-model="mixForm.formula_name" />
            </el-form-item>
            <el-form-item label="总目标质量(mg)" required>
              <el-input-number v-model="mixForm.total_mass_mg" :min="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="比例类型" required>
              <el-select v-model="mixForm.ratio_type" style="width:100%">
                <el-option label="质量分数" value="mass_fraction" />
                <el-option label="摩尔分数" value="molar_fraction" />
              </el-select>
            </el-form-item>
            <el-form-item label="目标容器" required>
              <el-input v-model="mixForm.target_vessel" placeholder="如 main" />
            </el-form-item>
          </el-form>
          <!-- 组分列表 -->
          <div class="section-title" style="margin-top:12px">
            组分列表
            <el-button size="small" @click="addMixComponent" style="margin-left:8px">+ 添加组分</el-button>
          </div>
          <div v-for="(comp, i) in mixForm.components" :key="i" class="mix-comp-row">
            <div class="comp-header">
              <span>组分 {{ i + 1 }}</span>
              <el-button size="small" type="danger" link @click="removeMixComponent(i)">删除</el-button>
            </div>
            <el-form :model="comp" label-width="120px" size="default">
              <el-form-item label="药品编号">
                <el-input v-model="comp.reagent_code" placeholder="如 NaCl-AR" />
              </el-form-item>
              <el-form-item label="药品中文名">
                <el-input v-model="comp.reagent_name_cn" />
              </el-form-item>
              <el-form-item label="工位">
                <el-input v-model="comp.station_id" />
              </el-form-item>
              <el-form-item label="占比(0~1)">
                <el-input-number v-model="comp.fraction" :min="0.001" :max="0.999" :step="0.01" :precision="3" style="width:100%" />
              </el-form-item>
              <el-form-item label="称量质量(mg)">
                <el-input-number v-model="comp.calculated_mass_mg" :min="1" style="width:100%" />
              </el-form-item>
              <el-form-item label="误差(mg)">
                <el-input-number v-model="comp.tolerance_mg" :min="0" style="width:100%" />
              </el-form-item>
              <el-form-item v-if="mixForm.ratio_type === 'molar_fraction'" label="摩尔质量(g/mol)">
                <el-input-number v-model="comp.molar_weight_g_mol" :min="0.01" :step="0.01" style="width:100%" />
              </el-form-item>
            </el-form>
          </div>
        </el-card>

        <!-- ── restock：库存录入 ──────────────────────────────── -->
        <el-card v-if="commandType === 'restock'" class="form-card">
          <div class="section-title">库存录入参数</div>
          <el-form :model="restockForm" label-width="110px" size="large">
            <el-form-item label="药品编号" required>
              <el-input v-model="restockForm.reagent_code" />
            </el-form-item>
            <el-form-item label="录入质量(mg)" required>
              <el-input-number v-model="restockForm.added_mass_mg" :min="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="工位">
              <el-input v-model="restockForm.station_id" />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ── cancel：取消任务 ───────────────────────────────── -->
        <el-card v-if="commandType === 'cancel'" class="form-card">
          <div class="section-title">取消当前任务</div>
          <el-alert
            title="将向 C++ 控制程序下发取消指令，中止当前正在执行的任务"
            type="warning"
            show-icon
            :closable="false"
          />
        </el-card>

        <!-- ── emergency_stop ───────────────────────────────── -->
        <el-card v-if="commandType === 'emergency_stop'" class="form-card">
          <el-alert
            title="紧急停机：立即停止所有动作，设备将进入锁定状态，需人工确认后才能恢复"
            type="error"
            show-icon
            :closable="false"
          />
        </el-card>

        <!-- ── device_status ────────────────────────────────── -->
        <el-card v-if="commandType === 'device_status'" class="form-card">
          <div class="section-title">查询设备状态</div>
          <el-alert
            title="下发后后端将主动查询 C++ 控制程序当前状态，结果返回到系统状态页"
            type="info"
            show-icon
            :closable="false"
          />
        </el-card>

        <!-- 确认并下发 -->
        <el-card class="form-card confirm-card">
          <el-checkbox v-model="confirmed" size="large">
            我已确认参数正确，同意下发
          </el-checkbox>
          <el-button
            type="danger"
            size="large"
            :disabled="!confirmed || submitting"
            :loading="submitting"
            style="margin-top:12px; width:100%"
            @click="handleSubmit"
          >
            {{ submitLabel }}
          </el-button>
          <div v-if="submitResult" class="submit-result" :class="submitResult.ok ? 'ok' : 'err'">
            {{ submitResult.message }}
          </div>
        </el-card>
      </div>

      <!-- 右侧：command JSON 预览 -->
      <div class="preview-col">
        <el-card class="preview-card">
          <div class="section-title">
            Command JSON 预览
            <el-tag size="small" type="info" style="margin-left:8px">schema_version 2.1</el-tag>
          </div>
          <pre class="json-preview">{{ jsonPreview }}</pre>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { manualApi } from '@/services/api'

// ─── 指令类型 ─────────────────────────────────────────────────────
type CmdType = 'dispense' | 'aliquot' | 'mix' | 'restock' | 'cancel' | 'emergency_stop' | 'device_status'
const commandType = ref<CmdType>('dispense')

// ─── dispense 表单 ────────────────────────────────────────────────
const dispenseForm = reactive({
  reagent_code: '',
  reagent_name_cn: '',
  station_id: '',
  target_mass_mg: 100,
  tolerance_mg: 5,
  target_vessel: 'A1',
  purity_grade: '',
  notes: '',
})

// ─── aliquot 表单 ─────────────────────────────────────────────────
const aliquotForm = reactive({
  reagent_code: '',
  reagent_name_cn: '',
  station_id: '',
  portions: 2,
  mass_per_portion_mg: 100,
  tolerance_mg: 5,
  target_vessels: ['A1', 'A2'] as string[],
})

function syncVessels(n: number): void {
  const arr = [...aliquotForm.target_vessels]
  while (arr.length < n) arr.push('')
  while (arr.length > n) arr.pop()
  aliquotForm.target_vessels = arr
}

// ─── mix 表单 ─────────────────────────────────────────────────────
interface MixComp {
  reagent_code: string
  reagent_name_cn: string
  station_id: string
  fraction: number
  calculated_mass_mg: number
  tolerance_mg: number
  molar_weight_g_mol: number
}

const mixForm = reactive({
  formula_name: '',
  total_mass_mg: 1000,
  ratio_type: 'mass_fraction' as 'mass_fraction' | 'molar_fraction',
  target_vessel: 'main',
  components: [] as MixComp[],
})

function addMixComponent(): void {
  mixForm.components.push({
    reagent_code: '', reagent_name_cn: '', station_id: '',
    fraction: 0.5, calculated_mass_mg: 500, tolerance_mg: 10, molar_weight_g_mol: 58.44,
  })
}

function removeMixComponent(i: number): void {
  mixForm.components.splice(i, 1)
}

// ─── restock 表单 ─────────────────────────────────────────────────
const restockForm = reactive({
  reagent_code: '',
  added_mass_mg: 1000,
  station_id: '',
})

// ─── 类型切换重置 ─────────────────────────────────────────────────
function onTypeChange(): void {
  confirmed.value = false
  submitResult.value = null
}

// ─── 生成 command JSON ────────────────────────────────────────────
function buildPayload(): Record<string, unknown> {
  switch (commandType.value) {
    case 'dispense':
      return {
        reagent_code:     dispenseForm.reagent_code,
        reagent_name_cn:  dispenseForm.reagent_name_cn,
        reagent_name_en:  '',
        reagent_name_formula: '',
        purity_grade:     dispenseForm.purity_grade || undefined,
        station_id:       dispenseForm.station_id || undefined,
        target_mass_mg:   dispenseForm.target_mass_mg,
        tolerance_mg:     dispenseForm.tolerance_mg,
        target_vessel:    dispenseForm.target_vessel,
        notes:            dispenseForm.notes || '',
      }
    case 'aliquot':
      return {
        reagent_code:         aliquotForm.reagent_code,
        reagent_name_cn:      aliquotForm.reagent_name_cn,
        station_id:           aliquotForm.station_id || undefined,
        portions:             aliquotForm.portions,
        mass_per_portion_mg:  aliquotForm.mass_per_portion_mg,
        tolerance_mg:         aliquotForm.tolerance_mg,
        target_vessels:       [...aliquotForm.target_vessels],
      }
    case 'mix':
      return {
        formula_name:   mixForm.formula_name || undefined,
        total_mass_mg:  mixForm.total_mass_mg,
        ratio_type:     mixForm.ratio_type,
        components:     mixForm.components.map(c => ({
          reagent_code:         c.reagent_code,
          reagent_name_cn:      c.reagent_name_cn,
          station_id:           c.station_id || undefined,
          fraction:             c.fraction,
          calculated_mass_mg:   c.calculated_mass_mg,
          tolerance_mg:         c.tolerance_mg,
          molar_weight_g_mol:   mixForm.ratio_type === 'molar_fraction' ? c.molar_weight_g_mol : undefined,
        })),
        target_vessel:  mixForm.target_vessel,
        execution_mode: 'sequential',
      }
    case 'restock':
      return {
        reagent_code:  restockForm.reagent_code,
        added_mass_mg: restockForm.added_mass_mg,
        station_id:    restockForm.station_id || undefined,
      }
    case 'cancel':
      return {}
    case 'emergency_stop':
      return {}
    case 'device_status':
      return {}
    default:
      return {}
  }
}

const commandTypeLabels: Record<string, string> = {
  dispense: '单步称量', aliquot: '等量分装', mix: '混合配料',
  restock: '库存录入', cancel: '取消任务', emergency_stop: '紧急停机', device_status: '查询状态',
}

const jsonPreview = computed(() => {
  const obj = {
    schema_version: '2.1',
    command_id: '<由后端生成 UUID>',
    timestamp: '<由后端生成>',
    operator_id: 'admin',
    command_type: commandType.value,
    payload: buildPayload(),
    confirmation: ['dispense','aliquot','mix','restock'].includes(commandType.value)
      ? { method: 'screen', confirmed_at: '<由后端填充>' }
      : undefined,
  }
  return JSON.stringify(obj, null, 2)
})

// ─── 提交 ─────────────────────────────────────────────────────────
const confirmed  = ref(false)
const submitting = ref(false)
const submitResult = ref<{ ok: boolean; message: string } | null>(null)

const submitLabel = computed(() => {
  const labels: Record<string, string> = {
    emergency_stop: '⚠️ 立即急停',
    cancel: '取消当前任务',
  }
  return labels[commandType.value] ?? `下发 ${commandTypeLabels[commandType.value]} 指令`
})

async function handleSubmit(): Promise<void> {
  // 高危操作二次确认
  if (commandType.value === 'emergency_stop') {
    try {
      await ElMessageBox.confirm(
        '确认执行紧急停机？所有动作将立即停止！',
        '⚠️ 紧急停机确认',
        { type: 'error', confirmButtonText: '确认急停', cancelButtonText: '取消' }
      )
    } catch { return }
  }

  submitting.value = true
  submitResult.value = null
  try {
    const { data } = await manualApi.sendCommand({
      command_type: commandType.value,
      payload: buildPayload(),
    })
    submitResult.value = { ok: true, message: `下发成功，任务 ID: ${data.task_id ?? data.command_id}` }
    ElMessage.success('指令已下发')
    confirmed.value = false
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '下发失败，请检查设备状态'
    submitResult.value = { ok: false, message: msg }
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.manual-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  height: 100%;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  flex-shrink: 0;
}

.manual-layout {
  display: grid;
  grid-template-columns: 1fr 420px;
  gap: var(--spacing-4);
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.form-col {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  overflow-y: auto;
  padding-right: 4px;
}

.preview-col {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.form-card { flex-shrink: 0; }

.section-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-3);
  display: flex;
  align-items: center;
}

.vessel-list {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.mix-comp-row {
  background: var(--bg-card-hover);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-3);
}

.comp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.confirm-card {
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.submit-result {
  margin-top: 10px;
  font-size: 0.88rem;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
}
.submit-result.ok  { background: rgba(34,197,94,0.1); color: var(--status-success); }
.submit-result.err { background: rgba(239,68,68,0.1); color: var(--status-error); }

/* 右侧预览 */
.preview-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.json-preview {
  flex: 1;
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.78rem;
  line-height: 1.6;
  color: #9cdcfe;
  background: #0d1117;
  border-radius: var(--radius-sm);
  padding: var(--spacing-3);
  white-space: pre;
  margin: 0;
}
</style>
