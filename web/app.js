"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const STORAGE = {
  view: "daily-plan:view",
  date: "daily-plan:selected-date",
  timer: "daily-plan:timer-checkpoint",
  reportPeriod: "daily-plan:report-period",
  focusMinutes: "daily-plan:focus-minutes",
  breakMinutes: "daily-plan:break-minutes",
  breakUntil: "daily-plan:break-until",
};

const storedView = safeStorageGet(STORAGE.view);
const state = {
  view: storedView === "week" ? "report" : storedView || "today",
  date: safeStorageGet(STORAGE.date) || localDateString(new Date()),
  reportPeriod: safeStorageGet(STORAGE.reportPeriod) || "week",
  day: null,
  report: null,
  memos: [],
  todayMemos: [],
  activeTimer: null,
  syncedAt: Date.now(),
  parentEntry: null,
  editingEntry: null,
  editingSegment: null,
  editingMemo: null,
  focusEntry: null,
  mood: null,
  closeMood: null,
  saveTimer: null,
  memoSearchTimer: null,
  toastTimer: null,
  loadSequence: 0,
  finishingFocus: false,
  breakUntil: Number(safeStorageGet(STORAGE.breakUntil) || 0),
  profile: {
    display_name: "",
    avatar_data: "",
    focus_minutes: 25,
    break_minutes: 5,
  },
  routines: [],
  routineUnlock: "",
  challenge: null,
};

const outcomeLabels = {
  carried: "已顺延",
  rescheduled: "已改期",
  abandoned: "已放弃",
};

function safeStorageGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeStorageSet(key, value) {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // SQLite 是业务数据的唯一权威来源，本地偏好失败不影响记录。
  }
}

function safeStorageRemove(key) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // 同上。
  }
}

