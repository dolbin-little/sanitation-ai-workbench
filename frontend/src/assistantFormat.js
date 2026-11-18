export const fieldLabels = {
  id: '任务编号',
  name: '任务名称',
  kind: '作业类型',
  start: '作业地点 / 起点',
  end: '终点',
  earliest: '最早时间',
  deadline: '完成时限',
  service: '作业时长（分钟）',
  demand: '垃圾量（吨）',
  water: '用水量（立方米）',
  priority: '优先级 1–3',
  locked_to: '车牌 / 车辆',
  longitude: '经度',
  latitude: '纬度',
  coordinate_system: '坐标系',
}

export function time(value) {
  if (value == null) return '—'
  const minutes = Math.round(value)
  const hours = String(Math.floor(minutes / 60)).padStart(2, '0')
  const remainder = String(minutes % 60).padStart(2, '0')
  return `${hours}:${remainder}`
}

export function assignment(value) {
  return value
    ? `${value.vehicle} · 第${value.order}个动作 · 完成 ${time(value.finish)}`
    : '未安排'
}
