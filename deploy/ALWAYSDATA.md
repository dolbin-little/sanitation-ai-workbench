# 环卫智枢公网评审部署

在 alwaysdata 的 SSH 控制台安装本项目。使用 Python 3.12。

```sh
git clone --branch review-deploy https://github.com/dolbin-little/sanitation-ai-workbench.git ~/sanitation-review
cd ~/sanitation-review
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

在 **Web → Sites** 添加 **User program**，填写下列参数。

| 项目 | 值 |
| --- | --- |
| 地址 | 账号分配的 `<账号>.alwaysdata.net` |
| 工作目录 | `/home/<账号>/sanitation-review` |
| 启动命令 | `.venv/bin/python deploy/review_server.py` |
| SSL | 启用 HTTP 到 HTTPS 的跳转 |

平台提供 `IP` 和 `PORT`。在站点环境变量中单独设置评审配置。

| 变量 | 用途 |
| --- | --- |
| `SANITATION_PUBLIC_ORIGIN` | 完整 HTTPS 来源，如 `https://<账号>.alwaysdata.net`，末尾不带斜杠 |
| `SANITATION_REVIEW_DATADIR` | `/home/<账号>/sanitation-review-data`，保留车队和仿真的 SQLite 数据 |
| `SANITATION_REVIEW_USER` | 专门的评审用户名 |
| `SANITATION_REVIEW_PASSWORD` | 至少 16 位的独立评审密码，只通过赛事表单分享 |

若需运行大模型对话，在托管后台设置 `SANITATION_AI_BASE_URL`、`SANITATION_AI_MODEL` 和 `SANITATION_AI_API_KEY`。评审实例使用小规模合成车队，支持清单校验、候选方案、求解依据和人工审核。完整规模的实验、模型训练和算法调参在本地版本运行。评审账号共用一份模拟任务数据。

发布后用外部网络打开 `https://<账号>.alwaysdata.net/assistant`，输入评审凭据，点击「生成候选方案」并检查调度工作台的候选结果。赛事表单填写该 HTTPS 链接及评审凭据。

平台设置见 [User program](https://help.alwaysdata.com/en/docs/web-hosting/sites/http-servers/user-program/) 和 [Python 配置](https://help.alwaysdata.com/en/docs/web-hosting/languages/python/configuration/)。