function localDateString(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDate(value) {
  return new Date(`${value}T00:00:00`);
}

function shiftDate(value, days) {
  const next = parseLocalDate(value);
  next.setDate(next.getDate() + days);
  return localDateString(next);
}

function shiftPeriod(value, period, direction) {
  const next = parseLocalDate(value);
  if (period === "week") next.setDate(next.getDate() + direction * 7);
  if (period === "month") next.setMonth(next.getMonth() + direction);
  if (period === "quarter") next.setMonth(next.getMonth() + direction * 3);
  return localDateString(next);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatMinutes(minutes) {
  const rounded = Math.max(0, Math.round(Number(minutes) || 0));
  if (rounded < 60) return `${rounded} 分钟`;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return rest ? `${hours} 小时 ${rest} 分` : `${hours} 小时`;
}

function formatHours(minutes) {
  const number = Math.max(0, Number(minutes) || 0);
  if (number === 0) return "0 小时";
  const hours = number / 60;
  return `${hours >= 10 ? hours.toFixed(1) : hours.toFixed(2).replace(/0$/, "")} 小时`;
}

function formatClock(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = String(Math.floor(total / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const rest = String(total % 60).padStart(2, "0");
  return `${hours}:${minutes}:${rest}`;
}

function formatShortClock(value) {
  if (!value) return "进行中";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatMemoDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(parseLocalDate(value));
}

function splitTags(value) {
  return String(value || "")
    .split(/[,，\s]+/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function liveSeconds(entry) {
  const base = Number(entry.actual_seconds) || 0;
  if (!entry.is_running) return base;
  return base + Math.max(0, Math.floor((Date.now() - state.syncedAt) / 1000));
}

function aggregateSeconds(entry) {
  if (!state.day) return liveSeconds(entry);
  const children = state.day.entries.filter(
    (candidate) => candidate.parent_id === entry.task_id,
  );
  return (
    liveSeconds(entry) +
    children.reduce((sum, child) => sum + aggregateSeconds(child), 0)
  );
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("没有收到有效响应，请确认每日计划仍在运行");
  }
  if (!response.ok) {
    throw new Error(data.error || "操作没有完成，请稍后再试");
  }
  return data;
}

function notify(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("is-error", isError);
  toast.hidden = false;
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, isError ? 5000 : 2800);
}

function reportError(error) {
  notify(error instanceof Error ? error.message : "操作没有完成，请稍后再试", true);
}

function setBusy(button, busy, text = "处理中…") {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = text;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

function switchView(view) {
  state.view = ["today", "report", "memos", "settings"].includes(view)
    ? view
    : "today";
  safeStorageSet(STORAGE.view, state.view);
  $("#todayView").hidden = state.view !== "today";
  $("#reportView").hidden = state.view !== "report";
  $("#memosView").hidden = state.view !== "memos";
  $("#settingsView").hidden = state.view !== "settings";
  $$(".nav-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === state.view);
  });
  if (state.view === "today") loadDay();
  if (state.view === "report") loadReport();
  if (state.view === "memos") {
    $("#memoDate").value = localDateString(new Date());
    loadMemos();
    refreshGlobalTimer();
  }
  if (state.view === "settings") loadSettings();
}

async function refreshGlobalTimer() {
  try {
    const data = await api(`/api/day?date=${encodeURIComponent(state.date)}`);
    state.activeTimer = data.active_timer;
    renderRunningBar();
  } catch (error) {
    reportError(error);
  }
}

async function loadDay() {
  const sequence = ++state.loadSequence;
  $("#dayPicker").value = state.date;
  safeStorageSet(STORAGE.date, state.date);
  try {
    const [data, memos] = await Promise.all([
      api(`/api/day?date=${encodeURIComponent(state.date)}`),
      api(`/api/memos?date=${encodeURIComponent(state.date)}&limit=5`),
    ]);
    if (sequence !== state.loadSequence || state.view !== "today") return;
    state.day = data;
    state.activeTimer = data.active_timer;
    state.todayMemos = memos;
    state.mood = data.day.mood;
    state.syncedAt = Date.now();
    renderDay();
  } catch (error) {
    reportError(error);
  }
}

function renderDay() {
  if (!state.day) return;
  const today = localDateString(new Date());
  const current = parseLocalDate(state.date);
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  });
  $("#dateTitle").textContent =
    state.date === today ? "今日计划" : formatter.format(current);
  $("#dateEyebrow").textContent =
    state.date === today
      ? "今天"
      : state.date === shiftDate(today, -1)
        ? "昨天"
        : state.date === shiftDate(today, 1)
          ? "明天"
          : `${current.getFullYear()} 年`;
  $("#backToday").hidden = state.date === today;
  $("#focusInput").value = state.day.day.focus || "";
  $("#reflectionInput").value = state.day.day.reflection || "";
  updateMoodButtons();
  renderProjectOptions();
  renderTasks();
  renderTodayRoutines();
  renderSummary();
  renderWorklog();
  renderTodayMemos();
  renderRunningBar();

  const closed = Boolean(state.day.day.closed_at);
  $("#closedDayNote").hidden = !closed;
  $("#openCloseDay").textContent = closed ? "重新查看并收工" : "开始收工复盘";
  $("#daySaveStatus").textContent = "";
}

function renderProjectOptions() {
  $("#projectOptions").innerHTML = (state.day.projects || [])
    .map((project) => `<option value="${escapeHtml(project.name)}"></option>`)
    .join("");
}

function entriesInTreeOrder(entries) {
  const byTask = new Map(entries.map((entry) => [entry.task_id, entry]));
  const children = new Map();
  entries.forEach((entry) => {
    const parentKey = byTask.has(entry.parent_id) ? entry.parent_id : null;
    if (!children.has(parentKey)) children.set(parentKey, []);
    children.get(parentKey).push(entry);
  });
  const result = [];
  const visit = (parentKey, depth) => {
    (children.get(parentKey) || []).forEach((entry) => {
      result.push({ entry, depth: Math.min(depth, 3) });
      visit(entry.task_id, depth + 1);
    });
  };
  visit(null, 0);
  return result;
}

function renderTasks() {
  const list = $("#taskList");
  const empty = $("#emptyTasks");
  const entries = state.day.entries || [];
  empty.hidden = entries.length > 0;
  list.hidden = entries.length === 0;
  if (!entries.length) {
    list.innerHTML = "";
    return;
  }

  list.innerHTML = entriesInTreeOrder(entries)
    .map(({ entry, depth }) => {
      const completed = entry.outcome === "completed";
      const finished = entry.outcome !== "planned";
      const actual = aggregateSeconds(entry);
      const over =
        entry.estimate_minutes > 0 && actual / 60 > entry.estimate_minutes;
      const statusBadge =
        outcomeLabels[entry.outcome] && !completed
          ? `<span class="outcome-badge">${outcomeLabels[entry.outcome]}</span>`
          : "";
      const project = entry.project_name
        ? `<span class="project-tag">${escapeHtml(entry.project_name)}</span>`
        : "";
      let timerButtons = "";
      if (!finished && entry.is_running) {
        timerButtons = `<button class="task-action timer is-running"
          data-action="stop" data-entry-id="${entry.id}">■ 结束计时</button>`;
      } else if (!finished) {
        timerButtons = `
          <button class="task-action timer" data-action="start"
            data-entry-id="${entry.id}">▶ 开始</button>
          <button class="task-action focus" data-action="focus"
            data-entry-id="${entry.id}">◎ 专注</button>
        `;
      }
      const containerHint = entry.has_children
        ? "<span>含子任务</span>"
        : `<span>预估 <strong>${formatMinutes(entry.estimate_minutes)}</strong></span>`;
      return `
        <article class="task-row ${completed ? "is-completed" : ""} ${finished ? "is-finished" : ""}"
          data-entry-id="${entry.id}" data-depth="${depth}" style="--depth:${depth}">
          <button class="task-check" data-action="toggle-complete"
            data-entry-id="${entry.id}" ${finished && !completed ? "disabled" : ""}
            aria-label="${completed ? "重新打开" : "标为完成"}">✓</button>
          <div class="task-main">
            <div class="task-title-line">
              ${project}
              <h3 class="task-title">${escapeHtml(entry.title)}</h3>
              ${statusBadge}
            </div>
            <div class="task-meta">
              ${entry.planned_start ? `<span>${escapeHtml(entry.planned_start)} 开始</span>` : ""}
              ${containerHint}
              <span class="${over ? "over-estimate" : ""}">
                实际 <strong class="actual-time" data-entry-id="${entry.id}">${formatMinutes(actual / 60)}</strong>
              </span>
            </div>
          </div>
          <div class="task-actions">
            ${timerButtons}
            ${
              !finished
                ? `<button class="task-action" data-action="subtask"
                     data-entry-id="${entry.id}">＋ 子任务</button>`
                : ""
            }
            <button class="task-action task-more" data-action="edit"
              data-entry-id="${entry.id}" aria-label="编辑任务">···</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function leafEntries(entries) {
  return entries.filter((entry) => !entry.has_children);
}

function renderSummary() {
  if (!state.day) return;
  const allEntries = state.day.entries || [];
  const entries = leafEntries(allEntries);
  const planned = entries.reduce(
    (sum, entry) => sum + Number(entry.estimate_minutes || 0),
    0,
  );
  const actualSeconds = allEntries.reduce(
    (sum, entry) => sum + liveSeconds(entry),
    0,
  );
  const completed = entries.filter(
    (entry) => entry.outcome === "completed",
  ).length;
  const rate = entries.length ? Math.round((completed / entries.length) * 100) : 0;
  const variance = Math.round(actualSeconds / 60 - planned);

  $("#plannedTotal").textContent = formatMinutes(planned);
  $("#plannedTaskCount").textContent = entries.length
    ? `${entries.length} 条可执行任务`
    : "还没有任务";
  $("#actualTotal").textContent = formatMinutes(actualSeconds / 60);
  $("#completionTotal").textContent = `${completed} / ${entries.length}`;
  $("#completionBar").style.width = `${rate}%`;
  $("#varianceTotal").textContent =
    actualSeconds === 0 && planned === 0
      ? "—"
      : variance === 0
        ? "刚好"
        : `${variance > 0 ? "+" : "−"}${formatMinutes(Math.abs(variance))}`;
  $("#varianceHint").textContent =
    variance > 0
      ? "实际高于预估"
      : variance < 0
        ? "实际低于预估"
        : "计划与实际一致";

  const capacity = $("#capacityHint");
  capacity.classList.toggle("is-heavy", planned > 480);
  capacity.textContent =
    planned > 480
      ? `计划 ${formatHours(planned)}，负荷偏高`
      : planned
        ? `计划负荷 ${formatHours(planned)}`
        : "";
}

function renderWorklog() {
  const segments = state.day?.segments || [];
  const container = $("#worklogList");
  const total = segments.reduce((sum, segment) => {
    if (segment.end_at) return sum + Number(segment.duration_seconds || 0);
    return sum + Math.max(0, (Date.now() - new Date(segment.start_at).getTime()) / 1000);
  }, 0);
  $("#worklogTotal").textContent = formatMinutes(total / 60);
  if (!segments.length) {
    container.innerHTML =
      '<div class="empty-inline">开始一次计时后，这里会按时间段留下工作日志</div>';
    return;
  }
  container.innerHTML = segments
    .map((segment) => {
      const running = !segment.end_at;
      const duration = running
        ? Math.max(0, (Date.now() - new Date(segment.start_at).getTime()) / 1000)
        : Number(segment.duration_seconds || 0);
      const focus = segment.mode === "focus";
      return `
        <article class="worklog-row" data-segment-id="${segment.id}">
          <span class="worklog-icon ${focus ? "is-focus" : ""}">${focus ? "◎" : "▶"}</span>
          <div class="worklog-main">
            <strong>${escapeHtml(segment.title)}</strong>
            <span>${escapeHtml(segment.project_name)} · ${focus ? (segment.focus_completed ? "完整专注" : "专注段") : "自由计时"}</span>
          </div>
          <div>
            <strong class="worklog-duration">${formatMinutes(duration / 60)}</strong>
            <span class="worklog-clock">${formatShortClock(segment.start_at)}–${formatShortClock(segment.end_at)}</span>
          </div>
          ${
            running
              ? ""
              : `<button class="worklog-edit" data-action="edit-segment"
                    data-segment-id="${segment.id}" aria-label="修正工作记录">···</button>`
          }
        </article>
      `;
    })
    .join("");
}

function renderTodayMemos() {
  const container = $("#todayMemoList");
  if (!state.todayMemos.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = state.todayMemos
    .slice(0, 3)
    .map(
      (memo) =>
        `<div class="today-memo-item">${escapeHtml(memo.content)}</div>`,
    )
    .join("");
}

function renderRunningBar() {
  const active = state.activeTimer;
  const bar = $("#runningBar");
  bar.hidden = !active;
  if (!active) {
    safeStorageRemove(STORAGE.timer);
    return;
  }
  const elapsed = Math.max(
    0,
    (Date.now() - new Date(active.start_at).getTime()) / 1000,
  );
  const isFocus = active.mode === "focus" && active.target_seconds;
  $("#runningTitle").textContent = active.title;
  $("#runningModeLabel").textContent = isFocus ? "专注倒计时" : "正在计时";
  $("#runningTime").textContent = isFocus
    ? formatClock(Math.max(0, Number(active.target_seconds) - elapsed))
    : formatClock(elapsed);
  $("#runningProgress").hidden = !isFocus;
  if (isFocus) {
    $("#runningProgress i").style.width =
      `${Math.min(100, (elapsed / Number(active.target_seconds)) * 100)}%`;
  }
  safeStorageSet(
    STORAGE.timer,
    JSON.stringify({
      entryId: active.plan_entry_id,
      title: active.title,
      startedAt: active.start_at,
      date: active.plan_date,
      mode: active.mode,
      targetSeconds: active.target_seconds,
    }),
  );
}

function updateLiveTimers() {
  const active = state.activeTimer;
  if (active) {
    const elapsed = Math.max(
      0,
      (Date.now() - new Date(active.start_at).getTime()) / 1000,
    );
    if (active.mode === "focus" && active.target_seconds) {
      const remaining = Number(active.target_seconds) - elapsed;
      $("#runningTime").textContent = formatClock(Math.max(0, remaining));
      $("#runningProgress i").style.width =
        `${Math.min(100, (elapsed / Number(active.target_seconds)) * 100)}%`;
      if (remaining <= 0 && !state.finishingFocus) finishFocusTimer();
    } else {
      $("#runningTime").textContent = formatClock(elapsed);
    }
  }
  if (state.view === "today" && state.day) {
    $$(".actual-time").forEach((timeElement) => {
      const entry = state.day.entries.find(
        (item) => item.id === Number(timeElement.dataset.entryId),
      );
      if (entry) {
        timeElement.textContent = formatMinutes(aggregateSeconds(entry) / 60);
      }
    });
    renderSummary();
    if (state.day.segments?.some((segment) => !segment.end_at)) renderWorklog();
  }
  updateBreakTimer();
}

function showAddTask(parentEntry = null) {
  state.parentEntry = parentEntry;
  $("#addTaskForm").hidden = false;
  $("#toggleAddTask").hidden = true;
  $("#subtaskContext").hidden = !parentEntry;
  $("#parentTaskName").textContent = parentEntry?.title || "";
  if (parentEntry?.project_name) {
    $("#newTaskProject").value = parentEntry.project_name;
  }
  window.setTimeout(() => $("#newTaskTitle").focus(), 0);
}

function hideAddTask() {
  state.parentEntry = null;
  $("#addTaskForm").reset();
  $("#newTaskEstimate").value = "60";
  $("#subtaskContext").hidden = true;
  $("#addTaskForm").hidden = true;
  $("#toggleAddTask").hidden = false;
}

async function createTask(event) {
  event.preventDefault();
  const button = event.submitter;
  setBusy(button, true, "添加中…");
  try {
    await api("/api/entries", {
      method: "POST",
      body: JSON.stringify({
        date: state.date,
        title: $("#newTaskTitle").value,
        project_name: $("#newTaskProject").value,
        estimate_minutes: $("#newTaskEstimate").value,
        planned_start: $("#newTaskStart").value,
        parent_entry_id: state.parentEntry?.id || null,
      }),
    });
    hideAddTask();
    await loadDay();
    notify("任务已加入今天");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function startTimer(
  entryId,
  button,
  mode = "open",
  focusMinutes = 25,
) {
  setBusy(button, true, mode === "focus" ? "准备专注…" : "启动中…");
  try {
    stopBreak();
    const result = await api("/api/timer/start", {
      method: "POST",
      body: JSON.stringify({
        entry_id: entryId,
        mode,
        focus_minutes: focusMinutes,
      }),
    });
    if (state.view === "today") await loadDay();
    else await refreshGlobalTimer();
    notify(
      result.stopped_entry_id
        ? "已结束上一条任务，并开始新的计时"
        : mode === "focus"
          ? `开始 ${focusMinutes} 分钟专注`
          : "已经开始计时",
    );
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function stopTimer(
  entryId = null,
  button = null,
  targetReached = false,
) {
  setBusy(button, true, "结束中…");
  try {
    const result = await api("/api/timer/stop", {
      method: "POST",
      body: JSON.stringify({
        entry_id: entryId,
        target_reached: targetReached,
      }),
    });
    state.activeTimer = null;
    safeStorageRemove(STORAGE.timer);
    renderRunningBar();
    if (result.focus_completed) {
      const breakMinutes = Number(
        safeStorageGet(STORAGE.breakMinutes) || $("#breakMinutes").value || 5,
      );
      startBreak(breakMinutes);
      playTone();
    }
    if (state.view === "today") await loadDay();
    if (state.view === "report") await loadReport();
    if (state.view === "memos") await refreshGlobalTimer();
    notify(
      result.stopped
        ? result.focus_completed
          ? `完整专注 ${formatMinutes(result.duration_seconds / 60)}，现在休息一下`
          : `本次有效工作 ${formatMinutes(result.duration_seconds / 60)}`
        : "当前没有正在计时的任务",
    );
    return result;
  } catch (error) {
    reportError(error);
    return null;
  } finally {
    setBusy(button, false);
  }
}

async function finishFocusTimer() {
  if (state.finishingFocus || !state.activeTimer) return;
  state.finishingFocus = true;
  try {
    await stopTimer(state.activeTimer.plan_entry_id, null, true);
  } finally {
    state.finishingFocus = false;
  }
}

function openFocusDialog(entryId) {
  const entry = state.day.entries.find((item) => item.id === entryId);
  if (!entry) return;
  state.focusEntry = entry;
  const focusMinutes = Number(safeStorageGet(STORAGE.focusMinutes) || 25);
  const breakMinutes = Number(safeStorageGet(STORAGE.breakMinutes) || 5);
  $("#focusTaskName").textContent = entry.title;
  $("#focusMinutes").value = focusMinutes;
  $("#breakMinutes").value = breakMinutes;
  updateFocusPresets(focusMinutes);
  $("#focusDialog").showModal();
}

function updateFocusPresets(minutes) {
  $$("[data-focus-minutes]").forEach((button) => {
    button.classList.toggle(
      "is-active",
      Number(button.dataset.focusMinutes) === Number(minutes),
    );
  });
}

async function submitFocus(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    $("#focusDialog").close();
    return;
  }
  if (!state.focusEntry) return;
  const focusMinutes = Number($("#focusMinutes").value);
  const breakMinutes = Number($("#breakMinutes").value);
  safeStorageSet(STORAGE.focusMinutes, focusMinutes);
  safeStorageSet(STORAGE.breakMinutes, breakMinutes);
  $("#focusDialog").close();
  await startTimer(
    state.focusEntry.id,
    $("#startFocusButton"),
    "focus",
    focusMinutes,
  );
}

function startBreak(minutes) {
  state.breakUntil = Date.now() + Math.max(1, Number(minutes)) * 60_000;
  safeStorageSet(STORAGE.breakUntil, state.breakUntil);
  renderBreakBar();
}

function stopBreak() {
  state.breakUntil = 0;
  safeStorageRemove(STORAGE.breakUntil);
  renderBreakBar();
}

function renderBreakBar() {
  const remaining = state.breakUntil - Date.now();
  $("#breakBar").hidden = remaining <= 0;
  if (remaining > 0) $("#breakTime").textContent = formatClock(remaining / 1000);
}

function updateBreakTimer() {
  if (!state.breakUntil) return;
  const remaining = state.breakUntil - Date.now();
  if (remaining <= 0) {
    stopBreak();
    playTone();
    notify("休息结束，可以开始下一段工作");
  } else {
    $("#breakTime").textContent = formatClock(remaining / 1000);
  }
}

function playTone() {
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 660;
    gain.gain.setValueAtTime(0.08, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.5);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.5);
  } catch {
    // 声音不可用时，页面提示仍会出现。
  }
}

async function toggleComplete(entryId, button) {
  const entry = state.day.entries.find((item) => item.id === entryId);
  if (!entry) return;
  setBusy(button, true, "…");
  try {
    await api(`/api/entries/${entryId}`, {
      method: "PATCH",
      body: JSON.stringify({
        outcome: entry.outcome === "completed" ? "planned" : "completed",
      }),
    });
    await loadDay();
    notify(entry.outcome === "completed" ? "任务已重新打开" : "任务已完成");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

function openEditDialog(entryId) {
  const entry = state.day.entries.find((item) => item.id === entryId);
  if (!entry) return;
  state.editingEntry = entry;
  $("#editTitle").value = entry.title;
  $("#editProject").value = entry.project_name || "";
  $("#editEstimate").value = entry.estimate_minutes;
  $("#editStart").value = entry.planned_start || "";
  $("#editDefinition").value = entry.definition || "";
  $("#editDialog").showModal();
}

async function saveTaskEdit(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    $("#editDialog").close();
    return;
  }
  if (!state.editingEntry) return;
  const button = $("#saveTaskEdit");
  setBusy(button, true, "保存中…");
  try {
    await api(`/api/entries/${state.editingEntry.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: $("#editTitle").value,
        project_name: $("#editProject").value,
        estimate_minutes: $("#editEstimate").value,
        planned_start: $("#editStart").value,
        definition: $("#editDefinition").value,
      }),
    });
    $("#editDialog").close();
    await loadDay();
    notify("任务已更新");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function deleteTask() {
  if (!state.editingEntry) return;
  if (!window.confirm(`确定删除“${state.editingEntry.title}”吗？`)) return;
  const button = $("#deleteTask");
  setBusy(button, true, "删除中…");
  try {
    await api(`/api/entries/${state.editingEntry.id}`, { method: "DELETE" });
    $("#editDialog").close();
    await loadDay();
    notify("任务已删除");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

function openSegmentDialog(segmentId) {
  const segment = state.day.segments.find((item) => item.id === segmentId);
  if (!segment || !segment.end_at) return;
  state.editingSegment = segment;
  $("#segmentTaskName").textContent =
    `${segment.title} · ${formatShortClock(segment.start_at)}–${formatShortClock(segment.end_at)}`;
  $("#segmentDuration").value = Math.max(
    1,
    Math.round(Number(segment.duration_seconds || 0) / 60),
  );
  $("#segmentDialog").showModal();
}

async function saveSegmentEdit(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    $("#segmentDialog").close();
    return;
  }
  if (!state.editingSegment) return;
  const button = $("#saveSegment");
  setBusy(button, true, "保存中…");
  try {
    await api(`/api/segments/${state.editingSegment.id}`, {
      method: "PATCH",
      body: JSON.stringify({ duration_minutes: $("#segmentDuration").value }),
    });
    $("#segmentDialog").close();
    await loadDay();
    notify("工作记录已修正");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function deleteSegment() {
  if (!state.editingSegment) return;
  if (!window.confirm("确定删除这段工作记录吗？")) return;
  const button = $("#deleteSegment");
  setBusy(button, true, "删除中…");
  try {
    await api(`/api/segments/${state.editingSegment.id}`, {
      method: "DELETE",
    });
    $("#segmentDialog").close();
    await loadDay();
    notify("工作记录已删除");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

function scheduleDaySave() {
  const snapshot = {
    date: state.date,
    focus: $("#focusInput").value,
    reflection: $("#reflectionInput").value,
    mood: state.mood,
  };
  $("#daySaveStatus").textContent = "等待保存…";
  window.clearTimeout(state.saveTimer);
  state.saveTimer = window.setTimeout(async () => {
    try {
      await api("/api/day/save", {
        method: "POST",
        body: JSON.stringify(snapshot),
      });
      if (state.date === snapshot.date) {
        $("#daySaveStatus").textContent = "已保存";
        window.setTimeout(() => {
          if ($("#daySaveStatus").textContent === "已保存") {
            $("#daySaveStatus").textContent = "";
          }
        }, 1500);
      }
    } catch (error) {
      reportError(error);
      if (state.date === snapshot.date) $("#daySaveStatus").textContent = "保存失败";
    }
  }, 550);
}

function updateMoodButtons() {
  $$("[data-mood]").forEach((button) => {
    button.classList.toggle("is-active", Number(button.dataset.mood) === state.mood);
  });
}

function openCloseDay() {
  if (!state.day) return;
  $("#closeReflection").value = $("#reflectionInput").value;
  state.closeMood = state.mood;
  renderCloseMood();
  renderCloseTasks();
  $("#closeDayDialog").showModal();
}

function renderCloseMood() {
  $$("[data-close-mood]").forEach((button) => {
    button.classList.toggle(
      "is-active",
      Number(button.dataset.closeMood) === state.closeMood,
    );
  });
}

function renderCloseTasks() {
  const pending = state.day.entries.filter(
    (entry) => entry.outcome === "planned" && !entry.has_children,
  );
  const container = $("#closeDayTasks");
  if (!pending.length) {
    container.innerHTML =
      '<div class="empty-inline">今天的任务已经全部处理，可以直接写下感悟并收工。</div>';
    return;
  }
  const reasonOptions = state.day.reasons
    .map(
      (reason) =>
        `<option value="${escapeHtml(reason.value)}">${escapeHtml(reason.label)}</option>`,
    )
    .join("");
  const tomorrow = shiftDate(state.date, 1);
  container.innerHTML = pending
    .map(
      (entry) => `
        <article class="close-task" data-close-entry="${entry.id}">
          <strong>${escapeHtml(entry.title)}</strong>
          <div class="close-task-grid">
            <label>
              <span>这条任务怎么处理</span>
              <select data-field="action" required>
                <option value="">请选择去向</option>
                <option value="completed">其实已经完成</option>
                <option value="carry">明天继续</option>
                <option value="reschedule">改到其他日期</option>
                <option value="abandoned">放弃，不再做</option>
              </select>
            </label>
            <div class="close-task-details" data-details hidden>
              <label>
                <span>没完成的主要原因</span>
                <select data-field="reason">
                  <option value="">请选择原因</option>
                  ${reasonOptions}
                </select>
              </label>
              <label data-target-wrap hidden>
                <span>改到哪一天</span>
                <input data-field="target-date" type="date" min="${tomorrow}" value="${tomorrow}" />
              </label>
              <label data-estimate-wrap>
                <span>下次预估分钟</span>
                <input data-field="next-estimate" type="number" min="0" max="1440"
                  step="5" value="${Number(entry.estimate_minutes) || 0}" />
              </label>
              <label class="note-field">
                <span>补充一句（可选）</span>
                <input data-field="note" type="text" maxlength="1000"
                  placeholder="下次怎么避免，或卡在哪里？" />
              </label>
            </div>
          </div>
        </article>
      `,
    )
    .join("");
}

function updateCloseTaskDetails(select) {
  const card = select.closest("[data-close-entry]");
  const details = $("[data-details]", card);
  const target = $("[data-target-wrap]", card);
  const estimate = $("[data-estimate-wrap]", card);
  const action = select.value;
  details.hidden = !action || action === "completed";
  target.hidden = action !== "reschedule";
  estimate.hidden = !["carry", "reschedule"].includes(action);
}

async function submitCloseDay(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    $("#closeDayDialog").close();
    return;
  }
  const decisions = [];
  for (const card of $$("[data-close-entry]", $("#closeDayTasks"))) {
    const action = $('[data-field="action"]', card).value;
    if (!action) {
      notify("请为每一条任务选择去向", true);
      $('[data-field="action"]', card).focus();
      return;
    }
    const incomplete = action !== "completed";
    const reason = $('[data-field="reason"]', card)?.value || null;
    if (incomplete && !reason) {
      notify("未完成的任务需要选择主要原因", true);
      $('[data-field="reason"]', card).focus();
      return;
    }
    const targetDate =
      action === "carry"
        ? shiftDate(state.date, 1)
        : $('[data-field="target-date"]', card)?.value || null;
    decisions.push({
      entry_id: Number(card.dataset.closeEntry),
      action,
      reason,
      note: $('[data-field="note"]', card)?.value || "",
      target_date: targetDate,
      next_estimate_minutes:
        $('[data-field="next-estimate"]', card)?.value || 0,
    });
  }

  const button = $("#submitCloseDay");
  setBusy(button, true, "正在收工…");
  try {
    const data = await api("/api/day/close", {
      method: "POST",
      body: JSON.stringify({
        date: state.date,
        focus: $("#focusInput").value,
        reflection: $("#closeReflection").value,
        mood: state.closeMood,
        decisions,
      }),
    });
    state.day = data;
    state.activeTimer = data.active_timer;
    state.mood = data.day.mood;
    state.syncedAt = Date.now();
    $("#closeDayDialog").close();
    renderDay();
    notify("今天已经收好，记录会进入复盘报告");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function createMemo(payload, button) {
  setBusy(button, true, "保存中…");
  try {
    await api("/api/memos", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    notify("碎片感悟已保存");
    return true;
  } catch (error) {
    reportError(error);
    return false;
  } finally {
    setBusy(button, false);
  }
}

async function submitQuickMemo(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const success = await createMemo(
    {
      date: state.date,
      content: $("#quickMemoContent").value,
      tags: $("#quickMemoTags").value,
    },
    event.submitter,
  );
  if (success) {
    form.reset();
    state.todayMemos = await api(
      `/api/memos?date=${encodeURIComponent(state.date)}&limit=5`,
    );
    renderTodayMemos();
  }
}

async function submitMemoCompose(event) {
  event.preventDefault();
  const success = await createMemo(
    {
      date: $("#memoDate").value,
      content: $("#memoContent").value,
      tags: $("#memoTags").value,
    },
    event.submitter,
  );
  if (success) {
    $("#memoContent").value = "";
    $("#memoTags").value = "";
    await loadMemos();
  }
}

async function loadMemos() {
  const query = $("#memoSearchInput")?.value.trim() || "";
  try {
    state.memos = await api(
      `/api/memos?query=${encodeURIComponent(query)}&limit=200`,
    );
    renderMemos(query);
  } catch (error) {
    reportError(error);
  }
}

function renderMemos(query = "") {
  $("#memoFilterSummary").textContent = query
    ? `“${query}”找到 ${state.memos.length} 条记录（包含每日感悟）`
    : `共显示 ${state.memos.length} 条碎片感悟`;
  const feed = $("#memoFeed");
  if (!state.memos.length) {
    feed.innerHTML =
      '<div class="panel empty-inline">还没有记录。想到一句就先记一句，不必等完整文章。</div>';
    return;
  }
  feed.innerHTML = state.memos
    .map((memo) => {
      const tags = splitTags(memo.tags);
      const daily = memo.kind === "daily";
      return `
        <article class="memo-card ${memo.pinned ? "is-pinned" : ""}" data-memo-id="${escapeHtml(memo.id)}">
          <div class="memo-card-header">
            <span>${memo.pinned ? "📌 " : ""}${formatMemoDate(memo.memo_date)}${daily ? " · 每日感悟" : ""}</span>
            <div class="memo-card-actions">
              ${
                daily
                  ? `<button data-memo-action="open-day" data-date="${memo.memo_date}">打开当天</button>`
                  : `<button data-memo-action="pin" data-memo-id="${memo.id}">${memo.pinned ? "取消置顶" : "置顶"}</button>
                     <button data-memo-action="edit" data-memo-id="${memo.id}">编辑</button>`
              }
            </div>
          </div>
          <p class="memo-content">${escapeHtml(memo.content)}</p>
          ${
            tags.length
              ? `<div class="memo-tags">${tags.map((tag) => `<span class="memo-tag">#${escapeHtml(tag)}</span>`).join("")}</div>`
              : ""
          }
        </article>
      `;
    })
    .join("");
}

function openMemoEdit(memoId) {
  const memo = state.memos.find((item) => Number(item.id) === Number(memoId));
  if (!memo || memo.kind !== "memo") return;
  state.editingMemo = memo;
  $("#memoEditContent").value = memo.content;
  $("#memoEditDate").value = memo.memo_date;
  $("#memoEditTags").value = memo.tags || "";
  $("#memoEditPinned").checked = Boolean(memo.pinned);
  $("#memoDialog").showModal();
}

async function saveMemoEdit(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    $("#memoDialog").close();
    return;
  }
  if (!state.editingMemo) return;
  const button = $("#saveMemoEdit");
  setBusy(button, true, "保存中…");
  try {
    await api(`/api/memos/${state.editingMemo.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        date: $("#memoEditDate").value,
        content: $("#memoEditContent").value,
        tags: $("#memoEditTags").value,
        pinned: $("#memoEditPinned").checked,
      }),
    });
    $("#memoDialog").close();
    await loadMemos();
    notify("感悟已更新");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function toggleMemoPin(memoId) {
  const memo = state.memos.find((item) => Number(item.id) === Number(memoId));
  if (!memo) return;
  try {
    await api(`/api/memos/${memo.id}`, {
      method: "PATCH",
      body: JSON.stringify({ pinned: !memo.pinned }),
    });
    await loadMemos();
  } catch (error) {
    reportError(error);
  }
}

async function deleteMemo() {
  if (!state.editingMemo) return;
  if (!window.confirm("确定删除这条感悟吗？")) return;
  const button = $("#deleteMemo");
  setBusy(button, true, "删除中…");
  try {
    await api(`/api/memos/${state.editingMemo.id}`, { method: "DELETE" });
    $("#memoDialog").close();
    await loadMemos();
    notify("感悟已删除");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function loadReport() {
  const sequence = ++state.loadSequence;
  safeStorageSet(STORAGE.reportPeriod, state.reportPeriod);
  try {
    const data = await api(
      `/api/report?date=${encodeURIComponent(state.date)}&period=${encodeURIComponent(state.reportPeriod)}`,
    );
    if (sequence !== state.loadSequence || state.view !== "report") return;
    state.report = data;
    renderReport();
    await refreshGlobalTimer();
  } catch (error) {
    reportError(error);
  }
}

function reportTitle() {
  const start = parseLocalDate(state.report.start);
  const end = parseLocalDate(state.report.end);
  if (state.reportPeriod === "month") {
    return `${start.getFullYear()}年${start.getMonth() + 1}月`;
  }
  if (state.reportPeriod === "quarter") {
    return `${start.getFullYear()}年第${Math.floor(start.getMonth() / 3) + 1}季度`;
  }
  const short = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
  });
  return `${short.format(start)} — ${short.format(end)}`;
}

function renderReport() {
  if (!state.report) return;
  $("#weekTitle").textContent = reportTitle();
  $$("[data-period]").forEach((button) => {
    button.classList.toggle(
      "is-active",
      button.dataset.period === state.reportPeriod,
    );
  });
  const periodName = { week: "本周", month: "本月", quarter: "本季度" }[
    state.reportPeriod
  ];
  $("#reportPlannedLabel").textContent = `${periodName}计划`;
  $("#reviewHeading").textContent = `${periodName}结论`;
  $("#weekReviewInput").placeholder = {
    week: "哪类任务总是低估？下周减少什么、继续什么、调整什么？",
    month: "这个月有哪些反复出现的规律？下个月停止什么、延续什么？",
    quarter: "这个季度的时间投向是否正确？下季度最重要的调整是什么？",
  }[state.reportPeriod];

  const planned = state.report.days.reduce(
    (sum, day) => sum + Number(day.estimate_minutes || 0),
    0,
  );
  const actualSeconds = state.report.days.reduce(
    (sum, day) => sum + Number(day.actual_seconds || 0),
    0,
  );
  const completed = state.report.days.reduce(
    (sum, day) => sum + Number(day.completed_count || 0),
    0,
  );
  const total = state.report.days.reduce(
    (sum, day) => sum + Number(day.total_count || 0),
    0,
  );
  const rate = total ? Math.round((completed / total) * 100) : 0;
  const variance = Math.round(actualSeconds / 60 - planned);
  $("#weekPlanned").textContent = formatHours(planned);
  $("#weekActual").textContent = formatHours(actualSeconds / 60);
  $("#weekCompleted").textContent = `${completed} / ${total}`;
  $("#weekCompletionRate").textContent = `完成率 ${rate}%`;
  $("#weekVariance").textContent =
    actualSeconds === 0 && planned === 0
      ? "—"
      : variance === 0
        ? "刚好"
        : `${variance > 0 ? "+" : "−"}${formatMinutes(Math.abs(variance))}`;

  renderReportChart();
  renderHeatmap();
  renderInsights();
  renderReasons();
  renderProjectStats();
  renderCarryovers();
  renderFocusStats();
  renderRoutineBoard();
  $("#weekReviewInput").value = state.report.review || "";
  $("#weekReviewStatus").textContent = "";
}

function reportChartGroups() {
  const days = state.report.days;
  if (state.reportPeriod !== "quarter") {
    return days.map((day) => ({
      label:
        state.reportPeriod === "week"
          ? ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
              parseLocalDate(day.plan_date).getDay() === 0
                ? 6
                : parseLocalDate(day.plan_date).getDay() - 1
            ]
          : String(parseLocalDate(day.plan_date).getDate()),
      date: day.plan_date,
      estimate_minutes: Number(day.estimate_minutes || 0),
      actual_seconds: Number(day.actual_seconds || 0),
    }));
  }
  const groups = [];
  for (let index = 0; index < days.length; index += 7) {
    const chunk = days.slice(index, index + 7);
    groups.push({
      label: `第${Math.floor(index / 7) + 1}周`,
      date: chunk[0].plan_date,
      estimate_minutes: chunk.reduce(
        (sum, day) => sum + Number(day.estimate_minutes || 0),
        0,
      ),
      actual_seconds: chunk.reduce(
        (sum, day) => sum + Number(day.actual_seconds || 0),
        0,
      ),
    });
  }
  return groups;
}

function renderReportChart() {
  const groups = reportChartGroups();
  const maximum = Math.max(
    1,
    ...groups.flatMap((item) => [
      item.estimate_minutes,
      item.actual_seconds / 60,
    ]),
  );
  const chart = $("#weekChart");
  const minimum = state.reportPeriod === "week" ? 70 : 34;
  chart.style.gridTemplateColumns = `repeat(${groups.length}, minmax(${minimum}px, 1fr))`;
  chart.innerHTML = groups
    .map((item) => {
      const planned = item.estimate_minutes;
      const actual = item.actual_seconds / 60;
      const dateValue = parseLocalDate(item.date);
      return `
        <div class="day-column">
          <div class="bar-space" title="计划 ${formatMinutes(planned)}；实际 ${formatMinutes(actual)}">
            <i class="chart-bar planned" style="height:${(planned / maximum) * 170}px"></i>
            <i class="chart-bar actual" style="height:${(actual / maximum) * 170}px"></i>
          </div>
          <div class="day-label">
            <strong>${escapeHtml(item.label)}</strong>
            <span>${dateValue.getMonth() + 1}/${dateValue.getDate()}</span>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderHeatmap() {
  const days = state.report.days;
  const first = parseLocalDate(days[0].plan_date);
  const mondayOffset = first.getDay() === 0 ? 6 : first.getDay() - 1;
  const placeholders = Array.from(
    { length: mondayOffset },
    () => '<span class="heat-cell" style="visibility:hidden"></span>',
  ).join("");
  $("#focusHeatmap").innerHTML =
    placeholders +
    days
      .map((day) => {
        const minutes = Number(day.actual_seconds || 0) / 60;
        const level =
          minutes === 0 ? 0 : minutes <= 30 ? 1 : minutes <= 90 ? 2 : minutes <= 180 ? 3 : 4;
        return `<span class="heat-cell" data-level="${level}"
          title="${day.plan_date} · ${formatMinutes(minutes)}"></span>`;
      })
      .join("");
  $("#streakLabel").textContent =
    `最长连续记录 ${state.report.focus.longest_streak || 0} 天`;
}

function renderInsights() {
  const items = state.report.insights || [];
  $("#insightList").innerHTML = items
    .map(
      (item) => `
        <article class="insight-item" data-tone="${escapeHtml(item.tone)}">
          <strong>${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.body)}</p>
        </article>
      `,
    )
    .join("");
}

function renderReasons() {
  const reasons = state.report.reasons || [];
  if (!reasons.length) {
    $("#reasonList").innerHTML =
      '<div class="empty-inline">本周期还没有未完成原因记录</div>';
    return;
  }
  const maximum = Math.max(...reasons.map((item) => Number(item.count)));
  $("#reasonList").innerHTML = reasons
    .map(
      (item) => `
        <div class="rank-row">
          <div class="rank-heading">
            <span>${escapeHtml(item.label)}</span>
            <strong>${item.count} 次</strong>
          </div>
          <div class="rank-track">
            <span style="width:${(Number(item.count) / maximum) * 100}%"></span>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderProjectStats() {
  const projects = state.report.projects || [];
  if (!projects.length) {
    $("#projectStats").innerHTML =
      '<div class="empty-inline">开始计时后，这里会显示时间投入去向</div>';
    return;
  }
  $("#projectStats").innerHTML = projects
    .map(
      (project) => `
        <div class="project-row">
          <strong>${escapeHtml(project.project_name)}</strong>
          <span class="project-actual">${formatMinutes(Number(project.actual_seconds) / 60)}</span>
          <span>计划 ${formatMinutes(project.estimate_minutes)} · 完成 ${project.completed_count}/${project.total_count}</span>
          <span>实际有效</span>
        </div>
      `,
    )
    .join("");
}

function renderCarryovers() {
  const items = state.report.carryovers || [];
  if (!items.length) {
    $("#carryoverList").innerHTML =
      '<div class="empty-inline">本周期没有连续顺延两次以上的任务</div>';
    return;
  }
  $("#carryoverList").innerHTML = items
    .map(
      (item) => `
        <div class="carryover-item">
          <strong>${escapeHtml(item.title)}</strong>
          <span>已经顺延 ${item.carry_count} 次，最新安排到 ${escapeHtml(item.latest_target_date || "未定")}</span>
        </div>
      `,
    )
    .join("");
}

function renderFocusStats() {
  const focus = state.report.focus || {};
  $("#focusStats").innerHTML = `
    <div class="focus-stat">
      <strong>${focus.completed_count || 0}</strong>
      <span>完整专注段</span>
    </div>
    <div class="focus-stat">
      <strong>${focus.segment_count || 0}</strong>
      <span>全部专注段</span>
    </div>
    <div class="focus-stat">
      <strong>${formatHours(Number(focus.actual_seconds || 0) / 60)}</strong>
      <span>专注有效时间</span>
    </div>
  `;
}

async function saveReportReview() {
  const button = $("#saveWeekReview");
  setBusy(button, true, "保存中…");
  try {
    const result = await api("/api/review", {
      method: "POST",
      body: JSON.stringify({
        period: state.reportPeriod,
        start: state.report.start,
        content: $("#weekReviewInput").value,
      }),
    });
    state.report.review = result.content;
    $("#weekReviewStatus").textContent = "已保存";
    notify("复盘结论已保存");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

function changeDate(days) {
  state.date = shiftDate(state.date, days);
  safeStorageSet(STORAGE.date, state.date);
  if (state.view === "today") loadDay();
  if (state.view === "report") loadReport();
}

function renderAvatar(node, data, initial) {
  node.replaceChildren();
  if (typeof data === "string" && data.startsWith("data:image/")) {
    const image = document.createElement("img");
    image.alt = "";
    image.src = data;
    node.append(image);
    return;
  }
  node.textContent = initial;
}

function renderProfile() {
  const name = state.profile.display_name.trim();
  const initial = (name || "设").slice(0, 1);
  $("#headerName").textContent = name || "设置";
  renderAvatar($("#headerAvatar"), state.profile.avatar_data, initial);
  if ($("#avatarPreview")) {
    renderAvatar($("#avatarPreview"), state.profile.avatar_data, initial);
  }
  if (state.view === "settings") {
    $("#displayNameInput").value = name;
    $("#settingFocusMinutes").value = state.profile.focus_minutes || 25;
    $("#settingBreakMinutes").value = state.profile.break_minutes || 5;
  }
  safeStorageSet(STORAGE.focusMinutes, state.profile.focus_minutes || 25);
  safeStorageSet(STORAGE.breakMinutes, state.profile.break_minutes || 5);
}

async function loadSettings() {
  try {
    const data = await api("/api/settings");
    state.profile = data.profile;
    state.routines = data.routines;
    renderProfile();
    if (state.view === "settings") renderRoutineSettings();
  } catch (error) {
    reportError(error);
  }
}

function renderTodayRoutines() {
  const routines = state.day?.routines || [];
  const container = $("#routineTodayList");
  if (!routines.length) {
    container.innerHTML = `
      <div class="routine-empty">
        还没有每天必做的事。
        <button type="button" data-action="open-settings">去设置里添加</button>
      </div>`;
    return;
  }
  const future = state.date > localDateString(new Date());
  container.innerHTML = routines
    .map((routine) => {
      const done = Boolean(routine.completed);
      return `
        <article class="routine-item ${done ? "is-done" : ""}" style="--routine:${escapeHtml(routine.color)}">
          <button class="routine-check" type="button" data-action="toggle-routine"
            data-routine-id="${routine.id}" data-completed="${done ? "1" : "0"}"
            ${future ? "disabled" : ""}
            aria-label="${done ? "取消今天的打卡" : "完成今天的必做"}">✓</button>
          <div>
            <h3 class="routine-title">${escapeHtml(routine.title)}</h3>
            <div class="routine-meta">
              <span>每日必做</span>
              ${routine.note ? `<span>${escapeHtml(routine.note)}</span>` : ""}
              ${routine.estimate_minutes ? `<span>${formatMinutes(routine.estimate_minutes)}</span>` : ""}
              <span>${future ? "还没到这一天" : "首页不能修改"}</span>
            </div>
          </div>
        </article>`;
    })
    .join("");
}

async function toggleRoutine(routineId, completed) {
  try {
    const result = await api("/api/routines/check", {
      method: "POST",
      body: JSON.stringify({
        routine_id: routineId,
        date: state.date,
        completed,
      }),
    });
    if (state.day) state.day.routines = result.routines;
    renderTodayRoutines();
    notify(completed ? "今日必做已打卡" : "已取消今天的打卡");
  } catch (error) {
    reportError(error);
  }
}

function renderRoutineSettings() {
  const locked = state.routines.length > 0 && !state.routineUnlock;
  $("#unlockRoutines").hidden = !locked;
  $("#routineCreateForm").hidden = false;
  $("#routineUnlockNote").hidden = !state.routineUnlock;
  const list = $("#routineSettingsList");
  if (!state.routines.length) {
    list.innerHTML =
      '<div class="routine-empty">例如：每天锻炼 5 分钟，每天看飞书里的 5 篇生财有术文章。已经生效的项目，改掉或删除前要先答对 3 道题。</div>';
    return;
  }
  list.innerHTML = state.routines
    .map((routine) =>
      locked
        ? `
          <article class="routine-setting-card">
            <strong class="routine-title">${escapeHtml(routine.title)}</strong>
            <div class="routine-meta">
              ${routine.note ? `<span>${escapeHtml(routine.note)}</span>` : ""}
              <span>${routine.estimate_minutes ? formatMinutes(routine.estimate_minutes) : "不计入预估"}</span>
              <span>已锁定</span>
            </div>
          </article>`
        : `
          <article class="routine-setting-card" data-routine-id="${routine.id}">
            <label>
              <span>必做事项</span>
              <input data-field="title" type="text" maxlength="80" value="${escapeHtml(routine.title)}" />
            </label>
            <div class="field-row">
              <label>
                <span>补充说明</span>
                <input data-field="note" type="text" maxlength="200" value="${escapeHtml(routine.note || "")}" />
              </label>
              <label>
                <span>预估分钟</span>
                <input data-field="estimate" type="number" min="0" max="240" step="5"
                  value="${Number(routine.estimate_minutes) || 0}" />
              </label>
            </div>
            <div class="form-actions">
              <button type="button" class="button danger-text" data-routine-action="delete">删除</button>
              <button type="button" class="button primary" data-routine-action="save">保存这项</button>
            </div>
          </article>`,
    )
    .join("");
}

function resizeAvatar(file) {
  if (!file.type.startsWith("image/")) {
    return Promise.reject(new Error("请选择图片文件"));
  }
  if (file.size > 8_000_000) {
    return Promise.reject(new Error("图片太大，请换一张较小的"));
  }
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      const scale = Math.min(1, 256 / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("这张图片无法读取"));
    };
    image.src = url;
  });
}

async function saveProfile(event) {
  event.preventDefault();
  const button = event.submitter;
  setBusy(button, true, "保存中…");
  try {
    state.profile = await api("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({
        profile: {
          display_name: $("#displayNameInput").value,
          avatar_data: state.profile.avatar_data,
          focus_minutes: $("#settingFocusMinutes").value,
          break_minutes: $("#settingBreakMinutes").value,
        },
      }),
    });
    renderProfile();
    notify("资料已保存");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function createRoutine(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = event.submitter;
  setBusy(button, true, "添加中…");
  try {
    await api("/api/routines", {
      method: "POST",
      body: JSON.stringify({
        title: $("#routineTitle").value,
        note: $("#routineNote").value,
        estimate_minutes: $("#routineEstimate").value,
      }),
    });
    form.reset();
    $("#routineEstimate").value = "5";
    await loadSettings();
    notify("每日必做已添加，从今天开始出现");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function saveRoutineCard(card) {
  await api(`/api/routines/${card.dataset.routineId}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: $('[data-field="title"]', card).value,
      note: $('[data-field="note"]', card).value,
      estimate_minutes: $('[data-field="estimate"]', card).value,
      unlock_token: state.routineUnlock,
    }),
  });
  await loadSettings();
  notify("每日必做已更新");
}

async function deleteRoutineCard(card) {
  const title = $('[data-field="title"]', card).value;
  if (!window.confirm(`确定删除每日必做“${title}”吗？已有打卡记录仍会留在复盘里。`)) {
    return;
  }
  await api(`/api/routines/${card.dataset.routineId}`, {
    method: "DELETE",
    body: JSON.stringify({ unlock_token: state.routineUnlock }),
  });
  await loadSettings();
  notify("每日必做已删除");
}

async function openRoutineGate() {
  try {
    state.challenge = await api("/api/routines/challenge", {
      method: "POST",
      body: JSON.stringify({}),
    });
    $("#routineQuestions").innerHTML = state.challenge.questions
      .map(
        (question, index) => `
          <label>
            <span>第 ${index + 1} 题：${escapeHtml(question.prompt)} = ？</span>
            <input data-answer-index="${index}" type="number" inputmode="numeric" required />
          </label>`,
      )
      .join("");
    $("#routineGateDialog").showModal();
    window.setTimeout(() => $("#routineQuestions input")?.focus(), 0);
  } catch (error) {
    reportError(error);
  }
}

async function submitRoutineGate(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    $("#routineGateDialog").close();
    return;
  }
  const button = $("#submitRoutineGate");
  setBusy(button, true, "核对中…");
  try {
    const answers = $$("[data-answer-index]", $("#routineQuestions")).map(
      (input) => input.value,
    );
    const result = await api("/api/routines/challenge/verify", {
      method: "POST",
      body: JSON.stringify({ id: state.challenge.id, answers }),
    });
    state.routineUnlock = result.unlock_token;
    $("#routineGateDialog").close();
    renderRoutineSettings();
    notify("3 道题全部正确，现在可以修改");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

function routineStatusText(status) {
  return {
    done: "已完成",
    missed: "未完成",
    future: "未到",
    unset: "尚未开始",
  }[status] || status;
}

function renderRoutineBoard() {
  const routines = state.report?.routines || [];
  const board = $("#routineBoard");
  if (!routines.length) {
    board.innerHTML =
      '<div class="routine-empty">在设置里添加每日必做后，这里会按周、月、季度显示打卡。</div>';
    return;
  }
  const sample = routines[0].days || [];
  const axis = sample
    .map((day) => {
      const date = parseLocalDate(day.date);
      let label = "";
      if (state.reportPeriod === "week") {
        label = ["一", "二", "三", "四", "五", "六", "日"][
          date.getDay() === 0 ? 6 : date.getDay() - 1
        ];
      } else if (state.reportPeriod === "month") {
        label = String(date.getDate());
      } else if (date.getDay() === 1) {
        label = `${date.getMonth() + 1}/${date.getDate()}`;
      }
      return `<span>${escapeHtml(label)}</span>`;
    })
    .join("");
  board.dataset.period = state.reportPeriod;
  board.innerHTML = `
    <div class="routine-chart">
      <div class="routine-names">
        <span class="routine-axis-spacer"></span>
        ${routines
          .map((routine) => {
            const rate = routine.applicable_count
              ? Math.round((routine.completed_count / routine.applicable_count) * 100)
              : 0;
            return `
              <div class="routine-chart-name">
                <strong>${escapeHtml(routine.title)}</strong>
                <span>${routine.completed_count}/${routine.applicable_count} · ${rate}% · 连续 ${routine.streak} 天${routine.active ? "" : " · 已停用"}</span>
              </div>`;
          })
          .join("")}
      </div>
      <div class="routine-scroll">
        <div class="routine-axis">${axis}</div>
        ${routines
          .map(
            (routine) => `
              <div class="routine-cells">
                ${routine.days
                  .map(
                    (day) =>
                      `<span class="routine-cell" data-status="${escapeHtml(day.status)}"
                        title="${escapeHtml(day.date)} · ${routineStatusText(day.status)}"></span>`,
                  )
                  .join("")}
              </div>`,
          )
          .join("")}
      </div>
    </div>`;
}

function bindEvents() {
  $$(".nav-button").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  $("#openSettings").addEventListener("click", () => switchView("settings"));
  $("#previousDay").addEventListener("click", () => changeDate(-1));
  $("#nextDay").addEventListener("click", () => changeDate(1));
  $("#backToday").addEventListener("click", () => {
    state.date = localDateString(new Date());
    loadDay();
  });
  $("#dayPicker").addEventListener("change", (event) => {
    if (!event.target.value) return;
    state.date = event.target.value;
    loadDay();
  });

  $$("[data-period]").forEach((button) => {
    button.addEventListener("click", () => {
      state.reportPeriod = button.dataset.period;
      loadReport();
    });
  });
  $("#previousPeriod").addEventListener("click", () => {
    state.date = shiftPeriod(state.date, state.reportPeriod, -1);
    loadReport();
  });
  $("#nextPeriod").addEventListener("click", () => {
    state.date = shiftPeriod(state.date, state.reportPeriod, 1);
    loadReport();
  });
  $("#currentPeriod").addEventListener("click", () => {
    state.date = localDateString(new Date());
    loadReport();
  });

  $("#toggleAddTask").addEventListener("click", () => showAddTask());
  $("#cancelAddTask").addEventListener("click", hideAddTask);
  $("#cancelSubtask").addEventListener("click", hideAddTask);
  $$('[data-action="show-add"]').forEach((button) => {
    button.addEventListener("click", () => showAddTask());
  });
  $$(".estimate-presets button").forEach((button) => {
    button.addEventListener("click", () => {
      $("#newTaskEstimate").value = button.dataset.minutes;
    });
  });
  $("#addTaskForm").addEventListener("submit", createTask);

  $("#taskList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const entryId = Number(button.dataset.entryId);
    const entry = state.day.entries.find((item) => item.id === entryId);
    if (button.dataset.action === "start") startTimer(entryId, button);
    if (button.dataset.action === "stop") stopTimer(entryId, button);
    if (button.dataset.action === "focus") openFocusDialog(entryId);
    if (button.dataset.action === "toggle-complete") {
      toggleComplete(entryId, button);
    }
    if (button.dataset.action === "edit") openEditDialog(entryId);
    if (button.dataset.action === "subtask" && entry) {
      showAddTask(entry);
      $("#addTaskForm").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
  $("#globalStopButton").addEventListener("click", (event) => {
    stopTimer(null, event.currentTarget);
  });
  $("#stopBreakButton").addEventListener("click", stopBreak);

  $("#focusForm").addEventListener("submit", submitFocus);
  $$("[data-focus-minutes]").forEach((button) => {
    button.addEventListener("click", () => {
      $("#focusMinutes").value = button.dataset.focusMinutes;
      updateFocusPresets(button.dataset.focusMinutes);
    });
  });
  $("#focusMinutes").addEventListener("input", (event) => {
    updateFocusPresets(event.target.value);
  });

  $("#editTaskForm").addEventListener("submit", saveTaskEdit);
  $("#deleteTask").addEventListener("click", deleteTask);
  $("#segmentForm").addEventListener("submit", saveSegmentEdit);
  $("#deleteSegment").addEventListener("click", deleteSegment);
  $("#worklogList").addEventListener("click", (event) => {
    const button = event.target.closest('[data-action="edit-segment"]');
    if (button) openSegmentDialog(Number(button.dataset.segmentId));
  });

  $("#focusInput").addEventListener("input", scheduleDaySave);
  $("#reflectionInput").addEventListener("input", scheduleDaySave);
  $$("[data-mood]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mood = Number(button.dataset.mood);
      updateMoodButtons();
      scheduleDaySave();
    });
  });

  $("#openCloseDay").addEventListener("click", openCloseDay);
  $("#closeDayTasks").addEventListener("change", (event) => {
    if (event.target.matches('[data-field="action"]')) {
      updateCloseTaskDetails(event.target);
    }
  });
  $$("[data-close-mood]").forEach((button) => {
    button.addEventListener("click", () => {
      state.closeMood = Number(button.dataset.closeMood);
      renderCloseMood();
    });
  });
  $("#closeDayForm").addEventListener("submit", submitCloseDay);

  $("#quickMemoForm").addEventListener("submit", submitQuickMemo);
  $("#memoComposeForm").addEventListener("submit", submitMemoCompose);
  $("#memoSearchInput").addEventListener("input", () => {
    window.clearTimeout(state.memoSearchTimer);
    state.memoSearchTimer = window.setTimeout(loadMemos, 300);
  });
  $("#clearMemoSearch").addEventListener("click", () => {
    $("#memoSearchInput").value = "";
    loadMemos();
  });
  $("#memoFeed").addEventListener("click", (event) => {
    const button = event.target.closest("[data-memo-action]");
    if (!button) return;
    if (button.dataset.memoAction === "edit") {
      openMemoEdit(Number(button.dataset.memoId));
    }
    if (button.dataset.memoAction === "pin") {
      toggleMemoPin(Number(button.dataset.memoId));
    }
    if (button.dataset.memoAction === "open-day") {
      state.date = button.dataset.date;
      switchView("today");
    }
  });
  $("#memoEditForm").addEventListener("submit", saveMemoEdit);
  $("#deleteMemo").addEventListener("click", deleteMemo);
  $("#saveWeekReview").addEventListener("click", saveReportReview);

  $("#routineTodayList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "open-settings") switchView("settings");
    if (button.dataset.action === "toggle-routine") {
      toggleRoutine(
        Number(button.dataset.routineId),
        button.dataset.completed !== "1",
      );
    }
  });
  $("#profileForm").addEventListener("submit", saveProfile);
  $("#avatarInput").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      state.profile.avatar_data = await resizeAvatar(file);
      const initial = ($("#displayNameInput").value.trim() || "设").slice(0, 1);
      renderAvatar($("#avatarPreview"), state.profile.avatar_data, initial);
    } catch (error) {
      reportError(error);
    }
  });
  $("#removeAvatar").addEventListener("click", () => {
    state.profile.avatar_data = "";
    const initial = ($("#displayNameInput").value.trim() || "设").slice(0, 1);
    renderAvatar($("#avatarPreview"), "", initial);
  });
  $("#unlockRoutines").addEventListener("click", openRoutineGate);
  $("#routineGateForm").addEventListener("submit", submitRoutineGate);
  $("#routineCreateForm").addEventListener("submit", createRoutine);
  $("#routineSettingsList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-routine-action]");
    if (!button) return;
    const card = button.closest("[data-routine-id]");
    try {
      if (button.dataset.routineAction === "save") await saveRoutineCard(card);
      if (button.dataset.routineAction === "delete") await deleteRoutineCard(card);
    } catch (error) {
      reportError(error);
    }
  });
}

function initialize() {
  bindEvents();
  $("#memoDate").value = localDateString(new Date());
  renderBreakBar();
  loadSettings();
  switchView(state.view);
  window.setInterval(updateLiveTimers, 1000);
}

initialize();
