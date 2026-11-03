# Agent Arena

[English](README.md) | [简体中文](README.zh-CN.md)

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-local_API-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-42B883?logo=vuedotjs&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-embedded-003B57?logo=sqlite&logoColor=white)

<div align="center">
  <img src="docs/screenshots/arena.png" alt="Agent Arena 方案评审舱" width="92%">
</div>

**让多个大模型坐上一张真正的议事桌：用独立裁判比较可执行方案，或按你设定的胜出标准进行自定义淘汰赛。**

Agent Arena 是一个本地优先的多模型决策会场，提供两种模式：

- **方案评审**是默认模式。参赛模型独立作答，独立裁判只看到匿名且乱序的
  方案，再按四个维度评分，最后给出排名、推荐、否决理由与整合建议。
- **自定义模式**让模型围绕同一命题跨轮交锋、并发投票、按淘汰制推进。胜出标准
  为必填项，会写入每轮发言、投票和最终总结的 Prompt。

它输出的是可审计战报，而不是把多个答案揉进一个不可追踪的 Prompt。页面只展示
服务商实际返回的可观察输出，不伪造隐藏思维链；如果兼容服务返回
`reasoning_content` 或 `reasoning`，页面会按服务商实际流式返回的内容展示。

## 核心能力

| 模块 | 能力 |
| --- | --- |
| 模型 | 登记任意兼容 OpenAI Chat Completions 的接口 |
| 方案评审 | 并行独立作答、匿名乱序评审、四维评分、推荐与整合建议 |
| 自定义模式 | 必填胜出标准、跨轮点评、并发投票、淘汰、加赛与最终总结 |
| 裁决 | 默认选择最可行方案，或按自定义模式的胜出标准裁决 |
| 证据 | 评分矩阵、否决理由、主张台账、立场离散度和完整轮次记录 |
| 稳定性 | 超时、重试、中止控制、SSE 进度心跳和可读失败原因 |
| 记录 | 模式化历史、档案检索、预设复用，禁止跨模式混排 |
| 界面 | 桌面与移动端自适应，支持亮色/深色主题，中英文随时切换 |

## 两种模式

| | 方案评审 | 自定义模式 |
| --- | --- | --- |
| 适合 | 快速比较多个可执行方案 | 用明确胜出标准对争议观点做压力测试 |
| 参赛模型 | 2-8 个 | 2-8 个 |
| 裁判 | 一名不参赛的独立模型 | 一名不参赛的独立模型在每次淘汰后核验胜出标准 |
| 胜出标准 | 不适用 | 必填；默认「投票至最后一人」 |
| 典型成本 | `N + 2` 次调用 | 多轮推进，通常更慢 |
| 产出 | 对比矩阵、推荐、否决理由、整合方案 | 胜者或未决结论，以及完整交锋过程 |
| 默认 | 是 | 可选深挖模式 |

评审采用匿名与确定性乱序，裁判只看到 `方案1...方案N`，看不到真实模型名。每个
未被推荐的方案都必须给出具体理由，最终整合建议还要说明前提与失效条件。

## 界面

| 登记页 | 评审记录 |
| --- | --- |
| ![登记页](docs/screenshots/register.png) | ![评审记录](docs/screenshots/record.png) |
| **档案对比** | **亮色模式** |
| ![档案对比](docs/screenshots/archive.png) | ![亮色模式](docs/screenshots/arena-light.png) |

实时评审舱会展示方案提交、匿名评审、评分矩阵、推荐、否决理由和整合步骤。
自定义赛会持续展示生成、投票、加赛和归档状态。亮色/深色主题与语言选择会保存在本地。

## 快速开始

环境要求：

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- 方案评审至少需要三个模型配置：两个参赛模型加一个独立裁判
- 自定义模式至少需要三个模型配置：两个参赛模型加一个独立裁判

```bash
git clone https://github.com/chenxy1021/agent-arena.git
cd agent-arena
uv sync
uv run python arena.py --serve
```

打开 <http://127.0.0.1:7788/>。如果端口被占用，启动器会继续尝试后续 11 个端口。
也可以自行指定：

```bash
uv run python arena.py --serve --port 8899 --no-open
```

或者直接启动 ASGI 应用：

```bash
uv run uvicorn config.asgi:app --reload
```

第一次使用：

1. 打开「模型」，登记需要使用的接口。
2. 打开「登记」，选择「方案评审」或「自定义模式」。
3. 选择 2-8 个参赛模型；两种模式都需要选择一个不参赛的独立裁判。
4. 自定义模式必须填写胜出标准（例如「投票至最后一人」，或「甲、乙同阵营，
   淘汰丙即该阵营获胜」）。每次淘汰后裁判核验该标准；条件成立时宣布指定胜者
   并结束比赛。同时填写命题、背景、约束与附加评判要求。
5. 开始比赛。

「预览一场」只使用前端本地 Mock 数据，不请求模型接口，不创建后端 run，也不会
覆盖已保存的模型配置。

## 模型接口

每个模型配置需要兼容：

```text
POST {base_url}/chat/completions
Authorization: Bearer <API_KEY>
```

示例：

```text
Base URL: https://api.openai.com/v1
模型 ID: gpt-4.1
```

应用默认启用流式响应。不同服务商对推理字段、工具调用、多模态输入和流式 usage
的支持程度不同；不支持的字段会被忽略，不会伪造。

## 架构

