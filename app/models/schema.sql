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
    thread_id INTEGER,
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
    updated_at TEXT NOT NULL,
    source_entry_id INTEGER,
    source_title TEXT NOT NULL DEFAULT '',
    source_estimate_minutes INTEGER,
    source_actual_seconds INTEGER,
    source_plan_date TEXT,
    source_kind TEXT NOT NULL DEFAULT '',
    source_routine_id INTEGER,
    source_thread_id INTEGER,
    source_task_id INTEGER,
    note_title TEXT NOT NULL DEFAULT '',
    note_link TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS plan_entries_by_date
ON plan_entries(plan_date, sort_order);

CREATE INDEX IF NOT EXISTS time_segments_by_entry
ON time_segments(plan_entry_id, start_at);

CREATE INDEX IF NOT EXISTS memos_by_date
ON memos(memo_date DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS memo_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL
        CHECK (owner_type IN ('day', 'memo')),
    owner_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS note_images_by_owner
ON note_images(owner_type, owner_key, id);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'done')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS reminders_by_time
ON reminders(status, remind_at);

CREATE TABLE IF NOT EXISTS memo_reads (
    owner_kind TEXT NOT NULL
        CHECK (owner_kind IN ('memo', 'daily')),
    owner_key TEXT NOT NULL,
    read_count INTEGER NOT NULL DEFAULT 0
        CHECK (read_count >= 0),
    last_read_at TEXT NOT NULL,
    PRIMARY KEY (owner_kind, owner_key)
);

CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    done_when TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'done')),
    featured INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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

CREATE TABLE IF NOT EXISTS routine_segments (
    id INTEGER PRIMARY KEY,
    routine_id INTEGER NOT NULL
        REFERENCES routines(id) ON DELETE CASCADE,
    plan_date TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT,
    duration_seconds INTEGER
        CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS routine_segments_by_day
ON routine_segments(plan_date, routine_id);

CREATE TABLE IF NOT EXISTS routine_challenges (
    id TEXT PRIMARY KEY,
    questions_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    unlock_token TEXT,
    unlock_expires_at TEXT,
    created_at TEXT NOT NULL
);
