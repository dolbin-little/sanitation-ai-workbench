<script setup>
import { assignment, time } from './assistantFormat.js'

defineProps({ state: Object })
</script>

<template>
  <p v-if="!state?.candidate_metrics" class="muted">尚无候选方案。导入任务或登记事件后，可生成候选方案。</p>
  <template v-else>
    <p>待人工确认 · 以下内容不会自动下发。</p>
    <div v-for="change in state.changes" :key="change.task" class="item">
      <b>{{ change.task }}</b>
      <div>原：{{ assignment(change.before) }}</div>
      <div class="arrow">新：{{ assignment(change.after) }}</div>
    </div>
    <p v-if="!state.changes.length">任务分配、顺序和完成时间未变化；仍可检查完整动作路线。</p>
    <div v-for="task in state.deferred || []" :key="task" class="item">{{ task }}：在当前滚动规划窗口之外，暂缓安排。</div>
    <div v-for="(item, index) in state.unassigned" :key="index" class="item error">待处理：{{ JSON.stringify(item) }}</div>
    <details>
      <summary>完整候选路线（含补水 / 卸载等动作）</summary>
      <template v-for="(actions, vehicle) in state.candidate_routes" :key="vehicle">
        <b v-if="actions.length">{{ vehicle }}</b>
        <div v-for="(action, index) in actions" :key="index" class="item">
          {{ action.task || action.label || action.type || '设施动作' }}：
          {{ action.start }} → {{ action.end }} · {{ time(action.arrive) }}—{{ time(action.finish) }}
        </div>
      </template>
    </details>
  </template>
</template>
