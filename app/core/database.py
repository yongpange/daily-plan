"""SQLite 数据访问层：Database 与全部数据访问逻辑（唯一允许写 SQL 的地方）。

从旧 server.py 整体搬迁，逻辑逐字不变；仅调整 import，initialize 改为
执行 app/models/schema.sql 并调用 app/models/migrations 里的迁移函数。
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from app.models import migrations

from .errors import AppError
from .text import memo_content_from_payload, rich_plain_text
from .time import DATE_FORMAT, seconds_between, utc_now
from .validators import as_non_negative_int, period_bounds, valid_date, valid_remind_at

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "daily_plan.sqlite3"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "models" / "schema.sql"

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
ROUTINE_COLOR = "#c47b1a"
ROUTINE_SYMBOLS = ("+", "−", "×", "÷")


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
            db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            migrations.ensure_columns(db)
            migrations.ensure_thread_step_index(db)
            migrations.rebuild_note_images_id(db)
            migrations.merge_daily_notes(db)

    @staticmethod
    def _ensure_image_ids(db: sqlite3.Connection) -> None:
        row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'note_images'"
        ).fetchone()
        if not row or "AUTOINCREMENT" in row["sql"].upper():
            return
        db.execute("ALTER TABLE note_images RENAME TO note_images_old")
        db.execute(
            """
            CREATE TABLE note_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_type TEXT NOT NULL
                    CHECK (owner_type IN ('day', 'memo')),
                owner_key TEXT NOT NULL,
                content_type TEXT NOT NULL,
                width INTEGER,
                height INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            INSERT INTO note_images(
                id, owner_type, owner_key, content_type, width, height, created_at
            )
            SELECT id, owner_type, owner_key, content_type, width, height, created_at
            FROM note_images_old
            """
        )
        db.execute("DROP TABLE note_images_old")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS note_images_by_owner
            ON note_images(owner_type, owner_key, id)
            """
        )

    @staticmethod
    def _merge_daily_notes(db: sqlite3.Connection) -> None:
        marker = db.execute(
            "SELECT 1 FROM app_settings WHERE key = 'daily_notes_merged'"
        ).fetchone()
        if marker:
            return
        now = utc_now()
        dates = [
            row["plan_date"]
            for row in db.execute(
                """
                SELECT plan_date FROM days WHERE TRIM(reflection) <> ''
                UNION
                SELECT owner_key AS plan_date FROM note_images
                WHERE owner_type = 'day'
                """
            )
        ]
        for plan_date in dates:
            day = db.execute(
                "SELECT reflection, updated_at FROM days WHERE plan_date = ?",
                (plan_date,),
            ).fetchone()
            content = str(day["reflection"]).strip() if day else ""
            has_images = db.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM note_images
                    WHERE owner_type = 'day' AND owner_key = ?
                )
                """,
                (plan_date,),
            ).fetchone()[0]
            if not content and not has_images:
                continue
            existing = None
            if content:
                existing = db.execute(
                    """
                    SELECT id FROM memos
                    WHERE memo_date = ? AND content = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (plan_date, content),
                ).fetchone()
            if existing:
                memo_id = int(existing["id"])
            else:
                created_at = day["updated_at"] if day else now
                cursor = db.execute(
                    """
                    INSERT INTO memos(
                        memo_date, content, tags, pinned, created_at, updated_at
                    ) VALUES (?, ?, '', 0, ?, ?)
                    """,
                    (plan_date, content, created_at, now),
                )
                memo_id = int(cursor.lastrowid)
            db.execute(
                """
                UPDATE note_images
                SET owner_type = 'memo', owner_key = ?
                WHERE owner_type = 'day' AND owner_key = ?
                """,
                (str(memo_id), plan_date),
            )
            if content:
                db.execute(
                    "UPDATE days SET reflection = '' WHERE plan_date = ?",
                    (plan_date,),
                )
        db.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES ('daily_notes_merged', '1', ?)
            """,
            (now,),
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

    def _close_running_routine(self, db: sqlite3.Connection, now: str) -> sqlite3.Row | None:
        running = db.execute(
            """
            SELECT id, routine_id, plan_date, start_at
            FROM routine_segments
            WHERE end_at IS NULL
            """
        ).fetchone()
        if not running:
            return None
        db.execute(
            """
            UPDATE routine_segments
            SET end_at = ?, duration_seconds = ?
            WHERE id = ?
            """,
            (now, seconds_between(running["start_at"], now), running["id"]),
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
                pe.reason_note, pe.target_date, pe.thread_id,
                t.id AS task_id, t.title, t.parent_id, t.definition,
                t.status AS task_status,
                p.name AS project_name,
                th.title AS thread_title,
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
            LEFT JOIN threads th ON th.id = pe.thread_id
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
            routine_running = db.execute(
                """
                SELECT rs.id, rs.routine_id, rs.plan_date, rs.start_at, r.title
                FROM routine_segments rs
                JOIN routines r ON r.id = rs.routine_id
                WHERE rs.end_at IS NULL
                """
            ).fetchone()
            if running is None and routine_running is not None:
                running = {
                    "id": routine_running["id"],
                    "plan_entry_id": None,
                    "routine_id": int(routine_running["routine_id"]),
                    "start_at": routine_running["start_at"],
                    "mode": "open",
                    "target_seconds": None,
                    "plan_date": routine_running["plan_date"],
                    "title": routine_running["title"],
                }
            for row in db.execute(
                """
                SELECT rs.id, rs.routine_id, rs.start_at, rs.end_at,
                       rs.duration_seconds, r.title
                FROM routine_segments rs
                JOIN routines r ON r.id = rs.routine_id
                WHERE rs.plan_date = ?
                ORDER BY rs.start_at DESC, rs.id DESC
                """,
                (clean_date,),
            ):
                segments.append(
                    {
                        "id": int(row["id"]),
                        "plan_entry_id": None,
                        "routine_id": int(row["routine_id"]),
                        "start_at": row["start_at"],
                        "end_at": row["end_at"],
                        "duration_seconds": row["duration_seconds"],
                        "mode": "open",
                        "target_seconds": None,
                        "focus_completed": 0,
                        "title": row["title"],
                        "project_name": "每日必做",
                        "kind": "routine",
                    }
                )
            day_record = (
                dict(day)
                if day
                else {
                    "plan_date": clean_date,
                    "focus": "",
                    "reflection": "",
                    "mood": None,
                    "closed_at": None,
                }
            )
            day_record["images"] = self._images_for(db, "day", clean_date)
            return {
                "date": clean_date,
                "day": day_record,
                "entries": [self._entry(db, int(row["id"])) for row in entries],
                "projects": projects,
                "active_timer": dict(running) if running else None,
                "segments": segments,
                "reasons": REASONS,
                "routines": self._routines_on(db, clean_date),
                "threads": self._threads_for_day(db, clean_date),
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
            stopped_routine = self._close_running_routine(db, now)
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
                "stopped_routine_id": int(stopped_routine["routine_id"])
                if stopped_routine
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
                routine_open = db.execute(
                    """
                    SELECT id FROM routine_segments
                    WHERE end_at IS NULL
                    """
                ).fetchone()
                if not routine_open:
                    return {"stopped": False, "entry_id": None}
                if entry_id is not None:
                    raise AppError("当前计时属于另一条任务")
                routine = self._close_running_routine(db, now)
                return {
                    "stopped": True,
                    "entry_id": None,
                    "routine_id": int(routine["routine_id"]),
                    "duration_seconds": seconds_between(routine["start_at"], now),
                    "mode": "open",
                    "focus_completed": False,
                }
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
        self,
        query: str = "",
        memo_date: str | None = None,
        limit: int = 100,
        source_kind: str = "",
        source_id: int | None = None,
        task_id: int | None = None,
    ) -> list[dict]:
        clean_query = query.strip()[:200]
        if memo_date:
            memo_date = valid_date(memo_date)
        limit = max(1, min(int(limit), 300))
        source_kind = str(source_kind or "").strip()
        if source_kind and source_kind not in {"routine", "thread"}:
            raise AppError("感悟来源不正确")
        clauses = []
        params: list[object] = []
        if clean_query:
            clauses.append(
                "(content LIKE ? OR tags LIKE ? OR source_title LIKE ? OR note_title LIKE ?)"
            )
            wildcard = f"%{clean_query}%"
            params.extend([wildcard, wildcard, wildcard, wildcard])
        if memo_date:
            clauses.append("memo_date = ?")
            params.append(memo_date)
        if source_kind == "routine":
            if source_id is None:
                raise AppError("感悟来源不正确")
            clauses.append("source_routine_id = ?")
            params.append(int(source_id))
        elif source_kind == "thread":
            if source_id is None:
                raise AppError("感悟来源不正确")
            clauses.append(
                """
                (
                    source_thread_id = ?
                    OR source_entry_id IN (
                        SELECT id FROM plan_entries WHERE thread_id = ?
                    )
                )
                """
            )
            params.extend([int(source_id), int(source_id)])
        if task_id is not None:
            clauses.append(
                """
                (
                    source_task_id = ?
                    OR source_entry_id IN (
                        SELECT id FROM plan_entries WHERE task_id = ?
                    )
                )
                """
            )
            params.extend([int(task_id), int(task_id)])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with closing(self.connect()) as db, db:
            memos = [
                dict(row)
                for row in db.execute(
                    f"""
                    SELECT id, memo_date, content, tags, pinned,
                           note_title, note_link,
                           source_entry_id, source_title, source_estimate_minutes,
                           source_actual_seconds, source_plan_date,
                           source_kind, source_routine_id, source_thread_id,
                           source_task_id,
                           created_at, updated_at, 'memo' AS kind
                    FROM memos
                    {where}
                    ORDER BY pinned DESC, memo_date DESC, created_at DESC
                    LIMIT ?
                    """,
                    params,
                )
            ]
            if not memo_date and not source_kind and task_id is None:
                if clean_query:
                    daily_rows = db.execute(
                        """
                        SELECT plan_date, reflection, updated_at
                        FROM days
                        WHERE reflection <> '' AND reflection LIKE ?
                        ORDER BY plan_date DESC
                        LIMIT 50
                        """,
                        (f"%{clean_query}%",),
                    )
                else:
                    daily_rows = db.execute(
                        """
                        SELECT ni.owner_key AS plan_date,
                               COALESCE(d.reflection, '') AS reflection,
                               COALESCE(d.updated_at, MAX(ni.created_at)) AS updated_at
                        FROM note_images ni
                        LEFT JOIN days d ON d.plan_date = ni.owner_key
                        WHERE ni.owner_type = 'day'
                        GROUP BY ni.owner_key
                        ORDER BY ni.owner_key DESC
                        LIMIT 50
                        """
                    )
                memos.extend(
                    {
                        "id": row["plan_date"],
                        "memo_date": row["plan_date"],
                        "content": row["reflection"],
                        "tags": "每日复盘",
                        "pinned": 0,
                        "source_entry_id": None,
                        "source_title": "",
                        "source_estimate_minutes": None,
                        "source_actual_seconds": None,
                        "source_plan_date": None,
                        "source_kind": "",
                        "source_routine_id": None,
                        "source_thread_id": None,
                        "source_task_id": None,
                        "note_title": "",
                        "note_link": "",
                        "source_thread_title": "",
                        "created_at": row["updated_at"],
                        "updated_at": row["updated_at"],
                        "kind": "daily",
                    }
                    for row in daily_rows
                )
                memos.sort(
                    key=lambda item: (
                        int(item["pinned"]),
                        item["memo_date"],
                        item["created_at"] or "",
                    ),
                    reverse=True,
                )
            memos = memos[:limit]
            self._attach_images(
                db,
                [item for item in memos if item["kind"] == "memo"],
                "memo",
                lambda item: str(item["id"]),
            )
            self._attach_images(
                db,
                [item for item in memos if item["kind"] == "daily"],
                "day",
                lambda item: str(item["memo_date"]),
            )
            self._decorate_memo_sources(db, memos)
            self._attach_reads(db, memos)
            return memos

    def list_memo_sources(self) -> list[dict]:
        with closing(self.connect()) as db:
            thread_counts: dict[int, int] = {}
            for row in db.execute(
                """
                SELECT thread_id, COUNT(*) AS total
                FROM (
                    SELECT source_thread_id AS thread_id
                    FROM memos
                    WHERE source_thread_id IS NOT NULL
                    UNION ALL
                    SELECT pe.thread_id
                    FROM memos m
                    JOIN plan_entries pe ON pe.id = m.source_entry_id
                    WHERE m.source_thread_id IS NULL AND pe.thread_id IS NOT NULL
                ) AS linked
                GROUP BY thread_id
                """
            ):
                thread_counts[int(row["thread_id"])] = int(row["total"])
            routine_counts = {
                int(row["source_routine_id"]): int(row["total"])
                for row in db.execute(
                    """
                    SELECT source_routine_id, COUNT(*) AS total
                    FROM memos
                    WHERE source_routine_id IS NOT NULL
                    GROUP BY source_routine_id
                    """
                )
            }
            sources = []
            for row in db.execute(
                "SELECT id, title, status, featured FROM threads ORDER BY featured DESC, id"
            ):
                thread_id = int(row["id"])
                count = thread_counts.get(thread_id, 0)
                if row["status"] != "active" and count == 0:
                    continue
                sources.append(
                    {
                        "kind": "thread",
                        "id": thread_id,
                        "title": row["title"],
                        "count": count,
                        "featured": bool(row["featured"]),
                        "active": row["status"] == "active",
                    }
                )
            for row in db.execute(
                "SELECT id, title, active FROM routines ORDER BY sort_order, id"
            ):
                routine_id = int(row["id"])
                count = routine_counts.get(routine_id, 0)
                if not row["active"] and count == 0:
                    continue
                sources.append(
                    {
                        "kind": "routine",
                        "id": routine_id,
                        "title": row["title"],
                        "count": count,
                        "featured": False,
                        "active": bool(row["active"]),
                    }
                )
            sources.sort(
                key=lambda item: (
                    0 if item["kind"] == "thread" else 1,
                    0 if item["featured"] else 1,
                    0 if item["active"] else 1,
                    -item["count"],
                    item["id"],
                )
            )
            return sources

    @staticmethod
    def _decorate_memo_sources(db: sqlite3.Connection, memos: list[dict]) -> None:
        entry_ids = [
            int(item["source_entry_id"])
            for item in memos
            if item.get("kind") == "memo" and item.get("source_entry_id")
        ]
        entry_threads: dict[int, int] = {}
        entry_tasks: dict[int, int] = {}
        if entry_ids:
            placeholders = ",".join("?" * len(entry_ids))
            for row in db.execute(
                f"""
                SELECT id, thread_id, task_id FROM plan_entries
                WHERE id IN ({placeholders})
                """,
                entry_ids,
            ):
                entry_tasks[int(row["id"])] = int(row["task_id"])
                if row["thread_id"]:
                    entry_threads[int(row["id"])] = int(row["thread_id"])
        thread_ids: set[int] = set()
        for item in memos:
            if item.get("kind") != "memo":
                item["source_thread_title"] = ""
                continue
            if not item.get("source_thread_id") and item.get("source_entry_id"):
                thread_id = entry_threads.get(int(item["source_entry_id"]))
                if thread_id:
                    item["source_thread_id"] = thread_id
                    if not item.get("source_kind"):
                        item["source_kind"] = "thread"
            if not item.get("source_task_id") and item.get("source_entry_id"):
                task_id = entry_tasks.get(int(item["source_entry_id"]))
                if task_id:
                    item["source_task_id"] = task_id
                    if not item.get("source_kind") and not item.get("source_thread_id"):
                        item["source_kind"] = "task"
            if item.get("source_thread_id"):
                thread_ids.add(int(item["source_thread_id"]))
        titles: dict[int, str] = {}
        if thread_ids:
            placeholders = ",".join("?" * len(thread_ids))
            for row in db.execute(
                f"SELECT id, title FROM threads WHERE id IN ({placeholders})",
                list(thread_ids),
            ):
                titles[int(row["id"])] = row["title"]
        for item in memos:
            if item.get("kind") != "memo":
                continue
            thread_id = item.get("source_thread_id")
            item["source_thread_title"] = titles.get(int(thread_id), "") if thread_id else ""

    @staticmethod
    def _note_link(value: object) -> str:
        link = str(value or "").strip()
        if not link:
            return ""
        if len(link) > 500:
            raise AppError("链接请控制在 500 个字符以内")
        if re.match(r"^[a-z][a-z0-9+.-]*:", link, re.IGNORECASE) and not re.match(
            r"^https?://", link, re.IGNORECASE
        ):
            raise AppError("请填写可以打开的网页链接")
        if not re.match(r"^https?://", link, re.IGNORECASE):
            link = f"https://{link}"
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError("请填写可以打开的网页链接")
        return link

    def _memo_task_source(self, db: sqlite3.Connection, entry_id: int) -> dict:
        root = db.execute(
            """
            SELECT pe.id, pe.plan_date, pe.estimate_minutes, pe.thread_id,
                   t.id AS task_id, t.title, t.parent_id
            FROM plan_entries pe
            JOIN tasks t ON t.id = pe.task_id
            WHERE pe.id = ?
            """,
            (entry_id,),
        ).fetchone()
        if not root:
            raise AppError("没有找到这条任务", HTTPStatus.NOT_FOUND)
        if root["parent_id"] is not None:
            raise AppError("感悟写在主任务上")
        nodes = [dict(root)]
        frontier = [int(root["task_id"])]
        while frontier:
            placeholders = ",".join("?" * len(frontier))
            children = db.execute(
                f"""
                SELECT pe.id, pe.estimate_minutes, t.id AS task_id, t.parent_id
                FROM tasks t
                JOIN plan_entries pe
                  ON pe.task_id = t.id AND pe.plan_date = ?
                WHERE t.parent_id IN ({placeholders})
                """,
                [root["plan_date"], *frontier],
            ).fetchall()
            frontier = []
            for child in children:
                nodes.append(dict(child))
                frontier.append(int(child["task_id"]))
        parent_task_ids = {
            int(node["parent_id"]) for node in nodes if node["parent_id"] is not None
        }
        leaves = [
            node for node in nodes if int(node["task_id"]) not in parent_task_ids
        ]
        estimate = sum(int(node["estimate_minutes"] or 0) for node in leaves)
        entry_ids = [int(node["id"]) for node in nodes]
        placeholders = ",".join("?" * len(entry_ids))
        now = datetime.now(timezone.utc)
        actual = 0
        for segment in db.execute(
            f"""
            SELECT start_at, end_at, duration_seconds
            FROM time_segments
            WHERE plan_entry_id IN ({placeholders})
            """,
            entry_ids,
        ):
            if segment["end_at"]:
                actual += int(segment["duration_seconds"] or 0)
                continue
            start = datetime.fromisoformat(str(segment["start_at"]).replace("Z", "+00:00"))
            actual += max(0, int((now - start).total_seconds()))
        thread_id = root["thread_id"]
        return {
            "source_kind": "thread" if thread_id else "task",
            "source_entry_id": int(root["id"]),
            "source_routine_id": None,
            "source_thread_id": int(thread_id) if thread_id else None,
            "source_task_id": int(root["task_id"]),
            "source_title": root["title"],
            "source_estimate_minutes": estimate,
            "source_actual_seconds": actual,
            "source_plan_date": root["plan_date"],
        }

    def _memo_routine_source(
        self, db: sqlite3.Connection, raw_id: object, raw_date: object
    ) -> dict:
        try:
            routine_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise AppError("没有找到这项每日必做", HTTPStatus.NOT_FOUND) from exc
        routine = db.execute(
            "SELECT id, title FROM routines WHERE id = ?", (routine_id,)
        ).fetchone()
        if not routine:
            raise AppError("没有找到这项每日必做", HTTPStatus.NOT_FOUND)
        return {
            "source_kind": "routine",
            "source_entry_id": None,
            "source_routine_id": int(routine["id"]),
            "source_thread_id": None,
            "source_task_id": None,
            "source_title": routine["title"],
            "source_estimate_minutes": None,
            "source_actual_seconds": None,
            "source_plan_date": valid_date(
                raw_date or date.today().isoformat(), "记录日期"
            ),
        }

    def _memo_thread_source(
        self, db: sqlite3.Connection, raw_id: object, raw_date: object
    ) -> dict:
        try:
            thread_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise AppError("没有找到这条主线", HTTPStatus.NOT_FOUND) from exc
        thread = db.execute(
            "SELECT id, title FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
        if not thread:
            raise AppError("没有找到这条主线", HTTPStatus.NOT_FOUND)
        return {
            "source_kind": "thread",
            "source_entry_id": None,
            "source_routine_id": None,
            "source_thread_id": int(thread["id"]),
            "source_task_id": None,
            "source_title": thread["title"],
            "source_estimate_minutes": None,
            "source_actual_seconds": None,
            "source_plan_date": valid_date(
                raw_date or date.today().isoformat(), "记录日期"
            ),
        }

    def create_memo(self, payload: dict) -> dict:
        content = memo_content_from_payload(payload)
        text = rich_plain_text(content) if payload.get("content_format") == "rich" else content.strip()
        if not text and not payload.get("has_images"):
            raise AppError("先写下一点内容，或添加一张图片")
        tags = str(payload.get("tags", "")).strip()[:300]
        note_title = str(payload.get("note_title", "")).strip()[:80]
        note_link = self._note_link(payload.get("note_link"))
        now = utc_now()
        raw_entry = payload.get("entry_id")
        raw_routine = payload.get("routine_id")
        raw_thread = payload.get("thread_id")
        with closing(self.connect()) as db, db:
            source = None
            if raw_entry not in (None, ""):
                try:
                    entry_id = int(raw_entry)
                except (TypeError, ValueError) as exc:
                    raise AppError("任务不正确") from exc
                source = self._memo_task_source(db, entry_id)
            elif raw_routine not in (None, ""):
                source = self._memo_routine_source(db, raw_routine, payload.get("date"))
            elif raw_thread not in (None, ""):
                source = self._memo_thread_source(db, raw_thread, payload.get("date"))
            memo_date = (
                source["source_plan_date"]
                if source
                else valid_date(payload.get("date") or date.today().isoformat(), "记录日期")
            )
            blank = {
                "source_kind": "",
                "source_entry_id": None,
                "source_routine_id": None,
                "source_thread_id": None,
                "source_task_id": None,
                "source_title": "",
                "source_estimate_minutes": None,
                "source_actual_seconds": None,
                "source_plan_date": None,
            }
            source = source or blank
            cursor = db.execute(
                """
                INSERT INTO memos(
                    memo_date, content, tags, pinned, created_at, updated_at,
                    source_entry_id, source_title, source_estimate_minutes,
                    source_actual_seconds,                     source_plan_date,
                    source_kind, source_routine_id, source_thread_id, source_task_id,
                    note_title, note_link
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memo_date,
                    content,
                    tags,
                    now,
                    now,
                    source["source_entry_id"],
                    source["source_title"],
                    source["source_estimate_minutes"],
                    source["source_actual_seconds"],
                    source["source_plan_date"],
                    source["source_kind"],
                    source["source_routine_id"],
                    source["source_thread_id"],
                    source["source_task_id"],
                    note_title,
                    note_link,
                ),
            )
            created = dict(
                db.execute(
                    "SELECT *, 'memo' AS kind FROM memos WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
            )
            created["images"] = []
            return created

    def update_memo(self, memo_id: int, payload: dict) -> dict:
        with closing(self.connect()) as db, db:
            current = db.execute(
                "SELECT * FROM memos WHERE id = ?", (memo_id,)
            ).fetchone()
            if not current:
                raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)
            content = memo_content_from_payload(payload, str(current["content"]))
            text = (
                rich_plain_text(content)
                if payload.get("content_format") == "rich" or "<" in content
                else content.strip()
            )
            if not text:
                has_images = db.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM note_images
                        WHERE owner_type = 'memo' AND owner_key = ?
                    )
                    """,
                    (str(memo_id),),
                ).fetchone()[0]
                if not has_images:
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
                (memo_date, content[:12000], tags, pinned, utc_now(), memo_id),
            )
            updated = dict(
                db.execute(
                    "SELECT *, 'memo' AS kind FROM memos WHERE id = ?", (memo_id,)
                ).fetchone()
            )
            self._attach_images(db, [updated], "memo", lambda item: str(item["id"]))
            return updated

    def delete_memo(self, memo_id: int) -> None:
        with closing(self.connect()) as db, db:
            image_ids = [
                int(row["id"])
                for row in db.execute(
                    """
                    SELECT id FROM note_images
                    WHERE owner_type = 'memo' AND owner_key = ?
                    """,
                    (str(memo_id),),
                )
            ]
            cursor = db.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
            if cursor.rowcount == 0:
                raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)
            db.execute(
                "DELETE FROM note_images WHERE owner_type = 'memo' AND owner_key = ?",
                (str(memo_id),),
            )
            db.execute(
                "DELETE FROM memo_reads WHERE owner_kind = 'memo' AND owner_key = ?",
                (str(memo_id),),
            )
        for image_id in image_ids:
            self._remove_image_files(image_id)

    def mark_memo_read(self, payload: dict) -> dict:
        kind, key = self._memo_read_target(payload)
        now = utc_now()
        today = date.today()
        with closing(self.connect()) as db, db:
            if kind == "memo":
                exists = db.execute(
                    "SELECT 1 FROM memos WHERE id = ?", (int(key),)
                ).fetchone()
                if not exists:
                    raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)
            current = db.execute(
                """
                SELECT read_count, last_read_at
                FROM memo_reads
                WHERE owner_kind = ? AND owner_key = ?
                """,
                (kind, key),
            ).fetchone()
            if current and self._read_on_local_day(current["last_read_at"], today):
                return self._memo_read_payload(
                    kind, key, current["read_count"], current["last_read_at"], False
                )
            db.execute(
                """
                INSERT INTO memo_reads(owner_kind, owner_key, read_count, last_read_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(owner_kind, owner_key) DO UPDATE SET
                    read_count = read_count + 1,
                    last_read_at = excluded.last_read_at
                """,
                (kind, key, now),
            )
            row = db.execute(
                """
                SELECT read_count, last_read_at
                FROM memo_reads
                WHERE owner_kind = ? AND owner_key = ?
                """,
                (kind, key),
            ).fetchone()
        return self._memo_read_payload(kind, key, row["read_count"], row["last_read_at"], True)

    @staticmethod
    def _read_on_local_day(stamp: object, day: date) -> bool:
        if not stamp:
            return False
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return parsed.astimezone().date() == day

    @classmethod
    def _memo_read_payload(
        cls, kind: str, key: str, read_count: object, last_read_at: object, counted: bool
    ) -> dict:
        return {
            "kind": kind,
            "id": int(key) if kind == "memo" else key,
            "read_count": int(read_count),
            "last_read_at": last_read_at,
            "read_today": cls._read_on_local_day(last_read_at, date.today()),
            "counted": counted,
        }

    @staticmethod
    def _memo_read_target(payload: dict) -> tuple[str, str]:
        kind = str(payload.get("kind", "memo")).strip()
        if kind not in {"memo", "daily"}:
            raise AppError("记录类型不正确")
        raw_id = payload.get("id")
        if kind == "daily":
            return kind, valid_date(raw_id, "记录日期")
        if isinstance(raw_id, bool) or raw_id in (None, ""):
            raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)
        try:
            memo_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND) from exc
        if memo_id <= 0:
            raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)
        return kind, str(memo_id)

    @staticmethod
    def _attach_reads(db: sqlite3.Connection, memos: list[dict]) -> None:
        today = date.today()
        for item in memos:
            item["read_count"] = 0
            item["last_read_at"] = None
            item["read_today"] = False
        grouped: dict[str, list[str]] = {"memo": [], "daily": []}
        for item in memos:
            kind = str(item.get("kind") or "")
            if kind in grouped:
                grouped[kind].append(str(item["id"]))
        found: dict[tuple[str, str], sqlite3.Row] = {}
        for kind, keys in grouped.items():
            if not keys:
                continue
            placeholders = ",".join("?" * len(keys))
            rows = db.execute(
                f"""
                SELECT owner_key, read_count, last_read_at
                FROM memo_reads
                WHERE owner_kind = ? AND owner_key IN ({placeholders})
                """,
                [kind, *keys],
            )
            for row in rows:
                found[(kind, str(row["owner_key"]))] = row
        for item in memos:
            row = found.get((str(item.get("kind")), str(item["id"])))
            if not row:
                continue
            item["read_count"] = int(row["read_count"])
            item["last_read_at"] = row["last_read_at"]
            item["read_today"] = Database._read_on_local_day(row["last_read_at"], today)

    def list_memo_templates(self) -> list[dict]:
        with closing(self.connect()) as db:
            return [
                {
                    "id": int(row["id"]),
                    "name": row["name"],
                    "content": row["content"],
                    "updated_at": row["updated_at"],
                }
                for row in db.execute(
                    """
                    SELECT id, name, content, updated_at
                    FROM memo_templates
                    ORDER BY updated_at DESC, id DESC
                    """
                )
            ]

    def create_memo_template(self, payload: dict) -> dict:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise AppError("先给模板起个名字")
        if len(name) > 40:
            raise AppError("模板名称请控制在 40 个字以内")
        content = memo_content_from_payload({**payload, "content_format": "rich"})
        if not rich_plain_text(content):
            raise AppError("模板里先写一点内容")
        now = utc_now()
        with closing(self.connect()) as db, db:
            count = db.execute("SELECT COUNT(*) FROM memo_templates").fetchone()[0]
            if int(count) >= 40:
                raise AppError("模板最多保存 40 个")
            cursor = db.execute(
                """
                INSERT INTO memo_templates(name, content, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, content, now, now),
            )
            return self._template_row(db, int(cursor.lastrowid))

    def update_memo_template(self, template_id: int, payload: dict) -> dict:
        with closing(self.connect()) as db, db:
            current = db.execute(
                "SELECT * FROM memo_templates WHERE id = ?", (template_id,)
            ).fetchone()
            if not current:
                raise AppError("没有找到这个模板", HTTPStatus.NOT_FOUND)
            name = str(payload.get("name", current["name"])).strip()
            if not name or len(name) > 40:
                raise AppError("模板名称请控制在 40 个字以内")
            if "content" in payload:
                content = memo_content_from_payload({**payload, "content_format": "rich"})
                if not rich_plain_text(content):
                    raise AppError("模板里先写一点内容")
            else:
                content = current["content"]
            db.execute(
                """
                UPDATE memo_templates
                SET name = ?, content = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, content, utc_now(), template_id),
            )
            return self._template_row(db, template_id)

    def delete_memo_template(self, template_id: int) -> None:
        with closing(self.connect()) as db, db:
            cursor = db.execute(
                "DELETE FROM memo_templates WHERE id = ?", (template_id,)
            )
            if cursor.rowcount == 0:
                raise AppError("没有找到这个模板", HTTPStatus.NOT_FOUND)

    @staticmethod
    def _template_row(db: sqlite3.Connection, template_id: int) -> dict:
        row = db.execute(
            "SELECT id, name, content, updated_at FROM memo_templates WHERE id = ?",
            (template_id,),
        ).fetchone()
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "content": row["content"],
            "updated_at": row["updated_at"],
        }

    def list_reminders(self) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        with closing(self.connect()) as db:
            return [
                self._reminder_dict(row)
                for row in db.execute(
                    """
                    SELECT * FROM reminders
                    WHERE status = 'pending' OR remind_at >= ?
                    ORDER BY
                        CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                        remind_at,
                        id
                    """,
                    (cutoff,),
                )
            ]

    def create_reminder(self, payload: dict) -> dict:
        message = self._reminder_message(payload.get("message"))
        remind_at = valid_remind_at(payload.get("remind_at"))
        self._require_future_reminder(remind_at)
        now = utc_now()
        with closing(self.connect()) as db, db:
            cursor = db.execute(
                """
                INSERT INTO reminders(message, remind_at, status, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?)
                """,
                (message, remind_at, now, now),
            )
            row = db.execute(
                "SELECT * FROM reminders WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return self._reminder_dict(row)

    def update_reminder(self, reminder_id: int, payload: dict) -> dict:
        with closing(self.connect()) as db, db:
            current = db.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
            if not current:
                raise AppError("没有找到这个提醒", HTTPStatus.NOT_FOUND)
            message = current["message"]
            remind_at = current["remind_at"]
            status = current["status"]
            if "message" in payload:
                message = self._reminder_message(payload.get("message"))
                status = "pending"
            if "remind_at" in payload:
                remind_at = valid_remind_at(payload.get("remind_at"))
                self._require_future_reminder(remind_at)
                status = "pending"
            if "status" in payload:
                status = str(payload.get("status"))
                if status not in {"pending", "done"}:
                    raise AppError("提醒状态不正确")
            db.execute(
                """
                UPDATE reminders
                SET message = ?, remind_at = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (message, remind_at, status, utc_now(), reminder_id),
            )
            row = db.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
            return self._reminder_dict(row)

    def delete_reminder(self, reminder_id: int) -> None:
        with closing(self.connect()) as db, db:
            cursor = db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            if cursor.rowcount == 0:
                raise AppError("没有找到这个提醒", HTTPStatus.NOT_FOUND)

    @staticmethod
    def _reminder_dict(row: sqlite3.Row) -> dict:
        return {
            "id": int(row["id"]),
            "message": row["message"],
            "remind_at": row["remind_at"],
            "status": row["status"],
        }

    @staticmethod
    def _reminder_message(value: object) -> str:
        message = str(value or "").strip()
        if not message:
            raise AppError("先写下要提醒的内容")
        if len(message) > 200:
            raise AppError("提醒内容请控制在 200 个字以内")
        return message

    @staticmethod
    def _require_future_reminder(remind_at: str) -> None:
        current = datetime.now().strftime("%Y-%m-%dT%H:%M")
        if remind_at < current:
            raise AppError("请选一个还没到的时间")

    @property
    def image_dir(self) -> Path:
        return self.path.parent / "images"

    def create_note_image(self, payload: dict) -> dict:
        owner_type = str(payload.get("owner_type", ""))
        if owner_type not in {"day", "memo"}:
            raise AppError("图片所属记录不正确")
        owner_key = str(payload.get("owner_key", "")).strip()
        if owner_type == "day":
            owner_key = valid_date(owner_key)
        elif not owner_key.isdigit():
            raise AppError("图片所属记录不正确")
        content_type, original = self._decode_image(
            payload.get("original"), "原图", 8_000_000
        )
        _, thumbnail = self._decode_image(
            payload.get("thumbnail"), "缩略图", 500_000
        )
        width = payload.get("width")
        height = payload.get("height")
        width = int(width) if isinstance(width, int) and width > 0 else None
        height = int(height) if isinstance(height, int) and height > 0 else None
        now = utc_now()
        with closing(self.connect()) as db, db:
            if owner_type == "memo":
                exists = db.execute(
                    "SELECT EXISTS(SELECT 1 FROM memos WHERE id = ?)",
                    (int(owner_key),),
                ).fetchone()[0]
                if not exists:
                    raise AppError("没有找到这条感悟", HTTPStatus.NOT_FOUND)
            count = db.execute(
                """
                SELECT COUNT(*) FROM note_images
                WHERE owner_type = ? AND owner_key = ?
                """,
                (owner_type, owner_key),
            ).fetchone()[0]
            if count >= 9:
                raise AppError("一条记录最多保存 9 张图片")
            cursor = db.execute(
                """
                INSERT INTO note_images(
                    owner_type, owner_key, content_type, width, height, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (owner_type, owner_key, content_type, width, height, now),
            )
            image_id = int(cursor.lastrowid)
        try:
            self.image_dir.mkdir(parents=True, exist_ok=True)
            (self.image_dir / str(image_id)).write_bytes(original)
            (self.image_dir / f"{image_id}.thumb").write_bytes(thumbnail)
        except OSError as exc:
            with closing(self.connect()) as db, db:
                db.execute("DELETE FROM note_images WHERE id = ?", (image_id,))
            raise AppError("图片没有保存成功") from exc
        return {
            "id": image_id,
            "width": width,
            "height": height,
            "owner_type": owner_type,
            "owner_key": owner_key,
        }

    def delete_note_image(self, image_id: int) -> None:
        with closing(self.connect()) as db, db:
            cursor = db.execute("DELETE FROM note_images WHERE id = ?", (image_id,))
            if cursor.rowcount == 0:
                raise AppError("没有找到这张图片", HTTPStatus.NOT_FOUND)
        self._remove_image_files(image_id)

    def read_note_image(self, image_id: int, thumbnail: bool = False) -> tuple[bytes, str]:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT content_type FROM note_images WHERE id = ?", (image_id,)
            ).fetchone()
        if not row:
            raise AppError("没有找到这张图片", HTTPStatus.NOT_FOUND)
        path = self.image_dir / (f"{image_id}.thumb" if thumbnail else str(image_id))
        if not path.is_file():
            raise AppError("没有找到这张图片", HTTPStatus.NOT_FOUND)
        content_type = "image/jpeg" if thumbnail else row["content_type"]
        return path.read_bytes(), content_type

    def suggested_tags(self, limit: int = 3) -> list[str]:
        with closing(self.connect()) as db:
            rows = db.execute(
                """
                SELECT tags, created_at FROM memos
                WHERE tags <> ''
                ORDER BY created_at DESC, id DESC
                LIMIT 200
                """
            ).fetchall()
        scores: dict[str, float] = {}
        latest: dict[str, str] = {}
        for index, row in enumerate(rows):
            weight = 1 + (200 - index) / 200
            for tag in re.split(r"[,，\s]+", row["tags"]):
                clean = tag.strip()
                if not clean:
                    continue
                scores[clean] = scores.get(clean, 0) + weight
                latest.setdefault(clean, row["created_at"])
        ranked = sorted(
            scores,
            key=lambda tag: (scores[tag], latest.get(tag, "")),
            reverse=True,
        )
        return ranked[:limit]

    def _remove_image_files(self, image_id: int) -> None:
        for path in (
            self.image_dir / str(image_id),
            self.image_dir / f"{image_id}.thumb",
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logging.exception("删除图片文件失败：%s", path)

    @staticmethod
    def _decode_image(value: object, field_name: str, max_bytes: int) -> tuple[str, bytes]:
        if not isinstance(value, str) or not value.startswith("data:image/"):
            raise AppError(f"{field_name}格式不正确")
        header, separator, data = value.partition(",")
        if not separator or ";base64" not in header:
            raise AppError(f"{field_name}格式不正确")
        content_type = header[5:].split(";", 1)[0].lower()
        if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise AppError("只支持 JPG、PNG、WEBP 和 GIF")
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AppError(f"{field_name}格式不正确") from exc
        if not raw or len(raw) > max_bytes:
            raise AppError(f"{field_name}太大，请换一张小一些的")
        return content_type, raw

    @staticmethod
    def _images_for(
        db: sqlite3.Connection, owner_type: str, owner_key: str
    ) -> list[dict]:
        return [
            {"id": int(row["id"]), "width": row["width"], "height": row["height"]}
            for row in db.execute(
                """
                SELECT id, width, height FROM note_images
                WHERE owner_type = ? AND owner_key = ?
                ORDER BY id
                """,
                (owner_type, owner_key),
            )
        ]

    @staticmethod
    def _attach_images(db, items: list[dict], owner_type: str, key_of) -> None:
        for item in items:
            item["images"] = []
        if not items:
            return
        keys = [str(key_of(item)) for item in items]
        placeholders = ",".join("?" for _ in keys)
        grouped: dict[str, list[dict]] = {}
        for row in db.execute(
            f"""
            SELECT id, owner_key, width, height FROM note_images
            WHERE owner_type = ? AND owner_key IN ({placeholders})
            ORDER BY id
            """,
            [owner_type, *keys],
        ):
            grouped.setdefault(row["owner_key"], []).append(
                {
                    "id": int(row["id"]),
                    "width": row["width"],
                    "height": row["height"],
                }
            )
        for item, key in zip(items, keys):
            item["images"] = grouped.get(key, [])

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

    def _threads_for_day(self, db: sqlite3.Connection, plan_date: str) -> list[dict]:
        anchor = datetime.strptime(plan_date, DATE_FORMAT).date()
        previous = [
            (anchor - timedelta(days=2)).isoformat(),
            (anchor - timedelta(days=1)).isoformat(),
        ]
        tomorrow = (anchor + timedelta(days=1)).isoformat()
        threads = [
            dict(row)
            for row in db.execute(
                """
                SELECT th.id, th.title, th.done_when, th.status, th.featured,
                       p.name AS project_name
                FROM threads th
                LEFT JOIN projects p ON p.id = th.project_id
                WHERE th.status IN ('active', 'paused')
                ORDER BY th.featured DESC, th.status, th.id
                """
            )
        ]
        if not threads:
            return []
        ids = [int(item["id"]) for item in threads]
        placeholders = ",".join("?" * len(ids))
        dates = [*previous, plan_date, tomorrow]
        date_marks = ",".join("?" * len(dates))
        steps = {
            (int(row["thread_id"]), row["plan_date"]): row
            for row in db.execute(
                f"""
                SELECT pe.thread_id, pe.plan_date, pe.id, pe.outcome, t.title
                FROM plan_entries pe
                JOIN tasks t ON t.id = pe.task_id
                WHERE pe.thread_id IN ({placeholders})
                  AND pe.plan_date IN ({date_marks})
                """,
                [*ids, *dates],
            )
        }
        note_counts = {
            int(row["thread_id"]): int(row["total"])
            for row in db.execute(
                f"""
                SELECT thread_id, COUNT(*) AS total
                FROM (
                    SELECT source_thread_id AS thread_id
                    FROM memos
                    WHERE source_thread_id IN ({placeholders})
                    UNION ALL
                    SELECT pe.thread_id
                    FROM memos m
                    JOIN plan_entries pe ON pe.id = m.source_entry_id
                    WHERE m.source_thread_id IS NULL
                      AND pe.thread_id IN ({placeholders})
                ) AS linked
                GROUP BY thread_id
                """,
                [*ids, *ids],
            )
        }
        result = []
        for item in threads:
            thread_id = int(item["id"])
            today = steps.get((thread_id, plan_date))
            next_day = steps.get((thread_id, tomorrow))
            today_outcome = today["outcome"] if today else None
            result.append(
                {
                    "id": thread_id,
                    "title": item["title"],
                    "done_when": item["done_when"],
                    "project_name": item["project_name"],
                    "status": item["status"],
                    "featured": bool(item["featured"]),
                    "today_entry_id": int(today["id"]) if today else None,
                    "needs_followup": (
                        item["status"] == "active"
                        and today_outcome == "completed"
                        and next_day is None
                    ),
                    "note_count": note_counts.get(thread_id, 0),
                    "recent": [
                        {
                            "date": day,
                            "title": ""
                            if steps.get((thread_id, day)) is None
                            else steps[(thread_id, day)]["title"],
                            "outcome": None
                            if steps.get((thread_id, day)) is None
                            else steps[(thread_id, day)]["outcome"],
                        }
                        for day in previous
                    ],
                }
            )
        result.sort(
            key=lambda item: (
                0 if item["featured"] else 1,
                0 if item["status"] == "active" else 1,
                item["id"],
            )
        )
        return result

    def create_thread(self, payload: dict) -> dict:
        title = str(payload.get("title", "")).strip()
        done_when = str(payload.get("done_when", "")).strip()
        step = str(payload.get("step", "")).strip()
        if not title:
            raise AppError("先给这条主线起个名字")
        if len(title) > 80:
            raise AppError("主线名称请控制在 80 个字以内")
        if not done_when:
            raise AppError("先写下一句完成标准，怎样算这条主线做完")
        if len(done_when) > 200:
            raise AppError("完成标准请控制在 200 个字以内")
        if not step:
            raise AppError("先写下今天这一步")
        if len(step) > 240:
            raise AppError("这一步请控制在 240 个字以内")
        plan_date = valid_date(payload.get("date"))
        estimate = as_non_negative_int(payload.get("estimate_minutes", 30), "预估时间")
        now = utc_now()
        with closing(self.connect()) as db, db:
            active = db.execute(
                "SELECT COUNT(*) FROM threads WHERE status = 'active'"
            ).fetchone()[0]
            if int(active) >= 2:
                raise AppError("同时进行的主线最多两条。先把一条暂停或做完")
            project_id = self._project_id(db, payload.get("project_name"))
            featured = 0 if int(active) else 1
            cursor = db.execute(
                """
                INSERT INTO threads(
                    title, done_when, project_id, status, featured,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (title, done_when, project_id, featured, now, now),
            )
            self._place_thread_step(
                db,
                int(cursor.lastrowid),
                plan_date,
                step,
                estimate,
                project_id,
                now,
            )
        return self.get_day(plan_date)

    def update_thread(self, thread_id: int, payload: dict) -> dict:
        now = utc_now()
        with closing(self.connect()) as db, db:
            current = db.execute(
                "SELECT * FROM threads WHERE id = ?", (thread_id,)
            ).fetchone()
            if not current:
                raise AppError("没有找到这条主线", HTTPStatus.NOT_FOUND)
            title = str(payload.get("title", current["title"])).strip()
            done_when = str(payload.get("done_when", current["done_when"])).strip()
            if not title:
                raise AppError("先给这条主线起个名字")
            if len(title) > 80:
                raise AppError("主线名称请控制在 80 个字以内")
            if not done_when:
                raise AppError("先写下一句完成标准，怎样算这条主线做完")
            if len(done_when) > 200:
                raise AppError("完成标准请控制在 200 个字以内")
            status = str(payload.get("status", current["status"]))
            if status not in {"active", "paused", "done"}:
                raise AppError("主线状态不正确")
            if status == "active" and current["status"] != "active":
                active = db.execute(
                    "SELECT COUNT(*) FROM threads WHERE status = 'active'"
                ).fetchone()[0]
                if int(active) >= 2:
                    raise AppError("同时进行的主线最多两条。先把一条暂停或做完")
            featured = int(current["featured"])
            if payload.get("featured") is True:
                if status != "active":
                    raise AppError("先恢复这条主线，再把它设为今天主推")
                featured = 1
            if status != "active":
                featured = 0
            project_id = current["project_id"]
            if "project_name" in payload:
                project_id = self._project_id(db, payload.get("project_name"))
            db.execute(
                """
                UPDATE threads
                SET title = ?, done_when = ?, project_id = ?, status = ?,
                    featured = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, done_when, project_id, status, featured, now, thread_id),
            )
            if featured:
                db.execute(
                    """
                    UPDATE threads
                    SET featured = 0, updated_at = ?
                    WHERE id <> ? AND featured = 1
                    """,
                    (now, thread_id),
                )
            self._ensure_featured_thread(db, now)
            anchor = payload.get("date") or date.today().isoformat()
        return self.get_day(valid_date(anchor))

    def create_thread_step(self, thread_id: int, payload: dict) -> dict:
        step = str(payload.get("step", payload.get("title", ""))).strip()
        if not step:
            raise AppError("先写下今天这一步")
        if len(step) > 240:
            raise AppError("这一步请控制在 240 个字以内")
        plan_date = valid_date(payload.get("date"))
        estimate = as_non_negative_int(payload.get("estimate_minutes", 30), "预估时间")
        now = utc_now()
        with closing(self.connect()) as db, db:
            thread = db.execute(
                "SELECT status, project_id FROM threads WHERE id = ?",
                (thread_id,),
            ).fetchone()
            if not thread:
                raise AppError("没有找到这条主线", HTTPStatus.NOT_FOUND)
            if thread["status"] != "active":
                raise AppError("先恢复这条主线，再写下今天这一步")
            self._place_thread_step(
                db,
                thread_id,
                plan_date,
                step,
                estimate,
                thread["project_id"],
                now,
            )
        return self.get_day(plan_date)

    def _place_thread_step(
        self,
        db: sqlite3.Connection,
        thread_id: int,
        plan_date: str,
        title: str,
        estimate: int,
        project_id: int | None,
        now: str,
    ) -> int:
        existing = db.execute(
            """
            SELECT pe.id, pe.outcome, pe.task_id
            FROM plan_entries pe
            WHERE pe.plan_date = ? AND pe.thread_id = ?
            """,
            (plan_date, thread_id),
        ).fetchone()
        if existing:
            if existing["outcome"] not in {"planned", "abandoned"}:
                raise AppError("这一天主线已经有一步")
            db.execute(
                """
                UPDATE tasks
                SET title = ?, status = 'active', completed_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (title[:240], now, existing["task_id"]),
            )
            db.execute(
                """
                UPDATE plan_entries
                SET estimate_minutes = ?, outcome = 'planned',
                    unfinished_reason = NULL, reason_note = '',
                    target_date = NULL, updated_at = ?
                WHERE id = ?
                """,
                (estimate, now, existing["id"]),
            )
            return int(existing["id"])
        task_cursor = db.execute(
            """
            INSERT INTO tasks(
                title, project_id, parent_id, definition,
                status, created_at, updated_at
            ) VALUES (?, ?, NULL, '', 'active', ?, ?)
            """,
            (title[:240], project_id, now, now),
        )
        next_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 "
            "FROM plan_entries WHERE plan_date = ?",
            (plan_date,),
        ).fetchone()[0]
        entry_cursor = db.execute(
            """
            INSERT INTO plan_entries(
                plan_date, task_id, estimate_minutes, sort_order,
                thread_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_date,
                int(task_cursor.lastrowid),
                estimate,
                next_order,
                thread_id,
                now,
                now,
            ),
        )
        return int(entry_cursor.lastrowid)

    @staticmethod
    def _ensure_featured_thread(db: sqlite3.Connection, now: str) -> None:
        db.execute(
            "UPDATE threads SET featured = 0, updated_at = ? WHERE status <> 'active' AND featured = 1",
            (now,),
        )
        active = db.execute(
            """
            SELECT id, featured FROM threads
            WHERE status = 'active'
            ORDER BY featured DESC, id
            """
        ).fetchall()
        if not active:
            return
        featured = [row for row in active if int(row["featured"])]
        keep = int(featured[0]["id"]) if len(featured) == 1 else int(active[0]["id"])
        if len(featured) == 1 and int(featured[0]["id"]) == keep:
            return
        db.execute(
            """
            UPDATE threads
            SET featured = CASE WHEN id = ? THEN 1 ELSE 0 END,
                updated_at = ?
            WHERE status = 'active'
            """,
            (keep, now),
        )

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
                SELECT pe.id, pe.task_id, pe.estimate_minutes, pe.thread_id,
                       th.project_id AS thread_project_id, th.status AS thread_status
                FROM plan_entries pe
                JOIN tasks t ON t.id = pe.task_id
                LEFT JOIN threads th ON th.id = pe.thread_id
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
            tomorrow = (
                datetime.strptime(plan_date, DATE_FORMAT).date() + timedelta(days=1)
            ).isoformat()
            followups = db.execute(
                """
                SELECT pe.id, pe.estimate_minutes, pe.thread_id, th.project_id
                FROM plan_entries pe
                JOIN threads th ON th.id = pe.thread_id
                WHERE pe.plan_date = ?
                  AND pe.outcome = 'completed'
                  AND th.status = 'active'
                  AND NOT EXISTS(
                      SELECT 1 FROM plan_entries next_step
                      WHERE next_step.thread_id = pe.thread_id
                        AND next_step.plan_date = ?
                  )
                """,
                (plan_date, tomorrow),
            ).fetchall()
            missing = [row["id"] for row in pending if row["id"] not in by_id]
            if missing:
                raise AppError("还有未处理的任务，请为每一条选择去向")
            missing_followups = [row["id"] for row in followups if row["id"] not in by_id]
            if missing_followups:
                raise AppError("主线还要写下明天的下一句")

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
                    if row["thread_id"] and row["thread_status"] == "active":
                        self._place_thread_step(
                            db,
                            int(row["thread_id"]),
                            tomorrow,
                            self._thread_next_sentence(decision),
                            int(row["estimate_minutes"] or 0),
                            row["thread_project_id"],
                            now,
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
                if row["thread_id"] and row["thread_status"] == "active":
                    self._place_thread_step(
                        db,
                        int(row["thread_id"]),
                        target_date,
                        self._thread_next_sentence(decision),
                        next_estimate,
                        row["thread_project_id"],
                        now,
                    )
                    continue
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

            for row in followups:
                self._place_thread_step(
                    db,
                    int(row["thread_id"]),
                    tomorrow,
                    self._thread_next_sentence(by_id[int(row["id"])]),
                    int(row["estimate_minutes"] or 0),
                    row["project_id"],
                    now,
                )

            self._resolve_parent_entries(db, plan_date, now)
            db.execute(
                "UPDATE days SET closed_at = ?, updated_at = ? "
                "WHERE plan_date = ?",
                (now, now, plan_date),
            )
        return self.get_day(plan_date)

    @staticmethod
    def _thread_next_sentence(decision: dict) -> str:
        sentence = str(decision.get("next_step", "")).strip()
        if not sentence:
            raise AppError("这条主线要写下明天的下一句")
        if len(sentence) > 240:
            raise AppError("这一步请控制在 240 个字以内")
        return sentence

    def move_entry(self, entry_id: int, payload: dict) -> dict:
        target_date = valid_date(payload.get("date"), "目标日期")
        today = date.today().isoformat()
        now = utc_now()
        with closing(self.connect()) as db, db:
            root = db.execute(
                """
                SELECT pe.id, pe.plan_date, pe.outcome, pe.estimate_minutes,
                       pe.task_id, pe.thread_id, t.parent_id, t.title
                FROM plan_entries pe
                JOIN tasks t ON t.id = pe.task_id
                WHERE pe.id = ?
                """,
                (entry_id,),
            ).fetchone()
            if not root:
                raise AppError("没有找到这条任务", HTTPStatus.NOT_FOUND)
            if root["thread_id"]:
                raise AppError("主线的这一步留在当天，收工时写下明天接着做的一句")
            if root["outcome"] != "planned":
                raise AppError("只有还没完成的任务可以移走")
            source_date = root["plan_date"]
            if target_date <= source_date:
                raise AppError("只能移到更晚的一天")
            if target_date < today:
                raise AppError("只能移到今天或之后")

            selected = [dict(root)]
            frontier = [int(root["task_id"])]
            while frontier:
                placeholders = ",".join("?" * len(frontier))
                children = db.execute(
                    f"""
                    SELECT pe.id, pe.plan_date, pe.outcome, pe.estimate_minutes,
                           pe.task_id, t.parent_id, t.title
                    FROM tasks t
                    JOIN plan_entries pe
                      ON pe.task_id = t.id AND pe.plan_date = ?
                    WHERE t.parent_id IN ({placeholders})
                      AND pe.outcome = 'planned'
                    """,
                    [source_date, *frontier],
                ).fetchall()
                frontier = []
                for child in children:
                    selected.append(dict(child))
                    frontier.append(int(child["task_id"]))

            climb_id = root["parent_id"]
            while climb_id is not None:
                parent_entry = db.execute(
                    """
                    SELECT pe.id, pe.plan_date, pe.outcome, pe.estimate_minutes,
                           pe.task_id, t.parent_id, t.title
                    FROM plan_entries pe
                    JOIN tasks t ON t.id = pe.task_id
                    WHERE pe.task_id = ? AND pe.plan_date = ?
                    """,
                    (climb_id, source_date),
                ).fetchone()
                if not parent_entry or parent_entry["outcome"] != "planned":
                    break
                selected_ids = [int(item["id"]) for item in selected]
                placeholders = ",".join("?" * len(selected_ids))
                others = db.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM plan_entries pe
                    JOIN tasks t ON t.id = pe.task_id
                    WHERE t.parent_id = ? AND pe.plan_date = ?
                      AND pe.id NOT IN ({placeholders})
                    """,
                    [climb_id, source_date, *selected_ids],
                ).fetchone()[0]
                if int(others):
                    break
                selected.append(dict(parent_entry))
                climb_id = parent_entry["parent_id"]

            entry_ids = [int(item["id"]) for item in selected]
            placeholders = ",".join("?" * len(entry_ids))
            running = db.execute(
                f"""
                SELECT 1 FROM time_segments
                WHERE plan_entry_id IN ({placeholders}) AND end_at IS NULL
                """,
                entry_ids,
            ).fetchone()
            if running:
                raise AppError("先结束计时，再把任务移走")

            moving_tasks = {int(item["task_id"]) for item in selected}
            for item in selected:
                parent_task = item["parent_id"]
                while parent_task is not None and int(parent_task) not in moving_tasks:
                    parent = db.execute(
                        "SELECT parent_id FROM tasks WHERE id = ?",
                        (parent_task,),
                    ).fetchone()
                    self._ensure_planned_entry(db, target_date, int(parent_task), 0, now)
                    moving_tasks.add(int(parent_task))
                    parent_task = parent["parent_id"] if parent else None

            for item in selected:
                self._relocate_entry(db, item, target_date, now)

        return {
            "moved_to": target_date,
            "title": root["title"],
            "source_date": source_date,
        }

    def _ensure_planned_entry(
        self,
        db: sqlite3.Connection,
        plan_date: str,
        task_id: int,
        estimate: int,
        now: str,
    ) -> None:
        existing = db.execute(
            """
            SELECT id, outcome, estimate_minutes
            FROM plan_entries
            WHERE plan_date = ? AND task_id = ?
            """,
            (plan_date, task_id),
        ).fetchone()
        if existing:
            if existing["outcome"] == "completed":
                raise AppError("这一天已经完成过这条任务")
            if existing["outcome"] != "planned" or (
                not int(existing["estimate_minutes"] or 0) and estimate
            ):
                db.execute(
                    """
                    UPDATE plan_entries
                    SET outcome = 'planned',
                        estimate_minutes = CASE
                            WHEN estimate_minutes = 0 THEN ? ELSE estimate_minutes
                        END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (estimate, now, existing["id"]),
                )
            return
        next_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM plan_entries WHERE plan_date = ?",
            (plan_date,),
        ).fetchone()[0]
        db.execute(
            """
            INSERT INTO plan_entries(
                plan_date, task_id, estimate_minutes, sort_order,
                outcome, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'planned', ?, ?)
            """,
            (plan_date, task_id, estimate, next_order, now, now),
        )

    def _relocate_entry(
        self, db: sqlite3.Connection, item: dict, target_date: str, now: str
    ) -> None:
        entry_id = int(item["id"])
        task_id = int(item["task_id"])
        estimate = int(item["estimate_minutes"] or 0)
        has_segments = db.execute(
            "SELECT EXISTS(SELECT 1 FROM time_segments WHERE plan_entry_id = ?)",
            (entry_id,),
        ).fetchone()[0]
        existing = db.execute(
            """
            SELECT id, outcome FROM plan_entries
            WHERE plan_date = ? AND task_id = ? AND id <> ?
            """,
            (target_date, task_id, entry_id),
        ).fetchone()
        if existing and existing["outcome"] == "completed":
            raise AppError("这一天已经完成过这条任务")
        if existing:
            self._ensure_planned_entry(db, target_date, task_id, estimate, now)
            if has_segments:
                db.execute(
                    """
                    UPDATE plan_entries
                    SET outcome = 'rescheduled', estimate_minutes = 0,
                        target_date = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (target_date, now, entry_id),
                )
            else:
                db.execute("DELETE FROM plan_entries WHERE id = ?", (entry_id,))
            return
        if has_segments:
            self._ensure_planned_entry(db, target_date, task_id, estimate, now)
            db.execute(
                """
                UPDATE plan_entries
                SET outcome = 'rescheduled', estimate_minutes = 0,
                    target_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (target_date, now, entry_id),
            )
            return
        next_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM plan_entries WHERE plan_date = ?",
            (target_date,),
        ).fetchone()[0]
        db.execute(
            """
            UPDATE plan_entries
            SET plan_date = ?, sort_order = ?, outcome = 'planned',
                estimate_minutes = ?, target_date = NULL,
                unfinished_reason = NULL, reason_note = '', updated_at = ?
            WHERE id = ?
            """,
            (target_date, next_order, estimate, now, entry_id),
        )

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

    def list_segments_between(self, start: str, end: str) -> list[dict]:
        start_date = valid_date(start, "开始日期")
        end_date = valid_date(end, "结束日期")
        if end_date < start_date:
            raise AppError("结束日期不能早于开始日期")
        if (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days > 31:
            raise AppError("一次最多查看 31 天的时间记录")
        now = utc_now()
        with closing(self.connect()) as db, db:
            self._expire_focus_timer(db, now)
            return [
                dict(row)
                for row in db.execute(
                    """
                    SELECT ts.id, ts.start_at, ts.end_at, ts.duration_seconds,
                           ts.mode, ts.focus_completed, pe.id AS entry_id,
                           pe.plan_date, pe.estimate_minutes, pe.planned_start,
                           t.title, COALESCE(p.name, '未分类') AS project_name
                    FROM time_segments ts
                    JOIN plan_entries pe ON pe.id = ts.plan_entry_id
                    JOIN tasks t ON t.id = ts.task_id
                    LEFT JOIN projects p ON p.id = t.project_id
                    WHERE pe.plan_date BETWEEN ? AND ?
                    ORDER BY ts.start_at, ts.id
                    """,
                    (start_date, end_date),
                )
            ]

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
        from app.services.routine_questions import generate_routine_questions

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

    def start_routine_timer(self, payload: dict) -> dict:
        routine_id = as_non_negative_int(payload.get("routine_id"), "每日必做")
        plan_date = valid_date(payload.get("date"))
        if plan_date > date.today().isoformat():
            raise AppError("还没到这一天，不能开始计时")
        now = utc_now()
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
            already = db.execute(
                """
                SELECT id FROM routine_segments
                WHERE routine_id = ? AND plan_date = ? AND end_at IS NULL
                """,
                (routine_id, plan_date),
            ).fetchone()
            if already:
                return {
                    "already_running": True,
                    "stopped_entry_id": None,
                    "date": plan_date,
                    "routines": self._routines_on(db, plan_date),
                }
            stopped = self._close_running(db, now)
            self._close_running_routine(db, now)
            db.execute(
                """
                INSERT INTO routine_segments(
                    routine_id, plan_date, start_at, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (routine_id, plan_date, now, now),
            )
            return {
                "already_running": False,
                "stopped_entry_id": int(stopped["plan_entry_id"]) if stopped else None,
                "date": plan_date,
                "routines": self._routines_on(db, plan_date),
            }

    def stop_routine_timer(self, payload: dict) -> dict:
        routine_id = as_non_negative_int(payload.get("routine_id"), "每日必做")
        now = utc_now()
        with closing(self.connect()) as db, db:
            running = db.execute(
                """
                SELECT id, routine_id, plan_date, start_at
                FROM routine_segments
                WHERE end_at IS NULL
                """
            ).fetchone()
            if not running or int(running["routine_id"]) != routine_id:
                raise AppError("这项每日必做现在没有在计时")
            self._close_running_routine(db, now)
            return {
                "stopped": True,
                "duration_seconds": seconds_between(running["start_at"], now),
                "date": running["plan_date"],
                "routines": self._routines_on(db, running["plan_date"]),
            }

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
            "feedback_count": 0,
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
        feedback = {
            int(row["source_routine_id"]): int(row["total"])
            for row in db.execute(
                """
                SELECT source_routine_id, COUNT(*) AS total
                FROM memos
                WHERE source_kind = 'routine'
                  AND source_routine_id IS NOT NULL
                  AND source_plan_date = ?
                GROUP BY source_routine_id
                """,
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
            item = Database._public_routine(row, int(row["id"]) in completed)
            item["feedback_count"] = feedback.get(int(row["id"]), 0)
            item["actual_seconds"] = 0
            item["is_running"] = False
            item["running_started_at"] = None
            routines.append(item)
        for row in db.execute(
            """
            SELECT routine_id, start_at, end_at, duration_seconds
            FROM routine_segments
            WHERE plan_date = ?
            """,
            (plan_date,),
        ):
            routine_id = int(row["routine_id"])
            item = next((entry for entry in routines if entry["id"] == routine_id), None)
            if not item:
                continue
            if row["end_at"]:
                item["actual_seconds"] += int(row["duration_seconds"] or 0)
            else:
                item["is_running"] = True
                item["running_started_at"] = row["start_at"]
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
