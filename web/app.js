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
  pendingQuickImages: [],
  pendingComposeImages: [],
  quickMemoDraftId: null,
  composeMemoDraftId: null,
  dayDetailDate: "",
  dayDetail: null,
  dayDetailSequence: 0,
  dayDetailWeek: "",
  daySegments: [],
  reminders: [],
  editingReminderId: null,
  alertedReminderIds: new Set(),
  suggestedTags: [],
  viewerImages: [],
  viewerIndex: 0,
  activeTimer: null,
  syncedAt: Date.now(),
  parentEntry: null,
  editingEntry: null,
  editingSegment: null,
  editingMemo: null,
  templates: [],
  editingTemplateId: null,
  templateTarget: null,
  taskNoteEntryId: null,
  moveEntryId: null,
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

function renderNote(value) {
  const text = String(value || "");
  if (!text.trim()) return "";
  const pattern = /https?:\/\/[^\s<>"']+/gi;
  let html = "";
  let lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    const rawUrl = match[0].replace(/[),.;，。；、]+$/u, "");
    html += escapeHtml(text.slice(lastIndex, match.index)).replaceAll("\n", "<br>");
    const href = escapeHtml(rawUrl);
    html += `<span class="note-link">
      <a href="${href}" target="_blank" rel="noopener noreferrer">${href}</a>
      <button type="button" class="copy-link" data-action="copy-link" data-url="${href}">复制</button>
    </span>`;
    lastIndex = match.index + rawUrl.length;
  }
  html += escapeHtml(text.slice(lastIndex)).replaceAll("\n", "<br>");
  return html;
}

function looksLikeRichHtml(value) {
  return /<\s*(p|br|strong|b|ul|ol|li|h3|div|span)\b/i.test(String(value || ""));
}

function sanitizeRichHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = String(html || "");
  const allowed = new Set(["P", "BR", "STRONG", "B", "UL", "OL", "LI", "H3", "DIV", "SPAN"]);
  const clean = (node) => {
    const fragment = document.createDocumentFragment();
    [...node.childNodes].forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        fragment.append(document.createTextNode(child.textContent));
        return;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) return;
      let tag = child.tagName;
      if (tag === "H1" || tag === "H2") tag = "H3";
      if (tag === "DIV") tag = "P";
      if (!allowed.has(tag) && tag !== "P" && tag !== "H3") {
        fragment.append(clean(child));
        return;
      }
      if (tag === "SPAN") {
        fragment.append(clean(child));
        return;
      }
      const element = document.createElement(tag.toLowerCase());
      if (child.classList.contains("note-lg")) element.classList.add("note-lg");
      if (child.classList.contains("note-title")) element.classList.add("note-title");
      if (tag !== "BR") element.append(clean(child));
      fragment.append(element);
    });
    return fragment;
  };
  const holder = document.createElement("div");
  holder.append(clean(template.content));
  return holder.innerHTML.trim();
}

function plainNoteText(content) {
  const text = String(content || "");
  if (!text) return "";
  if (!looksLikeRichHtml(text)) return text.replace(/\s+/g, " ").trim();
  const holder = document.createElement("div");
  holder.innerHTML = sanitizeRichHtml(text);
  return holder.innerText.replace(/\s+/g, " ").trim();
}

function renderMemoHtml(content) {
  if (!content) return "";
  if (!looksLikeRichHtml(content)) return renderNote(content);
  return sanitizeRichHtml(content);
}

function richEditor(id) {
  return document.getElementById(id);
}

function syncRichEmpty(editor) {
  if (!editor) return;
  const empty = !editor.innerText.replace(/\u00a0/g, " ").trim();
  editor.classList.toggle("is-empty", empty);
}

function readRich(id) {
  const editor = richEditor(id);
  if (!editor || !editor.innerText.replace(/\u00a0/g, " ").trim()) return "";
  return sanitizeRichHtml(editor.innerHTML);
}

function writeRich(id, content) {
  const editor = richEditor(id);
  if (!editor) return;
  if (!content) {
    editor.innerHTML = "";
  } else if (looksLikeRichHtml(content)) {
    editor.innerHTML = sanitizeRichHtml(content);
  } else {
    editor.innerHTML = String(content)
      .split("\n")
      .map((line) => `<p>${escapeHtml(line) || "<br>"}</p>`)
      .join("");
  }
  syncRichEmpty(editor);
}

function clearRich(id) {
  writeRich(id, "");
}

function richBlock(editor) {
  const selection = window.getSelection();
  if (!selection?.rangeCount) return null;
  let node = selection.anchorNode;
  if (!node || !editor.contains(node)) return null;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentNode;
  while (node && node !== editor && !["P", "H3", "LI", "DIV"].includes(node.tagName)) {
    node = node.parentNode;
  }
  return node && node !== editor ? node : null;
}

function applyRichCommand(editor, command) {
  editor.focus();
  if (command === "bold") {
    document.execCommand("bold");
  } else if (command === "list") {
    document.execCommand("insertUnorderedList");
  } else if (command === "title") {
    document.execCommand("formatBlock", false, "h3");
    richBlock(editor)?.classList.remove("note-lg");
  } else if (command === "large" || command === "body") {
    document.execCommand("formatBlock", false, "p");
    const block = richBlock(editor);
    if (!block) return;
    block.classList.remove("note-lg", "note-title");
    if (command === "large") block.classList.add("note-lg");
  }
  syncRichEmpty(editor);
}

function updateRichToolbar(wrap) {
  const editor = wrap.querySelector(".rich-note-body");
  const block = richBlock(editor);
  wrap.querySelectorAll("[data-command]").forEach((button) => {
    const command = button.dataset.command;
    let active = false;
    if (command === "bold") {
      try {
        active = document.queryCommandState("bold");
      } catch {
        active = false;
      }
    }
    if (command === "list") {
      try {
        active = document.queryCommandState("insertUnorderedList");
      } catch {
        active = false;
      }
    }
    if (command === "title") active = block?.tagName === "H3";
    if (command === "large") active = Boolean(block?.classList.contains("note-lg"));
    if (command === "body") {
      active = Boolean(block && block.tagName !== "H3" && !block.classList.contains("note-lg"));
    }
    button.classList.toggle("is-active", active);
  });
}

function markNoteSlots(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => {
    const parts = node.textContent.split(/(【[^】]{1,24}】)/);
    if (parts.length === 1) return;
    const fragment = document.createDocumentFragment();
    parts.forEach((part) => {
      if (/^【[^】]{1,24}】$/.test(part)) {
        const slot = document.createElement("span");
        slot.className = "note-slot";
        slot.textContent = part;
        fragment.append(slot);
      } else if (part) {
        fragment.append(document.createTextNode(part));
      }
    });
    node.parentNode.replaceChild(fragment, node);
  });
}

