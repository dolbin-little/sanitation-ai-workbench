# 环卫智枢公网评审版（Sealos 广东区）

使用仓库的 `review-deploy` 分支。已有镜像构建环境时，从根目录的 `Dockerfile` 构建镜像，在应用管理中填写镜像地址。也可使用 Sealos DevBox 的 Python 3.12 环境导入该分支，在仓库目录用 `python -m pip install -r requirements.txt` 安装依赖，将启动脚本设为 `exec python deploy/review_server.py`，然后从 DevBox 发布到应用管理。评审密码等变量在发布后的应用管理中设置。

| 配置 | 建议值 |
| --- | --- |
| 可用区 | 广东 |
| 实例数 | 固定 1 个实例 |
| 初始资源 | 0.5 核 CPU、512 MiB 内存，根据入口显示的可选规格和费用调整 |
| 端口 | 容器端口 `8080`，开启 HTTPS 公网访问 |
| 持久卷 | `1 GiB`，挂载到 `/var/lib/sanitation-review` |
| 健康检查 | `/api/health` |

把以下三项设在应用的环境变量中。

| 变量 | 值 |
| --- | --- |
| `IP`、`PORT` | `0.0.0.0`、`8080`（Dockerfile 已设置） |
| `SANITATION_REVIEW_DATADIR` | `/var/lib/sanitation-review`（Dockerfile 已设置） |
| `SANITATION_PUBLIC_ORIGIN` | 平台生成的 HTTPS 地址，不带结尾斜杠或路径 |
| `SANITATION_REVIEW_USER` | 赛事专用用户名 |
| `SANITATION_REVIEW_PASSWORD` | 至少 16 位的独立评审密码，仅通过赛事表单提供 |

容器默认在持久卷目录保存数据库。部署后打开公网地址的 `/assistant`，使用评审账号登录，点击「生成候选方案」。重启一次应用，登录检查原方案能否恢复，再用手机流量复测。提交给评委的是 `/assistant` 的公网地址，以及配套的评审账号。

如果需要在线体验大模型对话，在应用后台设置 `SANITATION_AI_BASE_URL`、`SANITATION_AI_MODEL` 和 `SANITATION_AI_API_KEY`。基础候选方案求解使用合成车队和 H-ALNS，可在没有模型密钥时运行。

[从 GitHub 部署](https://sealos.cn/docs/getting-started/deploy-github-repo) · [应用管理和持久卷](https://sealos.cn/docs/getting-started/deploy-docker-image) · [计费标准](https://sealos.cn/docs/billing)
