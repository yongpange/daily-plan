"""结构演进与数据迁移。

从旧 server.py 的 Database.initialize / 静态方法原样拆出：
对新建库，schema.sql 的 CREATE TABLE 已包含全部列，本模块的
ensure_columns 是空操作；对旧库，靠这里的 ALTER TABLE 补列。
"""

from __future__ import annotations

import sqlite3

from app.core.time import utc_now


def ensure_columns(db: sqlite3.Connection) -> None:
    """给旧库补齐后续版本才加入的列（新库已含这些列，自动跳过）。"""
    _ensure_column(db, "time_segments", "mode", "TEXT NOT NULL DEFAULT 'open'")
    _ensure_column(db, "time_segments", "target_seconds", "INTEGER")
    _ensure_column(
        db,
        "time_segments",
        "focus_completed",
        "INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(db, "memos", "source_entry_id", "INTEGER")
    _ensure_column(db, "memos", "source_title", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(db, "memos", "source_estimate_minutes", "INTEGER")
    _ensure_column(db, "memos", "source_actual_seconds", "INTEGER")
    _ensure_column(db, "memos", "source_plan_date", "TEXT")
    _ensure_column(db, "memos", "source_kind", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(db, "memos", "source_routine_id", "INTEGER")
    _ensure_column(db, "memos", "source_thread_id", "INTEGER")
    _ensure_column(db, "memos", "source_task_id", "INTEGER")
    _ensure_column(db, "memos", "note_title", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(db, "memos", "note_link", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(db, "plan_entries", "thread_id", "INTEGER")


def ensure_thread_step_index(db: sqlite3.Connection) -> None:
    """每个主线每天最多一步。必须在 ensure_columns 之后调用：
    旧库缺 plan_entries.thread_id 列时该索引建不起来。"""
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS one_thread_step_per_day
        ON plan_entries(plan_date, thread_id)
        WHERE thread_id IS NOT NULL
        """
    )


def rebuild_note_images_id(db: sqlite3.Connection) -> None:
    """note_images.id 需要 AUTOINCREMENT；旧表整体重建补齐。"""
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


def merge_daily_notes(db: sqlite3.Connection) -> None:
    """把 days.reflection 与当天图片并入感悟，只做一次。"""
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


def _ensure_column(
    db: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