```mermaid
flowchart LR
    UI[Vue 3 界面] -->|REST + SSE| API[FastAPI 路由]
    API --> MANAGER[运行生命周期管理器]
    MANAGER --> REVIEW[方案评审引擎]
    MANAGER --> DEBATE[自定义淘汰赛引擎]
    REVIEW --> PROVIDERS[OpenAI-compatible 适配器]
    DEBATE --> PROVIDERS
    MANAGER --> DB[(SQLite)]
    REVIEW --> REVIEWRUNS[transcript.json + review.md]
    DEBATE --> DEBATERUNS[transcript.json + debate.md]
```

当前执行模型是确定性的流水线，内部做并行 fan-out / fan-in，不是自主多 Agent
蜂群：

1. 生命周期管理器创建独立运行，并校验模式、阵容和裁判独立性。
2. 方案评审并行收集独立答案，匿名乱序后交给裁判评分并生成整合建议。
3. 自定义模式把胜出标准写入全部 Prompt，并应用轮次、票权、淘汰与平票状态机。
4. 通过 SSE 推送过程，并在本地归档结果。

这样成本、顺序、中止和战报生成都可预测。

### 为什么不用 SQLModel？

当前只有两张小表，没有用户、关联关系、会话状态或迁移流程。标准库 `sqlite3`
足够直接，SQLModel 会增加依赖和 session 生命周期，却暂时减不掉多少应用代码。

等产品加入用户系统、每用户 API Key、共享部署或 schema 迁移后，再引入 ORM
和迁移工具才有实际收益。

### 为什么不用 LangChain？

这个项目的关键行为在通用 Agent 框架之下：

- 精确转发 SSE delta 与服务商公开的 reasoning；
- 控制超时、重试和中止语义；
- 确定性解析结构化评审与选票；
- 保证实时会场的事件顺序；
- 生成可复现、按模式隔离的战报。

LangChain 不提供评审量表或辩论赛制；在会场与服务商响应之间增加抽象层，反而会
让实时体验更难控制。如果未来增加工具调用、外部检索或依赖图任务，可以为这些新
能力单独引入 LangChain；核心会场仍应保持显式状态机。

## 项目结构

```text
arena.py                  本地服务启动器
apps/arena/api.py         HTTP 路由与 SSE
apps/arena/services.py    运行生命周期、模式分发与中止
apps/arena/review.py      方案评审、匿名评分与整合建议
apps/arena/moderator.py   辩论赛制、投票、加赛与战报模型
apps/arena/providers.py   OpenAI-compatible 流式适配器
apps/arena/database.py    SQLite 模型登记与历史索引
apps/arena/report.py      JSON 与 Markdown 战报
static/                   Vue 运行时与前端资源
templates/                应用外壳
tests/                    Mock 与回环测试
```

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/models` | 列出模型，不返回 API Key |
| `POST` | `/api/models` | 新建模型 |
| `PUT` | `/api/models/{id}` | 更新模型 |
| `DELETE` | `/api/models/{id}` | 删除模型 |
| `POST` | `/api/models/suggest-name` | 调用模型生成显示名 |
| `POST` | `/api/runs` | 创建并启动方案评审或自定义淘汰赛；`win_condition` 和 `judge_model_id` 必填 |
| `POST` | `/api/runs/{id}/stop` | 请求中止比赛 |
| `GET` | `/api/runs/active` | 查询当前活动比赛 |
| `GET` | `/api/runs/{id}/events` | 订阅 SSE 事件流 |
| `GET` | `/api/history` | 列出带模式信息的历史比赛 |
| `GET` | `/api/history/{id}` | 读取完整战报 |
| `GET` | `/api/history/{id}/preset` | 构造可复用的比赛预设 |

方案评审 SSE 包含独立作答进度、匿名标签、裁判重试、评分结果、推荐与整合建议。
自定义模式 SSE 包含发言流、等待心跳、并行进度、投票进度、评分、加赛、淘汰、胜出标准核验、主张、
收敛状态和归档完成。

## 数据与安全

- `arena.db`：本地 SQLite 模型登记与历史索引。
- `runs/<run_id>/transcript.json`：完整结构化战报。
- `runs/<run_id>/review.md` 或 `debate.md`：可读 Markdown 战报。

API Key 以明文保存在本地数据库，模型列表接口不会返回 Key。可以指定其他数据库
路径：

```bash
ARENA_DB=/path/to/arena.db uv run python arena.py --serve
```

`arena.db`、`arena.db-*` 和 `runs/` 已在 `.gitignore` 中。不要把真实 API Key、
私有战报或生产数据库提交到仓库。

当前版本按单实例、本地优先设计：

- 没有登录、用户系统或多租户隔离；
- 没有全局并发治理；
- 不兼容旧版数据库或旧版战报；
- 启动器只监听 `127.0.0.1`。

如果要公开部署，必须在反向代理或平台层增加认证、HTTPS、访问控制、进程隔离和
资源限制。

## 测试

```bash
uv run python -m unittest discover -s tests -v
node --check static/app.js
node --check static/i18n.js
git diff --check
```

测试使用确定性 Mock、临时 SQLite 和回环 HTTP 服务，不需要真实模型 API Key。

## 路线图

- 用户系统与每用户模型归属。
- 共享部署控制与额度限制。
- 多裁判评审团与人类采纳/驳回入口。
- 在核心评审和辩论引擎之外增加可选的研究/工具调用能力。

---

英文说明见 [README.md](README.md)。
