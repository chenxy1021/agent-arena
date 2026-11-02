# Agent Arena

[中文](#中文) · [English](#english)

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-42B883?logo=vuedotjs&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-local-003B57?logo=sqlite&logoColor=white)

## 中文

**让多个大模型坐上一张真正的辩论桌，把一次判断变成可复盘的决策过程。**

Agent Arena 是一个本地优先的多模型辩论与压力测试工具。不同模型围绕同一个命题独立发言，再基于上一轮公开内容互相质疑、投票和淘汰，最后留下一个经过多轮对抗的结论。

它不是把多个角色塞进一次 Prompt，也不会伪造模型隐藏的思维链。页面只展示服务商实际返回的可观察输出、运行阶段、等待时长和本地统计数据。

### 界面

| 登记与阵容 | 会场与并行生成 | 记录与最终裁决 |
| --- | --- | --- |
| ![登记页](docs/screenshots/register.png) | ![会场页](docs/screenshots/arena.png) | ![记录页](docs/screenshots/record.png) |

界面右上角可以随时切换中文和 English。语言偏好保存在浏览器本地。

### 核心能力

- **多模型登记**：通过 OpenAI-compatible `/chat/completions` 接入不同厂商和模型。
- **结构化命题**：支持背景、约束和评判标准，并随发言、投票与最终总结一起发送。
- **两种发言模式**：并行生成后同屏公开，或逐个实时流式输出。
- **两种胜负规则**：淘汰制投给最弱观点，评选制投给最强观点。
- **并发投票**：所有存活模型和评审同时投票，慢模型不会串行拖住整场。
- **加赛状态可见**：平票后明确显示加赛发言、加赛投票、参与模型和等待时间。
- **评审席与加权票**：出局模型转为评审继续投票；仅剩两人时评审权重归零。
- **确定性平票处理**：加赛后仍平票时，按评分、存活者票数和主张数量依次裁决。
- **评分与主张台账**：聚合多维评分，追踪每条主张的提出、挑战、支持与结局。
- **完整战报**：保存 `transcript.json` 和可读的 `debate.md`。
- **历史与再赛**：从历史预设回填登记页，确认阵容后再开始，不会偷跑模型请求。

### 运行中的可见反馈

- 顶部常驻运行条显示当前模型、阶段、投票进度、已等待秒数和加赛状态。
- 并行生成时，每张卡片持续显示真实阶段、等待时长、已接收字符数和进度条。
- 投票全部并发提交，页面显示 `已投 x/y`，而不是等所有请求结束后才更新。
- 加赛期间使用危险色状态条，明确区分“加赛发言”和“加赛投票”。
- 逐个实时模式会展示服务商实际流式返回的文本；如果服务商不公开 reasoning 字段，就不会伪造思考过程。

### 快速开始

环境要求：

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- 至少两个兼容 OpenAI Chat Completions 的模型配置

不需要 Node.js 构建前端，Vue 3 运行时已包含在仓库中。

```bash
git clone https://github.com/chenxy1021/agent-arena.git
cd agent-arena
uv sync
uv run python arena.py --serve
```

默认打开：

```text
http://127.0.0.1:7788/
```

如果端口被占用，启动器会继续寻找可用端口。也可以直接运行：

```bash
uv run uvicorn config.asgi:app --reload
```

第一次使用：

1. 打开「模型」，登记至少两个模型。
2. 打开「登记」，选择参赛模型并填写命题。
3. 选择发言方式和胜负规则。
4. 点击「开始比赛」。

「自动取名」和「开始比赛」会真实请求模型服务；「预览一场」只使用前端假数据。

### 离线检查界面

没有 API Key 时可以先打开登记页并点击「预览一场」。它不会请求任何模型，也不会覆盖真实模型登记。

命令行 Mock 模式：

```bash
uv run python arena.py "该不该把核心服务迁移到新架构" --mock 4
```

### 模型接口

模型服务需要兼容：

```text
POST {base_url}/chat/completions
Authorization: Bearer <API_KEY>
```

示例：

```text
Base URL: https://api.openai.com/v1
模型 ID: gpt-4.1
```