function insertTemplate(editor, content) {
  const incoming = document.createElement("div");
  incoming.innerHTML = looksLikeRichHtml(content)
    ? sanitizeRichHtml(content)
    : String(content || "")
        .split("\n")
        .map((line) => `<p>${escapeHtml(line) || "<br>"}</p>`)
        .join("");
  markNoteSlots(incoming);
  const empty = !editor.innerText.replace(/\u00a0/g, " ").trim();
  if (empty) editor.replaceChildren();
  else {
    const gap = document.createElement("p");
    gap.append(document.createElement("br"));
    editor.append(gap);
  }
  while (incoming.firstChild) editor.append(incoming.firstChild);
  const slot = editor.querySelector(".note-slot");
  editor.focus();
  if (slot) {
    const range = document.createRange();
    range.selectNodeContents(slot);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  syncRichEmpty(editor);
}

function memoSourceMarkup(memo) {
  if (!memo.source_title) return "";
  const estimate = Number(memo.source_estimate_minutes || 0)
    ? `预估 ${formatMinutes(memo.source_estimate_minutes)}`
    : "未设预估";
  const actual = `实际 ${formatMinutes(Number(memo.source_actual_seconds || 0) / 60)}`;
  return `<div class="memo-source"><span>来自任务</span><strong>${escapeHtml(memo.source_title)}</strong><em>${escapeHtml(`${estimate} · ${actual}`)}</em></div>`;
}

async function copyLink(url, button) {
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    const field = document.createElement("textarea");
    field.value = url;
    document.body.append(field);
    field.select();
    document.execCommand("copy");
    field.remove();
  }
  const original = button.textContent;
  button.textContent = "已复制";
  window.setTimeout(() => {
    button.textContent = original;
  }, 1200);
  notify("链接已复制");
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
    refreshReminders();
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
      api(`/api/memos?date=${encodeURIComponent(state.date)}&limit=30`),
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
  const backToday = $("#backToday");
  backToday.hidden = false;
  backToday.disabled = state.date === today;
  $("#focusInput").value = state.day.day.focus || "";
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
  const visible = entries.filter(
    (entry) => entry.outcome !== "carried" && entry.outcome !== "rescheduled",
  );
  empty.hidden = visible.length > 0;
  list.hidden = visible.length === 0;
  if (!visible.length) {
    list.innerHTML = "";
    return;
  }

  list.innerHTML = entriesInTreeOrder(visible)
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
      const noteCount = (state.todayMemos || []).filter(
        (memo) => Number(memo.source_entry_id) === Number(entry.id),
      ).length;
      const noteButton =
        !entry.parent_id && completed
          ? `<button class="task-action note" data-action="task-note" data-entry-id="${entry.id}">感悟${noteCount ? ` · ${noteCount}` : ""}</button>`
          : "";
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
              ${entry.outcome === "planned" ? '<span class="move-hint">右滑改期</span>' : ""}
              ${entry.definition?.trim() ? `<span class="note-hint">有说明</span>` : ""}
            </div>
            ${
              entry.definition?.trim()
                ? `<div class="task-note">
                    <div class="task-note-card">
                      <p>完成标准 / 补充说明</p>
                      <div class="task-note-body">${renderNote(entry.definition)}</div>
                    </div>
                  </div>`
                : ""
            }
          </div>
          <div class="task-actions">
            ${timerButtons}
            ${
              !finished
                ? `<button class="task-action" data-action="subtask"
                     data-entry-id="${entry.id}">＋ 子任务</button>`
                : ""
            }
            ${noteButton}
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
  const entries = leafEntries(
    allEntries.filter(
      (entry) => entry.outcome !== "carried" && entry.outcome !== "rescheduled",
    ),
  );
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

function imageThumbUrl(id) {
  return `/api/images/${id}/thumb`;
}

function imageOriginalUrl(id) {
  return `/api/images/${id}`;
}

function imageThumbMarkup(image, removable = false) {
  const remove = removable
    ? `<button type="button" class="image-remove" data-action="delete-image" data-image-id="${image.id}" aria-label="移除图片">×</button>`
    : "";
  return `<span class="image-tile">
    <button type="button" class="image-thumb" data-action="view-image" data-image-id="${image.id}" aria-label="查看原图">
      <img src="${imageThumbUrl(image.id)}" alt="图片缩略图" />
    </button>
    ${remove}
  </span>`;
}

function pendingThumbMarkup(item, bucket) {
  return `<span class="image-tile">
    <button type="button" class="image-thumb" data-action="view-pending" data-bucket="${bucket}" data-local-id="${item.localId}" aria-label="查看原图">
      <img src="${item.preview}" alt="待上传图片" />
    </button>
    <button type="button" class="image-remove" data-action="remove-pending" data-bucket="${bucket}" data-local-id="${item.localId}" aria-label="移除图片">×</button>
  </span>`;
}

function renderImageStrip(container, images, pending = [], bucket = "") {
  if (!container) return;
  container.innerHTML =
    (images || []).map((image) => imageThumbMarkup(image, true)).join("") +
    pending.map((item) => pendingThumbMarkup(item, bucket)).join("");
}

function syncImageAdder(input, count) {
  const label = input?.closest(".image-add");
  if (label) label.hidden = count >= 9;
}

function setStripBusy(strip, busy) {
  if (!strip) return;
  strip.querySelector("[data-image-busy]")?.remove();
  if (!busy) return;
  strip.insertAdjacentHTML(
    "beforeend",
    `<span class="image-tile is-uploading" data-image-busy="1" aria-label="正在处理图片"></span>`,
  );
}

function renderDayImages() {
  const images = state.day?.day?.images || [];
  renderImageStrip($("#dayImageStrip"), images);
  syncImageAdder($("#dayImageInput"), images.length);
}

function renderTodayMemos() {
  const container = $("#todayMemoList");
  if (!state.todayMemos.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = state.todayMemos
    .map((memo) => {
      const thumbs = (memo.images || [])
        .map((image) => imageThumbMarkup(image, false))
        .join("");
      return `<div class="today-memo-item">
        ${memoSourceMarkup(memo)}
        ${memo.content ? `<div class="memo-content">${renderMemoHtml(memo.content)}</div>` : ""}
        ${thumbs ? `<div class="image-strip">${thumbs}</div>` : ""}
      </div>`;
    })
    .join("");
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("这张图片无法读取"));
    reader.readAsDataURL(file);
  });
}

