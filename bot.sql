CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    is_allowed  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    kind           TEXT NOT NULL CHECK (kind IN ('print', 'scan')),
    file_path      TEXT,
    original_name  TEXT,
    copies         INTEGER NOT NULL DEFAULT 1,
    duplex         INTEGER NOT NULL DEFAULT 0,
    pages          TEXT,
    scale          TEXT NOT NULL DEFAULT 'fit' CHECK (scale IN ('fit', 'stretch')),
    status         TEXT NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft', 'queued', 'processing', 'done', 'error', 'cancelled')),
    error          TEXT,
    message_id     INTEGER,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs (user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
