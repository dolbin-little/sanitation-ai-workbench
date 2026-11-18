<script setup>
import { fieldLabels } from './assistantFormat.js'

defineProps({ response: Object })

const toolTitles = {
  plan: '候选方案已生成',
  import_tasks: '任务导入结果',
  event: '事件登记结果',
  manual: '人工改派候选',
}
</script>

<template>
  <p v-if="!response" class="muted">执行结果将显示在这里。</p>
  <template v-else>
    <p v-if="response.feedback">
      完整成功 {{ response.feedback.completed_steps }} 步，含失败/保护项 {{ response.feedback.failed_steps }}
      步（{{ response.feedback.failed_items || 0 }} 项）。{{ response.feedback.next }}
    </p>
    <p v-if="response.questions?.length" class="item error">
      请集中补充：{{ response.questions.map(field => fieldLabels[field] || field).join('、') }}
    </p>
    <div v-for="(result, index) in response.results || []" :key="index" class="item" :class="{ error: result.error }">
      <b>{{ result.error ? '操作未完成' : (toolTitles[result.tool] || '操作结果') }}</b>
      <p v-if="result.error">{{ result.error }}</p>
      <p v-if="result.imported">成功导入 {{ result.imported.length }} 项：{{ result.imported.join('、') || '无' }}</p>
      <p v-for="(error, i) in result.errors || []" :key="i">第{{ error.row }}行：{{ error.error }}</p>
      <p v-if="result.batch_id">批次：{{ result.batch_id }}</p>
      <p v-if="result.duplicate">检测到重复批次，未重复写入</p>
      <p v-if="result.removed">已撤回：{{ result.removed.join('、') || '无' }}</p>
      <p v-for="item in result.blocked || []" :key="item.task">{{ item.task }}：{{ item.reason }}</p>
      <p v-if="result.next">下一步：{{ result.next }}</p>
      <p v-if="result.event">{{ result.event.label }}</p>
      <template v-if="result.metrics">
        <p>安排 {{ result.metrics.scheduled }} 项 · 待处理 {{ result.metrics.unassigned }} 项 · 窗外暂缓 {{ result.metrics.deferred || 0 }} 项</p>
        <p>预计逾期 {{ result.metrics.late_tasks }} 项 · 非作业里程 {{ result.metrics.deadhead_km }} km</p>
        <p>尚未下发，请核对下方具体变更。</p>
      </template>
      <details>
        <summary>查看工具原始结果</summary>
        <pre>{{ JSON.stringify(result, null, 2) }}</pre>
      </details>
    </div>
    <template v-if="response.rows">
      <p>校验通过 {{ response.rows.length }} 项；错误 {{ response.errors.length }} 项。尚未导入。</p>
      <div v-for="(row, index) in response.rows" :key="index" class="item">
        {{ row.id }} · {{ row.name }} · {{ row.kind }} · {{ row.start }} → {{ row.end }}
      </div>
    </template>
    <div v-for="(error, index) in response.errors || []" :key="index" class="item error">
      第{{ error.row }}行：{{ error.error }}
    </div>
  </template>
</template>
