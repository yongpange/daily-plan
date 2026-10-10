from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import random
import secrets
import sqlite3
import threading
import webbrowser
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "daily_plan.sqlite3"
LOG_PATH = DATA_DIR / "daily_plan.log"

REASONS = [
    {"value": "underestimated", "label": "估时偏短"},
    {"value": "interrupted", "label": "中途被插入别的事"},
    {"value": "scope_changed", "label": "做着做着范围变大"},
    {"value": "blocked", "label": "在等别人、资料或环境"},
    {"value": "reprioritized", "label": "被更急的事挤掉"},
    {"value": "unclear", "label": "任务没定义清楚，难开工"},
    {"value": "partial", "label": "做了一部分，剩余已明确"},
    {"value": "not_worth_it", "label": "不再值得做"},
]
REASON_VALUES = {item["value"] for item in REASONS}
OUTCOMES = {"planned", "completed", "carried", "rescheduled", "abandoned"}
DATE_FORMAT = "%Y-%m-%d"
ROUTINE_COLOR = "#c47b1a"
ROUTINE_SYMBOLS = ("+", "−", "×", "÷")


class AppError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.message = message
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def valid_date(value: object, field_name: str = "日期") -> str:
    if not isinstance(value, str):
        raise AppError(f"{field_name}格式不正确")
    try:
        return datetime.strptime(value, DATE_FORMAT).date().isoformat()
    except ValueError as exc:
        raise AppError(f"{field_name}格式不正确") from exc


