# 环卫智枢 · AI 作业中心

环卫调度员可以在网页上导入任务清单、查询任务安排。遇到车辆故障时，可以登记事件，让系统重新排出一份候选方案。调度员核对路线变更和求解依据后，再确认下发。

这是第九届传智杯 AI WEB 网页开发挑战赛的参赛作品。演示用的车队、地图和任务都是合成数据，确认后的方案下发到本地仿真环境。

## 评审体验

1. 打开 [AI 作业中心](http://127.0.0.1:8785/assistant)，上传 `examples/enterprise-review.csv`。页面会识别中文表头，并提示第二条任务缺少垃圾量。
2. 点击「导入有效任务」，展开「导入批次 · 撤回与重试」。在字段映射区为垃圾量填入 `1`，点击「用当前补充值重试失败行」，检查两条任务是否都已导入。
3. 点击「生成候选方案」，输入 `T001` 后查看求解记录。进入 [调度工作台](http://127.0.0.1:8785/dispatch) 核对路线和任务差异，再按需确认下发。
4. 配置好模型后，先问「当前已安排哪些任务，依据是什么？」再勾选本条执行授权，发送「登记 V01 车辆故障，并生成候选方案，不要下发」。以工具返回结果和最新的工作卡为准。
5. 在本地知识库中搜索「H-ALNS 调度 约束」，可以看到原文和文件位置。如果清单是图片，需要选择支持 Chat Completions 图像输入的模型。

## 安装与运行

建议 Python 3.12。打开仓库根目录后执行以下命令。在 Windows 上如还未安装 Python，可从 [Python 官网](https://www.python.org/downloads/) 获取。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py --port 8785
```

macOS 或 Linux 可用 `python3.12 -m venv .venv`，并将上面两行的解释器路径改为 `.venv/bin/python`。服务启动后打开 `http://127.0.0.1:8785/assistant`。首次启动会从合成场景创建 SQLite 库，评审在本地使用无需账号。CSV / JSON 校验、计划生成和知识检索可以离线运行。依赖清单中的 openpyxl 与 pypdf 分别用于 XLSX 和文本型 PDF。

仓库包含已构建的 Vue 3 前端，按上面的 Python 流程即可启动。修改前端源码后，使用 Node.js 22.12 或更新版和 pnpm 11 重新构建：

```powershell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
```

### 接入模型

将以下值设置在**启动服务的终端**中。地址应填兼容 OpenAI Chat Completions 的 API 基址，末尾无需拼接 `/chat/completions`。模型名须与供应商账户实际开通项一致。

```powershell
$env:SANITATION_AI_BASE_URL = 'https://api.deepseek.com'
$env:SANITATION_AI_MODEL = '<供应商模型名>'
$env:SANITATION_AI_API_KEY = '<只在本机终端填入>'
.\.venv\Scripts\python.exe server.py --port 8785
```

环境变量和示例值见 [配置模板](.env.example)。服务直接读取进程环境变量，不会自动加载 `.env` 文件。旧版安装可继续用本机的 `assistant.local.json`，两处都设置时以环境变量为准。仓库忽略凭据配置、虚拟环境、本机数据库及测试缓存。

发给助手的文件和图片会传给所选的模型供应商。在本机校验或导入清单时，无需把清单发给模型。

## 技术架构

```
浏览器 Web 工作台
  /assistant  对话、清单、批次、出处和候选证据
  /dispatch   地图、计划对比和人工确认
  /           独立驾驶仿真
        │ 同源 JSON API
Python HTTP 服务 ── 助手编排 ── Chat Completions
        │                ├─ 本地 BM25 检索及来源编号过滤
        │                └─ JSON 动作提议 → 权限和业务参数校验
        └─ 车队状态与 SQLite ← H-ALNS 候选及求解轨迹
```

- AI 作业中心以 Vue 3 构建。`frontend/src/` 包含入口、响应式状态和界面组件，分别负责对话、清单编辑、工作结果、候选路线和证据引用。`web/assistant.html` 加载 Vite 构建的产物。调度工作台和驾驶仿真分别保留在 `legacy/web/` 和 `web/`。
- `assistant_service.py` 整理最新车队快照、检索片段和有界会话，解析模型提议，再调用受限业务工具。请求标识去重，过期版本要求刷新。
- `assistant_imports.py` 负责中文字段映射、地点与时间归一化、缺项合并和规则校验。`assistant_files.py` 提取附件内容，`assistant_knowledge.py` 索引本地资料。
- `legacy/backend/` 包含任务和路线模型、车辆约束、H-ALNS 与审计。候选说明来自求解器实际尝试，展示每个任务与车辆组合的可行计数和排除原因。
- `drive/` 和 `data/bc_model.json` 提供驾驶模拟及既有示例模型。Web 赛道演示聚焦 AI 作业与审核。

## 测试与证据

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip install -r requirements-research.txt
Push-Location legacy
..\.venv\Scripts\python.exe -m unittest discover -s tests -p test_dispatch.py -v
..\.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
..\.venv\Scripts\python.exe -m unittest discover -s tests -p test_research.py -v
..\.venv\Scripts\python.exe -m unittest discover -s tests -p test_reference.py -v
Pop-Location
```

- `evidence/assistant_round3_acceptance.json` 保留真实模型接口回放、成功结果与首次失败记录。
- `evidence/assistant_round3_ui.json` 保留网页语义交互对照。该样本为自动化操作，含等待和工具开销。
- 完整的第三方公开基准数据及二进制工具不随轻量源码分发。需要复跑基准时，参照 `legacy/scripts/download-public-benchmarks.ps1` 和 `legacy/scripts/prepare_public_benchmarks.py`，并安装 `legacy/requirements-benchmarks.txt`。源项目的 Windows 驾驶桌面软件和完整便携运行包另存于原始交付件。
- 本地 HTTP 服务绑定回环地址。生产部署前需另行实现鉴权、权限管理、会话隔离与 HTTPS，评审版沿用本地仿真设置。

## 团队信息

天枢智创来自云南大学，指导老师是何臻力。

| 成员 | 分工 | 主要工作 |
| --- | --- | --- |
| 朱宇轩 | 产品设计与前端开发 | 设计调度员的操作流程，开发 AI 作业中心、调度地图、方案对比和人工审核界面。 |
| 刘鸿瑞 | 调度算法与后端开发 | 负责 Python 后端、车队状态和调度记录，处理车辆与路线约束，用 H-ALNS 求解候选方案。 |
| 宋奕霖 | AI 助手与数据处理 | 接入大模型和本地知识库检索，解析清单及附件，把调度员的指令转成可校验的操作提议。 |

## 版本来源

仓库的首次提交导入了团队提供的 2026-11-14 第三轮交付包，后续提交记录参赛整理。原有开发历史未随交付包提供。

### 开发阶段存档

[存档分支](https://github.com/dolbin-little/sanitation-ai-workbench/commits/development-snapshots/)按团队确认的开发顺序整理。提交时间是整理存档的时间，旧版本的时间依据写在各提交的 `ARCHIVE-PROVENANCE.md` 中。

| 阶段 | 存档里的材料 |
| --- | --- |
| [车队调度工作台](https://github.com/dolbin-little/sanitation-ai-workbench/commit/e66bfccf781df70c8d15f04303ab189c66a75c5c) | 驾驶版交付包保留的 V0.2 调度源码。随包验证记录标注日期为 2026-10-08。 |
| [低速驾驶仿真](https://github.com/dolbin-little/sanitation-ai-workbench/commit/88460b0e727e2c13608b0d957db5d32010273dc0) | 2026-10-29 驾驶平台交付包中的 Web 版源码，包含感知、路径规划、安全监控和仿真记录。 |
| AI 作业中心 | 第三轮交付包内有[第一轮](https://github.com/dolbin-little/sanitation-ai-workbench/commit/cbedee98dd2a78166741ecf6e39ed3d5f6d65c5a)和[第二轮](https://github.com/dolbin-little/sanitation-ai-workbench/commit/0752080d7c0fc7c12f394da5eb4908ddb64b61ff)的部分文件，以及 [2026-11-14 第三轮参赛源码](https://github.com/dolbin-little/sanitation-ai-workbench/commit/2357f67f197d8c279daeaeea9bd38f594e93bcec)。前两轮备份可用来对比文件改动。 |

上一轮的 `backups/round2/model.py` 用于路线行为回归测试。第三方实现和参考论文见 `references/`，依赖沿用各自的许可。

