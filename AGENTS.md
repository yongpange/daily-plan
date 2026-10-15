# 每日计划 — 全栈规范

个人每日计划 / 复盘 / 感悟库应用。后端：Python 3.12 + FastAPI + Pydantic v2，SQLite（裸 SQL，异步包装）。前端：Vue 3 + Vite + TypeScript + Pinia + Vue Router（工程在 `frontend/`，构建产物输出到 `web/` 由 FastAPI 伺服）。

## 目录结构

```
app/
├── main.py            # 应用工厂：lifespan、异常处理、中间件、路由注册、静态资源、CLI 入口
├── core/              # 与业务无关的基础设施
│   ├── config.py      #   Settings（pydantic-settings，环境变量前缀 DAILY_PLAN_）
│   ├── errors.py      #   AppError + 全局异常处理（错误响应统一 {"error": "..."}）
│   ├── security.py    #   认证（API Key，未配置时放行）、滑动窗口限流
│   ├── deps.py        #   通用 Depends：db / settings / auth / extensions / usage_recorder
│   ├── time.py        #   utc_now / seconds_between / add_seconds / DATE_FORMAT
│   ├── validators.py  #   valid_date / valid_remind_at / as_non_negative_int / period_bounds
│   └── database.py    #   Database：SQLite 连接与全部数据访问（同步实现，唯一允许写 SQL 的地方）
├── models/            # 数据模型层
│   ├── schema.sql     #   全部 DDL（唯一事实来源）
│   └── migrations.py  #   结构演进与数据迁移
├── schemas/           # Pydantic 请求/响应模型（接口类型契约，一个业务域一个文件）
├── services/          # 业务逻辑层：async，一个业务域一个文件
├── routers/           # 路由层：薄路由，只做 解析 → 调 service → 返回
└── extensions/        # AI 能力扩展点（协议 + 空实现，不在业务代码里实现 AI）
    ├── base.py        #   UsageRecorder / UsageRecord（Token 统计）
    ├── llm.py         #   LLMProvider（对话流 / 生图流）
    ├── rag.py         #   RAGRetriever
    ├── agent.py       #   AgentRunner
    ├── mcp.py         #   MCPToolRegistry
    └── registry.py    #   Extensions 容器 + build_extensions 装配

frontend/                # Vue 3 + Vite + TS 前端（Vite 构建产物输出到 ../web）
├── src/
│   ├── api/             #   axios 实例（http.ts：baseURL /api、统一错误文案、loading 计数）
│   │                    #   + 各业务域模块 + sse.ts（SSE 流式通用封装，预留）
│   ├── stores/          #   Pinia：day / timer / memo / report / routine / reminder / settings / ui / dialogs
│   ├── router/          #   /today /report /memos /settings
│   ├── types/api.ts     #   全部接口类型（与 docs/refactor/api-catalog.md 一致）
│   ├── utils/           #   date / format / note（富文本白名单消毒）/ storage / image
│   ├── assets/base.css  #   主题变量、reset、按钮、面板、弹窗基类、富文本排版（跨组件公共样式）
│   └── components/      #   layout / common / today / report / memos / settings / dialogs
web/                     # Vite 构建产物（git 忽略，由 启动每日计划.bat 生成）
```

## 硬性约定

1. **契约优先**：HTTP 方法、路径、请求字段、响应字段、状态码、错误文案必须与
   `docs/refactor/api-catalog.md` 一致——前端依赖这些形状。错误响应统一 `{"error": "文案"}`。
2. **分层调用**：routers → services → database。路由不写业务/SQL；service 不直接碰 request/response。
3. **不许阻塞事件循环**：Database 方法是同步的，service 里一律
   `from starlette.concurrency import run_in_threadpool`，`await run_in_threadpool(db.xxx, ...)`。
4. **业务错误抛 `AppError(message, status)`**，文案保持中文原文，由全局处理器转成响应。
5. **请求/响应模型**：所有请求体、响应体用 Pydantic v2 定义在 `app/schemas/`，路由声明
   `response_model`。字段默认值、枚举、约束（如长度上限）沿用旧实现。
6. **横切关注点用 Depends**：认证 `AuthDep`、限流 `Depends(rate_limit)`、扩展点 `ExtensionsDep`、
   Token 统计 `UsageDep`。不许在路由里手写鉴权/计数。
7. **AI 功能只走 extensions 协议**，本阶段不实现任何真实大模型/RAG/Agent/MCP 逻辑。
8. **领域术语**以 `CONTEXT.md` 术语表为准（主线 / 一步 / 下一句 / 今天主推 / 暂停 / 项目 / 任务 / 顺延）。

## 前端约定

1. 组件一律 `<script setup lang="ts">`；HTTP 调用只能走 `src/api/`；跨组件共享状态放 `src/stores/`。
2. 秒级实时 UI 依赖 `timer` store 的 `now`（全局每秒 tick），不要自建 setInterval 刷 DOM。
3. memo 等富文本用 `utils/note.ts` 的 `renderMemoHtml` + `v-html`（白名单消毒在此）。
4. 新增接口先在 `types/api.ts` 补类型，再在各域 api 模块加函数。
5. AI 流式能力统一走 `api/sse.ts` 的 `postStream`（后端帧格式 `data: <json>\n\n`）。

## 常用命令

```bash
py -3 -m pytest                          # 跑后端测试
py -3 -m app.main --port 8765 --no-browser   # 本地起服务（伺服 web/ 构建产物）
npm run dev                              # 前端开发服务器（:5173，/api 代理到 8765）
npm run build                            # 构建前端到 web/
启动每日计划.bat                          # 双击：构建 + 生产模式启动
```