def as_non_negative_int(value: object, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(f"{field_name}需要填写整数") from exc
    if parsed < 0:
        raise AppError(f"{field_name}不能小于 0")
    return parsed


def seconds_between(start_at: str, end_at: str) -> int:
    start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
    return max(0, int((end - start).total_seconds()))


def generate_routine_questions(count: int = 3) -> list[dict]:
    rng = random.SystemRandom()
    questions: list[dict] = []
    prompts: set[str] = set()
    attempts = 0
    while len(questions) < count:
        attempts += 1
        if attempts > 40:
            raise AppError("暂时无法生成题目，请再试一次")
        question = _routine_question(rng)
        if question["prompt"] in prompts:
            continue
        if any(symbol not in question["prompt"] for symbol in ROUTINE_SYMBOLS):
            continue
        prompts.add(question["prompt"])
        questions.append(question)
    return questions


def _routine_question(rng: random.SystemRandom) -> dict:
    divisor = rng.randint(2, 9)
    factor = rng.randint(2, 8)
    inner = rng.randint(2, 12)
    while (inner * factor) % divisor != 0:
        inner += 1
    subtrahend = rng.randint(1, 12)
    total = inner + subtrahend
    left = rng.randint(2, max(2, total - 1))
    right = total - left
    answer = (inner * factor) // divisor
    prompt = f"(({left} + {right}) − {subtrahend}) × {factor} ÷ {divisor}"
    return {"prompt": prompt, "answer": answer}


def period_bounds(anchor: str, period: str) -> tuple[date, date]:
    anchor_date = datetime.strptime(valid_date(anchor), DATE_FORMAT).date()
    if period == "week":
        start = anchor_date - timedelta(days=anchor_date.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = anchor_date.replace(day=1)
        next_month = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return start, next_month - timedelta(days=1)
    if period == "quarter":
        start_month = ((anchor_date.month - 1) // 3) * 3 + 1
        start = date(anchor_date.year, start_month, 1)
        next_start = (
            date(anchor_date.year + 1, 1, 1)
            if start_month == 10
            else date(anchor_date.year, start_month + 3, 1)
        )
        return start, next_start - timedelta(days=1)
    raise AppError("复盘周期不正确")


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as db, db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    color TEXT NOT NULL DEFAULT '#5b6cf9',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                    parent_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                    definition TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'completed', 'abandoned')),
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS plan_entries (
                    id INTEGER PRIMARY KEY,
                    plan_date TEXT NOT NULL,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    estimate_minutes INTEGER NOT NULL DEFAULT 0
                        CHECK (estimate_minutes >= 0),
                    planned_start TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    outcome TEXT NOT NULL DEFAULT 'planned'
                        CHECK (outcome IN (
                            'planned', 'completed', 'carried',
                            'rescheduled', 'abandoned'
                        )),
                    unfinished_reason TEXT,
                    reason_note TEXT NOT NULL DEFAULT '',
                    target_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(plan_date, task_id)
                );

                CREATE TABLE IF NOT EXISTS time_segments (
                    id INTEGER PRIMARY KEY,
                    plan_entry_id INTEGER NOT NULL
                        REFERENCES plan_entries(id) ON DELETE CASCADE,
                    task_id INTEGER NOT NULL
                        REFERENCES tasks(id) ON DELETE CASCADE,
                    start_at TEXT NOT NULL,
                    end_at TEXT,
                    duration_seconds INTEGER
                        CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
                    mode TEXT NOT NULL DEFAULT 'open',
                    target_seconds INTEGER,
                    focus_completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_running_timer
                ON time_segments((1))
                WHERE end_at IS NULL;

                CREATE TABLE IF NOT EXISTS days (
                    plan_date TEXT PRIMARY KEY,
                    focus TEXT NOT NULL DEFAULT '',
                    reflection TEXT NOT NULL DEFAULT '',
                    mood INTEGER CHECK (mood IS NULL OR mood BETWEEN 1 AND 5),
                    closed_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY,
                    period_type TEXT NOT NULL
                        CHECK (period_type IN ('week', 'month', 'quarter')),
                    period_start TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    UNIQUE(period_type, period_start)
                );

                CREATE TABLE IF NOT EXISTS memos (
                    id INTEGER PRIMARY KEY,
                    memo_date TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS plan_entries_by_date
                ON plan_entries(plan_date, sort_order);

                CREATE INDEX IF NOT EXISTS time_segments_by_entry
                ON time_segments(plan_entry_id, start_at);

                CREATE INDEX IF NOT EXISTS memos_by_date
                ON memos(memo_date DESC, created_at DESC);

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS routines (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    estimate_minutes INTEGER NOT NULL DEFAULT 0
                        CHECK (estimate_minutes >= 0),
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_on TEXT NOT NULL,
                    deactivated_on TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS routine_checks (
                    routine_id INTEGER NOT NULL
                        REFERENCES routines(id) ON DELETE CASCADE,
                    plan_date TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (routine_id, plan_date)
                );

                CREATE TABLE IF NOT EXISTS routine_challenges (
                    id TEXT PRIMARY KEY,
                    questions_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    passed INTEGER NOT NULL DEFAULT 0,
                    unlock_token TEXT,
                    unlock_expires_at TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(db, "time_segments", "mode", "TEXT NOT NULL DEFAULT 'open'")
            self._ensure_column(db, "time_segments", "target_seconds", "INTEGER")
            self._ensure_column(
                db,
                "time_segments",
                "focus_completed",
                "INTEGER NOT NULL DEFAULT 0",
            )

    @staticmethod
    def _ensure_column(
        db: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _project_id(db: sqlite3.Connection, name: object) -> int | None:
        if not isinstance(name, str) or not name.strip():
            return None
        clean_name = name.strip()[:80]
        row = db.execute(
            "SELECT id FROM projects WHERE name = ? COLLATE NOCASE", (clean_name,)
        ).fetchone()
        if row:
            return int(row["id"])
        cursor = db.execute(
            "INSERT INTO projects(name, created_at) VALUES (?, ?)",
            (clean_name, utc_now()),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _close_running(db: sqlite3.Connection, now: str) -> sqlite3.Row | None:
        running = db.execute(
            "SELECT id, plan_entry_id, start_at FROM time_segments "
            "WHERE end_at IS NULL"
        ).fetchone()
        if not running:
            return None
        duration = seconds_between(running["start_at"], now)
        db.execute(
            "UPDATE time_segments "
            "SET end_at = ?, duration_seconds = ? WHERE id = ?",
            (now, duration, running["id"]),
        )
        return running

    @staticmethod
    def _expire_focus_timer(
        db: sqlite3.Connection, now: str
    ) -> sqlite3.Row | None:
        running = db.execute(
            """
            SELECT id, plan_entry_id, start_at, target_seconds
            FROM time_segments
            WHERE end_at IS NULL AND mode = 'focus'
            AND target_seconds IS NOT NULL
            """
        ).fetchone()
        if not running:
            return None
        if seconds_between(running["start_at"], now) < int(running["target_seconds"]):
            return None
        start = datetime.fromisoformat(running["start_at"].replace("Z", "+00:00"))
        target_end = (
            start + timedelta(seconds=int(running["target_seconds"]))
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        db.execute(
            """
            UPDATE time_segments
            SET end_at = ?, duration_seconds = ?, focus_completed = 1
            WHERE id = ?
            """,
            (target_end, running["target_seconds"], running["id"]),
        )
        return running

    def _entry(self, db: sqlite3.Connection, entry_id: int) -> dict:
        now = utc_now()
        row = db.execute(
            """
            SELECT
                pe.id, pe.plan_date, pe.estimate_minutes, pe.planned_start,
                pe.sort_order, pe.outcome, pe.unfinished_reason,
                pe.reason_note, pe.target_date,
                t.id AS task_id, t.title, t.parent_id, t.definition,
                t.status AS task_status,
                p.name AS project_name,
                COALESCE((
                    SELECT SUM(
                        CASE
                            WHEN ts.end_at IS NULL THEN
                                CAST((julianday(?) - julianday(ts.start_at))
                                    * 86400 AS INTEGER)
                            ELSE ts.duration_seconds
                        END
                    )
                    FROM time_segments ts
                    WHERE ts.plan_entry_id = pe.id
                ), 0) AS actual_seconds,
                EXISTS(
                    SELECT 1 FROM time_segments running
                    WHERE running.plan_entry_id = pe.id
                    AND running.end_at IS NULL
                ) AS is_running,
                EXISTS(
                    SELECT 1
                    FROM plan_entries child_entry
                    JOIN tasks child_task ON child_task.id = child_entry.task_id
                    WHERE child_task.parent_id = t.id
                    AND child_entry.plan_date = pe.plan_date
                ) AS has_children
            FROM plan_entries pe
            JOIN tasks t ON t.id = pe.task_id
            LEFT JOIN projects p ON p.id = t.project_id
            WHERE pe.id = ?
            """,
            (now, entry_id),
        ).fetchone()
        if not row:
            raise AppError("没有找到这条任务", HTTPStatus.NOT_FOUND)
        return dict(row)

    def get_day(self, plan_date: str) -> dict:
        clean_date = valid_date(plan_date)
        with closing(self.connect()) as db, db:
            self._expire_focus_timer(db, utc_now())
            day = db.execute(
                "SELECT * FROM days WHERE plan_date = ?", (clean_date,)
            ).fetchone()
            entries = db.execute(
                "SELECT id FROM plan_entries WHERE plan_date = ? "
                "ORDER BY sort_order, id",
                (clean_date,),
            ).fetchall()
            projects = [
                dict(row)
                for row in db.execute(
                    "SELECT id, name, color FROM projects ORDER BY name COLLATE NOCASE"
                )
            ]
            running = db.execute(
                """
                SELECT ts.id, ts.plan_entry_id, ts.start_at, ts.mode,
                       ts.target_seconds, pe.plan_date, t.title
                FROM time_segments ts
                JOIN plan_entries pe ON pe.id = ts.plan_entry_id
                JOIN tasks t ON t.id = ts.task_id
                WHERE ts.end_at IS NULL
                """
            ).fetchone()
            segments = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT ts.id, ts.plan_entry_id, ts.start_at, ts.end_at,
                           ts.duration_seconds, ts.mode, ts.target_seconds,
                           ts.focus_completed, t.title,
                           COALESCE(p.name, '未分类') AS project_name
                    FROM time_segments ts
                    JOIN plan_entries pe ON pe.id = ts.plan_entry_id
                    JOIN tasks t ON t.id = ts.task_id
                    LEFT JOIN projects p ON p.id = t.project_id
                    WHERE pe.plan_date = ?
                    ORDER BY ts.start_at DESC, ts.id DESC
                    """,
                    (clean_date,),
                )
            ]
            return {
                "date": clean_date,
                "day": dict(day)
                if day
                else {
                    "plan_date": clean_date,
                    "focus": "",
                    "reflection": "",
                    "mood": None,
                    "closed_at": None,
                },
                "entries": [self._entry(db, int(row["id"])) for row in entries],
                "projects": projects,
                "active_timer": dict(running) if running else None,
                "segments": segments,
                "reasons": REASONS,
                "routines": self._routines_on(db, clean_date),
            }

    def create_entry(self, payload: dict) -> dict:
        plan_date = valid_date(payload.get("date"))
        title = str(payload.get("title", "")).strip()
        if not title:
            raise AppError("请先写下任务名称")
        if len(title) > 240:
            raise AppError("任务名称请控制在 240 个字以内")
        estimate = as_non_negative_int(
            payload.get("estimate_minutes", 0), "预估时间"
        )
        definition = str(payload.get("definition", "")).strip()[:1000]
        parent_entry_id = payload.get("parent_entry_id")
        now = utc_now()

        with closing(self.connect()) as db, db:
            parent_id = None
            inherited_project_id = None
            if parent_entry_id not in (None, ""):
                try:
                    parent_entry_id = int(parent_entry_id)
                except (TypeError, ValueError) as exc:
                    raise AppError("父任务不正确") from exc
                parent = db.execute(
                    """
                    SELECT pe.plan_date, t.id AS task_id, t.project_id
                    FROM plan_entries pe
                    JOIN tasks t ON t.id = pe.task_id
                    WHERE pe.id = ?
                    """,
                    (parent_entry_id,),
                ).fetchone()
                if not parent or parent["plan_date"] != plan_date:
                    raise AppError("父任务不在当前日期中")
                parent_id = int(parent["task_id"])
                inherited_project_id = parent["project_id"]

            project_id = self._project_id(db, payload.get("project_name"))
            if project_id is None:
                project_id = inherited_project_id

            task_cursor = db.execute(
                """
                INSERT INTO tasks(
                    title, project_id, parent_id, definition,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (title, project_id, parent_id, definition, now, now),
            )
            task_id = int(task_cursor.lastrowid)
            next_order = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 "
                "FROM plan_entries WHERE plan_date = ?",
                (plan_date,),
            ).fetchone()[0]
            entry_cursor = db.execute(
                """
                INSERT INTO plan_entries(
                    plan_date, task_id, estimate_minutes, planned_start,
                    sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_date,
                    task_id,
                    estimate,
                    payload.get("planned_start") or None,
                    next_order,
                    now,
                    now,
                ),
            )
            if parent_entry_id is not None:
                # 一旦任务被拆成子任务，父任务只作为容器，避免预估被重复统计。
                db.execute(
                    "UPDATE plan_entries SET estimate_minutes = 0, updated_at = ? "
                    "WHERE id = ?",
                    (now, parent_entry_id),
                )
            return self._entry(db, int(entry_cursor.lastrowid))

    def update_entry(self, entry_id: int, payload: dict) -> dict:
        now = utc_now()
        with closing(self.connect()) as db, db:
            current = self._entry(db, entry_id)
            title = str(payload.get("title", current["title"])).strip()
            if not title:
                raise AppError("任务名称不能为空")
            estimate = as_non_negative_int(
                payload.get("estimate_minutes", current["estimate_minutes"]),
                "预估时间",
            )
            definition = str(
                payload.get("definition", current["definition"])
            ).strip()[:1000]
            project_name = payload.get("project_name", current["project_name"])
            project_id = self._project_id(db, project_name)
            planned_start = payload.get("planned_start", current["planned_start"])
            if planned_start == "":
                planned_start = None
            outcome = payload.get("outcome", current["outcome"])
            if outcome not in OUTCOMES:
                raise AppError("任务状态不正确")

            db.execute(
                """
                UPDATE tasks
                SET title = ?, project_id = ?, definition = ?, updated_at = ?
                WHERE id = ?
                """,
                (title[:240], project_id, definition, now, current["task_id"]),
            )
            db.execute(
                """
                UPDATE plan_entries
                SET estimate_minutes = ?, planned_start = ?,
                    outcome = ?, updated_at = ?
                WHERE id = ?
                """,
                (estimate, planned_start, outcome, now, entry_id),
            )
            if outcome == "completed":
                self._close_entry_timer(db, entry_id, now)
                db.execute(
                    "UPDATE tasks SET status = 'completed', completed_at = ?, "
                    "updated_at = ? WHERE id = ?",
                    (now, now, current["task_id"]),
                )
            elif outcome == "planned":
                db.execute(
                    "UPDATE tasks SET status = 'active', completed_at = NULL, "
                    "updated_at = ? WHERE id = ?",
                    (now, current["task_id"]),
                )
            return self._entry(db, entry_id)

    def delete_entry(self, entry_id: int) -> None:
        with closing(self.connect()) as db, db:
            current = self._entry(db, entry_id)
            used = db.execute(
                "SELECT EXISTS(SELECT 1 FROM time_segments WHERE plan_entry_id = ?)",
                (entry_id,),
            ).fetchone()[0]
            children = db.execute(
                "SELECT EXISTS(SELECT 1 FROM tasks WHERE parent_id = ?)",
                (current["task_id"],),
            ).fetchone()[0]
            if used:
                raise AppError("这条任务已有计时记录，不能删除；可以将它标为放弃")
            if children:
                raise AppError("请先处理它下面的子任务")
            db.execute("DELETE FROM plan_entries WHERE id = ?", (entry_id,))
            remaining = db.execute(
                "SELECT EXISTS(SELECT 1 FROM plan_entries WHERE task_id = ?)",
                (current["task_id"],),
            ).fetchone()[0]
            if not remaining:
                db.execute("DELETE FROM tasks WHERE id = ?", (current["task_id"],))

    @staticmethod
    def _close_entry_timer(
        db: sqlite3.Connection, entry_id: int, now: str
    ) -> bool:
        running = db.execute(
            "SELECT id, start_at FROM time_segments "
            "WHERE plan_entry_id = ? AND end_at IS NULL",
            (entry_id,),
        ).fetchone()
        if not running:
            return False
        db.execute(
            "UPDATE time_segments SET end_at = ?, duration_seconds = ? "
            "WHERE id = ?",
            (now, seconds_between(running["start_at"], now), running["id"]),
        )
        return True

    def start_timer(
        self, entry_id: int, mode: str = "open", focus_minutes: int = 25
    ) -> dict:
        if mode not in {"open", "focus"}:
            raise AppError("计时模式不正确")
        target_seconds = None
        if mode == "focus":
            focus_minutes = as_non_negative_int(focus_minutes, "专注时长")
            if focus_minutes < 5 or focus_minutes > 180:
                raise AppError("单次专注时长需要在 5 到 180 分钟之间")
            target_seconds = focus_minutes * 60
        now = utc_now()
        with closing(self.connect()) as db, db:
            self._expire_focus_timer(db, now)
            entry = self._entry(db, entry_id)
            if entry["outcome"] != "planned":
                raise AppError("只有进行中的任务可以开始计时")
            running = db.execute(
                "SELECT id, plan_entry_id FROM time_segments "
                "WHERE end_at IS NULL"
            ).fetchone()
            if running and int(running["plan_entry_id"]) == entry_id:
                return {
                    "started": entry,
                    "stopped_entry_id": None,
                    "already_running": True,
                }
            stopped = self._close_running(db, now)
            db.execute(
                """
                INSERT INTO time_segments(
                    plan_entry_id, task_id, start_at, mode,
                    target_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    entry["task_id"],
                    now,
                    mode,
                    target_seconds,
                    now,
                ),
            )
            return {
                "started": self._entry(db, entry_id),
                "stopped_entry_id": int(stopped["plan_entry_id"])
                if stopped
                else None,
                "already_running": False,
                "mode": mode,
                "target_seconds": target_seconds,
            }

    def stop_timer(
        self, entry_id: int | None = None, target_reached: bool = False
    ) -> dict:
        now = utc_now()
        with closing(self.connect()) as db, db:
            running = db.execute(
                "SELECT id, plan_entry_id, start_at, mode, target_seconds "
                "FROM time_segments "
                "WHERE end_at IS NULL"
            ).fetchone()
            if not running:
                return {"stopped": False, "entry_id": None}
            if entry_id is not None and int(running["plan_entry_id"]) != entry_id:
                raise AppError("当前计时属于另一条任务")
            duration = seconds_between(running["start_at"], now)
            focus_completed = False
            end_at = now
            if (
                running["mode"] == "focus"
                and running["target_seconds"]
                and (target_reached or duration >= int(running["target_seconds"]))
            ):
                duration = int(running["target_seconds"])
                start = datetime.fromisoformat(
                    running["start_at"].replace("Z", "+00:00")
                )
                end_at = (
                    start + timedelta(seconds=duration)
                ).isoformat(timespec="seconds").replace("+00:00", "Z")
                focus_completed = True
            db.execute(
                "UPDATE time_segments "
                "SET end_at = ?, duration_seconds = ?, focus_completed = ? "
                "WHERE id = ?",
                (end_at, duration, int(focus_completed), running["id"]),
            )
            return {
                "stopped": True,
                "entry_id": int(running["plan_entry_id"]),
                "duration_seconds": duration,
                "mode": running["mode"],
                "focus_completed": focus_completed,
            }

    def update_segment(self, segment_id: int, payload: dict) -> dict:
        duration_minutes = as_non_negative_int(
            payload.get("duration_minutes"), "修正时长"
        )
        if duration_minutes < 1 or duration_minutes > 1440:
            raise AppError("修正时长需要在 1 到 1440 分钟之间")
        with closing(self.connect()) as db, db:
            segment = db.execute(
                """
                SELECT id, start_at, end_at, mode, target_seconds
                FROM time_segments WHERE id = ?
                """,
                (segment_id,),
            ).fetchone()
            if not segment:
                raise AppError("没有找到这段工作记录", HTTPStatus.NOT_FOUND)
            if segment["end_at"] is None:
                raise AppError("请先结束计时，再修正这段记录")
            duration_seconds = duration_minutes * 60
            start = datetime.fromisoformat(
                segment["start_at"].replace("Z", "+00:00")
            )
            end_at = (
                start + timedelta(seconds=duration_seconds)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            focus_completed = int(
                segment["mode"] == "focus"
                and segment["target_seconds"] is not None
                and duration_seconds >= int(segment["target_seconds"])
            )
            db.execute(
                """
                UPDATE time_segments
                SET end_at = ?, duration_seconds = ?, focus_completed = ?
                WHERE id = ?
                """,
                (end_at, duration_seconds, focus_completed, segment_id),
            )
            updated = db.execute(
                "SELECT * FROM time_segments WHERE id = ?", (segment_id,)
            ).fetchone()
            return dict(updated)

    def delete_segment(self, segment_id: int) -> None:
        with closing(self.connect()) as db, db:
            segment = db.execute(
                "SELECT end_at FROM time_segments WHERE id = ?", (segment_id,)
            ).fetchone()
            if not segment:
                raise AppError("没有找到这段工作记录", HTTPStatus.NOT_FOUND)
            if segment["end_at"] is None:
                raise AppError("正在计时的记录不能删除，请先结束计时")
            db.execute("DELETE FROM time_segments WHERE id = ?", (segment_id,))

    def list_memos(
        self, query: str = "", memo_date: str | None = None, limit: int = 100
    ) -> list[dict]:
        clean_query = query.strip()[:200]
        if memo_date:
            memo_date = valid_date(memo_date)
        limit = max(1, min(int(limit), 300))
        clauses = []
        params: list[object] = []
        if clean_query:
            clauses.append("(content LIKE ? OR tags LIKE ?)")
            wildcard = f"%{clean_query}%"
            params.extend([wildcard, wildcard])
        if memo_date:
            clauses.append("memo_date = ?")
            params.append(memo_date)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with closing(self.connect()) as db, db:
            memos = [
                dict(row)
                for row in db.execute(
                    f"""
                    SELECT id, memo_date, content, tags, pinned,
                           created_at, updated_at, 'memo' AS kind
                    FROM memos
                    {where}
                    ORDER BY pinned DESC, memo_date DESC, created_at DESC
                    LIMIT ?
                    """,
                    params,
                )
            ]
            if clean_query and not memo_date:
                reflections = [
                    {
                        "id": row["plan_date"],
                        "memo_date": row["plan_date"],
                        "content": row["reflection"],
                        "tags": "每日复盘",
                        "pinned": 0,
                        "created_at": row["updated_at"],
                        "updated_at": row["updated_at"],
                        "kind": "daily",
                    }
                    for row in db.execute(
                        """
                        SELECT plan_date, reflection, updated_at
                        FROM days
                        WHERE reflection <> '' AND reflection LIKE ?
                        ORDER BY plan_date DESC
                        LIMIT 50
                        """,
                        (f"%{clean_query}%",),
                    )
                ]
                memos.extend(reflections)
                memos.sort(
                    key=lambda item: (
                        int(item["pinned"]),
                        item["memo_date"],
                        item["created_at"],
                    ),
                    reverse=True,
                )
            return memos[:limit]

    def create_memo(self, payload: dict) -> dict:
        memo_date = valid_date(
            payload.get("date") or date.today().isoformat(), "记录日期"
        )
        content = str(payload.get("content", "")).strip()
        if not content:
            raise AppError("先写下一点内容")
        if len(content) > 4000:
            raise AppError("单条感悟请控制在 4000 个字以内")
        tags = str(payload.get("tags", "")).strip()[:300]
        now = utc_now()
        with closing(self.connect()) as db, db:
            cursor = db.execute(
                """
                INSERT INTO memos(
                    memo_date, content, tags, pinned, created_at, updated_at
                ) VALUES (?, ?, ?, 0, ?, ?)
                """,
                (memo_date, content, tags, now, now),
            )
            row = db.execute(
                "SELECT *, 'memo' AS kind FROM memos WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)

    def update_memo(self, memo_id: int, payload: dict) -> dict:
        with closing(self.connect()) as db, db:
            current = db.execute(
                "SELECT * FROM memos WHERE id = ?", (memo_id,)
            ).fetchone()
            if not current:
                raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)
            content = str(payload.get("content", current["content"])).strip()
            if not content:
                raise AppError("感悟内容不能为空")
            tags = str(payload.get("tags", current["tags"])).strip()[:300]
            pinned = int(bool(payload.get("pinned", current["pinned"])))
            memo_date = valid_date(
                payload.get("date", current["memo_date"]), "记录日期"
            )
            db.execute(
                """
                UPDATE memos
                SET memo_date = ?, content = ?, tags = ?, pinned = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (memo_date, content[:4000], tags, pinned, utc_now(), memo_id),
            )
            row = db.execute(
                "SELECT *, 'memo' AS kind FROM memos WHERE id = ?", (memo_id,)
            ).fetchone()
            return dict(row)

    def delete_memo(self, memo_id: int) -> None:
        with closing(self.connect()) as db, db:
            cursor = db.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
            if cursor.rowcount == 0:
                raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)

    def save_day(self, payload: dict) -> dict:
        plan_date = valid_date(payload.get("date"))
        focus = str(payload.get("focus", "")).strip()[:500]
        reflection = str(payload.get("reflection", "")).strip()[:8000]
        mood = payload.get("mood")
        if mood in ("", None):
            mood = None
        else:
            try:
                mood = int(mood)
            except (TypeError, ValueError) as exc:
                raise AppError("状态评分不正确") from exc
            if mood < 1 or mood > 5:
                raise AppError("状态评分需要在 1 到 5 之间")
        now = utc_now()
        with closing(self.connect()) as db, db:
            db.execute(
                """
                INSERT INTO days(plan_date, focus, reflection, mood, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(plan_date) DO UPDATE SET
                    focus = excluded.focus,
                    reflection = excluded.reflection,
                    mood = excluded.mood,
                    updated_at = excluded.updated_at
                """,
                (plan_date, focus, reflection, mood, now),
            )
            row = db.execute(
                "SELECT * FROM days WHERE plan_date = ?", (plan_date,)
            ).fetchone()
            return dict(row)

    def close_day(self, payload: dict) -> dict:
        plan_date = valid_date(payload.get("date"))
        decisions = payload.get("decisions", [])
        if not isinstance(decisions, list):
            raise AppError("收工选择不完整")
        by_id = {}
        for decision in decisions:
            if not isinstance(decision, dict):
                raise AppError("收工选择不完整")
            try:
                by_id[int(decision.get("entry_id"))] = decision
            except (TypeError, ValueError) as exc:
                raise AppError("收工选择不完整") from exc

        now = utc_now()
        with closing(self.connect()) as db, db:
            pending = db.execute(
                """
                SELECT pe.id, pe.task_id, pe.estimate_minutes
                FROM plan_entries pe
                JOIN tasks t ON t.id = pe.task_id
                WHERE pe.plan_date = ? AND pe.outcome = 'planned'
                AND NOT EXISTS(
                    SELECT 1
                    FROM plan_entries child_entry
                    JOIN tasks child_task ON child_task.id = child_entry.task_id
                    WHERE child_task.parent_id = t.id
                    AND child_entry.plan_date = pe.plan_date
                )
                ORDER BY pe.sort_order, pe.id
                """,
                (plan_date,),
            ).fetchall()
            missing = [row["id"] for row in pending if row["id"] not in by_id]
            if missing:
                raise AppError("还有未处理的任务，请为每一条选择去向")

            self.save_day(
                {
                    "date": plan_date,
                    "focus": payload.get("focus", ""),
                    "reflection": payload.get("reflection", ""),
                    "mood": payload.get("mood"),
                }
            )

            for row in pending:
                decision = by_id[int(row["id"])]
                action = decision.get("action")
                if action not in {"completed", "carry", "reschedule", "abandoned"}:
                    raise AppError("请选择任务的去向")
                self._close_entry_timer(db, int(row["id"]), now)

                if action == "completed":
                    db.execute(
                        "UPDATE plan_entries SET outcome = 'completed', "
                        "updated_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    db.execute(
                        "UPDATE tasks SET status = 'completed', completed_at = ?, "
                        "updated_at = ? WHERE id = ?",
                        (now, now, row["task_id"]),
                    )
                    continue

                reason = decision.get("reason")
                if reason not in REASON_VALUES:
                    raise AppError("未完成的任务需要选择原因")
                note = str(decision.get("note", "")).strip()[:1000]

                if action == "abandoned":
                    db.execute(
                        """
                        UPDATE plan_entries
                        SET outcome = 'abandoned', unfinished_reason = ?,
                            reason_note = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (reason, note, now, row["id"]),
                    )
                    db.execute(
                        "UPDATE tasks SET status = 'abandoned', updated_at = ? "
                        "WHERE id = ?",
                        (now, row["task_id"]),
                    )
                    continue

                target_date = valid_date(
                    decision.get("target_date"), "顺延日期"
                )
                if target_date <= plan_date:
                    raise AppError("顺延日期需要晚于当前日期")
                outcome = "carried" if action == "carry" else "rescheduled"
                db.execute(
                    """
                    UPDATE plan_entries
                    SET outcome = ?, unfinished_reason = ?, reason_note = ?,
                        target_date = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (outcome, reason, note, target_date, now, row["id"]),
                )
                next_estimate = as_non_negative_int(
                    decision.get("next_estimate_minutes", row["estimate_minutes"]),
                    "下次预估时间",
                )
                next_order = db.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 "
                    "FROM plan_entries WHERE plan_date = ?",
                    (target_date,),
                ).fetchone()[0]
                db.execute(
                    """
                    INSERT INTO plan_entries(
                        plan_date, task_id, estimate_minutes, sort_order,
                        outcome, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'planned', ?, ?)
                    ON CONFLICT(plan_date, task_id) DO UPDATE SET
                        estimate_minutes = excluded.estimate_minutes,
                        outcome = 'planned',
                        updated_at = excluded.updated_at
                    """,
                    (
                        target_date,
                        row["task_id"],
                        next_estimate,
                        next_order,
                        now,
                        now,
                    ),
                )
                db.execute(
                    "UPDATE tasks SET status = 'active', completed_at = NULL, "
                    "updated_at = ? WHERE id = ?",
                    (now, row["task_id"]),
                )

            self._resolve_parent_entries(db, plan_date, now)
            db.execute(
                "UPDATE days SET closed_at = ?, updated_at = ? "
                "WHERE plan_date = ?",
                (now, now, plan_date),
            )
        return self.get_day(plan_date)

    @staticmethod
    def _resolve_parent_entries(
        db: sqlite3.Connection, plan_date: str, now: str
    ) -> None:
        """根据叶子任务的去向收拢父任务，并在顺延日期保留任务树。"""
        for _ in range(8):
            parents = db.execute(
                """
                SELECT pe.id, pe.task_id
                FROM plan_entries pe
                WHERE pe.plan_date = ? AND pe.outcome = 'planned'
                AND EXISTS(
                    SELECT 1
                    FROM plan_entries child_entry
                    JOIN tasks child_task ON child_task.id = child_entry.task_id
                    WHERE child_task.parent_id = pe.task_id
                    AND child_entry.plan_date = pe.plan_date
                )
                """,
                (plan_date,),
            ).fetchall()
            changed = False
            for parent in parents:
                children = db.execute(
                    """
                    SELECT child_entry.outcome, child_entry.target_date
                    FROM plan_entries child_entry
                    JOIN tasks child_task ON child_task.id = child_entry.task_id
                    WHERE child_task.parent_id = ?
                    AND child_entry.plan_date = ?
                    """,
                    (parent["task_id"], plan_date),
                ).fetchall()
                if not children or any(row["outcome"] == "planned" for row in children):
                    continue
                changed = True
                if all(row["outcome"] == "completed" for row in children):
                    db.execute(
                        "UPDATE plan_entries SET outcome = 'completed', "
                        "updated_at = ? WHERE id = ?",
                        (now, parent["id"]),
                    )
                    db.execute(
                        "UPDATE tasks SET status = 'completed', completed_at = ?, "
                        "updated_at = ? WHERE id = ?",
                        (now, now, parent["task_id"]),
                    )
                    continue

                target_dates = sorted(
                    {
                        row["target_date"]
                        for row in children
                        if row["target_date"]
                        and row["outcome"] in {"carried", "rescheduled"}
                    }
                )
                if target_dates:
                    db.execute(
                        """
                        UPDATE plan_entries
                        SET outcome = 'carried', unfinished_reason = NULL,
                            target_date = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (target_dates[0], now, parent["id"]),
                    )
                    for target_date in target_dates:
                        next_order = db.execute(
                            "SELECT COALESCE(MAX(sort_order), 0) + 1 "
                            "FROM plan_entries WHERE plan_date = ?",
                            (target_date,),
                        ).fetchone()[0]
                        db.execute(
                            """
                            INSERT INTO plan_entries(
                                plan_date, task_id, estimate_minutes, sort_order,
                                outcome, created_at, updated_at
                            ) VALUES (?, ?, 0, ?, 'planned', ?, ?)
                            ON CONFLICT(plan_date, task_id) DO UPDATE SET
                                estimate_minutes = 0,
                                outcome = 'planned',
                                updated_at = excluded.updated_at
                            """,
                            (
                                target_date,
                                parent["task_id"],
                                next_order,
                                now,
                                now,
                            ),
                        )
                    db.execute(
                        "UPDATE tasks SET status = 'active', completed_at = NULL, "
                        "updated_at = ? WHERE id = ?",
                        (now, parent["task_id"]),
                    )
                else:
                    db.execute(
                        """
                        UPDATE plan_entries
                        SET outcome = 'abandoned',
                            unfinished_reason = 'not_worth_it',
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, parent["id"]),
                    )
                    db.execute(
                        "UPDATE tasks SET status = 'abandoned', updated_at = ? "
                        "WHERE id = ?",
                        (now, parent["task_id"]),
                    )
            if not changed:
                break

    def get_week(self, anchor: str) -> dict:
        anchor_date = datetime.strptime(valid_date(anchor), DATE_FORMAT).date()
        monday = anchor_date - timedelta(days=anchor_date.weekday())
        sunday = monday + timedelta(days=6)
        start = monday.isoformat()
        end = sunday.isoformat()
        now = utc_now()

        with closing(self.connect()) as db, db:
            rows = db.execute(
                """
                SELECT
                    pe.plan_date,
                    SUM(CASE WHEN NOT EXISTS(
                        SELECT 1
                        FROM plan_entries child_entry
                        JOIN tasks child_task
                            ON child_task.id = child_entry.task_id
                        WHERE child_task.parent_id = t.id
                        AND child_entry.plan_date = pe.plan_date
                    ) THEN pe.estimate_minutes ELSE 0 END) AS estimate_minutes,
                    SUM(CASE WHEN pe.outcome = 'completed' AND NOT EXISTS(
                        SELECT 1
                        FROM plan_entries child_entry
                        JOIN tasks child_task
                            ON child_task.id = child_entry.task_id
                        WHERE child_task.parent_id = t.id
                        AND child_entry.plan_date = pe.plan_date
                    ) THEN 1 ELSE 0 END) AS completed_count,
                    SUM(CASE WHEN NOT EXISTS(
                        SELECT 1
                        FROM plan_entries child_entry
                        JOIN tasks child_task
                            ON child_task.id = child_entry.task_id
                        WHERE child_task.parent_id = t.id
                        AND child_entry.plan_date = pe.plan_date
                    ) THEN 1 ELSE 0 END) AS total_count,
                    COALESCE(SUM((
                        SELECT SUM(
                            CASE
                                WHEN ts.end_at IS NULL THEN
                                    CAST((julianday(?) - julianday(ts.start_at))
                                        * 86400 AS INTEGER)
                                ELSE ts.duration_seconds
                            END
                        )
                        FROM time_segments ts
                        WHERE ts.plan_entry_id = pe.id
                    )), 0) AS actual_seconds
                FROM plan_entries pe
                JOIN tasks t ON t.id = pe.task_id
                WHERE pe.plan_date BETWEEN ? AND ?
                GROUP BY pe.plan_date
                """,
                (now, start, end),
            ).fetchall()
            by_date = {row["plan_date"]: dict(row) for row in rows}
            days = []
            for offset in range(7):
                current = monday + timedelta(days=offset)
                item = by_date.get(current.isoformat())
                days.append(
                    item
                    or {
                        "plan_date": current.isoformat(),
                        "estimate_minutes": 0,
                        "actual_seconds": 0,
                        "completed_count": 0,
                        "total_count": 0,
                    }
                )

            reasons = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT unfinished_reason AS reason, COUNT(*) AS count
                    FROM plan_entries
                    WHERE plan_date BETWEEN ? AND ?
                    AND unfinished_reason IS NOT NULL
                    GROUP BY unfinished_reason
                    ORDER BY count DESC
                    """,
                    (start, end),
                )
            ]
            reason_labels = {item["value"]: item["label"] for item in REASONS}
            for item in reasons:
                item["label"] = reason_labels.get(item["reason"], item["reason"])

            projects = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT
                        COALESCE(p.name, '未分类') AS project_name,
                        SUM(CASE WHEN NOT EXISTS(
                            SELECT 1
                            FROM plan_entries child_entry
                            JOIN tasks child_task
                                ON child_task.id = child_entry.task_id
                            WHERE child_task.parent_id = t.id
                            AND child_entry.plan_date = pe.plan_date
                        ) THEN pe.estimate_minutes ELSE 0 END)
                            AS estimate_minutes,
                        COALESCE(SUM((
                            SELECT SUM(
                                CASE
                                    WHEN ts.end_at IS NULL THEN
                                        CAST((julianday(?) - julianday(ts.start_at))
                                            * 86400 AS INTEGER)
                                    ELSE ts.duration_seconds
                                END
                            )
                            FROM time_segments ts
                            WHERE ts.plan_entry_id = pe.id
                        )), 0) AS actual_seconds
                    FROM plan_entries pe
                    JOIN tasks t ON t.id = pe.task_id
                    LEFT JOIN projects p ON p.id = t.project_id
                    WHERE pe.plan_date BETWEEN ? AND ?
                    GROUP BY COALESCE(p.name, '未分类')
                    ORDER BY actual_seconds DESC
                    """,
                    (now, start, end),
                )
            ]

            carryovers = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT t.id AS task_id, t.title, COUNT(*) AS carry_count,
                           MAX(pe.target_date) AS latest_target_date
                    FROM plan_entries pe
                    JOIN tasks t ON t.id = pe.task_id
                    WHERE pe.outcome IN ('carried', 'rescheduled')
                    AND t.status = 'active'
                    GROUP BY t.id, t.title
                    HAVING COUNT(*) >= 2
                    ORDER BY carry_count DESC, t.title
                    """
                )
            ]
            review = db.execute(
                "SELECT content FROM reviews "
                "WHERE period_type = 'week' AND period_start = ?",
                (start,),
            ).fetchone()
            return {
                "start": start,
                "end": end,
                "days": days,
                "reasons": reasons,
                "projects": projects,
                "carryovers": carryovers,
                "review": review["content"] if review else "",
            }

    def get_report(self, anchor: str, period: str) -> dict:
        start_date, end_date = period_bounds(anchor, period)
        start = start_date.isoformat()
        end = end_date.isoformat()
        now = utc_now()
        with closing(self.connect()) as db, db:
            self._expire_focus_timer(db, now)
            rows = db.execute(
                """
                SELECT
                    pe.plan_date,
                    SUM(CASE WHEN NOT EXISTS(
                        SELECT 1
                        FROM plan_entries child_entry
                        JOIN tasks child_task
                            ON child_task.id = child_entry.task_id
                        WHERE child_task.parent_id = t.id
                        AND child_entry.plan_date = pe.plan_date
                    ) THEN pe.estimate_minutes ELSE 0 END) AS estimate_minutes,
                    SUM(CASE WHEN pe.outcome = 'completed' AND NOT EXISTS(
                        SELECT 1
                        FROM plan_entries child_entry
                        JOIN tasks child_task
                            ON child_task.id = child_entry.task_id
                        WHERE child_task.parent_id = t.id
                        AND child_entry.plan_date = pe.plan_date
                    ) THEN 1 ELSE 0 END) AS completed_count,
                    SUM(CASE WHEN NOT EXISTS(
                        SELECT 1
                        FROM plan_entries child_entry
                        JOIN tasks child_task
                            ON child_task.id = child_entry.task_id
                        WHERE child_task.parent_id = t.id
                        AND child_entry.plan_date = pe.plan_date
                    ) THEN 1 ELSE 0 END) AS total_count,
                    COALESCE(SUM((
                        SELECT SUM(
                            CASE
                                WHEN ts.end_at IS NULL THEN
                                    CAST((julianday(?) - julianday(ts.start_at))
                                        * 86400 AS INTEGER)
                                ELSE ts.duration_seconds
                            END
                        )
                        FROM time_segments ts
                        WHERE ts.plan_entry_id = pe.id
                    )), 0) AS actual_seconds,
                    COALESCE(SUM((
                        SELECT COUNT(*)
                        FROM time_segments focus_segment
                        WHERE focus_segment.plan_entry_id = pe.id
                        AND focus_segment.focus_completed = 1
                    )), 0) AS focus_count
                FROM plan_entries pe
                JOIN tasks t ON t.id = pe.task_id
                WHERE pe.plan_date BETWEEN ? AND ?
                GROUP BY pe.plan_date
                """,
                (now, start, end),
            ).fetchall()
            by_date = {row["plan_date"]: dict(row) for row in rows}
            days = []
            cursor = start_date
            while cursor <= end_date:
                days.append(
                    by_date.get(cursor.isoformat())
                    or {
                        "plan_date": cursor.isoformat(),
                        "estimate_minutes": 0,
                        "actual_seconds": 0,
                        "completed_count": 0,
                        "total_count": 0,
                        "focus_count": 0,
                    }
                )
                cursor += timedelta(days=1)

            reasons = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT unfinished_reason AS reason, COUNT(*) AS count
                    FROM plan_entries
                    WHERE plan_date BETWEEN ? AND ?
                    AND unfinished_reason IS NOT NULL
                    GROUP BY unfinished_reason
                    ORDER BY count DESC
                    """,
                    (start, end),
                )
            ]
            reason_labels = {item["value"]: item["label"] for item in REASONS}
            for item in reasons:
                item["label"] = reason_labels.get(item["reason"], item["reason"])

            projects = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT
                        COALESCE(p.name, '未分类') AS project_name,
                        SUM(CASE WHEN NOT EXISTS(
                            SELECT 1
                            FROM plan_entries child_entry
                            JOIN tasks child_task
                                ON child_task.id = child_entry.task_id
                            WHERE child_task.parent_id = t.id
                            AND child_entry.plan_date = pe.plan_date
                        ) THEN pe.estimate_minutes ELSE 0 END)
                            AS estimate_minutes,
                        COALESCE(SUM((
                            SELECT SUM(
                                CASE
                                    WHEN ts.end_at IS NULL THEN
                                        CAST((julianday(?) - julianday(ts.start_at))
                                            * 86400 AS INTEGER)
                                    ELSE ts.duration_seconds
                                END
                            )
                            FROM time_segments ts
                            WHERE ts.plan_entry_id = pe.id
                        )), 0) AS actual_seconds,
                        SUM(CASE WHEN pe.outcome = 'completed' AND NOT EXISTS(
                            SELECT 1
                            FROM plan_entries child_entry
                            JOIN tasks child_task
                                ON child_task.id = child_entry.task_id
                            WHERE child_task.parent_id = t.id
                            AND child_entry.plan_date = pe.plan_date
                        ) THEN 1 ELSE 0 END) AS completed_count,
                        SUM(CASE WHEN NOT EXISTS(
                            SELECT 1
                            FROM plan_entries child_entry
                            JOIN tasks child_task
                                ON child_task.id = child_entry.task_id
                            WHERE child_task.parent_id = t.id
                            AND child_entry.plan_date = pe.plan_date
                        ) THEN 1 ELSE 0 END) AS total_count
                    FROM plan_entries pe
                    JOIN tasks t ON t.id = pe.task_id
                    LEFT JOIN projects p ON p.id = t.project_id
                    WHERE pe.plan_date BETWEEN ? AND ?
                    GROUP BY COALESCE(p.name, '未分类')
                    ORDER BY actual_seconds DESC
                    """,
                    (now, start, end),
                )
            ]

            carryovers = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT t.id AS task_id, t.title, COUNT(*) AS carry_count,
                           MAX(pe.target_date) AS latest_target_date
                    FROM plan_entries pe
                    JOIN tasks t ON t.id = pe.task_id
                    WHERE pe.plan_date BETWEEN ? AND ?
                    AND pe.outcome IN ('carried', 'rescheduled')
                    GROUP BY t.id, t.title
                    HAVING COUNT(*) >= 2
                    ORDER BY carry_count DESC, t.title
                    """,
                    (start, end),
                )
            ]
            focus = db.execute(
                """
                SELECT
                    COUNT(*) AS segment_count,
                    COALESCE(SUM(ts.focus_completed), 0) AS completed_count,
                    COALESCE(SUM(ts.duration_seconds), 0) AS actual_seconds
                FROM time_segments ts
                JOIN plan_entries pe ON pe.id = ts.plan_entry_id
                WHERE pe.plan_date BETWEEN ? AND ?
                AND ts.mode = 'focus'
                """,
                (start, end),
            ).fetchone()

            longest_streak = 0
            current_streak = 0
            for item in days:
                if int(item["actual_seconds"] or 0) > 0:
                    current_streak += 1
                    longest_streak = max(longest_streak, current_streak)
                else:
                    current_streak = 0

            planned = sum(int(item["estimate_minutes"] or 0) for item in days)
            actual_seconds = sum(int(item["actual_seconds"] or 0) for item in days)
            total_count = sum(int(item["total_count"] or 0) for item in days)
            completed_count = sum(
                int(item["completed_count"] or 0) for item in days
            )
            insights = self._build_insights(
                planned,
                actual_seconds,
                completed_count,
                total_count,
                reasons,
                projects,
                carryovers,
                int(focus["completed_count"] or 0),
            )
            review = db.execute(
                """
                SELECT content FROM reviews
                WHERE period_type = ? AND period_start = ?
                """,
                (period, start),
            ).fetchone()
            return {
                "period": period,
                "start": start,
                "end": end,
                "days": days,
                "reasons": reasons,
                "projects": projects,
                "carryovers": carryovers,
                "focus": {
                    **dict(focus),
                    "longest_streak": longest_streak,
                },
                "insights": insights,
                "review": review["content"] if review else "",
                "routines": self._routine_report(db, start_date, end_date),
            }

    @staticmethod
    def _build_insights(
        planned_minutes: int,
        actual_seconds: int,
        completed_count: int,
        total_count: int,
        reasons: list[dict],
        projects: list[dict],
        carryovers: list[dict],
        focus_completed: int,
    ) -> list[dict]:
        insights = []
        actual_minutes = actual_seconds / 60
        if not total_count and not actual_seconds:
            return [
                {
                    "tone": "neutral",
                    "title": "还没有足够数据",
                    "body": "先安排任务并完成几次计时，系统会从估时偏差和顺延原因中提炼规律。",
                }
            ]
        if planned_minutes and actual_seconds:
            ratio = actual_minutes / planned_minutes
            if ratio >= 1.2:
                insights.append(
                    {
                        "tone": "warning",
                        "title": "整体估时偏短",
                        "body": (
                            f"实际投入是计划的 {ratio:.1f} 倍。"
                            f"下个周期可先把类似任务预估乘以 {min(ratio, 2.5):.1f}。"
                        ),
                    }
                )
            elif ratio <= 0.65:
                insights.append(
                    {
                        "tone": "info",
                        "title": "计划容量高于实际投入",
                        "body": (
                            f"实际只达到计划的 {ratio:.0%}。"
                            "减少当天任务数量，比继续压缩单项预估更有帮助。"
                        ),
                    }
                )
            else:
                insights.append(
                    {
                        "tone": "positive",
                        "title": "估时处在可信区间",
                        "body": f"实际与计划的比例是 {ratio:.0%}，可以继续沿用当前估时方式。",
                    }
                )
        if total_count:
            rate = completed_count / total_count
            if rate < 0.6:
                insights.append(
                    {
                        "tone": "warning",
                        "title": "承诺完成率偏低",
                        "body": f"本周期完成了 {completed_count}/{total_count} 条安排，建议每天只保留最重要的 3 项。",
                    }
                )
        if reasons:
            top = reasons[0]
            insights.append(
                {
                    "tone": "info",
                    "title": f"最常见阻碍：{top['label']}",
                    "body": f"共出现 {top['count']} 次。下次规划前先检查这一项是否已经被消除。",
                }
            )
        project_candidates = [
            item
            for item in projects
            if int(item["estimate_minutes"] or 0) >= 30
            and int(item["actual_seconds"] or 0) > 0
        ]
        if project_candidates:
            most_underestimated = max(
                project_candidates,
                key=lambda item: (item["actual_seconds"] / 60)
                / item["estimate_minutes"],
            )
            project_ratio = (
                most_underestimated["actual_seconds"]
                / 60
                / most_underestimated["estimate_minutes"]
            )
            if project_ratio >= 1.25:
                insights.append(
                    {
                        "tone": "warning",
                        "title": f"{most_underestimated['project_name']} 最容易低估",
                        "body": f"该项目实际约为预估的 {project_ratio:.1f} 倍，建议建立单独的估时系数。",
                    }
                )
        if carryovers:
            top = carryovers[0]
            insights.append(
                {
                    "tone": "warning",
                    "title": "有任务被反复顺延",
                    "body": f"“{top['title']}”已顺延 {top['carry_count']} 次，建议重新定义完成标准或直接放弃。",
                }
            )
        if focus_completed:
            insights.append(
                {
                    "tone": "positive",
                    "title": f"完成 {focus_completed} 个完整专注段",
                    "body": "完整专注段会计入趋势，短暂停止仍保留为实际工作时间。",
                }
            )
        return insights[:6]

    def save_period_review(self, payload: dict) -> dict:
        period = str(payload.get("period", "week"))
        if period not in {"week", "month", "quarter"}:
            raise AppError("复盘周期不正确")
        period_start = valid_date(payload.get("start"), "周期开始日期")
        content = str(payload.get("content", "")).strip()[:10000]
        now = utc_now()
        with closing(self.connect()) as db, db:
            db.execute(
                """
                INSERT INTO reviews(period_type, period_start, content, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(period_type, period_start) DO UPDATE SET
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                (period, period_start, content, now),
            )
        return {
            "period": period,
            "start": period_start,
            "content": content,
        }

    def save_week_review(self, payload: dict) -> dict:
        period_start = valid_date(payload.get("start"), "周开始日期")
        content = str(payload.get("content", "")).strip()[:10000]
        now = utc_now()
        with closing(self.connect()) as db, db:
            db.execute(
                """
                INSERT INTO reviews(period_type, period_start, content, updated_at)
                VALUES ('week', ?, ?, ?)
                ON CONFLICT(period_type, period_start) DO UPDATE SET
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                (period_start, content, now),
            )
        return {"start": period_start, "content": content}

    def get_settings(self) -> dict:
        with closing(self.connect()) as db:
            return {
                "profile": self._profile(db),
                "routines": self._active_routines(db),
            }

    def save_settings(self, payload: dict) -> dict:
        profile = payload.get("profile", payload)
        if not isinstance(profile, dict):
            raise AppError("个人资料格式不正确")
        display_name = str(profile.get("display_name", "")).strip()[:40]
        avatar = str(profile.get("avatar_data", "")).strip()
        if avatar and (
            len(avatar) > 500_000
            or not avatar.startswith("data:image/")
            or ";base64," not in avatar
        ):
            raise AppError("头像需要是较小的图片")
        focus_minutes = as_non_negative_int(
            profile.get("focus_minutes", 25), "专注时长"
        )
        break_minutes = as_non_negative_int(
            profile.get("break_minutes", 5), "休息时长"
        )
        if focus_minutes < 5 or focus_minutes > 180:
            raise AppError("默认专注时长需要在 5 到 180 分钟之间")
        if break_minutes < 1 or break_minutes > 60:
            raise AppError("默认休息时长需要在 1 到 60 分钟之间")
        now = utc_now()
        values = {
            "display_name": display_name,
            "avatar_data": avatar,
            "focus_minutes": str(focus_minutes),
            "break_minutes": str(break_minutes),
        }
        with closing(self.connect()) as db, db:
            for key, value in values.items():
                db.execute(
                    """
                    INSERT INTO app_settings(key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value, now),
                )
            return self._profile(db)

    def create_routine(self, payload: dict) -> dict:
        title, note, estimate = self._routine_fields(payload)
        now = utc_now()
        today = date.today().isoformat()
        with closing(self.connect()) as db, db:
            sort_order = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM routines"
            ).fetchone()[0]
            cursor = db.execute(
                """
                INSERT INTO routines(
                    title, note, estimate_minutes, sort_order, active,
                    created_on, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (title, note, estimate, sort_order, today, now, now),
            )
            return self._routine_by_id(db, int(cursor.lastrowid))

    def update_routine(self, routine_id: int, payload: dict) -> dict:
        title, note, estimate = self._routine_fields(payload, partial=True)
        with closing(self.connect()) as db, db:
            self._require_routine_unlock(db, payload.get("unlock_token"))
            current = db.execute(
                "SELECT * FROM routines WHERE id = ? AND active = 1",
                (routine_id,),
            ).fetchone()
            if not current:
                raise AppError("没有找到这项每日必做", HTTPStatus.NOT_FOUND)
            db.execute(
                """
                UPDATE routines
                SET title = ?, note = ?, estimate_minutes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title if title is not None else current["title"],
                    note if note is not None else current["note"],
                    estimate
                    if estimate is not None
                    else current["estimate_minutes"],
                    utc_now(),
                    routine_id,
                ),
            )
            return self._routine_by_id(db, routine_id)

    def delete_routine(self, routine_id: int, unlock_token: object) -> None:
        with closing(self.connect()) as db, db:
            self._require_routine_unlock(db, unlock_token)
            cursor = db.execute(
                """
                UPDATE routines
                SET active = 0, deactivated_on = ?, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (date.today().isoformat(), utc_now(), routine_id),
            )
            if cursor.rowcount == 0:
                raise AppError("没有找到这项每日必做", HTTPStatus.NOT_FOUND)

    def create_routine_challenge(self) -> dict:
        questions = generate_routine_questions()
        challenge_id = secrets.token_urlsafe(18)
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(minutes=10)).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        with closing(self.connect()) as db, db:
            db.execute(
                "DELETE FROM routine_challenges WHERE expires_at < ?",
                (utc_now(),),
            )
            db.execute(
                """
                INSERT INTO routine_challenges(
                    id, questions_json, expires_at, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    challenge_id,
                    json.dumps(questions, ensure_ascii=False),
                    expires,
                    utc_now(),
                ),
            )
        return {
            "id": challenge_id,
            "expires_at": expires,
            "questions": [
                {"prompt": item["prompt"]} for item in questions
            ],
        }

    def verify_routine_challenge(self, payload: dict) -> dict:
        challenge_id = str(payload.get("id", "")).strip()
        answers = payload.get("answers")
        if not challenge_id or not isinstance(answers, list):
            raise AppError("请完成全部题目")
        with closing(self.connect()) as db, db:
            row = db.execute(
                "SELECT * FROM routine_challenges WHERE id = ?",
                (challenge_id,),
            ).fetchone()
            if not row or row["expires_at"] < utc_now():
                raise AppError("这组题目已过期，请重新出题")
            questions = json.loads(row["questions_json"])
            if len(answers) != len(questions):
                raise AppError("请完成全部题目")
            parsed = [_as_whole_number(item, "答案") for item in answers]
            if any(parsed[index] != int(item["answer"]) for index, item in enumerate(questions)):
                raise AppError("三道题需要全部答对，才能修改每日必做")
            token = secrets.token_urlsafe(24)
            unlock_expires = (
                datetime.now(timezone.utc) + timedelta(minutes=10)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            db.execute(
                """
                UPDATE routine_challenges
                SET passed = 1, unlock_token = ?, unlock_expires_at = ?
                WHERE id = ?
                """,
                (token, unlock_expires, challenge_id),
            )
            return {"unlocked": True, "unlock_token": token, "expires_at": unlock_expires}

    def set_routine_check(self, payload: dict) -> dict:
        routine_id = as_non_negative_int(payload.get("routine_id"), "每日必做")
        plan_date = valid_date(payload.get("date"))
        if plan_date > date.today().isoformat():
            raise AppError("还没到这一天，不能提前打卡")
        completed = bool(payload.get("completed"))
        with closing(self.connect()) as db, db:
            routine = db.execute(
                "SELECT * FROM routines WHERE id = ?", (routine_id,)
            ).fetchone()
            if not routine or not routine["active"]:
                raise AppError("没有找到这项每日必做", HTTPStatus.NOT_FOUND)
            if plan_date < routine["created_on"]:
                raise AppError("这一天还没有这项每日必做")
            if routine["deactivated_on"] and plan_date >= routine["deactivated_on"]:
                raise AppError("这项每日必做已经停用")
            if completed:
                db.execute(
                    """
                    INSERT INTO routine_checks(routine_id, plan_date, completed_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(routine_id, plan_date) DO UPDATE SET
                        completed_at = excluded.completed_at
                    """,
                    (routine_id, plan_date, utc_now()),
                )
            else:
                db.execute(
                    "DELETE FROM routine_checks WHERE routine_id = ? AND plan_date = ?",
                    (routine_id, plan_date),
                )
            return {"date": plan_date, "routines": self._routines_on(db, plan_date)}

    @staticmethod
    def _profile(db: sqlite3.Connection) -> dict:
        rows = {
            row["key"]: row["value"]
            for row in db.execute("SELECT key, value FROM app_settings")
        }
        try:
            focus_minutes = int(rows.get("focus_minutes", "25"))
        except ValueError:
            focus_minutes = 25
        try:
            break_minutes = int(rows.get("break_minutes", "5"))
        except ValueError:
            break_minutes = 5
        return {
            "display_name": rows.get("display_name", ""),
            "avatar_data": rows.get("avatar_data", ""),
            "focus_minutes": focus_minutes,
            "break_minutes": break_minutes,
        }

    @staticmethod
    def _routine_fields(
        payload: dict, partial: bool = False
    ) -> tuple[str | None, str | None, int | None]:
        has_title = "title" in payload or not partial
        title = str(payload.get("title", "")).strip() if has_title else None
        if title is not None:
            if not title:
                raise AppError("先写下每日必做的名称")
            if len(title) > 80:
                raise AppError("每日必做的名称请控制在 80 个字以内")
        note = str(payload.get("note", "")).strip()[:200] if "note" in payload or not partial else None
        estimate = None
        if "estimate_minutes" in payload or not partial:
            estimate = as_non_negative_int(
                payload.get("estimate_minutes", 0), "预估分钟"
            )
            if estimate > 240:
                raise AppError("单项每日必做的预估不要超过 240 分钟")
        return title, note, estimate

    def _require_routine_unlock(self, db: sqlite3.Connection, token: object) -> None:
        if not isinstance(token, str) or len(token) < 20:
            raise AppError("修改每日必做前，需要先答对 3 道题")
        row = db.execute(
            """
            SELECT unlock_expires_at FROM routine_challenges
            WHERE unlock_token = ? AND passed = 1
            """,
            (token,),
        ).fetchone()
        if not row or not row["unlock_expires_at"] or row["unlock_expires_at"] < utc_now():
            raise AppError("修改时间已过，请重新答题")

    @staticmethod
    def _active_routines(db: sqlite3.Connection) -> list[dict]:
        return [
            Database._public_routine(row)
            for row in db.execute(
                """
                SELECT * FROM routines
                WHERE active = 1
                ORDER BY sort_order, id
                """
            )
        ]

    @staticmethod
    def _routine_by_id(db: sqlite3.Connection, routine_id: int) -> dict:
        row = db.execute(
            "SELECT * FROM routines WHERE id = ?", (routine_id,)
        ).fetchone()
        if not row:
            raise AppError("没有找到这项每日必做", HTTPStatus.NOT_FOUND)
        return Database._public_routine(row)

    @staticmethod
    def _public_routine(row: sqlite3.Row, completed: bool = False) -> dict:
        return {
            "id": int(row["id"]),
            "title": row["title"],
            "note": row["note"],
            "estimate_minutes": int(row["estimate_minutes"]),
            "color": ROUTINE_COLOR,
            "created_on": row["created_on"],
            "active": bool(row["active"]),
            "completed": completed,
            "locked": True,
        }

    @staticmethod
    def _routines_on(db: sqlite3.Connection, plan_date: str) -> list[dict]:
        completed = {
            int(row["routine_id"])
            for row in db.execute(
                "SELECT routine_id FROM routine_checks WHERE plan_date = ?",
                (plan_date,),
            )
        }
        routines = []
        for row in db.execute(
            """
            SELECT * FROM routines
            WHERE active = 1 AND created_on <= ?
            ORDER BY sort_order, id
            """,
            (plan_date,),
        ):
            routines.append(
                Database._public_routine(row, int(row["id"]) in completed)
            )
        return routines

    @staticmethod
    def _routine_report(
        db: sqlite3.Connection, start_date: date, end_date: date
    ) -> list[dict]:
        today = date.today()
        start = start_date.isoformat()
        end = end_date.isoformat()
        routines = db.execute("SELECT * FROM routines ORDER BY sort_order, id").fetchall()
        result = []
        for routine in routines:
            created = datetime.strptime(routine["created_on"], DATE_FORMAT).date()
            deactivated = (
                datetime.strptime(routine["deactivated_on"], DATE_FORMAT).date()
                if routine["deactivated_on"]
                else None
            )
            if created > end_date or (deactivated and deactivated <= start_date):
                continue
            done_dates = {
                row["plan_date"]
                for row in db.execute(
                    """
                    SELECT plan_date FROM routine_checks
                    WHERE routine_id = ? AND plan_date BETWEEN ? AND ?
                    """,
                    (routine["id"], start, end),
                )
            }
            all_done = {
                row["plan_date"]
                for row in db.execute(
                    "SELECT plan_date FROM routine_checks WHERE routine_id = ?",
                    (routine["id"],),
                )
            }
            days = []
            completed = 0
            applicable = 0
            cursor = start_date
            while cursor <= end_date:
                if cursor < created or (deactivated and cursor >= deactivated):
                    status = "unset"
                elif cursor > today:
                    status = "future"
                elif cursor.isoformat() in done_dates:
                    status = "done"
                    completed += 1
                    applicable += 1
                else:
                    status = "missed"
                    applicable += 1
                days.append({"date": cursor.isoformat(), "status": status})
                cursor += timedelta(days=1)
            if applicable == 0 and not routine["active"]:
                continue
            streak = 0
            streak_cursor = today if today.isoformat() in all_done else today - timedelta(days=1)
            while streak_cursor >= created and streak_cursor.isoformat() in all_done:
                streak += 1
                streak_cursor -= timedelta(days=1)
            result.append(
                {
                    "id": int(routine["id"]),
                    "title": routine["title"],
                    "note": routine["note"],
                    "estimate_minutes": int(routine["estimate_minutes"]),
                    "color": ROUTINE_COLOR,
                    "active": bool(routine["active"]),
                    "completed_count": completed,
                    "applicable_count": applicable,
                    "streak": streak,
                    "days": days,
                }
            )
        return result


def _as_whole_number(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise AppError(f"{field_name}需要填写整数")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise AppError(f"{field_name}需要填写整数") from exc
    return parsed


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "DailyPlan"

    @property
    def database(self) -> Database:
        return self.server.database  # type: ignore[attr-defined]

    def log_message(self, format_string: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), format_string % args)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_PATCH(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api(parsed.path, parse_qs(parsed.query))
            else:
                self._serve_static(parsed.path)
        except AppError as exc:
            self._json({"error": exc.message}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            logging.exception("处理请求时发生异常")
            self._json(
                {"error": "暂时出了问题，请稍后重试；详细信息已写入本地日志"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise AppError("请求内容不正确") from exc
        if length > 1_000_000:
            raise AppError("内容过长")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError("请求内容不正确") from exc
        if not isinstance(payload, dict):
            raise AppError("请求内容不正确")
        return payload

    def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        method = self.command
        if method == "GET" and path == "/api/day":
            value = query.get("date", [date.today().isoformat()])[0]
            self._json(self.database.get_day(value))
            return
        if method == "GET" and path == "/api/week":
            value = query.get("date", [date.today().isoformat()])[0]
            self._json(self.database.get_week(value))
            return
        if method == "GET" and path == "/api/report":
            value = query.get("date", [date.today().isoformat()])[0]
            period = query.get("period", ["week"])[0]
            self._json(self.database.get_report(value, period))
            return
        if method == "GET" and path == "/api/memos":
            search = query.get("query", [""])[0]
            memo_date = query.get("date", [None])[0]
            raw_limit = query.get("limit", ["100"])[0]
            try:
                limit = int(raw_limit)
            except ValueError as exc:
                raise AppError("数量参数不正确") from exc
            self._json(self.database.list_memos(search, memo_date, limit))
            return
        if method == "POST" and path == "/api/entries":
            self._json(self.database.create_entry(self._body()), HTTPStatus.CREATED)
            return
        if method == "POST" and path == "/api/memos":
            self._json(self.database.create_memo(self._body()), HTTPStatus.CREATED)
            return
        if method == "POST" and path == "/api/timer/start":
            payload = self._body()
            self._json(
                self.database.start_timer(
                    as_non_negative_int(payload.get("entry_id"), "任务"),
                    str(payload.get("mode", "open")),
                    payload.get("focus_minutes", 25),
                )
            )
            return
        if method == "POST" and path == "/api/timer/stop":
            payload = self._body()
            raw_id = payload.get("entry_id")
            entry_id = (
                None
                if raw_id in (None, "")
                else as_non_negative_int(raw_id, "任务")
            )
            self._json(
                self.database.stop_timer(
                    entry_id, bool(payload.get("target_reached", False))
                )
            )
            return
        if method == "POST" and path == "/api/day/save":
            self._json(self.database.save_day(self._body()))
            return
        if method == "POST" and path == "/api/day/close":
            self._json(self.database.close_day(self._body()))
            return
        if method == "POST" and path == "/api/week/review":
            self._json(self.database.save_week_review(self._body()))
            return
        if method == "POST" and path == "/api/review":
            self._json(self.database.save_period_review(self._body()))
            return
        if method == "GET" and path == "/api/settings":
            self._json(self.database.get_settings())
            return
        if method == "PATCH" and path == "/api/settings":
            self._json(self.database.save_settings(self._body()))
            return
        if method == "POST" and path == "/api/routines/challenge":
            self._json(self.database.create_routine_challenge())
            return
        if method == "POST" and path == "/api/routines/challenge/verify":
            self._json(self.database.verify_routine_challenge(self._body()))
            return
        if method == "POST" and path == "/api/routines/check":
            self._json(self.database.set_routine_check(self._body()))
            return
        if method == "POST" and path == "/api/routines":
            self._json(self.database.create_routine(self._body()), HTTPStatus.CREATED)
            return

        routine_prefix = "/api/routines/"
        if path.startswith(routine_prefix):
            suffix = path[len(routine_prefix) :].strip("/")
            if "/" not in suffix and suffix.isdigit():
                routine_id = int(suffix)
                if method == "PATCH":
                    self._json(self.database.update_routine(routine_id, self._body()))
                    return
                if method == "DELETE":
                    self.database.delete_routine(
                        routine_id, self._body().get("unlock_token")
                    )
                    self._json({"deleted": True})
                    return

        entry_prefix = "/api/entries/"
        if path.startswith(entry_prefix):
            suffix = path[len(entry_prefix) :].strip("/")
            if "/" in suffix or not suffix.isdigit():
                raise AppError("没有找到这个操作", HTTPStatus.NOT_FOUND)
            entry_id = int(suffix)
            if method == "PATCH":
                self._json(self.database.update_entry(entry_id, self._body()))
                return
            if method == "DELETE":
                self.database.delete_entry(entry_id)
                self._json({"deleted": True})
                return

        segment_prefix = "/api/segments/"
        if path.startswith(segment_prefix):
            suffix = path[len(segment_prefix) :].strip("/")
            if "/" in suffix or not suffix.isdigit():
                raise AppError("没有找到这个操作", HTTPStatus.NOT_FOUND)
            segment_id = int(suffix)
            if method == "PATCH":
                self._json(self.database.update_segment(segment_id, self._body()))
                return
            if method == "DELETE":
                self.database.delete_segment(segment_id)
                self._json({"deleted": True})
                return

        memo_prefix = "/api/memos/"
        if path.startswith(memo_prefix):
            suffix = path[len(memo_prefix) :].strip("/")
            if "/" in suffix or not suffix.isdigit():
                raise AppError("没有找到这个操作", HTTPStatus.NOT_FOUND)
            memo_id = int(suffix)
            if method == "PATCH":
                self._json(self.database.update_memo(memo_id, self._body()))
                return
            if method == "DELETE":
                self.database.delete_memo(memo_id)
                self._json({"deleted": True})
                return
        raise AppError("没有找到这个操作", HTTPStatus.NOT_FOUND)

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in ("", "/") else unquote(
            request_path.lstrip("/")
        )
        target = (WEB_DIR / relative).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError as exc:
            raise AppError("没有找到这个页面", HTTPStatus.NOT_FOUND) from exc
        if not target.is_file():
            target = WEB_DIR / "index.html"
        if not target.is_file():
            raise AppError("页面文件还没有准备好", HTTPStatus.NOT_FOUND)
        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
        }:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class DailyPlanServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], database: Database):
        super().__init__(address, RequestHandler)
        self.database = database


def main() -> None:
    parser = argparse.ArgumentParser(description="每日计划")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        encoding="utf-8",
        format="%(asctime)s %(levelname)s %(message)s",
    )
    database = Database()
    server = DailyPlanServer(("127.0.0.1", args.port), database)
    url = f"http://127.0.0.1:{args.port}"
    print(f"每日计划已启动：{url}")
    print(f"数据文件：{database.path}")
    print("按 Ctrl+C 停止")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。数据已经保存在 SQLite 文件中。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
