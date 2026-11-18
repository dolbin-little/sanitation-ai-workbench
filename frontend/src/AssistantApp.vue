<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import CandidatePlan from './CandidatePlan.vue'
import SourceList from './SourceList.vue'
import WorkResults from './WorkResults.vue'
import { assignment, fieldLabels, time } from './assistantFormat.js'

const sessionKey = 'sanitation-session'
const retryable = new Set(['chat', 'import', 'plan', 'withdraw', 'retry_import'])
const messages = ref([])
const conversation = ref(null)
const fileInput = ref(null)
const importSetup = ref(null)
const sessionId = ref(localStorage.getItem(sessionKey) || crypto.randomUUID())
const state = ref(null)
const status = ref(null)
const history = ref([])
const batches = ref([])
const response = ref(null)
const sources = ref([])
const busy = ref(false)
const lastFailed = ref(null)
const connectionError = ref(false)
const notice = ref('正在连接作业助手……')
const question = ref('')
const execute = ref(false)
const attachment = ref(null)
const headers = ref([])
const mapping = ref({})
const defaults = ref({})
const locations = ref('')
const knowledgeQuery = ref('')
const knowledgeResults = ref([])
const explainTask = ref('')
const explanation = ref(null)

const stats = computed(() => state.value ? [
  ['未完成任务', state.value.tasks.filter(task => task.status !== 'done').length],
  ['可用车辆', state.value.vehicles.filter(vehicle => vehicle.enabled).length],
  ['方案变更', state.value.changes.length],
] : [])

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
  try {
    const result = await fetch('/api/assistant/' + path, options)
    const data = await result.json()
    if (!result.ok) throw new Error(data.error || '请求失败')
    return data
  } catch (error) {
    if (body && retryable.has(path)) lastFailed.value = { path, body }
    throw error
  }
}

function addMessage(text, role = 'assistant', citations = []) {
  messages.value.push({ text, role, citations })
}

watch(() => messages.value.length, async () => {
  await nextTick()
  if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight
})

async function refresh() {
  const [configuration, data] = await Promise.all([api('status'), api('state')])
  status.value = configuration
  state.value = data.state
  batches.value = (data.batches || []).slice().reverse()
  history.value = data.history.slice().reverse()
  connectionError.value = false
  if (!busy.value) {
    notice.value = configuration.configured
      ? '模型配置已加载。支持多轮补充；每次写操作须勾选本条执行授权。'
      : '尚未配置模型，可先使用本地清单工具。'
  }
}

async function run(action) {
  if (busy.value) return
  busy.value = true
  notice.value = '处理中，请勿重复提交……'
  try {
    await action()
    notice.value = '处理结束。候选方案仍需前往调度工作台人工审核。'
  } catch (error) {
    notice.value = error.message
    addMessage(error.message)
  } finally {
    busy.value = false
  }
}

function requestContext() {
  if (!state.value) throw new Error('请先刷新状态')
  return {
    revision: state.value.revision,
    request_id: crypto.randomUUID(),
    session_id: sessionId.value,
  }
}

function showResult(data) {
  response.value = data
  if (data.state) state.value = data.state
}

async function startSession() {
  sessionId.value = crypto.randomUUID()
  localStorage.setItem(sessionKey, sessionId.value)
  messages.value = []
  addMessage('新会话已开始。旧会话操作记录仍保留在本地。')
}

function importOptions() {
  const rows = locations.value.split('\n').filter(line => line.trim())
  const locationMap = Object.fromEntries(rows.map(line => {
    const separator = line.indexOf('=')
    if (separator < 1) throw new Error('地点对应须写成：地点名称=节点')
    return [line.slice(0, separator).trim(), line.slice(separator + 1).trim()]
  }))
  return {
    mapping: headers.value.length ? Object.fromEntries(Object.keys(fieldLabels)
      .map(field => [field, mapping.value[field] || ''])) : {},
    defaults: Object.fromEntries(Object.entries(defaults.value)
      .filter(([, value]) => value.trim())
      .map(([field, value]) => [field, value.trim()])),
    locations: locationMap,
  }
}

function isTaskFile(file) {
  return file && ['csv', 'json'].includes(file.ext)
}

function fileBody() {
  if (!isTaskFile(attachment.value)) throw new Error('请先选择 CSV、JSON 或 Excel 任务清单')
  const { name, content } = attachment.value
  return { filename: name, content, options: importOptions() }
}