服务支持流式响应，并会读取部分兼容服务返回的 `reasoning_content` 或 `reasoning` 字段。不同服务商对推理字段、工具调用、多模态和流式 usage 的支持程度不同。

### API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/models` | 列出模型，不返回 API Key |
| `POST` | `/api/models` | 新建模型 |
| `PUT` | `/api/models/{id}` | 更新模型 |
| `DELETE` | `/api/models/{id}` | 删除模型 |
| `POST` | `/api/models/suggest-name` | 调用模型生成显示名称 |
| `POST` | `/api/runs` | 创建并启动比赛 |
| `POST` | `/api/runs/{id}/stop` | 请求中止比赛 |
| `GET` | `/api/runs/active` | 查询当前活动比赛 |
| `GET` | `/api/runs/{id}/events` | 订阅 SSE 事件流 |
| `GET` | `/api/history` | 列出历史比赛 |
| `GET` | `/api/history/{id}` | 读取完整战报 |
| `GET` | `/api/history/{id}/preset` | 将历史预设解析为登记草稿 |

SSE 事件包含轮次、模型输出、等待心跳、并行生成进度、并发投票进度、计票、评分、加赛、淘汰、主张、收敛读数和归档状态。

### 数据与安全

- `arena.db`：SQLite，保存模型配置和历史索引。
- `runs/<run_id>/transcript.json`：完整结构化战报。
- `runs/<run_id>/debate.md`：可读 Markdown 战报。

API Key 以明文保存在本机 SQLite 中，模型列表接口不会返回 Key。可以通过 `ARENA_DB` 指定数据库路径：

```bash
ARENA_DB=/path/to/arena.db uv run python arena.py --serve
```

`arena.db`、`arena.db-*` 和 `runs/` 已在 `.gitignore` 中。不要把真实 API Key、数据库或战报提交到公开仓库。

### 部署边界

当前版本是本地优先的单实例应用：

- 没有登录、用户系统或多租户隔离。
- 没有全局并发治理；部署者需要自行控制访问量和资源。
- 模型配置和比赛档案属于运行实例的本机。
- 默认启动器只监听 `127.0.0.1`。
- 不兼容旧版数据库或旧版战报，当前以最新 schema 为准。

如果要公开部署，必须自行增加反向代理认证、HTTPS、访问控制、进程隔离和资源限制。

### 开发与测试

```bash
uv run python -m unittest discover -s tests -v
node --check static/app.js
node --check static/i18n.js
git diff --check
```

测试使用本地 Mock、临时 SQLite 和回环 HTTP 服务，不需要真实模型 API Key。

---

## English

**Put multiple models at one real debate table and turn a single judgment into an auditable decision process.**

Agent Arena is a local-first multi-model debate and stress-testing tool. Models answer the same question independently, challenge the previous public round, vote, and get eliminated until one survivable conclusion remains.

It is not role-play packed into one prompt, and it never fabricates hidden chain-of-thought. The UI only shows observable provider output, stages, elapsed time, and locally computed statistics.

### Interface

| Setup | Live arena | Record |
| --- | --- | --- |
| ![Setup](docs/screenshots/register.png) | ![Arena](docs/screenshots/arena.png) | ![Record](docs/screenshots/record.png) |

Use the language button in the top-right corner to switch between Chinese and English. The preference is stored locally in the browser.

### Features

- **Model registry** through OpenAI-compatible `/chat/completions` endpoints.
- **Structured questions** with background, constraints, and evaluation criteria.
- **Parallel or live-sequential speech**: reveal all cases together or stream one model at a time.
- **Elimination or selection voting**: remove the weakest case or keep the strongest one.
- **Concurrent voting**: every active model and judge votes in parallel, so one slow provider does not serialize the whole match.
- **Visible tiebreaks**: tied candidates, tiebreak speeches, tiebreak votes, and waiting time are explicitly shown.
- **Judging panel and weighted ballots**: eliminated models keep voting; judge weight drops to zero when only two remain.
- **Deterministic tie resolution**: score, active-player votes, and claim count decide remaining ties.
- **Score matrix and claim ledger**: track multi-dimensional scores plus each claim's origin, challenges, support, and final status.
- **Complete transcripts** in `transcript.json` and readable `debate.md`.
- **History and reruns** that refill the setup form without silently calling any model.

