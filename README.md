# 环卫智枢 · AI 作业中心

第九届传智杯 AI WEB 网页开发挑战赛参赛作品。面向环卫调度员，浏览器端提供清单导入、任务问答、事件登记、候选重排、证据核验和人工审核。示例车队、地图和任务均为合成数据，下发目标为本地仿真。

## 评审体验

1. 打开 [AI 作业中心](http://127.0.0.1:8785/assistant)，上传 `examples/enterprise-review.csv`。页面会识别中文表头，并提示第二条任务缺少垃圾量。
2. 点击「导入有效任务」，展开「导入批次 · 撤回与重试」。在字段映射区为垃圾量补入 `1`，点击「用当前补充值重试失败行」，核对批次中完整的两条任务。
3. 点击「生成候选方案」，输入 `T001` 后查看求解记录。进入 [调度工作台](http://127.0.0.1:8785/dispatch) 核对路线和任务差异，再按需确认下发。
4. 加载模型配置后，先问「当前已安排哪些任务，依据是什么？」再勾选本条执行授权并发送「登记 V01 车辆故障，并生成候选方案，不要下发」。操作结果以工具返回和最新工作卡为准。
5. 本地知识库检索可用「H-ALNS 调度 约束」查看带文件位置的原文。图像清单需另选兼容 Chat Completions 图像输入的模型。

## 安装与运行

建议 Python 3.12。打开仓库根目录后执行以下命令。在 Windows 上如还未安装 Python，可从 [Python 官网](https://www.python.org/downloads/) 获取。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py --port 8785
```

macOS 或 Linux 可用 `python3.12 -m venv .venv`，并将上面两行的解释器路径改为 `.venv/bin/python`。服务启动后打开 `http://127.0.0.1:8785/assistant`。首次启动会从合成场景创建 SQLite 库，评审在本地使用无需账号。CSV / JSON 校验、计划生成和知识检索可以离线运行。依赖清单中的 openpyxl 与 pypdf 分别用于 XLSX 和文本型 PDF。

### 接入模型

将以下值设置在**启动服务的终端**中。地址应填兼容 OpenAI Chat Completions 的 API 基址，末尾无需拼接 `/chat/completions`。模型名须与供应商账户实际开通项一致。

```powershell
$env:SANITATION_AI_BASE_URL = 'https://api.deepseek.com'
$env:SANITATION_AI_MODEL = '<供应商模型名>'
$env:SANITATION_AI_API_KEY = '<只在本机终端填入>'
.\.venv\Scripts\python.exe server.py --port 8785
```

环境变量和示例值见 [配置模板](.env.example)。服务直接读取进程环境变量，不自动加载 `.env` 文件。可用本机 `assistant.local.json` 兼容旧安装，环境变量优先。仓库忽略凭据配置、虚拟环境、本机数据库及测试缓存。文件或图片经用户发送给助手时会交给其选择的模型供应商；本地清单校验和导入不需要发送给模型。

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

- `web/` 与 `legacy/web/` 提供 HTML、CSS 和原生 JavaScript 界面、状态卡和调度地图。
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

| 项目 | 信息 |
| --- | --- |
| 队名、学校 | 待补 |
| 成员与分工 | 待补 |
| 指导老师 | 如有请补充 |

## 版本来源

源码由团队提供的 2026-11-14 第三轮交付包整理。仓库的首次提交是现存版本的导入记录，后续提交记录参赛整理；原有开发历史未随交付包提供。保留的上一轮 `backups/round2/model.py` 用于路线行为回归。第三方实现及论文参考可见 `references/`，第三方依赖沿用各自许可。

