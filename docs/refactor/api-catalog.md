# 每日计划 — 现状 API 目录（FastAPI 重构基线盘点）

> 盘点对象：`server.py`（4770 行，纯标准库 `http.server.ThreadingHTTPServer` 实现，UTF-8 + CRLF）。
> 目的：作为 FastAPI 重构的兼容性基线。**响应 JSON 的字段名、枚举值、错误文案与状态码均被前端 `web/app.js` 依赖，重构时必须逐项保持。**
> 全局约定：
> - 所有 JSON 响应 `Content-Type: application/json; charset=utf-8`，`Cache-Control: no-store`。
> - 错误响应统一为 `{"error": <string>}`，状态码取自 `AppError.status`（默认 400，资源不存在为 404）。
> - 未捕获异常 → 500 `{"error": "暂时出了问题，请稍后重试；详细信息已写入本地日志"}`。
> - 请求体解析：非 JSON / 非 object / 超长 → 400 `"请求内容不正确"`（超长为 `"内容过长"`，默认上限 1 MB，`POST /api/images` 为 14 MB）。
> - 枚举值：`outcome ∈ {planned, completed, carried, rescheduled, abandoned}`；任务 `status ∈ {active, completed, abandoned}`（库内）；主线 `status ∈ {active, paused, done}`；提醒 `status ∈ {pending, done}`；计时 `mode ∈ {open, focus}`；感悟来源 `source_kind ∈ {"", task, thread, routine}`；感悟 `kind ∈ {memo, daily}`；复盘 `period ∈ {week, month, quarter}`。
> - `REASONS`（未完成原因，常量，随 `/api/day` 下发）：`underestimated/估时偏短`、`interrupted/中途被插入别的事`、`scope_changed/做着做着范围变大`、`blocked/在等别人、资料或环境`、`reprioritized/被更急的事挤掉`、`unclear/任务没定义清楚，难开工`、`partial/做了一部分，剩余已明确`、`not_worth_it/不再值得做`。
> - 时间戳格式：UTC ISO8601 秒级，形如 `2026-10-15T08:18:17Z`。

---

## 1. HTTP 端点全表

### 1.1 Day / 计划条目

#### `GET /api/day`
- 查询参数：`date`（默认今天，`YYYY-MM-DD`，非法 → 400 `"日期格式不正确"`）
- 响应 200（`get_day`），形状：
```json
{
  "date": "2026-10-10",
  "day": {
    "plan_date": "2026-10-10", "focus": "", "reflection": "",
    "mood": null, "closed_at": null,
    "updated_at": "...(仅当 day 记录已存在时存在)",
    "images": [{"id": 1, "width": 800, "height": 600}]
  },
  "entries": [ <entry> ],
  "projects": [{"id": 1, "name": "用户研究", "color": "#5b6cf9"}],
  "active_timer": null,
  "segments": [ <segment> ],
  "reasons": [ {"value": "underestimated", "label": "估时偏短"} ],
  "routines": [ <routineDay> ],
  "threads": [ <threadDay> ]
}
```
- `<entry>`（`_entry()` 的 dict，字段名固定）：
  `id, plan_date, estimate_minutes, planned_start, sort_order, outcome, unfinished_reason, reason_note, target_date, thread_id, task_id, title, parent_id, definition, task_status, project_name, thread_title, actual_seconds, is_running(0/1), has_children(0/1)`
- `active_timer` 非空时两种形状之一：
  - 任务计时：`{id, plan_entry_id, start_at, mode, target_seconds, plan_date, title}`
  - 每日必做计时：`{id, plan_entry_id: null, routine_id, start_at, mode: "open", target_seconds: null, plan_date, title}`（仅当无任务计时运行时）
- `<segment>`（工作日志，两种）：
  - 任务段：`{id, plan_entry_id, start_at, end_at, duration_seconds, mode, target_seconds, focus_completed, title, project_name}`（`project_name` 无项目时为 `"未分类"`）
  - 必做段（追加在后）：`{id, plan_entry_id: null, routine_id, start_at, end_at, duration_seconds, mode: "open", target_seconds: null, focus_completed: 0, title, project_name: "每日必做", kind: "routine"}`
- `<routineDay>`（`_routines_on`）：`{id, title, note, estimate_minutes, color: "#c47b1a", created_on, active, completed, locked: true, feedback_count, actual_seconds, is_running, running_started_at}`
- `<threadDay>`（`_threads_for_day`）：`{id, title, done_when, project_name, status, featured, today_entry_id, needs_followup, note_count, recent: [{"date", "title", "outcome"}]}`（recent 固定为前两天；`title`/`outcome` 为 `""`/`null` 表示那天没碰）
- 副作用：先 `_expire_focus_timer`（到点的 focus 段自动收尾）。

#### `POST /api/entries` — 新建任务
- 请求体：`date*`(日期)、`title*`(1–240 字，空 → 400 `"请先写下任务名称"`，超长 → `"任务名称请控制在 240 个字以内"`)、`project_name`(可空，自动建项目，截 80 字)、`estimate_minutes`(默认 0，须非负整数，否则 400 `"预估时间需要填写整数"`/`"预估时间不能小于 0"`)、`planned_start`(可空字符串)、`definition`(截 1000 字)、`parent_entry_id`(可选；非整数 → `"父任务不正确"`；父条目不在当天 → `"父任务不在当前日期中"`。设父后父条目 estimate 归零)
- 响应 201：`<entry>`
- 前端随后重新 `GET /api/day`，不直接用返回值。

#### `PATCH /api/entries/{id}` — 更新任务
- 请求体（均可选）：`title, project_name, estimate_minutes, planned_start`(""→null), `definition, outcome`
- 校验：title 空 → 400 `"任务名称不能为空"`；`outcome` 非法 → `"任务状态不正确"`；不存在 → 404 `"没有找到这条任务"`
- 副作用：`outcome=completed` 会停掉该条目计时并把 task 标 completed；`outcome=planned` 重新激活 task。
- 响应 200：`<entry>`

#### `DELETE /api/entries/{id}`
- 错误：已有计时记录 → 400 `"这条任务已有计时记录，不能删除；可以将它标为放弃"`；有子任务 → 400 `"请先处理它下面的子任务"`；404 同上。
- 响应 200：`{"deleted": true}`（若 task 不再有其他 plan_entries 则连 task 一并删除）

#### `POST /api/entries/{id}/move` — 移到更晚的一天
- 请求体：`date*`（目标日期；"目标日期格式不正确"）
- 错误（均 400）：404 `"没有找到这条任务"`；主线步骤 → `"主线的这一步留在当天，收工时写下明天接着做的一句"`；非 planned → `"只有还没完成的任务可以移走"`；`<=` 源日期 → `"只能移到更晚的一天"`；`<` 今天 → `"只能移到今天或之后"`；计时中 → `"先结束计时，再把任务移走"`；目标日已完成过 → `"这一天已经完成过这条任务"`
- 行为：连同子树与"只剩它的父链"一起移动；有计时记录的条目原条目置 `outcome=rescheduled, estimate_minutes=0` 且时间保留在原天；无计时记录则原条目删除/改期。
- 响应 200：`{"moved_to": "...", "title": "...", "source_date": "..."}`

