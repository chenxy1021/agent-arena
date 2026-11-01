# Agent Arena

让多个 OpenAI-compatible 大模型参加同一场辩论：独立首轮、跨轮点评、全员投票、逐轮淘汰，最后由胜者给出结论。

## 技术栈

- 后端：FastAPI + Uvicorn
- 实时过程：Server-Sent Events（SSE）
- 前端：Vue 3，本地运行时，无构建步骤
- 历史与模型配置：SQLite
- 依赖管理：uv

## 启动

```bash
uv sync
uv run python arena.py --serve

# 或直接启动 ASGI 应用
uv run uvicorn config.asgi:app --reload
```

网页默认打开 `http://127.0.0.1:7788/`，端口被占用时自动向后寻找可用端口。

## 添加模型

在网页「参赛登记」区域点击「＋ 登记模型」，填写：

- 显示名称
- Base URL，例如 `https://api.openai.com/v1`
- API Key
- 模型 ID
- 系统提示词（选填）
- 温度（选填）

接口需要兼容 OpenAI 的 `POST /chat/completions`，并支持流式返回。API Key 只保存在本机 `arena.db`，列表接口不会返回 Key。

## 界面

前端采用「赛程纸」布局：空闲时是赛事登记表，开赛后按轮次装订成赛程纸。实时事件通过 SSE 显示在轮次纸的现场记录区，票数使用中文「正」字计票，历史提问保存在 SQLite 并可从赛事档案回放。

中文优先使用本机 `PingFang SC`，计时和数字使用本机 `SF Mono` 等宽字体，不加载中文 Web 字体。

## 赛制

1. 第一轮不点评。每个模型独立给出观点，看不到其他模型本轮输出。
2. 第二轮起只点评上一轮全部发言。本轮其他模型的发言不会进入提示词。
3. 每轮结束后，存活模型和已出局评审共同投票。
4. 淘汰制投「最没用」，评选制投「最该留下」，直到只剩一人。

每轮纸张的「现场记录」展示服务商实际返回的流式内容。它展示的是可观察输出，不是伪造的隐藏思维链。

## 目录结构

项目采用类似 Django 的 `config + apps + templates + static` 组织方式：

```text
.
├── arena.py                 # 统一入口
├── config/
│   ├── settings.py          # 路径与项目配置
│   ├── urls.py              # 应用组装、路由和静态资源
│   ├── asgi.py              # uvicorn config.asgi:app
│   └── server.py            # 本地开发服务器
├── apps/
│   └── arena/
│       ├── api.py           # API 路由
│       ├── schemas.py       # Pydantic 请求模型
│       ├── services.py      # 比赛生命周期
│       ├── providers.py     # OpenAI-compatible 流式模型适配
│       ├── moderator.py     # 赛制核心
│       ├── prompts.py       # 发言与投票提示词
│       ├── database.py      # SQLite 历史与模型配置
│       └── ...
├── templates/index.html     # Vue 页面模板
├── static/                  # 前端脚本、样式和 Vue 运行时
├── tests/
├── pyproject.toml
└── uv.lock
```

## 平票规则

投票先按当前轮规则确定最低或最高票数；若多人平票，依次按以下规则裁决：

1. `eliminate`：累计得票更多的人出局；`support`：累计支持票更少的人出局。
2. 累计分数仍相同，则本轮观点信息量更少的人出局。
3. 仍然相同，则按模型名字字典序决定，保证结果确定。
4. 如果整轮没有任何有效票，直接按本轮观点信息量最少、再按名字决定。

## 主要接口

- `GET /api/models`：读取模型配置，不返回 API Key。
- `POST /api/models`：添加模型。
- `DELETE /api/models/{id}`：删除模型。
- `POST /api/runs`：启动比赛。
- `GET /api/runs/active`：获取正在运行的比赛。
- `GET /api/runs/{id}/events`：SSE 实时事件，支持 `Last-Event-ID` 断线续传。
- `GET /api/history`：SQLite 历史提问列表。
- `GET /api/history/{id}`：读取历史战报用于回放。

## 测试

```bash
uv run python -m unittest discover -s tests -v
node --check static/app.js
```

## 安全边界

Web 服务只监听 `127.0.0.1`。模型 API Key 以明文存入本机 SQLite，因此不要提交 `arena.db`，也不要让不可信用户访问本机服务。
