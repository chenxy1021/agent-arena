# Agent Arena

把本机安装的 AI agent CLI 拉进同一场辩论：轮流发言、交叉点评、全员投票、淘汰到最后一人，再由胜者给出最终结论。

## 技术栈

- 后端：FastAPI + Uvicorn
- 实时过程：Server-Sent Events（SSE）
- 前端：Vue 3，本地运行时，无构建步骤
- 历史记录：SQLite
- 赛制与 CLI 适配：Python 标准库，外部 CLI 运行在独立工作目录

## 启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 图形界面
python arena.py --serve

# 或者直接启动 ASGI 应用
uvicorn config.asgi:app --reload

# 命令行
python arena.py "小团队该不该上 Kubernetes"
```

图形界面默认打开 `http://127.0.0.1:7788/`，端口被占用时自动向后寻找可用端口。

离线演示不需要任何真实模型：

```bash
python arena.py "团队应该优先追求速度还是质量" --mock 4
```

## 主要功能

- 实时展示每轮发言顺序、agent 思考状态、单次耗时、投票明细和淘汰过程。
- 支持 `eliminate`（投最没用）和 `support`（投最该留）两种规则。
- 已出局者禁言，但保留评审投票权。
- 历史提问存入 `arena.db`，旧版 `runs/` 战报会在启动时自动补录。
- 历史记录可以回放完整的发言、投票和最终结论。

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
│       ├── services.py      # 比赛生命周期与后台线程
│       ├── adapters.py      # CLI 探测与调用
│       ├── moderator.py     # 赛制核心
│       ├── database.py      # SQLite 历史
│       └── ...
├── templates/
│   └── index.html           # Vue 页面模板
├── static/
│   ├── app.js
│   ├── style.css
│   └── vendor/
└── tests/
```

## 平票规则

投票先按当前轮规则确定最低或最高票数；若多人平票，按以下顺序确定性裁决：

1. `eliminate`：累计得票更多的人出局；`support`：累计支持票更少的人出局。
2. 累计分数仍相同，则本轮观点信息量更少（字数更少）的人出局。
3. 仍然相同，则按 agent 名字字典序决定，保证同样输入得到同样结果。
4. 如果整轮没有任何有效票，直接按本轮观点信息量最少、再按名字决定。

## 主要接口

- `GET /api/agents`：探测本机 agent CLI。
- `POST /api/runs`：启动比赛。
- `GET /api/runs/active`：获取正在运行的比赛。
- `GET /api/runs/{id}/events`：SSE 实时事件，支持 `Last-Event-ID` 断线续传。
- `GET /api/history`：SQLite 历史提问列表。
- `GET /api/history/{id}`：读取历史战报用于回放。

## 测试

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

## 安全边界

Web 服务只监听 `127.0.0.1`，面向本机使用。真实比赛会调用你安装的 agent CLI，请确认对应工具的登录态、额度和命令参数；不要在不信任的命题或自定义命令中暴露敏感数据。