#### `POST /api/day/save` — 保存当日 focus/reflection/mood
- 请求体：`date*, focus`(截 500), `reflection`(截 8000), `mood`(null/""或 1–5 整数，否则 400 `"状态评分不正确"`/`"状态评分需要在 1 到 5 之间"`)
- 响应 200：days 行 `{"plan_date", "focus", "reflection", "mood", "closed_at", "updated_at"}`

#### `POST /api/day/close` — 收工
- 请求体：`date*, focus, reflection, mood, decisions: [...]`
- `decisions[i]`：`entry_id*, action*(completed|carry|reschedule|abandoned), reason*(REASON_VALUES，非 completed 时), note`(截 1000), `target_date*(carry/reschedule 时，须晚于当天，否则 `"顺延日期需要晚于当前日期"`), `next_estimate_minutes`(默认沿用), `next_step`(主线步骤必填，空 → 400 `"这条主线要写下明天的下一句"`，超 240 → `"这一步请控制在 240 个字以内"`)
- 错误（均 400）：decisions 非数组/元素非 dict/entry_id 非整数 → `"收工选择不完整"`；有 planned 叶子未给去向 → `"还有未处理的任务，请为每一条选择去向"`；主线 completed 且明天无步骤未给 next_step → `"主线还要写下明天的下一句"`；action 非法 → `"请选择任务的去向"`；reason 非法 → `"未完成的任务需要选择原因"`
- 行为：completed → task 标完成，若属活跃主线则在明天放下一步；carry/reschedule → 原条目记 outcome/原因并在目标日生成新 planned 条目（主线则把 next_step 放到目标日）；abandoned → task 标 abandoned；父条目按子条目去向收拢（`_resolve_parent_entries`）；写 days.closed_at。
- 响应 200：同 `GET /api/day`。

#### `GET /api/week`
- 查询参数：`date`（默认今天）
- 响应 200：`{"start", "end", "days": [{"plan_date","estimate_minutes","completed_count","total_count","actual_seconds"}×7], "reasons": [{"reason","count","label"}], "projects": [{"project_name","estimate_minutes","actual_seconds"}], "carryovers": [{"task_id","title","carry_count","latest_target_date"}], "review": ""}`
- ⚠️ 前端 app.js **当前未调用**此端点（保留兼容即可，测试在用）。

### 1.2 计时器（time_segments）

#### `POST /api/timer/start`
- 请求体二选一：
  - 任务：`{entry_id*, mode("open"|"focus"，否则 400 `"计时模式不正确"), focus_minutes(默认 25；focus 时须 5–180，否则 400 `"专注时长需要填写整数"`/`"单次专注时长需要在 5 到 180 分钟之间"`)}`
  - 必做：`{routine_id, date}`（等同于 `POST /api/routines/timer/start`）
- 错误：entry 非 planned → 400 `"只有进�行中的任务可以开始计时"`（`only planned`）；404 条目不存在。
- 行为：启动前自动停掉正在跑的任务计时和必做计时；同条目重复 start 直接返回。
- 响应 200，**两种形状**：
  - 已在跑（重复 start）：`{"started": <entry>, "stopped_entry_id": null, "already_running": true}`（无 mode/target_seconds 字段）
  - 正常启动：`{"started": <entry>, "stopped_entry_id": int|null, "stopped_routine_id": int|null, "already_running": false, "mode", "target_seconds"}`

#### `POST /api/timer/stop`
- 请求体：`{entry_id?}` 或 `{routine_id}` 或 `{}`；可加 `target_reached: bool`
- 分支：
  - 无任务计时在跑且无必做计时 → `{"stopped": false, "entry_id": null}`
  - 无任务计时但有必做计时：传了 entry_id → 400 `"当前计时属于另一条任务"`；否则停必做计时返回 `{"stopped": true, "entry_id": null, "routine_id", "duration_seconds", "mode": "open", "focus_completed": false}`
  - 任务计时：entry_id 不匹配 → 400 `"当前计时属于另一条任务"`；focus 段达标或 target_reached → duration 截到 target、`focus_completed=true`
  - 正常返回 `{"stopped": true, "entry_id", "duration_seconds", "mode", "focus_completed"}`
- 必做分支（有 routine_id）等同 `POST /api/routines/timer/stop`。

#### `PATCH /api/segments/{id}` — 修正工作记录时长
- 请求体：`duration_minutes*`（1–1440，否则 400 `"修正时长需要填写整数"`/`"修正时长需要在 1 到 1440 分钟之间"`）
- 错误：404 `"没有找到这段工作记录"`；计时中 → 400 `"请先结束计时，再修正这段记录"`
- 响应 200：time_segments 全行 `{"id","plan_entry_id","task_id","start_at","end_at","duration_seconds","mode","target_seconds","focus_completed","created_at"}`（end_at 按 start+时长重算，focus_completed 按是否达 target 重算）

#### `DELETE /api/segments/{id}`
- 错误：404 同上；计时中 → 400 `"正在计时的记录不能删除，请先结束计时"`
- 响应 200：`{"deleted": true}`

#### `GET /api/segments`
- 查询参数：`start, end`（默认 start=今天、end=start；日期非法 → 400 `"开始日期格式不正确"`/`"结束日期格式不正确"`；end<start → `"结束日期不能早于开始日期"`；跨度 >31 天 → `"一次最多查看 31 天的时间记录"`）
- 响应 200：数组 `[{id, start_at, end_at, duration_seconds, mode, focus_completed, entry_id, plan_date, estimate_minutes, planned_start, title, project_name}]`

### 1.3 每日必做（routines）

#### `POST /api/routines` — 新建（无需答题）
- 请求体：`title*`(1–80，空 → 400 `"先写下每日必做的名称"`，超长 → `"每日必做的名称请控制在 80 个字以内"`)、`note`(截 200)、`estimate_minutes`(默认 0，非负整数，>240 → `"单项每日必做的预估不要超过 240 分钟"`)
- 响应 201：`<publicRoutine>` = `{id, title, note, estimate_minutes, color: "#c47b1a", created_on, active, completed, locked: true, feedback_count: 0}`

#### `PATCH /api/routines/{id}` — 修改（需 unlock_token）
- 请求体：`title?, note?, estimate_minutes?, unlock_token*`
- 错误（均 400）：token 缺失/<20 字符 → `"修改每日必做前，需要先答对 3 道题"`；token 失效/过期 → `"修改时间已过，请重新答题"`；404 `"没有找到这项每日必做"`
- 响应 200：`<publicRoutine>`

#### `DELETE /api/routines/{id}` — 停用（需 unlock_token）
- 请求体：`{unlock_token}`；错误同上；404 同上
- 响应 200：`{"deleted": true}`（软删除：active=0, deactivated_on=今天；打卡记录保留）

#### `POST /api/routines/check` — 打卡/取消打卡
- 请求体：`routine_id*, date*, completed: bool`
- 错误（均 400）：未来日期 → `"还没到这一天，不能提前打卡"`；404 `"没有找到这项每日必做"`；早于 created_on → `"这一天还没有这项每日必做"`；晚于 deactivated_on → `"这项每日必做已经停用"`
- 响应 200：`{"date", "routines": [<routineDay>]}`（routineDay 形状见 GET /api/day）

#### `POST /api/routines/timer/start` / `POST /api/routines/timer/stop`
- start 请求体：`{routine_id*, date*}`（未来日期 → 400 `"还没到这一天，不能开始计时"`；404/created_on/deactivated 同 check）
  - 响应：`{already_running: bool, stopped_entry_id: int|null, date, routines: [<routineDay>]}`（重复启动时 stopped_entry_id 为 null）
- stop 请求体：`{routine_id*}`；不在计时 → 400 `"这项每日必做现在没有在计时"`
  - 响应：`{stopped: true, duration_seconds, date, routines: [<routineDay>]}`

### 1.4 主线（threads）

#### `POST /api/threads` — 开启主线
- 请求体：`date*, title*`(1–80)、`done_when*`(1–200)、`step*`(1–240)、`project_name?`、`estimate_minutes`(默认 30)
- 错误（均 400）：`"先给这条主线起个名字"`/`"主线名称请控制在 80 个字以内"`、`"先写下一句完成标准，怎样算这条主线做完"`/`"完成标准请控制在 200 个字以内"`、`"先写下今天这一步"`/`"这一步请控制在 240 个字以内"`；活跃主线 ≥2 → `"同时进行的主线最多两条。先把一条暂停或做完"`
- 响应 201：整个 `get_day(date)` 对象（今天这一步已入清单）。

#### `PATCH /api/threads/{id}`
- 请求体：`title?, done_when?, status?(active|paused|done), featured?: true, project_name?, date?`（响应锚点日期，默认今天）
- 错误：404 `"没有找到这条主线"`；status 非法 → `"主线状态不正确"`；恢复时满 2 条 → `"同时进行的主线最多两条。先把一条暂停或做完"`；非 active 设 featured → `"先恢复这条主线，再把它设为今天主推"`；title/done_when 空/超长同 POST。
- 行为：featured 全局唯一（自动清其他）；保证至少一条 active 主线 featured（`_ensure_featured_thread`）。
- 响应 200：`get_day(date)` 整个对象。

#### `POST /api/threads/{id}/steps` — 写今天这一步
- 请求体：`date*, step|title*`(1–240，空 → 400 `"先写下今天这一步"`，超长 → `"这一步请控制在 240 个字以内"`), `estimate_minutes?`(默认 30)
- 错误：404；主线非 active → `"先恢复这条主线，再写下今天这一步"`；当天该主线已有非 planned/abandoned 一步 → `"这一天主线已经有一步"`
- 行为：当天已有 planned/abandoned 的该主线条目则复用（改标题、重置 outcome），否则新建 task+entry（带 thread_id）。
- 响应 200：`get_day(date)` 整个对象。

### 1.5 感悟（memos）

#### `GET /api/memos`
- 查询参数：`query`(截 200)、`date`、`limit`(默认 100，夹取 1–300；非整数 → 400 `"数量参数不正确"`)、`source_kind`("" | routine | thread，否则 → `"感悟来源不正确"`)、`source_id`（非整数 → `"感悟来源不正确"`，给了 source_kind 而缺 source_id 亦同）、`task_id`（非整数 → 400 `"任务不正确"`）
- 响应 200：数组，元素两种形状：
  - memo：`{id, memo_date, content, tags, pinned, note_title, note_link, source_entry_id, source_title, source_estimate_minutes, source_actual_seconds, source_plan_date, source_kind, source_routine_id, source_thread_id, source_task_id, created_at, updated_at, kind: "memo", source_thread_title, images: [{"id","width","height"}], read_count, last_read_at, read_today}`
  - daily（仅当未按 date/source/task 过滤时并入，最多 50 条）：`{id: "<plan_date 字符串>", memo_date, content, tags: "每日复盘", pinned: 0, 全部 source_* 为 null/"" , note_title: "", note_link: "", source_thread_title: "", created_at, updated_at, kind: "daily", images, read_count, last_read_at, read_today}`
  - 排序：`pinned DESC, memo_date DESC, created_at DESC`（并入 daily 后整体重排再截 limit）
- 注意：`source_thread_title` 由 `_decorate_memo_sources` 回填；经 entry 归属主线的 memo 会补 `source_thread_id`/`source_task_id`/`source_kind`。

#### `POST /api/memos` — 新建
- 请求体：`date?`、`content`（纯文本 ≤4000 字；`content_format="rich"` 时走 `sanitize_rich_html`，纯文本 >4000 或 HTML >12000 → 400 `"单条感悟请控制在 4000 个字以内"`）、`content_format?`、`tags`(截 300)、`has_images?`（空内容时有图也允许，否则 400 `"先写下一点内容，或添加一张图片"`）、`note_title`(截 80)、`note_link`（>500 → `"链接请控制在 500 个字符以内"`；带非 http(s) scheme → `"请填写可以打开的网页链接"`；裸域名自动补 `https://`）
- 来源三选一：`entry_id`（404 `"没有找到这条任务"`；子任务 → 400 `"感悟写在主任务上"`；自动汇总整棵子树的预估与实际秒）、`routine_id`（404 `"没有找到这项每日必做"`）、`thread_id`（404 `"没有找到这条主线"`）。有来源时 memo_date 取 `source_plan_date`。
- 错误：entry_id 非整数 → 400 `"任务不正确"`
- 响应 201：`memos` 全行 + `kind: "memo"` + `images: []`（**无 source_thread_title、无 read_count 等装饰字段**）

#### `PATCH /api/memos/{id}`
- 请求体：`date?, content?(+content_format), tags?, pinned?`
- 错误：404 `"没有找到这条感悟"`；清空内容且无图 → 400 `"感悟内容不能为空"`
- 响应 200：memos 全行 + `kind` + `images`（同样无 read 字段装饰）

#### `DELETE /api/memos/{id}`
- 错误：404 `"没有找到这条感悟"`；级联删图片（库行+文件）与 memo_reads。
- 响应 200：`{"deleted": true}`

#### `POST /api/memo-reads` — 标记又读了一遍
- 请求体：`kind("memo"|"daily"，否则 400 `"记录类型不正确"`), id`（memo 时须正整数，否则 404 `"没有找到这条感悟"`；daily 时为日期，非法 → 400 `"记录日期格式不正确"`）
- 行为：同一自然日重复标记不重复计数（`counted=false`）。
- 响应 200：`{kind, id(memo 为 int，daily 为日期字符串), read_count, last_read_at, read_today, counted}`

#### `GET /api/memo-sources`
- 响应 200：`[{"kind": "thread"|"routine", "id", "title", "count", "featured", "active"}]`（非 active/done 且无感悟的来源被过滤；排序：thread 优先、featured 优先、active 优先、count 降序）

#### `GET /api/memo-templates`
- 响应 200：`[{"id", "name", "content", "updated_at"}]`

#### `POST /api/memo-templates`
- 请求体：`name*`(1–40，空 → 400 `"先给模板起个名字"`，超长 → `"模板名称请控制在 40 个字以内"`)、`content`（强制按 rich 处理，纯文本为空 → `"模板里先写一点内容"`）
- 错误：数量 ≥40 → 400 `"模板最多保存 40 个"`
- 响应 201：`{"id", "name", "content", "updated_at"}`

#### `PATCH /api/memo-templates/{id}` / `DELETE /api/memo-templates/{id}`
- 错误：404 `"没有找到这个模板"`；name/content 校验同 POST
- 响应 200：PATCH 返回模板对象；DELETE 返回 `{"deleted": true}`

#### `GET /api/tags/suggested`
- 响应 200：`{"tags": ["估时", "复盘", "产品"]}`（默认 3 个，按最近 200 条 memo 的 tags 加权）

### 1.6 复盘（reviews / report）

#### `GET /api/report`
- 查询参数：`date`(默认今天)、`period`(默认 week；非法 → 400 `"复盘周期不正确"`)
- 响应 200：
```json
{
  "period": "week", "start": "...", "end": "...",
  "days": [{"plan_date","estimate_minutes","actual_seconds","completed_count","total_count","focus_count"}],
  "reasons": [{"reason","count","label"}],
  "projects": [{"project_name","estimate_minutes","actual_seconds","completed_count","total_count"}],
  "carryovers": [{"task_id","title","carry_count","latest_target_date"}],
  "focus": {"segment_count","completed_count","actual_seconds","longest_streak"},
  "insights": [{"tone":"neutral|info|positive|warning","title","body"}],
  "review": "",
  "routines": [{"id","title","note","estimate_minutes","color","active","completed_count","applicable_count","streak","days":[{"date","status"}]}]
}
```
- `routines[].days[].status ∈ {done, missed, future, unset}`；days 数组覆盖整个周期（月 28–31 天、季度 92 天）。

#### `POST /api/review` — 保存周期复盘
- 请求体：`period*(week|month|quarter，否则 400 `"复盘周期不正确"`), start*(日期，文案"周期开始日期"), content`(截 10000)；upsert（period_type+period_start 唯一）
- 响应 200：`{"period", "start", "content"}`

#### `POST /api/week/review` — 保存周复盘（旧端点）
- 请求体：`start*(文案"周开始日期"), content`
- 响应 200：`{"start", "content"}`
- ⚠️ 前端当前只用 `/api/review`，此端点保留兼容即可。

### 1.7 图片（note_images）

#### `POST /api/images`
- 请求体：`owner_type*("day"|"memo"，否则 400 `"图片所属记录不正确"`)、owner_key*`（day=日期须合法；memo=纯数字字符串，否则同上 400）、`original*`(data URL，≤8 MB，仅 image/jpeg|png|webp|gif；错误文案：`"原图格式不正确"`/`"只支持 JPG、PNG、WEBP 和 GIF"`/`"原图太大，请换一张小一些的"`)、`thumbnail*`(≤500 KB，文案缩略图版)、`width?, height?`(正 int 否则 null)
- 错误：memo 不存在 → 404 `"没有找到这条感悟"`；单记录已有 9 张 → 400 `"一条记录最多保存 9 张图片"`；写文件失败回滚并 400 `"图片没有保存成功"`
- 存储：文件写 `data/images/{id}`（原图）与 `data/images/{id}.thumb`（缩略图）；库行存原图 content_type。
- 响应 201：`{"id", "width", "height", "owner_type", "owner_key"}`

#### `GET /api/images/{id}` / `GET /api/images/{id}/thumb`
- 响应 200：图片字节；`Content-Type`：原图=入库 content_type，缩略图固定 `image/jpeg`；`Cache-Control: private, no-cache`
- 错误：404 `"没有找到这张图片"`；`/thumb` 以外的第二段路径 → 404 `"没有找到这张图片"`

#### `DELETE /api/images/{id}`
- 错误：404 `"没有找到这张图片"`
- 响应 200：`{"deleted": true}`（删库行 + 两个文件）

### 1.8 提醒（reminders）

#### `GET /api/reminders`
- 响应 200：`[{"id", "message", "remind_at", "status"}]`（pending 全量 + 48 小时内的 done；排序 pending 优先、remind_at 升序、id 升序）

#### `POST /api/reminders`
- 请求体：`message*`(1–200，空 → 400 `"先写下要提醒的内容"`，超长 → `"提醒内容请控制在 200 个字以内"`)、`remind_at*`(`YYYY-MM-DDTHH:MM`，非法 → `"请选择提醒的日期和时间"`；过去时间 → `"请选一个还没到的时间"`)
- 响应 201：`{"id", "message", "remind_at", "status": "pending"}`

#### `PATCH /api/reminders/{id}`
- 请求体：任一 `message`(改后 status 重置 pending)、`remind_at`(同 POST 校验)、`status`(pending|done，否则 400 `"提醒状态不正确"`)
- 错误：404 `"没有找到这个提醒"`
- 响应 200：`{"id", "message", "remind_at", "status"}`

#### `DELETE /api/reminders/{id}`
- 错误：404 `"没有找到这个提醒"`
- 响应 200：`{"deleted": true}`

### 1.9 设置（settings）

#### `GET /api/settings`
- 响应 200：`{"profile": {"display_name", "avatar_data", "focus_minutes"(默认 25), "break_minutes"(默认 5)}, "routines": [<publicRoutine>...]}`

#### `PATCH /api/settings`
- 请求体：`{"profile": {...}}` 或直接平铺四字段：`display_name`(截 40)、`avatar_data`(data:image base64 ≤500 KB，否则 400 `"头像需要是较小的图片"`)、`focus_minutes`(5–180)、`break_minutes`(1–60)
- 错误：profile 非 dict → 400 `"个人资料格式不正确"`；整数/范围文案：`"专注时长需要填写整数"`/`"专注时长不能小于 0"`/`"默认专注时长需要在 5 到 180 分钟之间"`/`"休息时长需要填写整数"`/`"休息时长不能小于 0"`/`"默认休息时长需要在 1 到 60 分钟之间"`
- 响应 200：profile 对象（同 GET 内层）

### 1.10 挑战（challenge）

#### `POST /api/routines/challenge`
- 请求体：忽略（前端发 `{}`）
- 行为：生成 3 道四则混合题（SystemRandom；形如 `((a + b) − c) × f ÷ d`，答案为整数），10 分钟过期；先清理过期挑战。
- 响应 200：`{"id", "expires_at", "questions": [{"prompt"}]}`（**只给 prompt，不给答案**）
- 生成失败 → 400 `"暂时无法生成题目，请再试一次"`

#### `POST /api/routines/challenge/verify`
- 请求体：`id*, answers*[3]`
- 错误（均 400）：缺 id / answers 非数组 / 长度不符 → `"请完成全部题目"`；挑战不存在或过期 → `"这组题目已过期，请重新出题"`；任一答错 → `"三道题需要全部答对，才能修改每日必做"`；非整数答案 → `"答案需要填写整数"`
- 响应 200：`{"unlocked": true, "unlock_token", "expires_at"}`（token 10 分钟有效，供 PATCH/DELETE `/api/routines/{id}`）

### 1.11 其他

- 所有未匹配的 `/api/*` 路径/方法组合 → 404 `{"error": "没有找到这个操作"}`。
- 请求体解析失败/非 JSON object/超长 → 400 `{"error": "请求内容不正确"}`（超长 `"内容过长"`）。
- 静态文件与 SPA 回退见第 3 节。

---

## 2. Database 类公共方法清单

构造：`Database(path: Path = DB_PATH)`；`connect()` 返回 `sqlite3.Connection`（Row factory、`PRAGMA foreign_keys=ON`、`busy_timeout=10000`，文件锁 timeout=10s）。`image_dir` property → `path.parent / "images"`。

### Day / 条目
- `get_day(plan_date: str) -> dict` — 校验日期；先过期 focus 计时。返回形状见 `GET /api/day`。无副作用外的抛出（日期非法 400 `"日期格式不正确"`）。
- `create_entry(payload: dict) -> dict` — 返回 `<entry>`。错误：`"请先写下任务名称"`、`"任务名称请控制在 240 个字以内"`、`"预估时间需要填写整数"`/`"预估时间不能小于 0"`、`"父任务不正确"`、`"父任务不在当前日期中"`（均 400）。
- `update_entry(entry_id: int, payload: dict) -> dict` — 返回 `<entry>`。错误：404 `"没有找到这条任务"`；`"任务名称不能为空"`、`"任务状态不正确"`（400）。
- `delete_entry(entry_id: int) -> None` — 错误：404 同上；400 `"这条任务已有计时记录，不能删除；可以将它标为放弃"`、`"请先处理它下面的子任务"`。
- `save_day(payload: dict) -> dict` — upsert days；返回 days 行。错误：`"状态评分不正确"`、`"状态评分需要在 1 到 5 之间"`（400）。
- `close_day(payload: dict) -> dict` — 返回 `get_day(date)`。错误见 1.1 收工端点。
- `move_entry(entry_id: int, payload: dict) -> dict` — 返回 `{"moved_to", "title", "source_date"}`。错误见 1.1 move 端点。
- `get_week(anchor: str) -> dict` — 返回周对象（见 1.1）。日期非法 400。

### 计时器
- `start_timer(entry_id: int, mode: str = "open", focus_minutes: int = 25) -> dict` — 错误：`"计时模式不正确"`、`"专注时长需要填写整数"`、`"单次专注时长需要在 5 到 180 分钟之间"`、`"只有进行中的任务可以开始计时"`（400）；404 条目不存在。返回两种形状见 1.2。
- `stop_timer(entry_id: int | None = None, target_reached: bool = False) -> dict` — 错误：400 `"当前计时属于另一条任务"`。返回见 1.2。
- `update_segment(segment_id: int, payload: dict) -> dict` — 返回 time_segments 全行。错误：404 `"没有找到这段工作记录"`；400 `"修正时长需要填写整数"`、`"修正时长需要在 1 到 1440 分钟之间"`、`"请先结束计时，再修正这段记录"`。
- `delete_segment(segment_id: int) -> None` — 错误：404 同上；400 `"正在计时的记录不能删除，请先结束计时"`。
- `list_segments_between(start: str, end: str) -> list[dict]` — 错误：400 `"开始日期格式不正确"`/`"结束日期格式不正确"`/`"结束日期不能早于开始日期"`/`"一次最多查看 31 天的时间记录"`。

### 感悟
- `list_memos(query="", memo_date=None, limit=100, source_kind="", source_id=None, task_id=None) -> list[dict]` — 错误：400 `"感悟来源不正确"`、`"记录日期格式不正确"`。返回元素见 1.5（memo/daily 两种，含 images/read 装饰）。
- `create_memo(payload: dict) -> dict` — 返回 memos 全行 + `kind` + `images: []`。错误见 1.5。
- `update_memo(memo_id: int, payload: dict) -> dict` — 返回 memos 全行 + `kind` + `images`。错误：404 `"没有找到这条感悟"`；400 `"感悟内容不能为空"`。
- `delete_memo(memo_id: int) -> None` — 错误：404 同上。级联清理图片文件与 memo_reads。
- `mark_memo_read(payload: dict) -> dict` — 返回 `{kind, id, read_count, last_read_at, read_today, counted}`。错误：400 `"记录类型不正确"`；404 `"没有找到这条感悟"`。
- `list_memo_sources() -> list[dict]` — 返回 `[{kind, id, title, count, featured, active}]`。
- `list_memo_templates() -> list[dict]`；`create_memo_template(payload) -> dict`；`update_memo_template(template_id, payload) -> dict`；`delete_memo_template(template_id) -> None` — 错误：400 `"先给模板起个名字"`/`"模板名称请控制在 40 个字以内"`/`"模板里先写一点内容"`/`"模板最多保存 40 个"`；404 `"没有找到这个模板"`。模板对象为 `{id, name, content, updated_at}`。
- `suggested_tags(limit: int = 3) -> list[str]`

### 提醒
- `list_reminders() -> list[dict]` — `[{id, message, remind_at, status}]`。
- `create_reminder(payload) -> dict`；`update_reminder(reminder_id, payload) -> dict`；`delete_reminder(reminder_id) -> None` — 错误：400 `"先写下要提醒的内容"`/`"提醒内容请控制在 200 个字以内"`/`"请选择提醒的日期和时间"`/`"请选一个还没到的时间"`/`"提醒状态不正确"`；404 `"没有找到这个提醒"`。

### 图片
- `create_note_image(payload) -> dict` — 返回 `{id, width, height, owner_type, owner_key}`。错误：400 `"图片所属记录不正确"`/`"原图格式不正确"`/`"缩略图格式不正确"`/`"只支持 JPG、PNG、WEBP 和 GIF"`/`"原图太大，请换一张小一些的"`/`"缩略图太大，请换一张小一些的"`/`"一条记录最多保存 9 张图片"`/`"图片没有保存成功"`；404 `"没有找到这条感悟"`。
- `read_note_image(image_id: int, thumbnail: bool = False) -> tuple[bytes, str]` — 返回 `(内容, content_type)`（thumb 固定 `image/jpeg`）。错误：404 `"没有找到这张图片"`。
- `delete_note_image(image_id: int) -> None` — 错误：404 同上。删库行+文件。

### 主线
- `create_thread(payload) -> dict` — 返回 `get_day(date)`。错误见 1.4。
- `update_thread(thread_id, payload) -> dict` — 返回 `get_day(date)`。错误见 1.4。
- `create_thread_step(thread_id, payload) -> dict` — 返回 `get_day(date)`。错误见 1.4。

### 复盘
- `get_report(anchor: str, period: str) -> dict` — 错误：400 `"复盘周期不正确"`、日期格式。返回见 1.6。
- `save_period_review(payload) -> dict` — 返回 `{period, start, content}`。错误同上 + `"周期开始日期格式不正确"`。
- `save_week_review(payload) -> dict` — 返回 `{start, content}`。错误：`"周开始日期格式不正确"`。

### 设置 / 必做 / 挑战
- `get_settings() -> dict` — `{"profile": {...}, "routines": [...]}`。
- `save_settings(payload) -> dict` — 返回 profile。错误见 1.9。
- `create_routine(payload) -> dict`；`update_routine(routine_id, payload) -> dict`；`delete_routine(routine_id, unlock_token) -> None` — 返回 `<publicRoutine>` 或 None。错误：400 `"先写下每日必做的名称"`/`"每日必做的名称请控制在 80 个字以内"`/`"预估分钟需要填写整数"`/`"预估分钟不能小于 0"`/`"单项每日必做的预估不要超过 240 分钟"`/`"修改每日必做前，需要先答对 3 道题"`/`"修改时间已过，请重新答题"`；404 `"没有找到这项每日必做"`。
- `create_routine_challenge() -> dict`；`verify_routine_challenge(payload) -> dict` — 见 1.10。
- `set_routine_check(payload) -> dict` — 返回 `{date, routines}`。错误见 1.3。
- `start_routine_timer(payload) -> dict`；`stop_routine_timer(payload) -> dict` — 见 1.3。

---

## 3. 静态资源与启动行为

### 静态伺服（`_serve_static`）
- 仅处理非 `/api/` 路径；`""` 或 `/` → `web/index.html`；其余按 URL 路径（unquote 后）映射到 `WEB_DIR` 内文件。
- 目录逃逸防护：`target.resolve()` 后必须仍在 `WEB_DIR.resolve()` 之内，否则 404 `"没有找到这个页面"`。
- **SPA 式回退**：目标文件不存在时回退到 `web/index.html`（若 index.html 也不存在 → 404 `"页面文件还没有准备好"`）。即任意未知非 API 路径都返回 200 + index.html。
- Content-Type：`mimetypes.guess_type()`，未知 → `application/octet-stream`；`text/*`、`application/javascript`、`application/json` 追加 `; charset=utf-8`。
- 响应头：`Content-Length`、`Cache-Control: no-cache`（静态）；API JSON 为 `no-store`；图片为 `private, no-cache`。

### 图片 content-type
- 原图：读库中 `note_images.content_type`（上传时从 data URL 头解析，限定 jpeg/png/webp/gif）。
- 缩略图：一律 `image/jpeg`（前端 canvas 始终生成 JPEG 缩略图）。
- 读取成功返回 200 字节流；库行或文件缺失 → 404 `"没有找到这张图片"`。

### 启动（`main()`）
- `argparse`：`--port`（默认 **8765**）、`--no-browser`（不开浏览器）。
- 日志：`logging.basicConfig(filename=data/daily_plan.log, level=INFO, encoding=utf-8, format="%(asctime)s %(levelname)s %(message)s")`；请求日志经 `log_message` 覆写进 logging；未捕获异常 `logging.exception` 后返回 500。
- 数据目录 `data/` 自动创建；`Database()` 初始化（建表 + 迁移）。
- 绑定 `127.0.0.1:port`（仅本机）；`ThreadingHTTPServer`（`daemon_threads=True`）。
- 启动打印：启动 URL、数据文件路径、`Ctrl+C` 提示。
- **自动开浏览器**：除非 `--no-browser`，`threading.Timer(0.6, webbrowser.open(url))`。
- `KeyboardInterrupt` 时打印"已停止。数据已经保存在 SQLite 文件中。"并 `server_close()`。
- 启动脚本 `启动每日计划.bat`：`chcp 65001`、`py -3 server.py`（失败提示看 `data\daily_plan.log`）。

---

## 4. 模块级工具函数清单

| 函数 | 签名 | 用途 / 行为 |
|---|---|---|
| `utc_now()` | `() -> str` | UTC ISO8601 秒级（`...Z`），全部时间戳用它 |
| `AppError` | `(message: str, status: int = 400)` | 业务异常，`.message`/`.status`，HTTP 层转 `{"error"}` |
| `sanitize_rich_html(value: str) -> str` | | `_RichSanitizer`（HTMLParser）：白名单标签 `p,br,strong,b,ul,ol,li,h3,div`；`h1/h2→h3`、`div→p`；剥离 `script/style` 及其内容；仅保留 class 中的 `note-lg`/`note-title`（且只在 p/li/h3 上）；其余属性全丢弃；自闭合与错配标签自动收尾 |
| `rich_plain_text(value: str) -> str` | | 去标签转纯文本（块级标签换行，压缩 3+ 连续换行为 2），用于长度校验与空判断 |
| `memo_content_from_payload(payload, current=None) -> str` | | 依据 `content_format=="rich"` 决定 sanitize 与否；纯文本 ≤4000 字、rich 纯文本 ≤4000 且 HTML ≤12000，否则 `AppError("单条感悟请控制在 4000 个字以内")`；PATCH 时若无 content 且非 rich 则保留原文 |
| `valid_remind_at(value) -> str` | | `%Y-%m-%dT%H:%M` 解析归一化；非法 → 400 `"请选择提醒的日期和时间"` |
| `valid_date(value, field_name="日期") -> str` | | `%Y-%m-%d` 校验归一化；非法 → 400 `f"{field_name}格式不正确"` |
| `as_non_negative_int(value, field_name) -> int` | | int 化且 ≥0；否则 400 `f"{field_name}需要填写整数"` / `f"{field_name}不能小于 0"` |
| `seconds_between(start_at, end_at) -> int` | | ISO 时间差秒数（下限 0），兼容 `Z` 后缀 |
| `generate_routine_questions(count=3) -> list[dict]` | | 生成 3 道不重复且四符号齐全的四则题；40 次尝试不成 → 400 `"暂时无法生成题目，请再试一次"`。每题 `{"prompt", "answer"(int)}` |
| `_routine_question(rng) -> dict` | | 内部：`(inner×factor)%divisor==0` 构造，`prompt = "((L + R) − s) × f ÷ d"`（符号 + − × ÷） |
| `period_bounds(anchor, period) -> tuple[date, date]` | | week=周一至周日、month=自然月、quarter=自然季度；非法 → 400 `"复盘周期不正确"` |
| `_as_whole_number(value, field_name) -> int` | | 挑战答案用；bool 拒绝；否则 400 `f"{field_name}需要填写整数"` |

模块常量：`REASONS`/`REASON_VALUES`、`OUTCOMES`、`DATE_FORMAT="%Y-%m-%d"`、`ROUTINE_COLOR="#c47b1a"`、`ROUTINE_SYMBOLS=("+", "−", "×", "÷")`；路径常量 `ROOT/WEB_DIR/DATA_DIR/DB_PATH/LOG_PATH`。

---

## 5. 前端契约（web/app.js 全部 fetch 调用）

- `web/index.html` 无任何内联 JS，仅 `<script src="/app.js" defer>`。
- 统一封装 `api(path, options)`：始终带 `Content-Type: application/json`；`response.json()` 失败 → 抛 `"没有收到有效响应，请确认每日计划仍在运行"`；`!response.ok` → 抛 `data.error || "操作没有完成，请稍后再试"`。**即错误契约依赖 `{"error": string}`。**
- 图片展示直接用 `<img src="/api/images/{id}/thumb">` / `/api/images/{id}`（不经 fetch）。

### 今日视图 / 任务
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `GET /api/day?date=` | — | `active_timer, day.mood, day.reflection, day.images, entries[], projects[], segments[], routines[], threads[], reasons[], date`；entry 用 `id, task_id, parent_id, title, outcome, thread_id, has_children, estimate_minutes, planned_start, definition, project_name, thread_title, actual_seconds, is_running, unfinished_reason, reason_note, target_date, sort_order`；active_timer 用 `plan_entry_id, routine_id, start_at, mode, target_seconds, plan_date, title`；segment 用 `id, plan_entry_id, routine_id, start_at, end_at, duration_seconds, title, project_name, kind`；routine 用 `id, completed, is_running, actual_seconds, running_started_at, feedback_count, color, note, estimate_minutes`；thread 用 `id, title, status, featured, done_when, project_name, today_entry_id, needs_followup, note_count, recent[]`；reasons 用 `value, label`；projects 用 `name` |
| `GET /api/memos?date=...&limit=30` | — | 今日感悟列表：`id, kind, content, tags, pinned, note_title, note_link, source_*` |
| `POST /api/entries` | `{date, title, project_name, estimate_minutes, planned_start, parent_entry_id}` | 不用返回值（随后 loadDay） |
| `PATCH /api/entries/{id}` | `{outcome}`（toggleComplete）或 `{title, project_name, estimate_minutes, planned_start, definition}` | 不用返回值 |
| `DELETE /api/entries/{id}` | — | 不用 |
| `POST /api/entries/{id}/move` | `{date}` | `title, moved_to` |
| `POST /api/day/save` | `{date, focus, reflection, mood}` | 不用 |
| `POST /api/day/close` | `{date, focus, reflection, mood, decisions:[{entry_id, action, reason, note, target_date, next_estimate_minutes, next_step}]}` | 整个 day 对象（同 GET /api/day），用 `entries, active_timer, day.mood` |
| `GET /api/segments?start=&end=` | — | `id, entry_id, plan_date, start_at, end_at, duration_seconds, title, project_name, mode, focus_completed, estimate_minutes, planned_start`（报表页时间轴） |
| `PATCH /api/segments/{id}` | `{duration_minutes}` | 不用 |
| `DELETE /api/segments/{id}` | — | 不用 |

### 计时器
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `POST /api/timer/start` | `{entry_id, mode, focus_minutes}` 或 `{routine_id, date, mode:"open"}` | `stopped_entry_id, stopped_routine_id` |
| `POST /api/timer/stop` | `{entry_id, target_reached}` 或 `{routine_id}` | `stopped, focus_completed, duration_seconds`（focus_completed 触发休息条+提示音） |

### 主线
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `POST /api/threads` | `{date, title, done_when, step, project_name}` | 整个 day 对象 |
| `POST /api/threads/{id}/steps` | `{date, step}` | 整个 day 对象 |
| `PATCH /api/threads/{id}` | `{featured:true}` / `{status:"paused"|"active"|"done"}` + `date` | 整个 day 对象 |

### 感悟
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `POST /api/memos` | `{date, content, content_format:"rich", tags, has_images}`（快速/撰写框）；`{date, content, content_format:"rich", tags, note_title, note_link, entry_id?|routine_id?|thread_id?}`（任务/必做/主线感悟） | `id`（随后用它传图） |
| `PATCH /api/memos/{id}` | `{date, content, content_format:"rich", tags}`（重试补图后更新）或 `{date, content, content_format:"rich", tags, pinned}`（编辑框）或 `{pinned}`（置顶切换） | 不用 |
| `DELETE /api/memos/{id}` | — | 不用 |
| `GET /api/memos?query=&limit=200[&source_kind=&source_id=]` | — | memo 卡片：`id, kind, content, tags, pinned, note_title, note_link, memo_date, source_kind, source_title, source_entry_id, source_task_id, source_thread_id, source_thread_title, source_plan_date, images[], read_count, read_today, last_read_at` |
| `GET /api/memos?task_id=&limit=100` | — | 任务历史：`kind, note_title, note_link, memo_date, content` |
| `GET /api/memos?date=&limit=30` | — | 今日感悟（同上字段） |
| `POST /api/memo-reads` | `{kind, id}`（memo 时 id 为 Number，daily 时为日期字符串） | `read_count, last_read_at, read_today, counted` |
| `GET /api/memo-sources` | — | `kind, id, title, count` |
| `GET /api/tags/suggested` | — | `tags[]` |
| `GET /api/memo-templates` | — | `id, name, content` |
| `POST /api/memo-templates` / `PATCH /api/memo-templates/{id}` | `{name, content, content_format:"rich"}` | 不用 |
| `DELETE /api/memo-templates/{id}` | — | 不用 |

### 图片
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `POST /api/images` | `{owner_type, owner_key, original(dataURL), thumbnail(dataURL), width, height}` | `id`（拼 `<img>` URL 并维护删除） |
| `DELETE /api/images/{id}` | — | 不用 |

### 报表 / 复盘
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `GET /api/report?date=&period=` | — | `start, end, days[]（plan_date, actual_seconds, focus_count）, reasons[], projects[]（project_name, actual_seconds, estimate_minutes, completed_count, total_count）, carryovers[], focus（completed_count, segment_count, actual_seconds, longest_streak）, insights[]（tone, title, body）, review, routines[]（id, title, note, estimate_minutes, color, active, completed_count, applicable_count, streak, days[]（date, status））` |
| `POST /api/review` | `{period, start, content}` | `content` |
| `GET /api/day?date=`（报表页点开某天） | — | 整个 day 对象 |

### 设置 / 必做 / 挑战
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `GET /api/settings` | — | `profile（display_name, avatar_data, focus_minutes, break_minutes）, routines[]` |
| `PATCH /api/settings` | `{profile:{display_name, avatar_data, focus_minutes, break_minutes}}` | 整个 profile 对象 |
| `POST /api/routines` | `{title, note, estimate_minutes}` | 不用 |
| `PATCH /api/routines/{id}` | `{title, note, estimate_minutes, unlock_token}` | 不用 |
| `DELETE /api/routines/{id}` | `{unlock_token}` | 不用 |
| `POST /api/routines/check` | `{routine_id, date, completed}` | `routines[]`（更新今日列表） |
| `POST /api/routines/challenge` | `{}` | `id, questions[]（prompt）` |
| `POST /api/routines/challenge/verify` | `{id, answers[]}` | `unlock_token` |

### 提醒
| 调用 | 请求体 | 用到的响应字段 |
|---|---|---|
| `GET /api/reminders` | —（轮询） | `id, message, remind_at, status` |
| `POST /api/reminders` | `{message, remind_at}` | 不用 |
| `PATCH /api/reminders/{id}` | `{message, remind_at}` 或 `{status:"done"}` | 不用 |
| `DELETE /api/reminders/{id}` | — | 不用 |

### 前端未使用但存在的服务端端点
- `GET /api/week`、`POST /api/week/review`、`POST /api/routines/timer/start`、`POST /api/routines/timer/stop`（前端统一走 `/api/timer/start|stop` 的 routine 分支）。

---

## 6. 测试盘点（tests/test_database.py，1091 行）

- import：`from server import AppError, Database, generate_routine_questions`（标准库 unittest；`setUp` 用 `tempfile.TemporaryDirectory` + `Database(Path(tmp)/"test.sqlite3")`）。
- 两个 TestCase：`DatabaseTests`（27 个用例）与 `TaskNoteTests`（3 个用例）。
- 覆盖点：
  - 条目持久化、单计时器互斥（start_timer 返回 `stopped_entry_id`，stop 返回 `stopped`）
  - 子任务使父条目 estimate 归零 + 周报表聚合（`get_week` 的 days/reasons）
  - 收工 carry（原因/下次预估/跨天）与 close_day 的 404/400 行为
  - move_entry 规则（不能回移、计时中禁移、source 置 rescheduled 且 estimate=0、计时留在原天、父随子移动）
  - focus 计时过期（`_expire_focus_timer` 计 300 秒、`focus_completed=1`、report.focus.completed_count）
  - `update_segment` 修正时长
  - memo 搜索（含 daily 混入）、阅读计数（memo/daily、跨天重复计数、删除 memo 清理 memo_reads）
  - 月/季报表边界（10 月 → `2026-10-01`~`2026-10-31`、季度 92 天、insights 非空）
  - 必做四锁（题目生成、挑战存库、verify、unlock_token 修改、打卡日期限制、报表 routines/status 枚举 done/missed/future/unset、streak）
  - 图片全链路（data URL 校验、9 张上限、缩略图固定 image/jpeg、文件落盘与删除级联、`suggested_tags` 排序）
  - 每日感悟合并（`_merge_daily_notes` 幂等，直接调用私有方法 + 删 app_settings 标记重放）
  - 提醒 CRUD 与时间校验
  - 主线（开启/跨天推进/暂停恢复/2 条上限/featured、收工 next_step、completed 后必须补下一句）
  - 来源感悟（routine/thread/task 过滤、`source_title`/`source_thread_title`、`feedback_count`/`note_count`）
  - rich 内容清洗（script/onclick 剥离、note-lg 保留）、模板 CRUD、坏链接拒绝
  - `list_segments_between` 字段与 31 天限制
- **重构后最小改动方案**：测试只依赖 `server` 模块中的 `AppError`、`Database`、`generate_routine_questions` 三个名字及 `Database` 的公共方法签名/返回形状。把 `Database` 类（含 SQL 与迁移）原样保留——FastAPI 层只做 HTTP 封装，测试即零改动通过；若类移到新模块（如 `app/db.py`），只需改 import 行（`from server import ...` → `from app.db import ...`，或让 `server.py` 变成 re-export 薄壳）。

---

## 7. 数据表清单（`initialize()`）与迁移逻辑

### 表与关键约束
| 表 | 关键列 | 约束 / 索引 |
|---|---|---|
| `projects` | id, name, color(默认'#5b6cf9'), created_at | `name COLLATE NOCASE UNIQUE` |
| `tasks` | id, title, project_id, parent_id(自引用), definition, status, completed_at, created_at, updated_at | status CHECK(active/completed/abandoned)；两个 FK 均 `ON DELETE SET NULL` |
| `plan_entries` | id, plan_date, task_id→CASCADE, estimate_minutes(≥0), planned_start, sort_order, outcome(默认planned, 五值CHECK), unfinished_reason, reason_note, target_date, created_at, updated_at | `UNIQUE(plan_date, task_id)`；索引 `plan_entries_by_date(plan_date, sort_order)` |
| `time_segments` | id, plan_entry_id→CASCADE, task_id→CASCADE, start_at, end_at, duration_seconds(≥0), mode(默认'open'), target_seconds, focus_completed, created_at | **部分唯一索引 `one_running_timer`：`UNIQUE((1)) WHERE end_at IS NULL`**（全表同时最多一条未停计时） |
| `days` | plan_date(PK), focus, reflection, mood(CHECK 1–5 或 NULL), closed_at, updated_at | |
| `reviews` | id, period_type(week/month/quarter CHECK), period_start, content, updated_at | `UNIQUE(period_type, period_start)` |
| `memos` | id, memo_date, content, tags, pinned, created_at, updated_at + 迁移列（见下） | 索引 `memos_by_date(memo_date DESC, created_at DESC)` |
| `memo_templates` | id(AUTOINCREMENT), name, content, created_at, updated_at | |
| `note_images` | id(AUTOINCREMENT), owner_type('day'|'memo' CHECK), owner_key, content_type, width, height, created_at | 索引 `note_images_by_owner(owner_type, owner_key, id)` |
| `reminders` | id(AUTOINCREMENT), message, remind_at, status(pending/done CHECK), created_at, updated_at | 索引 `reminders_by_time(status, remind_at)` |
| `memo_reads` | owner_kind('memo'|'daily' CHECK), owner_key, read_count(≥0), last_read_at | `PRIMARY KEY(owner_kind, owner_key)` |
| `threads` | id, title, done_when, project_id→SET NULL, status(active/paused/done CHECK), featured, created_at, updated_at | |
| `app_settings` | key(PK), value, updated_at | |
| `routines` | id, title, note, estimate_minutes(≥0), sort_order, active, created_on, deactivated_on, created_at, updated_at | |
| `routine_checks` | routine_id→CASCADE, plan_date, completed_at | `PRIMARY KEY(routine_id, plan_date)` |
| `routine_segments` | id, routine_id→CASCADE, plan_date, start_at, end_at, duration_seconds(≥0), created_at | 索引 `routine_segments_by_day(plan_date, routine_id)`（无"单条在跑"唯一索引，靠应用层 `_close_running_routine`） |
| `routine_challenges` | id(TEXT PK, token), questions_json, expires_at, passed, unlock_token, unlock_expires_at, created_at | |

### 迁移逻辑存在意义（一句话）
- `_ensure_column(...)`（`time_segments.mode/target_seconds/focus_completed`、`memos.source_*` 8 列 + note_title/note_link、`plan_entries.thread_id`）：为已有老库增量补列，使新代码在旧 SQLite 文件上直接升级（initialize 每次启动都跑，幂等）。
- `one_thread_step_per_day` 唯一索引（部分索引 `WHERE thread_id IS NOT NULL`）：老库补建，保证同一天同一主线只有一条步骤。
- `_ensure_image_ids`：老库 `note_images` 没有 AUTOINCREMENT，重命名重建表补齐（新库建表语句已含 AUTOINCREMENT）。
- `_merge_daily_notes`：一次性迁移（`app_settings.daily_notes_merged` 标记防重跑）——把 `days.reflection` 与 owner_type='day' 的图片并入 memos（每日感悟合并为一条 memo，图片改挂 memo），迁移后 days.reflection 清空；新装库会直接跑一遍（空数据无影响）。测试直接调它验证幂等。
- `PRAGMA journal_mode=WAL`：并发读写性能。