function canvasDataUrl(source, maxEdge, quality) {
  const scale = Math.min(1, maxEdge / Math.max(source.width, source.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(source.width * scale));
  canvas.height = Math.max(1, Math.round(source.height * scale));
  const context = canvas.getContext("2d");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", quality);
}

async function prepareImage(file) {
  if (!file.type.startsWith("image/")) {
    throw new Error("请选择图片文件");
  }
  if (file.size > 12_000_000) {
    throw new Error("单张图片请小于 12 MB");
  }
  const bitmap = await createImageBitmap(file);
  const width = bitmap.width;
  const height = bitmap.height;
  const thumbnail = canvasDataUrl(bitmap, 360, 0.82);
  const original =
    file.size > 8_000_000
      ? canvasDataUrl(bitmap, 2560, 0.9)
      : await readFileAsDataUrl(file);
  bitmap.close?.();
  return { original, thumbnail, width, height };
}

async function uploadNoteImage(ownerType, ownerKey, prepared) {
  return api("/api/images", {
    method: "POST",
    body: JSON.stringify({
      owner_type: ownerType,
      owner_key: ownerKey,
      original: prepared.original,
      thumbnail: prepared.thumbnail,
      width: prepared.width,
      height: prepared.height,
    }),
  });
}

function renderPendingImages() {
  renderImageStrip(
    $("#quickImageStrip"),
    [],
    state.pendingQuickImages,
    "quick",
  );
  renderImageStrip(
    $("#composeImageStrip"),
    [],
    state.pendingComposeImages,
    "compose",
  );
  syncImageAdder(
    $("#quickImageInput"),
    state.pendingQuickImages.length,
  );
  syncImageAdder(
    $("#composeImageInput"),
    state.pendingComposeImages.length,
  );
}

function renderMemoEditImages() {
  const images = state.editingMemo?.images || [];
  renderImageStrip($("#memoEditImageStrip"), images);
  syncImageAdder($("#memoEditImageInput"), images.length);
}

async function addFilesToBucket(files, bucket) {
  const list =
    bucket === "quick" ? state.pendingQuickImages : state.pendingComposeImages;
  const strip = bucket === "quick" ? $("#quickImageStrip") : $("#composeImageStrip");
  for (const file of files) {
    if (list.length >= 9) {
      notify("一条记录最多 9 张图片", true);
      break;
    }
    setStripBusy(strip, true);
    try {
      const prepared = await prepareImage(file);
      list.push({
        localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        preview: prepared.thumbnail,
        prepared,
      });
    } finally {
      renderPendingImages();
    }
  }
}

async function addDayImages(files) {
  if (!state.day?.day) {
    notify("页面还在加载，请稍后再添加图片", true);
    return;
  }
  const current = state.day.day.images || (state.day.day.images = []);
  for (const file of files) {
    if (current.length >= 9) {
      notify("一条记录最多 9 张图片", true);
      break;
    }
    setStripBusy($("#dayImageStrip"), true);
    try {
      current.push(
        await uploadNoteImage("day", state.date, await prepareImage(file)),
      );
    } finally {
      renderDayImages();
    }
  }
}

async function addMemoEditImages(files) {
  if (!state.editingMemo) return;
  const current = state.editingMemo.images || (state.editingMemo.images = []);
  for (const file of files) {
    if (current.length >= 9) {
      notify("一条记录最多 9 张图片", true);
      break;
    }
    setStripBusy($("#memoEditImageStrip"), true);
    try {
      current.push(
        await uploadNoteImage(
          "memo",
          state.editingMemo.id,
          await prepareImage(file),
        ),
      );
    } finally {
      renderMemoEditImages();
    }
  }
}

async function deleteSavedImage(imageId) {
  await api(`/api/images/${imageId}`, { method: "DELETE" });
  if (state.day?.day?.images) {
    state.day.day.images = state.day.day.images.filter((image) => image.id !== imageId);
    renderDayImages();
  }
  if (state.editingMemo?.images) {
    state.editingMemo.images = state.editingMemo.images.filter(
      (image) => image.id !== imageId,
    );
    renderMemoEditImages();
  }
  state.todayMemos.forEach((memo) => {
    memo.images = (memo.images || []).filter((image) => image.id !== imageId);
  });
  state.memos.forEach((memo) => {
    memo.images = (memo.images || []).filter((image) => image.id !== imageId);
  });
  renderTodayMemos();
  if (state.view === "memos") renderMemos($("#memoSearchInput")?.value.trim() || "");
  notify("图片已移除");
}

async function uploadPendingImages(bucket, ownerKey) {
  const key = bucket === "quick" ? "pendingQuickImages" : "pendingComposeImages";
  const queue = [...state[key]];
  state[key] = [];
  renderPendingImages();
  for (let index = 0; index < queue.length; index += 1) {
    try {
      await uploadNoteImage("memo", ownerKey, queue[index].prepared);
    } catch (error) {
      state[key] = queue.slice(index);
      renderPendingImages();
      throw error;
    }
  }
}

function bindImageInput(input, handler) {
  input.addEventListener("change", async (event) => {
    const files = [...event.target.files];
    event.target.value = "";
    if (!files.length) return;
    try {
      await handler(files);
    } catch (error) {
      reportError(error);
    }
  });
}

function transferHasFile(dataTransfer) {
  if (!dataTransfer) return false;
  if ([...dataTransfer.types].includes("Files")) return true;
  return [...dataTransfer.items].some(
    (item) => item.kind === "file" || item.type.startsWith("image/"),
  );
}

function bindImageDrop(target, handler) {
  target.addEventListener("dragenter", (event) => {
    if (!transferHasFile(event.dataTransfer)) return;
    event.preventDefault();
    target.classList.add("is-dropping");
  });
  target.addEventListener("dragover", (event) => {
    if (!transferHasFile(event.dataTransfer)) return;
    event.preventDefault();
    target.classList.add("is-dropping");
  });
  target.addEventListener("dragleave", (event) => {
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.remove("is-dropping");
  });
  target.addEventListener("drop", async (event) => {
    if (!transferHasFile(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    target.classList.remove("is-dropping");
    const files = [...event.dataTransfer.files].filter((file) =>
      file.type.startsWith("image/"),
    );
    if (!files.length) {
      notify("请拖入图片文件", true);
      return;
    }
    try {
      await handler(files);
    } catch (error) {
      reportError(error);
    }
  });
}

function bindImagePaste(target, handler) {
  target.addEventListener("paste", async (event) => {
    const files = [...event.clipboardData.items]
      .filter((item) => item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter(Boolean);
    if (!files.length) return;
    event.preventDefault();
    try {
      await handler(files);
    } catch (error) {
      reportError(error);
    }
  });
}

function fitViewerImage(picture = $("#imageViewerPicture")) {
  if (!picture?.naturalWidth || !picture.naturalHeight) return;
  const maxWidth = Math.max(160, window.innerWidth - 144);
  const maxHeight = Math.max(160, window.innerHeight - 120);
  const scale = Math.min(
    maxWidth / picture.naturalWidth,
    maxHeight / picture.naturalHeight,
  );
  picture.style.width = `${Math.round(picture.naturalWidth * scale)}px`;
  picture.style.height = `${Math.round(picture.naturalHeight * scale)}px`;
}

function openImageViewer(images, index) {
  if (!images.length || index < 0) return;
  state.viewerImages = images;
  state.viewerIndex = index;
  const current = images[index];
  const picture = $("#imageViewerPicture");
  picture.alt = "原图";
  picture.style.width = "";
  picture.style.height = "";
  picture.src = current.preview || imageOriginalUrl(current.id);
  if (picture.complete) fitViewerImage(picture);
  const multiple = images.length > 1;
  $("#previousImage").hidden = !multiple;
  $("#nextImage").hidden = !multiple;
  const caption = $("#imageViewerCaption");
  caption.hidden = !multiple;
  caption.textContent = multiple ? `${index + 1} / ${images.length}` : "";
  if (!$("#imageViewer").open) $("#imageViewer").showModal();
}

function stepImageViewer(direction) {
  if (state.viewerImages.length < 2) return;
  state.viewerIndex =
    (state.viewerIndex + direction + state.viewerImages.length) %
    state.viewerImages.length;
  openImageViewer(state.viewerImages, state.viewerIndex);
}

function renderTagPresets() {
  $$(".tag-presets").forEach((box) => {
    const input = document.getElementById(box.dataset.tagInput);
    const current = new Set(splitTags(input?.value));
    box.hidden = state.suggestedTags.length === 0;
    box.innerHTML = state.suggestedTags.length
      ? `<span class="tag-presets-label">最近常用</span>${state.suggestedTags
          .map(
            (tag) =>
              `<button type="button" class="tag-preset ${current.has(tag) ? "is-active" : ""}" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>`,
          )
          .join("")}`
      : "";
  });
}

async function loadSuggestedTags() {
  try {
    const data = await api("/api/tags/suggested");
    state.suggestedTags = data.tags || [];
    renderTagPresets();
  } catch (error) {
    reportError(error);
  }
}

function applyTagPreset(input, tag) {
  const tags = splitTags(input.value);
  const existing = tags.indexOf(tag);
  if (existing >= 0) tags.splice(existing, 1);
  else tags.push(tag);
  input.value = tags.join(", ");
  input.dispatchEvent(new Event("input"));
  input.focus();
}

function syncStickyOffset() {
  const header = $(".app-header");
  if (!header) return;
  const headerHeight = Math.round(header.getBoundingClientRect().height);
  document.documentElement.style.setProperty(
    "--header-height",
    `${headerHeight}px`,
  );
  const running = $("#runningBar");
  const breakBar = $("#breakBar");
  const runningHeight =
    running && !running.hidden
      ? Math.round(running.getBoundingClientRect().height)
      : 0;
  const breakHeight =
    breakBar && !breakBar.hidden
      ? Math.round(breakBar.getBoundingClientRect().height)
      : 0;
  document.documentElement.style.setProperty(
    "--running-height",
    `${runningHeight}px`,
  );
  document.documentElement.style.setProperty(
    "--bar-height",
    `${runningHeight + breakHeight}px`,
  );
}

function renderRunningBar() {
  const active = state.activeTimer;
  const bar = $("#runningBar");
  bar.hidden = !active;
  if (!active) {
    safeStorageRemove(STORAGE.timer);
    syncStickyOffset();
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
  syncStickyOffset();
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
  syncStickyOffset();
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
    closeSegmentPopover();
    await loadDay();
    if (state.view === "report") await loadDayDetail();
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
    closeSegmentPopover();
    await loadDay();
    if (state.view === "report") await loadDayDetail();
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
    reflection: state.day?.day?.reflection || "",
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
  $("#closeReflection").value = state.day.day.reflection || "";
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
    const memo = await api("/api/memos", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    notify("已经记下来");
    return memo;
  } catch (error) {
    reportError(error);
    return null;
  } finally {
    setBusy(button, false);
  }
}

async function submitQuickMemo(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const content = readRich("quickMemoContent");
  const tags = $("#quickMemoTags").value;
  if (!content && !state.pendingQuickImages.length && !state.quickMemoDraftId) {
    notify("先写下一句，或添加一张图片", true);
    return;
  }
  let memoId = state.quickMemoDraftId;
  const retrying = Boolean(memoId);
  if (!memoId) {
    const memo = await createMemo(
      {
        date: state.date,
        content,
        content_format: "rich",
        tags,
        has_images: state.pendingQuickImages.length > 0,
      },
      event.submitter,
    );
    if (!memo) return;
    memoId = memo.id;
    state.quickMemoDraftId = memoId;
  }
  try {
    await uploadPendingImages("quick", memoId);
    if (retrying) {
      await api(`/api/memos/${memoId}`, {
        method: "PATCH",
        body: JSON.stringify({ date: state.date, content, content_format: "rich", tags }),
      });
    }
  } catch (error) {
    reportError(error);
    notify("文字已经保存，剩下的图片可以再点一次记下来", true);
    return;
  }
  state.quickMemoDraftId = null;
  form.reset();
  clearRich("quickMemoContent");
  renderTagPresets();
  state.todayMemos = await api(
    `/api/memos?date=${encodeURIComponent(state.date)}&limit=30`,
  );
  renderTodayMemos();
  await loadSuggestedTags();
}

async function submitMemoCompose(event) {
  event.preventDefault();
  const content = readRich("memoContent");
  const tags = $("#memoTags").value;
  if (!content && !state.pendingComposeImages.length && !state.composeMemoDraftId) {
    notify("先写下一句，或添加一张图片", true);
    return;
  }
  let memoId = state.composeMemoDraftId;
  const retrying = Boolean(memoId);
  if (!memoId) {
    const memo = await createMemo(
      {
        date: $("#memoDate").value,
        content,
        content_format: "rich",
        tags,
        has_images: state.pendingComposeImages.length > 0,
      },
      event.submitter,
    );
    if (!memo) return;
    memoId = memo.id;
    state.composeMemoDraftId = memoId;
  }
  try {
    await uploadPendingImages("compose", memoId);
    if (retrying) {
      await api(`/api/memos/${memoId}`, {
        method: "PATCH",
        body: JSON.stringify({
          date: $("#memoDate").value,
          content,
          content_format: "rich",
          tags,
        }),
      });
    }
  } catch (error) {
    reportError(error);
    notify("文字已经保存，剩下的图片可以再点一次保存", true);
    return;
  }
  state.composeMemoDraftId = null;
  clearRich("memoContent");
  $("#memoTags").value = "";
  renderPendingImages();
  renderTagPresets();
  await loadMemos();
  await loadSuggestedTags();
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
    : `共显示 ${state.memos.length} 条记录`;
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
                  ? `<button data-memo-action="promote" data-memo-id="${escapeHtml(memo.id)}">加入今天</button>
                     <button data-memo-action="open-day" data-date="${memo.memo_date}">打开当天</button>`
                  : `<button data-memo-action="promote" data-memo-id="${escapeHtml(memo.id)}">加入今天</button>
                     <button data-memo-action="pin" data-memo-id="${memo.id}">${memo.pinned ? "取消置顶" : "置顶"}</button>
                     <button data-memo-action="edit" data-memo-id="${memo.id}">编辑</button>`
              }
            </div>
          </div>
          ${memoSourceMarkup(memo)}
          ${memo.content ? `<div class="memo-content">${renderMemoHtml(memo.content)}</div>` : ""}
          ${
            (memo.images || []).length
              ? `<div class="image-strip">${memo.images.map((image) => imageThumbMarkup(image, false)).join("")}</div>`
              : ""
          }
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
  writeRich("memoEditContent", memo.content);
  $("#memoEditDate").value = memo.memo_date;
  $("#memoEditTags").value = memo.tags || "";
  $("#memoEditPinned").checked = Boolean(memo.pinned);
  renderMemoEditImages();
  renderTagPresets();
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
        content: readRich("memoEditContent"),
        content_format: "rich",
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

function taskDraftFromNote(content) {
  const text = plainNoteText(content);
  if (!text) return null;
  const title = text.length > 80 ? `${text.slice(0, 80).trim()}…` : text;
  const definition = text.length > 80 ? text.slice(0, 1000) : "";
  return { title: title.slice(0, 240), definition };
}

async function promoteMemo(memoId, button) {
  const memo = state.memos.find((item) => String(item.id) === String(memoId));
  const draft = taskDraftFromNote(memo?.content);
  if (!draft) {
    notify("先写下一句，再加入今天的清单", true);
    return;
  }
  const today = localDateString(new Date());
  setBusy(button, true, "加入中…");
  try {
    const day = await api(`/api/day?date=${encodeURIComponent(today)}`);
    const exists = (day.entries || []).some((entry) => entry.title === draft.title);
    if (exists) {
      notify("今天的清单里已经有这条任务");
      return;
    }
    await api("/api/entries", {
      method: "POST",
      body: JSON.stringify({
        date: today,
        title: draft.title,
        definition: draft.definition,
        estimate_minutes: 30,
      }),
    });
    if (state.view === "today" && state.date === today) await loadDay();
    notify("已加入今天的清单，原记录仍留在感悟库");
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
  ensureDayDetailDate();
  loadDayDetail();
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

function ensureDayDetailDate() {
  if (!state.dayDetailDate) {
    state.dayDetailDate = shiftDate(localDateString(new Date()), -1);
  }
}

function dayDetailHeading(date) {
  const today = localDateString(new Date());
  const parsed = parseLocalDate(date);
  const label = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(parsed);
  if (date === today) return `今天 · ${label}`;
  if (date === shiftDate(today, -1)) return `昨天 · ${label}`;
  if (date === shiftDate(today, -2)) return `前天 · ${label}`;
  return label;
}

async function loadDayDetail() {
  ensureDayDetailDate();
  const date = state.dayDetailDate;
  const input = $("#dayDetailDate");
  if (input) input.value = date;
  const range = weekBounds(date);
  const sequence = ++state.dayDetailSequence;
  try {
    const segments = await api(
      `/api/segments?start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}`,
    );
    if (sequence !== state.dayDetailSequence || state.dayDetailDate !== date) return;
    const weekChanged = state.dayDetailWeek !== range.start;
    state.dayDetailWeek = range.start;
    state.daySegments = segments;
    renderDayDetail(weekChanged);
    $$("[data-chart-date]").forEach((column) => {
      column.classList.toggle("is-selected", column.dataset.chartDate === date);
    });
  } catch (error) {
    reportError(error);
  }
}

function weekBounds(date) {
  const parsed = parseLocalDate(date);
  const mondayOffset = parsed.getDay() === 0 ? 6 : parsed.getDay() - 1;
  const start = new Date(parsed);
  start.setDate(parsed.getDate() - mondayOffset);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  return { start: localDateString(start), end: localDateString(end) };
}

function minutesFromMidnight(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 0;
  return parsed.getHours() * 60 + parsed.getMinutes() + parsed.getSeconds() / 60;
}

function segmentBounds(segment) {
  const start = Math.max(0, Math.min(24 * 60, minutesFromMidnight(segment.start_at)));
  let end = segment.end_at
    ? minutesFromMidnight(segment.end_at)
    : start + Math.max(1, (Date.now() - new Date(segment.start_at).getTime()) / 60000);
  if (end <= start) end = start + Math.max(1, Number(segment.duration_seconds || 60) / 60);
  end = Math.max(start + 1, Math.min(24 * 60, end));
  return { start, end };
}

function layoutDayBlocks(segments) {
  const items = segments
    .map((segment) => ({ segment, ...segmentBounds(segment) }))
    .sort((left, right) => left.start - right.start || left.end - right.end);
  const laneEnds = [];
  items.forEach((item) => {
    let lane = laneEnds.findIndex((end) => end <= item.start + 0.01);
    if (lane < 0) {
      lane = laneEnds.length;
      laneEnds.push(item.end);
    } else {
      laneEnds[lane] = item.end;
    }
    item.lane = lane;
  });
  items.forEach((item) => {
    const overlapping = items.filter(
      (other) => other.start < item.end - 0.01 && other.end > item.start + 0.01,
    );
    item.lanes = Math.max(1, ...overlapping.map((other) => other.lane + 1));
  });
  return items;
}

function renderDayDetail(scrollIntoTime = false) {
  closeSegmentPopover();
  const date = state.dayDetailDate;
  const heading = $("#dayDetailTitle");
  const summary = $("#dayDetailSummary");
  const calendar = $("#dayCalendar");
  if (!heading || !calendar) return;
  heading.textContent = dayDetailHeading(date);
  const selectedSegments = (state.daySegments || []).filter(
    (segment) => segment.plan_date === date,
  );
  const minutes = selectedSegments.reduce((sum, segment) => {
    if (segment.end_at) return sum + Number(segment.duration_seconds || 0) / 60;
    return sum + Math.max(0, (Date.now() - new Date(segment.start_at).getTime()) / 60000);
  }, 0);
  summary.textContent = selectedSegments.length
    ? `这一天 ${selectedSegments.length} 段计时 · 实际 ${formatMinutes(minutes)}`
    : "这一天还没有计时，空着的格子就是没记下的时间";

  const range = weekBounds(date);
  const today = localDateString(new Date());
  const hourHeight = 48;
  const hours = Array.from({ length: 24 }, (_, hour) => hour);
  const weekDays = Array.from({ length: 7 }, (_, index) => shiftDate(range.start, index));
  const weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  calendar.innerHTML = `
    <div class="cal-sheet">
      <div class="cal-head">
        <div class="cal-gutter-head"></div>
        ${weekDays
          .map((day, index) => {
            const parsed = parseLocalDate(day);
            return `<button type="button" class="cal-day ${day === date ? "is-selected" : ""} ${day === today ? "is-today" : ""}" data-cal-date="${day}">
              <span>${weekday[index]}</span>
              <strong>${parsed.getDate()}</strong>
            </button>`;
          })
          .join("")}
      </div>
      <div class="cal-scroll" id="dayCalendarScroll">
        <div class="cal-body">
          <div class="cal-hours">
            ${hours
              .map(
                (hour) =>
                  `<div class="cal-hour-label">${String(hour).padStart(2, "0")}:00</div>`,
              )
              .join("")}
          </div>
          <div class="cal-columns">
            ${
              weekDays.includes(today)
                ? `<div class="cal-now" style="top:${((new Date().getHours() * 60 + new Date().getMinutes()) / 60) * hourHeight}px"><i></i><span>${String(new Date().getHours()).padStart(2, "0")}:${String(new Date().getMinutes()).padStart(2, "0")}</span></div>`
                : ""
            }
            ${weekDays
              .map((day) => {
                const blocks = layoutDayBlocks(
                  (state.daySegments || []).filter((segment) => segment.plan_date === day),
                );
                return `<div class="cal-col ${day === date ? "is-selected" : ""} ${indexWeekend(day) ? "is-weekend" : ""}">
                  ${hours.map(() => '<div class="cal-hour-slot"></div>').join("")}
                  ${blocks
                    .map((item) => {
                      const top = (item.start / 60) * hourHeight;
                      const height = Math.max(22, ((item.end - item.start) / 60) * hourHeight - 2);
                      const width = 100 / item.lanes;
                      const left = item.lane * width;
                      const clock = `${formatShortClock(item.segment.start_at)}–${formatShortClock(item.segment.end_at)}`;
                      const focus = item.segment.mode === "focus";
                      return `<button type="button" class="cal-block ${focus ? "is-focus" : ""}" data-segment-id="${item.segment.id}" style="top:${top}px;height:${height}px;left:calc(${left}% + 2px);width:calc(${width}% - 4px)" title="${escapeHtml(item.segment.title)} ${clock}">
                        <strong>${escapeHtml(item.segment.title)}</strong>
                        ${height >= 38 ? `<span>${escapeHtml(clock)}</span>` : ""}
                      </button>`;
                    })
                    .join("")}
                </div>`;
              })
              .join("")}
          </div>
        </div>
      </div>
    </div>`;
  if (scrollIntoTime) {
    const scroller = $("#dayCalendarScroll");
    const earliest = (state.daySegments || []).map(segmentBounds).sort((a, b) => a.start - b.start)[0];
    const hour = earliest ? Math.max(0, Math.floor(earliest.start / 60) - 1) : 8;
    scroller.scrollTop = hour * hourHeight;
  }
}

function indexWeekend(date) {
  const day = parseLocalDate(date).getDay();
  return day === 0 || day === 6;
}

function formatSegmentMoment(value) {
  if (!value) return "进行中";
  const day = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
  }).format(new Date(value));
  return `${day} ${formatShortClock(value)}`;
}

function formatSegmentRange(segment) {
  const date = new Date(segment.start_at);
  const weekday = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()];
  return `${date.getMonth() + 1}月${date.getDate()}日 (${weekday}) ${formatShortClock(segment.start_at)} - ${formatShortClock(segment.end_at)}`;
}

function estimatedFinishText(segment) {
  const minutes = Number(segment.estimate_minutes || 0);
  if (!minutes) return "未设置";
  let start = new Date(segment.start_at);
  if (segment.planned_start) {
    const planned = new Date(
      `${segment.plan_date}T${String(segment.planned_start).slice(0, 5)}:00`,
    );
    if (!Number.isNaN(planned.getTime())) start = planned;
  }
  const finish = new Date(start.getTime() + minutes * 60000);
  return formatSegmentMoment(finish.toISOString());
}

function closeSegmentPopover() {
  state.popoverSegment = null;
  const popover = $("#segmentPopover");
  if (popover) popover.hidden = true;
  $$(".cal-block.is-open").forEach((block) => block.classList.remove("is-open"));
}

function openSegmentPopover(segment, anchor) {
  state.popoverSegment = segment;
  $$(".cal-block").forEach((block) => {
    block.classList.toggle("is-open", Number(block.dataset.segmentId) === Number(segment.id));
  });
  $("#segmentPopoverTitle").textContent = segment.title;
  $("#segmentPopoverWhen").textContent = formatSegmentRange(segment);
  $("#segmentPopoverEstimate").textContent = `预计完成时间　${estimatedFinishText(segment)}`;
  $("#segmentPopoverActual").textContent = `实际完成时间　${
    segment.end_at ? formatSegmentMoment(segment.end_at) : "进行中"
  }`;
  const popover = $("#segmentPopover");
  popover.hidden = false;
  const rect = anchor.getBoundingClientRect();
  const width = popover.offsetWidth;
  const height = popover.offsetHeight;
  let left = rect.right + 8;
  let top = rect.top;
  if (left + width > window.innerWidth - 8) left = rect.left - width - 8;
  if (top + height > window.innerHeight - 8) top = window.innerHeight - height - 8;
  popover.style.left = `${Math.max(8, left)}px`;
  popover.style.top = `${Math.max(8, top)}px`;
}

async function editPopoverTask() {
  const segment = state.popoverSegment;
  if (!segment) return;
  try {
    const data = await api(`/api/day?date=${encodeURIComponent(segment.plan_date)}`);
    const entry = (data.entries || []).find((item) => item.id === segment.entry_id);
    if (!entry) {
      notify("没有找到这条任务", true);
      return;
    }
    const previousDay = state.day;
    state.day = data;
    openEditDialog(entry.id);
    if (state.view !== "today") state.day = previousDay;
    closeSegmentPopover();
  } catch (error) {
    reportError(error);
  }
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
        <div class="day-column ${item.date === state.dayDetailDate ? "is-selected" : ""}" data-chart-date="${escapeHtml(item.date)}">
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

function localMinute(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${localDateString(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function prepareReminderForm() {
  const next = new Date();
  next.setMinutes(0, 0, 0);
  next.setHours(next.getHours() + 1);
  $("#reminderDate").value = localDateString(next);
  $("#reminderTime").value = `${String(next.getHours()).padStart(2, "0")}:${String(next.getMinutes()).padStart(2, "0")}`;
}

function reminderStamp(reminder) {
  return `${reminder.remind_at.slice(0, 10)}T${reminder.remind_at.slice(11, 16)}`;
}

function formatReminderWhen(value) {
  const date = value.slice(0, 10);
  const time = value.slice(11, 16);
  const today = localDateString(new Date());
  let day = date;
  if (date === today) day = "今天";
  else if (date === shiftDate(today, 1)) day = "明天";
  else if (date === shiftDate(today, -1)) day = "昨天";
  else {
    const parsed = parseLocalDate(date);
    day = new Intl.DateTimeFormat("zh-CN", {
      month: "long",
      day: "numeric",
    }).format(parsed);
  }
  return `${day} ${time}`;
}

function renderReminders() {
  const list = $("#reminderList");
  const pending = state.reminders.filter((item) => item.status === "pending");
  $("#reminderCount").textContent = pending.length ? `${pending.length} 个待提醒` : "";
  if (!state.reminders.length) {
    list.innerHTML =
      '<p class="reminder-empty">还没有提醒。选一个时间和一句话，到点会响。</p>';
    return;
  }
  const now = localMinute();
  list.innerHTML = state.reminders
    .map((reminder) => {
      const due = reminder.status === "pending" && reminderStamp(reminder) <= now;
      if (state.editingReminderId === reminder.id) {
        const [date, time] = reminder.remind_at.split("T");
        return `
          <form class="reminder-edit" data-reminder-edit="${reminder.id}">
            <input name="message" type="text" maxlength="200" required value="${escapeHtml(reminder.message)}" />
            <input name="date" type="date" required value="${escapeHtml(date)}" aria-label="提醒日期" />
            <input name="time" type="time" required value="${escapeHtml(time)}" aria-label="提醒时间" />
            <div class="reminder-edit-actions">
              <button type="submit" class="button primary compact">保存</button>
              <button type="button" class="button subtle compact" data-reminder-action="cancel-edit" data-reminder-id="${reminder.id}">取消</button>
            </div>
          </form>`;
      }
      return `
        <article class="reminder-card ${due ? "is-due" : ""} ${reminder.status === "done" ? "is-done" : ""}">
          <time>${escapeHtml(formatReminderWhen(reminder.remind_at))}</time>
          <p>${escapeHtml(reminder.message)}</p>
          <div class="reminder-actions">
            ${
              due
                ? `<button type="button" data-reminder-action="done" data-reminder-id="${reminder.id}">知道了</button>`
                : ""
            }
            <button type="button" data-reminder-action="edit" data-reminder-id="${reminder.id}">编辑</button>
            <button type="button" data-reminder-action="delete" data-reminder-id="${reminder.id}">删除</button>
          </div>
        </article>`;
    })
    .join("");
}

async function refreshReminders() {
  try {
    state.reminders = await api("/api/reminders");
    if (state.view === "memos" && state.editingReminderId == null) renderReminders();
    const now = localMinute();
    const due = state.reminders.filter(
      (item) => item.status === "pending" && reminderStamp(item) <= now,
    );
    const fresh = due.filter((item) => !state.alertedReminderIds.has(item.id));
    fresh.forEach((item) => state.alertedReminderIds.add(item.id));
    if (fresh.length) notifyDueReminders(fresh);
    const alert = $("#reminderAlert");
    if (due.length && fresh.length && !alert.open) {
      $("#reminderAlertList").innerHTML = due
        .map(
          (item) => `
            <article>
              <time>${escapeHtml(formatReminderWhen(item.remind_at))}</time>
              <p>${escapeHtml(item.message)}</p>
            </article>`,
        )
        .join("");
      alert.returnValue = "";
      try {
        alert.showModal();
      } catch {
        fresh.forEach((item) => state.alertedReminderIds.delete(item.id));
      }
    }
  } catch {
    // 轮询失败时不打断当前操作，下一轮会再试。
  }
}

function notifyDueReminders(reminders) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  reminders.forEach((item) => {
    const notice = new Notification("到点了", { body: item.message, tag: `reminder-${item.id}` });
    notice.onclick = () => window.focus();
  });
}

async function requestReminderPermission() {
  if (!("Notification" in window) || Notification.permission !== "default") return;
  try {
    await Notification.requestPermission();
  } catch {
    // 浏览器不允许时，页面里的提醒框仍然可用。
  }
}

async function submitReminder(event) {
  event.preventDefault();
  const message = $("#reminderMessage").value.trim();
  const remindAt = `${$("#reminderDate").value}T${$("#reminderTime").value}`;
  if (!message || !$("#reminderDate").value || !$("#reminderTime").value) {
    notify("先写下内容，并选好日期和时间", true);
    return;
  }
  const button = event.submitter;
  setBusy(button, true, "添加中…");
  try {
    await api("/api/reminders", {
      method: "POST",
      body: JSON.stringify({ message, remind_at: remindAt }),
    });
    $("#reminderMessage").value = "";
    prepareReminderForm();
    await requestReminderPermission();
    await refreshReminders();
    renderReminders();
    notify("提醒已设好");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function saveReminderEdit(form) {
  const reminderId = Number(form.dataset.reminderEdit);
  const message = form.elements.message.value.trim();
  const remindAt = `${form.elements.date.value}T${form.elements.time.value}`;
  try {
    await api(`/api/reminders/${reminderId}`, {
      method: "PATCH",
      body: JSON.stringify({ message, remind_at: remindAt }),
    });
    state.editingReminderId = null;
    state.alertedReminderIds.delete(reminderId);
    await refreshReminders();
    renderReminders();
    notify("提醒已更新");
  } catch (error) {
    reportError(error);
  }
}

async function deleteReminder(reminderId, button) {
  if (!window.confirm("确定删掉这个提醒吗？")) return;
  setBusy(button, true, "删除中…");
  try {
    await api(`/api/reminders/${reminderId}`, { method: "DELETE" });
    if (state.editingReminderId === reminderId) state.editingReminderId = null;
    state.alertedReminderIds.delete(reminderId);
    await refreshReminders();
    renderReminders();
    notify("提醒已删除");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function acknowledgeReminder(reminderId) {
  try {
    await api(`/api/reminders/${reminderId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "done" }),
    });
    state.alertedReminderIds.delete(reminderId);
    await refreshReminders();
    if (state.view === "memos") renderReminders();
  } catch (error) {
    reportError(error);
  }
}

async function acknowledgeOpenReminders() {
  const now = localMinute();
  const due = state.reminders.filter(
    (item) => item.status === "pending" && reminderStamp(item) <= now,
  );
  try {
    await Promise.all(
      due.map((item) =>
        api(`/api/reminders/${item.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "done" }),
        }),
      ),
    );
    due.forEach((item) => state.alertedReminderIds.delete(item.id));
    await refreshReminders();
    if (state.view === "memos") renderReminders();
  } catch (error) {
    reportError(error);
  }
}

function taskTreeEstimate(entry) {
  const children = (state.day?.entries || []).filter(
    (candidate) => candidate.parent_id === entry.task_id,
  );
  if (!children.length) return Number(entry.estimate_minutes || 0);
  return children.reduce((sum, child) => sum + taskTreeEstimate(child), 0);
}

function openTaskNote(entry) {
  state.taskNoteEntryId = entry.id;
  $("#taskNoteTitle").textContent = entry.title;
  const estimate = taskTreeEstimate(entry);
  const actual = aggregateSeconds(entry);
  const estimateText = estimate ? `预估 ${formatMinutes(estimate)}` : "未设预估";
  $("#taskNoteMeta").textContent = `${formatMemoDate(state.date)} · ${estimateText} · 实际 ${formatMinutes(actual / 60)}`;
  clearRich("taskNoteContent");
  $("#taskNoteTags").value = "";
  renderTagPresets();
  $("#taskNoteDialog").showModal();
}

async function submitTaskNote(event) {
  event.preventDefault();
  const content = readRich("taskNoteContent");
  if (!content) {
    notify("先写下一点感悟", true);
    return;
  }
  const button = event.submitter;
  const memo = await createMemo(
    {
      date: state.date,
      content,
      content_format: "rich",
      tags: $("#taskNoteTags").value,
      entry_id: state.taskNoteEntryId,
    },
    button,
  );
  if (!memo) return;
  $("#taskNoteDialog").close();
  clearRich("taskNoteContent");
  await loadDay();
  await loadMemos();
}

function renderTemplates() {
  const list = $("#templateList");
  if (!state.templates.length) {
    list.innerHTML = "";
    return;
  }
  list.innerHTML = state.templates
    .map(
      (template) => `
        <div class="template-row">
          <strong>${escapeHtml(template.name)}</strong>
          <div>
            <button type="button" data-template-action="use" data-template-id="${template.id}">使用</button>
            <button type="button" data-template-action="edit" data-template-id="${template.id}">编辑</button>
            <button type="button" data-template-action="delete" data-template-id="${template.id}">删除</button>
          </div>
        </div>`,
    )
    .join("");
}

async function loadTemplates() {
  state.templates = await api("/api/memo-templates");
  renderTemplates();
}

function resetTemplateForm() {
  state.editingTemplateId = null;
  $("#templateName").value = "";
  clearRich("templateContent");
  $("#saveTemplate").textContent = "保存模板";
}

async function openTemplateDialog(editor) {
  state.templateTarget = editor || richEditor("memoContent");
  resetTemplateForm();
  try {
    await loadTemplates();
  } catch (error) {
    reportError(error);
    return;
  }
  $("#templateDialog").showModal();
}

async function saveTemplate(event) {
  event.preventDefault();
  const name = $("#templateName").value.trim();
  const content = readRich("templateContent");
  if (!name) {
    notify("先给模板起个名字", true);
    return;
  }
  if (!content) {
    notify("模板里先写一点内容", true);
    return;
  }
  const button = $("#saveTemplate");
  setBusy(button, true, "保存中…");
  try {
    if (state.editingTemplateId) {
      await api(`/api/memo-templates/${state.editingTemplateId}`, {
        method: "PATCH",
        body: JSON.stringify({ name, content, content_format: "rich" }),
      });
    } else {
      await api("/api/memo-templates", {
        method: "POST",
        body: JSON.stringify({ name, content, content_format: "rich" }),
      });
    }
    resetTemplateForm();
    await loadTemplates();
    notify("模板已保存");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

async function deleteTemplate(templateId, button) {
  if (!window.confirm("确定删除这个模板吗？")) return;
  setBusy(button, true, "删除中…");
  try {
    await api(`/api/memo-templates/${templateId}`, { method: "DELETE" });
    if (state.editingTemplateId === templateId) resetTemplateForm();
    await loadTemplates();
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false);
  }
}

function formatMonthDay(value) {
  const date = parseLocalDate(value);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

function nextMonday(fromDate) {
  const date = parseLocalDate(fromDate);
  const day = date.getDay();
  const delta = day === 1 ? 7 : (8 - day) % 7;
  return shiftDate(fromDate, delta || 7);
}

function moveChoices(entry) {
  const today = localDateString(new Date());
  const earliest = entry.plan_date < today ? today : shiftDate(entry.plan_date, 1);
  const choices = [];
  const push = (key, date, label) => {
    if (date < earliest || choices.some((item) => item.date === date)) return;
    choices.push({ key, date, label });
  };
  if (entry.plan_date < today) push("today", today, "今天");
  push("tomorrow", shiftDate(today, 1), "明天");
  push("day-after", shiftDate(today, 2), "后天");
  push("monday", nextMonday(today), "下周一");
  return { earliest, choices };
}

function closeMovePopover() {
  state.moveEntryId = null;
  const popover = $("#moveTaskPopover");
  if (popover) popover.hidden = true;
  $$(".task-row.is-move-open").forEach((row) => row.classList.remove("is-move-open"));
}

function openMovePopover(entryId, row) {
  const entry = state.day?.entries?.find((item) => item.id === entryId);
  if (!entry || entry.outcome !== "planned") return;
  state.moveEntryId = entryId;
  const { earliest, choices } = moveChoices(entry);
  $("#moveTaskTitle").textContent = entry.title;
  $("#moveTaskChoices").innerHTML = choices
    .map(
      (choice) =>
        `<button type="button" class="${choice.key === "tomorrow" ? "is-primary" : ""}" data-move-date="${choice.date}">${choice.label} · ${formatMonthDay(choice.date)}</button>`,
    )
    .join("");
  const input = $("#moveTaskDate");
  input.min = earliest;
  input.value = choices.find((choice) => choice.key === "tomorrow")?.date || earliest;
  const logged = aggregateSeconds(entry) > 0;
  $("#moveTaskNote").textContent = logged
    ? "任务会从这一天剪走。已经记下的工作时间仍留在原来的工作日志里。"
    : "任务会从这一天剪走，只出现在选中的那一天。";
  $$(".task-row.is-move-open").forEach((item) => item.classList.remove("is-move-open"));
  row.classList.add("is-move-open");
  const popover = $("#moveTaskPopover");
  popover.hidden = false;
  const rect = row.getBoundingClientRect();
  const width = popover.offsetWidth;
  const height = popover.offsetHeight;
  let left = rect.right - width - 12;
  let top = rect.bottom + 6;
  if (left < 8) left = Math.min(rect.left, window.innerWidth - width - 8);
  if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 6);
  popover.style.left = `${Math.max(8, left)}px`;
  popover.style.top = `${Math.max(8, top)}px`;
}

async function moveTaskTo(targetDate) {
  const entryId = state.moveEntryId;
  if (!entryId || !targetDate) return;
  const entry = state.day?.entries?.find((item) => item.id === entryId);
  try {
    const result = await api(`/api/entries/${entryId}/move`, {
      method: "POST",
      body: JSON.stringify({ date: targetDate }),
    });
    closeMovePopover();
    await loadDay();
    notify(`「${entry?.title || result.title}」已移到 ${formatMonthDay(result.moved_to)}`);
  } catch (error) {
    reportError(error);
  }
}

function bindTaskMove() {
  const list = $("#taskList");
  if (!list) return;
  let drag = null;
  let ignoreNextClick = false;
  const resetDrag = () => {
    if (!drag) return;
    drag.row.style.transform = "";
    drag.row.classList.remove("is-dragging", "is-move-ready");
    drag = null;
  };
  list.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    if (event.target.closest("button, a, input, textarea, .task-note")) return;
    const row = event.target.closest(".task-row");
    if (!row) return;
    const entry = state.day?.entries?.find((item) => item.id === Number(row.dataset.entryId));
    if (!entry || entry.outcome !== "planned") return;
    drag = {
      pointerId: event.pointerId,
      row,
      entryId: entry.id,
      startX: event.clientX,
      startY: event.clientY,
      active: false,
    };
    row.setPointerCapture?.(event.pointerId);
  });
  list.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (!drag.active) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      if (Math.abs(dy) > Math.abs(dx)) {
        resetDrag();
        return;
      }
      drag.active = true;
      drag.row.classList.add("is-dragging");
    }
    const shift = Math.max(0, Math.min(dx * 0.28, 28));
    drag.row.style.transform = shift ? `translateX(${shift}px)` : "";
    drag.row.classList.toggle("is-move-ready", dx >= 64);
  });
  const finishDrag = (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const dx = event.clientX - drag.startX;
    const ready = drag.active && dx >= 64;
    const row = drag.row;
    const entryId = drag.entryId;
    resetDrag();
    if (!ready) return;
    ignoreNextClick = true;
    openMovePopover(entryId, row);
  };
  list.addEventListener("pointerup", finishDrag);
  list.addEventListener("pointercancel", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    resetDrag();
  });
  $("#moveTaskChoices").addEventListener("click", (event) => {
    const button = event.target.closest("[data-move-date]");
    if (!button) return;
    moveTaskTo(button.dataset.moveDate);
  });
  $("#moveTaskDate").addEventListener("change", (event) => {
    if (!event.target.value) return;
    moveTaskTo(event.target.value);
  });
  document.addEventListener("click", (event) => {
    if (ignoreNextClick) {
      ignoreNextClick = false;
      return;
    }
    const popover = $("#moveTaskPopover");
    if (!popover || popover.hidden) return;
    if (popover.contains(event.target) || event.target.closest(".task-row.is-move-open")) return;
    closeMovePopover();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMovePopover();
  });
}

function initRichNotes() {
  try {
    document.execCommand("defaultParagraphSeparator", false, "p");
  } catch {
    // 个别浏览器不支持默认段落，回车仍然可以换行。
  }
  const imageHandlers = {
    quickMemoContent: (files) => addFilesToBucket(files, "quick"),
    memoContent: (files) => addFilesToBucket(files, "compose"),
    memoEditContent: (files) => addMemoEditImages(files),
  };
  $$(".rich-note").forEach((wrap) => {
    const editor = wrap.querySelector(".rich-note-body");
    const toolbar = wrap.querySelector(".rich-note-toolbar");
    syncRichEmpty(editor);
    editor.addEventListener("input", () => syncRichEmpty(editor));
    editor.addEventListener("keyup", () => updateRichToolbar(wrap));
    editor.addEventListener("mouseup", () => updateRichToolbar(wrap));
    editor.addEventListener("click", (event) => {
      const slot = event.target.closest(".note-slot");
      if (!slot || !editor.contains(slot)) return;
      const range = document.createRange();
      range.selectNodeContents(slot);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    });
    editor.addEventListener("paste", async (event) => {
      const files = [...event.clipboardData.items]
        .filter((item) => item.type.startsWith("image/"))
        .map((item) => item.getAsFile())
        .filter(Boolean);
      const handler = imageHandlers[editor.id];
      if (files.length && handler) {
        event.preventDefault();
        try {
          await handler(files);
        } catch (error) {
          reportError(error);
        }
        return;
      }
      const text = event.clipboardData.getData("text/plain");
      if (!text) return;
      event.preventDefault();
      document.execCommand("insertText", false, text);
      syncRichEmpty(editor);
    });
    toolbar?.addEventListener("mousedown", (event) => {
      if (event.target.closest("button")) event.preventDefault();
    });
    toolbar?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-command]");
      if (!button) return;
      if (button.dataset.command === "template") {
        openTemplateDialog(editor);
        return;
      }
      applyRichCommand(editor, button.dataset.command);
      updateRichToolbar(wrap);
    });
  });
}

