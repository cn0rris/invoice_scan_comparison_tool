CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    prompt_text     TEXT NOT NULL,
    invoice_dir     TEXT NOT NULL,
    ground_truth_dir TEXT NOT NULL,
    models_json     TEXT NOT NULL,
    total_pairs     INTEGER NOT NULL DEFAULT 0,
    completed_pairs INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS results (
    id                TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    model_id          TEXT NOT NULL,
    invoice_stem      TEXT NOT NULL,
    invoice_filename  TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    raw_output        TEXT,
    parsed_json       TEXT,
    ground_truth_json TEXT,
    diff_json         TEXT,
    mistake_count     INTEGER,
    error_message     TEXT,
    started_at        TEXT,
    completed_at      TEXT,
    duration_ms       INTEGER,
    UNIQUE(run_id, model_id, invoice_stem)
);

CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_run_model ON results(run_id, model_id);