function clearAttachment() {
  attachment.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function selectFile(file) {
  attachment.value = null
  if (!file) return
  const ext = file.name.split('.').at(-1).toLowerCase()
  const image = ['png', 'jpg', 'jpeg'].includes(ext)
  const binary = ['xlsx', 'pdf'].includes(ext)
  if (file.size > (image || binary ? 2000000 : 500000)) {
    throw new Error('文本上限500KB，图片/工作簿/PDF上限2MB')
  }
  const content = image || binary ? await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsDataURL(file)
  }) : await file.text()
  if (binary) {
    const data = await api('extract', { filename: file.name, base64: content.split(',')[1] })
    attachment.value = {
      name: data.filename, ext: data.kind === 'tasks' ? 'json' : 'txt',
      content: data.content, displayName: file.name, image: false,
    }
    addMessage(data.note)
  } else {
    attachment.value = { name: file.name, ext, content, displayName: file.name, image }
  }
  headers.value = []
  mapping.value = {}
  defaults.value = {}
  locations.value = ''
  if (isTaskFile(attachment.value)) {
    const { name, content: taskContent } = attachment.value
    const data = await api('preview', { filename: name, content: taskContent, options: {} })
    headers.value = data.mapping_info.headers
    mapping.value = data.mapping_info.mapping
    showResult(data)
    if (data.errors.length) importSetup.value.open = true
  }
}

async function previewFile() {
  const data = await api('preview', fileBody())
  showResult(data)
  addMessage(`本地校验完成：${data.rows.length}条有效，${data.errors.length}条错误；尚未写入。`)
}

async function importFile() {
  const data = await api('import', {
    ...requestContext(), ...fileBody(), message: '导入文件：' + attachment.value.name,
  })
  showResult(data)
  addMessage('导入工具已返回，请核对右侧逐项结果。未生成或下发计划。')
  await refresh()
}

async function generatePlan() {
  showResult(await api('plan', { ...requestContext(), message: '生成候选调度方案' }))
  addMessage('请查看右侧候选方案与具体变更；确认下发请前往调度工作台。')
  await refresh()
}

async function sendMessage() {
  const text = question.value.trim()
  if (!text) throw new Error('请先输入问题或指令')
  const body = { ...requestContext(), message: text, execute: execute.value }
  const file = attachment.value
  if (file?.image) body.image = file.content
  else if (file) body.attachment = { filename: file.name, content: file.content, options: importOptions() }
  addMessage(text, 'user')
  const data = await api('chat', body)
  displayAnswer(data)
  question.value = ''
  execute.value = false
  await refresh()
}

function displayAnswer(data) {
  sources.value = data.sources || []
  addMessage(data.answer, 'assistant', sources.value.filter(source => (data.citations || []).includes(source.id)))
  showResult(data)
  if (data.proposed?.length && !data.results) addMessage('以上是建议步骤，未执行写入。需要执行时，请勾选允许执行并明确提出指令。')
  if (data.results) addMessage('实际执行结果已显示在工作结果中，请核对成功项与错误项。')
}

async function batchAction(path, batchId) {
  const body = { ...requestContext(), batch_id: batchId }
  if (path === 'retry_import') body.options = importOptions()
  showResult(await api(path, body))
  await refresh()
}

async function retryRequest() {
  const { path, body } = lastFailed.value
  const data = await api(path, body)
  if (path === 'chat') {
    displayAnswer(data)
    if (question.value.trim() === body.message) question.value = ''
    execute.value = false
  } else {
    showResult(data)
  }
  lastFailed.value = null
  await refresh()
}

async function explain() {
  explanation.value = await api('explain', { task: explainTask.value.trim() })
}

async function searchKnowledge() {
  const data = await api('knowledge', { query: knowledgeQuery.value })
  knowledgeResults.value = data.sources || []
}

onMounted(async () => {
  try {
    localStorage.setItem(sessionKey, sessionId.value)
    await refresh()
    const { turns } = await api('conversation', { session_id: sessionId.value })
    for (const turn of turns) {
      addMessage(turn.user.message, 'user')
      addMessage(turn.answer)
    }
  } catch (error) {
    connectionError.value = !status.value
    notice.value = error.message
  }
})
</script>

