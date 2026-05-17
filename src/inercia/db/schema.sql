PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upwork_id       TEXT    NOT NULL UNIQUE,
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    job_type        TEXT    NOT NULL CHECK(job_type IN ('hourly', 'fixed')),
    budget_min      REAL,
    budget_max      REAL,
    hourly_rate_min REAL,
    hourly_rate_max REAL,
    duration        TEXT,
    experience_level TEXT,
    skills          TEXT,
    client_country  TEXT,
    client_total_spent REAL DEFAULT 0,
    client_hire_rate   REAL DEFAULT 0,
    client_reviews     INTEGER DEFAULT 0,
    connects_required  INTEGER DEFAULT 0,
    questions       TEXT,
    allows_attachments INTEGER DEFAULT 0,
    raw_markdown    TEXT,
    scraped_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    roi_score       REAL,
    status          TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'scored', 'generating', 'ready', 'approved', 'rejected', 'submitted', 'blacklisted'))
) STRICT;

CREATE TABLE IF NOT EXISTS proposals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    cover_letter    TEXT    NOT NULL,
    screening_answers TEXT,
    bid_rate        REAL    NOT NULL,
    bid_type        TEXT    NOT NULL CHECK(bid_type IN ('hourly', 'fixed')),
    cv_pdf_path     TEXT,
    connects_cost   INTEGER NOT NULL,
    roi_score       REAL    NOT NULL,
    critic_approved INTEGER NOT NULL DEFAULT 0,
    critic_notes    TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'submitted')),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    submitted_at    TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS connects_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER REFERENCES proposals(id),
    amount      INTEGER NOT NULL,
    action      TEXT    NOT NULL CHECK(action IN ('spent', 'refunded')),
    timestamp   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,
    value       TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_roi ON jobs(roi_score DESC);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_job ON proposals(job_id);
CREATE INDEX IF NOT EXISTS idx_connects_ts ON connects_log(timestamp DESC);