function bindEvents() {
  initRichNotes();
  bindTaskMove();
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
    if (button.dataset.action === "copy-link") {
      event.preventDefault();
      event.stopPropagation();
      copyLink(button.dataset.url, button);
      return;
    }
    const entryId = Number(button.dataset.entryId);
    const entry = state.day.entries.find((item) => item.id === entryId);
    if (button.dataset.action === "start") startTimer(entryId, button);
    if (button.dataset.action === "stop") stopTimer(entryId, button);
    if (button.dataset.action === "focus") openFocusDialog(entryId);
    if (button.dataset.action === "toggle-complete") {
      toggleComplete(entryId, button);
    }
    if (button.dataset.action === "edit") openEditDialog(entryId);
    if (button.dataset.action === "task-note" && entry) openTaskNote(entry);
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
  $("#quickMemoTags").addEventListener("input", renderTagPresets);
  $("#memoTags").addEventListener("input", renderTagPresets);
  $("#memoEditTags").addEventListener("input", renderTagPresets);
  document.addEventListener("click", (event) => {
    const preset = event.target.closest(".tag-preset");
    if (!preset) return;
    const input = document.getElementById(
      preset.closest(".tag-presets").dataset.tagInput,
    );
    if (input) applyTagPreset(input, preset.dataset.tag);
  });
  bindImageInput($("#quickImageInput"), (files) => addFilesToBucket(files, "quick"));
  bindImageInput($("#composeImageInput"), (files) =>
    addFilesToBucket(files, "compose"),
  );
  bindImageInput($("#memoEditImageInput"), (files) => addMemoEditImages(files));
  bindImageDrop($(".quick-memo-panel"), (files) => addFilesToBucket(files, "quick"));
  bindImageDrop($(".memo-compose-panel"), (files) =>
    addFilesToBucket(files, "compose"),
  );
  bindImageDrop($("#memoDialog"), (files) => addMemoEditImages(files));
  document.addEventListener("click", async (event) => {
    const view = event.target.closest("[data-action='view-image']");
    if (view) {
      const strip = view.closest(".image-strip");
      const images = [...strip.querySelectorAll("[data-image-id]")].map((item) => ({
        id: Number(item.dataset.imageId),
      }));
      const unique = [];
      const seen = new Set();
      images.forEach((image) => {
        if (!seen.has(image.id)) {
          seen.add(image.id);
          unique.push(image);
        }
      });
      openImageViewer(
        unique,
        unique.findIndex((image) => image.id === Number(view.dataset.imageId)),
      );
      return;
    }
    const pendingView = event.target.closest("[data-action='view-pending']");
    if (pendingView) {
      const list =
        pendingView.dataset.bucket === "quick"
          ? state.pendingQuickImages
          : state.pendingComposeImages;
      openImageViewer(
        list.map((item) => ({ preview: item.prepared.original })),
        list.findIndex((item) => item.localId === pendingView.dataset.localId),
      );
      return;
    }
    const removePending = event.target.closest("[data-action='remove-pending']");
    if (removePending) {
      const key =
        removePending.dataset.bucket === "quick"
          ? "pendingQuickImages"
          : "pendingComposeImages";
      state[key] = state[key].filter(
        (item) => item.localId !== removePending.dataset.localId,
      );
      renderPendingImages();
      return;
    }
    const removeSaved = event.target.closest("[data-action='delete-image']");
    if (removeSaved) {
      event.preventDefault();
      event.stopPropagation();
      try {
        await deleteSavedImage(Number(removeSaved.dataset.imageId));
      } catch (error) {
        reportError(error);
      }
    }
  });
  $("#imageViewerPicture").addEventListener("load", () => fitViewerImage());
  $("#imageViewerPicture").addEventListener("error", () => {
    $("#imageViewerPicture").alt = "原图没有加载出来";
  });
  window.addEventListener("resize", () => {
    if ($("#imageViewer").open) fitViewerImage();
  });
  document.addEventListener("keydown", (event) => {
    if (!$("#imageViewer").open) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepImageViewer(-1);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      stepImageViewer(1);
    }
  });
  $("#closeImageViewer").addEventListener("click", () => $("#imageViewer").close());
  $("#imageViewer").addEventListener("click", (event) => {
    if (event.target === $("#imageViewer")) $("#imageViewer").close();
  });
  $("#previousImage").addEventListener("click", () => stepImageViewer(-1));
  $("#nextImage").addEventListener("click", () => stepImageViewer(1));
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
    if (button.dataset.memoAction === "promote") {
      promoteMemo(button.dataset.memoId, button);
    }
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
  $("#taskNoteForm").addEventListener("submit", submitTaskNote);
  $("#closeTaskNote").addEventListener("click", () => $("#taskNoteDialog").close());
  $("#cancelTaskNote").addEventListener("click", () => $("#taskNoteDialog").close());
  $("#openMemoTemplates").addEventListener("click", () => openTemplateDialog(richEditor("memoContent")));
  $("#templateForm").addEventListener("submit", saveTemplate);
  $("#closeTemplateDialog").addEventListener("click", () => $("#templateDialog").close());
  $("#resetTemplateForm").addEventListener("click", resetTemplateForm);
  $("#templateList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-template-action]");
    if (!button) return;
    const template = state.templates.find(
      (item) => Number(item.id) === Number(button.dataset.templateId),
    );
    if (!template) return;
    if (button.dataset.templateAction === "use") {
      insertTemplate(state.templateTarget || richEditor("memoContent"), template.content);
      $("#templateDialog").close();
    }
    if (button.dataset.templateAction === "edit") {
      state.editingTemplateId = template.id;
      $("#templateName").value = template.name;
      writeRich("templateContent", template.content);
      $("#saveTemplate").textContent = "更新模板";
    }
    if (button.dataset.templateAction === "delete") deleteTemplate(template.id, button);
  });
  $("#saveWeekReview").addEventListener("click", saveReportReview);
  $("#weekChart").addEventListener("click", (event) => {
    const column = event.target.closest("[data-chart-date]");
    if (!column) return;
    state.dayDetailDate = column.dataset.chartDate;
    loadDayDetail();
    $("#dayDetailPanel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  $("#dayDetailDate").addEventListener("change", (event) => {
    if (!event.target.value) return;
    state.dayDetailDate = event.target.value;
    loadDayDetail();
  });
  $("#dayDetailPrevious").addEventListener("click", () => {
    ensureDayDetailDate();
    state.dayDetailDate = shiftDate(state.dayDetailDate, -1);
    loadDayDetail();
  });
  $("#dayDetailNext").addEventListener("click", () => {
    ensureDayDetailDate();
    state.dayDetailDate = shiftDate(state.dayDetailDate, 1);
    loadDayDetail();
  });
  $("#dayDetailYesterday").addEventListener("click", () => {
    state.dayDetailDate = shiftDate(localDateString(new Date()), -1);
    loadDayDetail();
  });
  $("#dayCalendar").addEventListener("click", (event) => {
    const block = event.target.closest("[data-segment-id]");
    if (block) {
      const segment = (state.daySegments || []).find(
        (item) => String(item.id) === block.dataset.segmentId,
      );
      if (segment) openSegmentPopover(segment, block);
      return;
    }
    const day = event.target.closest("[data-cal-date]");
    if (!day || day.dataset.calDate === state.dayDetailDate) return;
    state.dayDetailDate = day.dataset.calDate;
    loadDayDetail();
  });
  $("#closeSegmentPopover").addEventListener("click", closeSegmentPopover);
  $("#editSegmentTask").addEventListener("click", editPopoverTask);
  document.addEventListener("click", (event) => {
    const popover = $("#segmentPopover");
    if (!popover || popover.hidden) return;
    if (popover.contains(event.target) || event.target.closest(".cal-block")) return;
    closeSegmentPopover();
  });

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
  prepareReminderForm();
  $("#reminderForm").addEventListener("submit", submitReminder);
  $("#reminderList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-reminder-action]");
    if (!button) return;
    const reminderId = Number(button.dataset.reminderId);
    if (button.dataset.reminderAction === "edit") {
      state.editingReminderId = reminderId;
      renderReminders();
    }
    if (button.dataset.reminderAction === "cancel-edit") {
      state.editingReminderId = null;
      renderReminders();
    }
    if (button.dataset.reminderAction === "delete") {
      deleteReminder(reminderId, button);
    }
    if (button.dataset.reminderAction === "done") {
      acknowledgeReminder(reminderId);
    }
  });
  $("#reminderList").addEventListener("submit", (event) => {
    const form = event.target.closest("[data-reminder-edit]");
    if (!form) return;
    event.preventDefault();
    saveReminderEdit(form);
  });
  $("#reminderAlert").addEventListener("close", () => {
    if ($("#reminderAlert").returnValue !== "ack") return;
    acknowledgeOpenReminders();
  });
  $("#acknowledgeReminders").addEventListener("click", () => {
    $("#reminderAlert").returnValue = "ack";
  });
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
  loadSuggestedTags();
  refreshReminders();
  switchView(state.view);
  window.setInterval(refreshReminders, 15000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refreshReminders();
  });
  syncStickyOffset();
  window.addEventListener("resize", syncStickyOffset);
  window.setInterval(updateLiveTimers, 1000);
}

initialize();