<template>
  <aside>
    <a class="brand" href="/">↗ 环卫智枢<small>URBAN AUTONOMY</small></a>
    <nav aria-label="应用导航">
      <a class="selected" href="/assistant" aria-current="page">✦ AI 作业中心</a>
      <a href="/dispatch">▦ 车队调度与任务中心</a>
      <a href="/">◎ 环卫驾驶协同</a>
    </nav>
    <div class="aside-bottom">理解需求 → 调用工具 → 核对结果<p>调度下发始终由人审核<br>本地仿真 · 不控制实车</p></div>
  </aside>
  <main>
    <header>
      <span>城市运行 / AI 作业中心</span>
      <button id="new-session" class="light" :disabled="busy" @click="run(startSession)">新会话</button>
      <button id="refresh" class="light" :disabled="busy" @click="run(refresh)">刷新状态</button>
    </header>
    <section class="heading">
      <div>
        <div class="eyebrow">SANITATION INTELLIGENCE / ASSISTANT</div>
        <h1>一句话，连接作业全流程。</h1>
        <p>导入清单、登记事件、生成候选方案，并看清每一次调整。</p>
      </div>
      <span id="connection" class="badge">{{ connectionError ? '连接失败' : (status?.mode || '连接中') }}</span>
    </section>
    <div class="layout">
      <section class="conversation panel">
        <div class="panelhead"><b>作业助手</b><span>指令与结果都可追溯</span></div>
        <div id="messages" ref="conversation" aria-live="polite">
          <article v-if="!messages.length" class="assistant">
            <b>从一份清单，或一个问题开始</b>
            <p>例如：“查询现在的未完成任务”“登记 V01 车辆故障，并生成候选方案”。请先在右侧核对车辆、节点编号。</p>
            <p>文件和图片会随消息发送给你配置的模型服务。CSV / JSON 的本地导入不发送给模型。</p>
          </article>
          <article v-for="(message, index) in messages" :key="index" :class="message.role">
            {{ message.text }}
            <small v-if="message.citations.length">依据：{{ message.citations.map(citation => citation.source).join(' / ') }}</small>
          </article>
        </div>
        <div class="composer">
          <div class="attachment">
            <label class="filebutton">＋ 清单 / 图片<input id="file" ref="fileInput" type="file"
              accept=".csv,.json,.txt,.xlsx,.pdf,.png,.jpg,.jpeg" :disabled="busy"
              @change="run(() => selectFile($event.target.files[0]))"></label>
            <span id="filename">{{ attachment?.displayName || '未选择文件' }}</span>
            <button id="clear" class="light" :disabled="busy" @click="clearAttachment">移除</button>
          </div>
          <textarea id="message" v-model="question" placeholder="描述你的任务，或询问方案发生了哪些变化……"
            aria-label="发送给作业助手的消息" maxlength="8000" :disabled="busy"></textarea>
          <div class="sendrow">
            <label><input id="execute" v-model="execute" type="checkbox" :disabled="busy"> 允许执行本条明确指令（不含下发）</label>
            <button id="send" :disabled="busy" @click="run(sendMessage)">发送给助手 ↗</button>
          </div>
          <div class="localtools">
            <button id="preview" class="light" :disabled="busy" @click="run(previewFile)">本地校验清单</button>
            <button id="import" class="light" :disabled="busy" @click="run(importFile)">导入有效任务</button>
            <button id="plan" class="light" :disabled="busy || !state" @click="run(generatePlan)">生成候选方案</button>
          </div>
          <button v-if="lastFailed" id="retry-last" class="light" :disabled="busy" @click="run(retryRequest)">重试上次失败请求</button>
          <p id="notice" role="status">{{ notice }}</p>
        </div>
      </section>
      <section class="results">
        <div class="panel">
          <details id="import-setup" ref="importSetup">
            <summary>企业清单 · 字段映射与缺项补充</summary>
            <div class="body">
              <p>选择清单后自动识别表头，可更改映射。统一补充值只用于空白单元格。</p>
              <div id="mapping-fields">
                <div v-for="(label, field) in (headers.length ? fieldLabels : {})" :key="field" class="mapline">
                  <label :for="'map-' + field">{{ label }}</label>
                  <select :id="'map-' + field" v-model="mapping[field]" :data-map="field">
                    <option value="">未提供</option>
                    <option v-for="header in headers" :key="header" :value="header">{{ header }}</option>
                  </select>
                  <input v-model="defaults[field]" :data-default="field" :aria-label="label + '统一补充值'" placeholder="空白项统一补充">
                </div>
              </div>
              <label>地点对应（每行：地点名称=现有节点）<textarea id="locations" v-model="locations" placeholder="东门垃圾站=N1-4"></textarea></label>
              <p>经纬度仅匹配已有 WGS84 节点，30 米内须唯一，当前合成路网不能直接套用真实坐标。</p>
            </div>
          </details>
        </div>
        <div class="panel">
          <div class="panelhead"><b>工作结果</b><span id="revision">{{ state ? '状态 v' + state.revision : '' }}</span></div>
          <div class="body">
            <div id="stats" class="stats"><div v-for="[label, count] in stats" :key="label">{{ label }}<strong>{{ count }}</strong></div></div>
            <div id="sources"><SourceList :rows="sources" /></div>
            <div id="result"><WorkResults :response="response" /></div>
          </div>
        </div>
        <div class="panel">
          <div class="panelhead"><b>候选方案 · 下发前预览</b><a href="/dispatch">前往人工审核 ↗</a></div>
          <div id="changes" class="body"><CandidatePlan :state="state" /></div>
        </div>
        <div class="panel">
          <div class="panelhead"><b>方案解释 · 核验依据</b></div>
          <div class="body">
            <input id="explain-task" v-model="explainTask" aria-label="任务编号" placeholder="输入任务编号，如 T001">
            <button id="explain-button" class="light" :disabled="busy" @click="run(explain)">查看求解记录</button>
            <div id="explanation" v-if="explanation">
              <b>① 客观变化</b>
              <p v-for="fact in explanation.facts" :key="fact.task">{{ fact.task }}：{{ assignment(fact.before) }} → {{ assignment(fact.after) }}</p>
              <b>② 已核验：求解器实际尝试</b>
              <p>{{ explanation.scope }}</p>
              <div v-for="item in explanation.evidence" :key="item.vehicle" class="item">
                {{ item.vehicle }}：记录 {{ item.tested }} 次，可行 {{ item.feasible }} 次。
                {{ Object.entries(item.rejections).map(([reason, count]) => reason + '（' + count + '次）').join('；') }}
              </div>
              <b>③ 推测 / 尚未确定</b><p>{{ explanation.inference }}</p>
            </div>
          </div>
        </div>
        <div class="panel">
          <details>
            <summary>导入批次 · 撤回与重试</summary>
            <div id="batches" class="body">
              <div v-for="batch in batches" :key="batch.id" class="item">
                <b>{{ batch.id }}</b><p>来源：{{ batch.source || '历史导入' }}</p>
                <p>状态 {{ batch.status }} · 累计导入 {{ batch.imported.length }} 项 · 失败 {{ batch.failed_rows.length }} 项 · 已归档 {{ batch.archived.length }} 项</p>
                <p v-for="(error, index) in batch.errors" :key="index">{{ error.error }}</p>
                <button v-if="batch.failed_rows.length && batch.status !== 'withdrawn'" class="light" :disabled="busy"
                  @click="run(() => batchAction('retry_import', batch.id))">用当前补充值重试失败行</button>
                <button v-if="batch.status !== 'withdrawn'" class="light" :disabled="busy"
                  @click="run(() => batchAction('withdraw', batch.id))">撤回符合条件的任务</button>
                <details>
                  <summary>失败行与归档原记录</summary>
                  <pre>{{ JSON.stringify({ failed: batch.failed_rows, archived: batch.archived }, null, 2) }}</pre>
                </details>
              </div>
            </div>
          </details>
        </div>
        <div class="panel">
          <details>
            <summary>车辆与路网节点</summary>
            <div id="resources" class="body" v-if="state">
              <b>车辆（可按编号向助手提问）</b>
              <p v-for="vehicle in state.vehicles" :key="vehicle.id">{{ vehicle.id }} · {{ vehicle.name }} · {{ vehicle.kind }} · {{ vehicle.enabled ? '可用' : '故障' }}</p>
              <b>现有节点</b><p>{{ state.nodes.map(node => node.id).join('、') }}</p>
            </div>
          </details>
          <details>
            <summary>操作记录</summary>
            <div id="history" class="body">
              <div v-for="(entry, index) in history" :key="index" class="item">
                {{ time(entry.at) }} · {{ entry.message }} · {{ entry.results.some(result => result.error) ? '含失败步骤，请核对' : '已记录' }}
              </div>
            </div>
          </details>
          <details>
            <summary>项目知识库</summary>
            <div class="body">
              <p id="knowledge-status" v-if="status">已索引 {{ status.retrieval.sources }} 个来源、{{ status.retrieval.chunks }} 个片段。{{ status.retrieval.method }}</p>
              <input id="knowledge-query" v-model="knowledgeQuery" aria-label="检索内容" placeholder="检索算法、导师技术或操作说明">
              <button id="knowledge-search" class="light" :disabled="busy" @click="run(searchKnowledge)">检索原文依据</button>
              <div id="knowledge-results"><SourceList :rows="knowledgeResults" /></div>
            </div>
          </details>
          <details>
            <summary>接入与文件格式</summary>
            <div class="body">
              <p>在平台目录复制 assistant.local.example.json 为 assistant.local.json，填写兼容 Chat Completions 的 API 地址、模型和密钥。密钥仅在服务端读取。</p>
              <p>CSV / XLSX 首行 / JSON 任务字段：</p>
              <code>id,name,kind,start,end,earliest,deadline,service,demand,water,priority</code>
              <p>时间单位为当日分钟，水量、载重沿用现有场景单位。节点必须已存在。XLSX 读取第一个工作表。扫描 PDF 请提供图片，图片识别要求模型支持视觉。</p>
              <a href="/assets/tasks-example.csv" download>下载 CSV 样例</a> · <a href="/assets/tasks-example.xlsx" download>下载 Excel 样例</a>
            </div>
          </details>
        </div>
      </section>
    </div>
  </main>
</template>