### Live feedback

- A persistent live bar shows the current model, stage, voting progress, elapsed time, and tiebreak state.
- Parallel cards show real generation phases, wait time, received character count, and progress.
- Votes are submitted concurrently, and the UI displays `voted x/y` while the round is still running.
- Tiebreak phases use a danger-colored status line to distinguish speeches from voting.
- Live-sequential mode displays streamed provider text. If a provider does not expose reasoning, the app does not invent it.

### Quick start

Requirements:

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- At least two OpenAI Chat Completions-compatible model configurations

No Node.js build step is required. The Vue 3 runtime is bundled in the repository.

```bash
git clone https://github.com/chenxy1021/agent-arena.git
cd agent-arena
uv sync
uv run python arena.py --serve
```

Open:

```text
http://127.0.0.1:7788/
```

The launcher searches for the next available port if `7788` is occupied. Alternatively:

```bash
uv run uvicorn config.asgi:app --reload
```

First run:

1. Open **Models** and register at least two models.
2. Open **Setup**, select participants, and enter a question.
3. Choose speech and decision modes.
4. Click **Start match**.

**Suggest name** and **Start match** make real model requests. **Preview match** uses frontend-only demo data.

### Offline preview

Without API keys, open Setup and click **Preview match**. It makes no model requests and does not overwrite your registry.

CLI Mock mode:

```bash
uv run python arena.py "Should we migrate the core service?" --mock 4
```

### Provider contract

```text
POST {base_url}/chat/completions
Authorization: Bearer <API_KEY>
```

Example:

```text
Base URL: https://api.openai.com/v1
Model ID: gpt-4.1
```

Streaming is supported. Some compatible providers expose `reasoning_content` or `reasoning`; support for reasoning fields, tool calls, multimodal content, and streamed usage varies by provider.

### API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/models` | List models without API keys |
| `POST` | `/api/models` | Create a model |
| `PUT` | `/api/models/{id}` | Update a model |
| `DELETE` | `/api/models/{id}` | Delete a model |
| `POST` | `/api/models/suggest-name` | Ask a model for a display name |
| `POST` | `/api/runs` | Create and start a match |
| `POST` | `/api/runs/{id}/stop` | Stop a match |
| `GET` | `/api/runs/active` | Read the active match |
| `GET` | `/api/runs/{id}/events` | Subscribe to the SSE stream |
| `GET` | `/api/history` | List archived matches |
| `GET` | `/api/history/{id}` | Read a transcript |
| `GET` | `/api/history/{id}/preset` | Resolve a historical preset |

SSE events include rounds, streamed model output, waiting heartbeats, parallel progress, concurrent voting, counts, scores, tiebreaks, eliminations, claims, convergence readings, and archive status.

### Data and security

- `arena.db`: SQLite model registry and history index.
- `runs/<run_id>/transcript.json`: complete structured transcript.
- `runs/<run_id>/debate.md`: readable Markdown report.

API keys are stored in plaintext in the local SQLite database; the list endpoint never returns them. Use `ARENA_DB` to choose another database path:

```bash
ARENA_DB=/path/to/arena.db uv run python arena.py --serve
```

`arena.db`, `arena.db-*`, and `runs/` are ignored by Git. Never commit real keys, databases, or private transcripts.

### Deployment boundary

This version is a local-first single-instance app:

- No login, user system, or tenant isolation.
- No global concurrency governance; operators must control access and resources.
- Model configs and transcripts belong to the local instance.
- The default launcher listens only on `127.0.0.1`.
- Legacy databases and transcripts are not supported; the current schema is authoritative.

For public deployment, add authentication, HTTPS, access control, process isolation, and resource limits at the reverse-proxy or platform layer.

### Development

```bash
uv run python -m unittest discover -s tests -v
node --check static/app.js
node --check static/i18n.js
git diff --check
```

Tests use local mocks, temporary SQLite files, and loopback HTTP servers. No real model API key is required.
