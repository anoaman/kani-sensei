-- Kani Sensei platform — Phase 0: data spine (Neon / Postgres).
-- Single-user (Kibz) for now, but no schema assumptions that block multi-user later.
-- Daily re-sync is idempotent: every table upserts on its natural WK key.
-- Apply via: psql "$DATABASE_URL" -f migrations/000_data_spine.sql

-- Cached WK subject catalog (kanji / vocabulary / radical).
create table if not exists wk_subjects (
    id              bigint primary key,              -- WK subject id
    object_type     text not null,                   -- kanji | vocabulary | radical | kana_vocabulary
    level           integer not null,
    characters      text,                            -- null for some radicals (image-only)
    slug            text,
    primary_meaning text,
    readings        jsonb not null default '[]'::jsonb, -- json array (as returned by WK)
    meanings        jsonb not null default '[]'::jsonb, -- json array
    raw             jsonb,                            -- full WK payload for future needs
    synced_at       timestamptz
);
create index if not exists wk_subjects_level_idx on wk_subjects (level);
create index if not exists wk_subjects_type_idx  on wk_subjects (object_type);

-- Snapshot of review performance per subject (the Decay Map fuel).
create table if not exists wk_review_stats (
    subject_id         bigint primary key,
    meaning_correct    integer,
    meaning_incorrect  integer,
    reading_correct    integer,
    reading_incorrect  integer,
    percentage_correct integer,
    updated_at         timestamptz
);

-- SRS state per subject (Runway pacing + "what rotted" signal).
create table if not exists wk_assignments (
    subject_id   bigint primary key,
    srs_stage    integer,
    available_at timestamptz,
    unlocked_at  timestamptz,
    started_at   timestamptz,
    passed_at    timestamptz,
    burned_at    timestamptz,
    synced_at    timestamptz
);
create index if not exists wk_assignments_srs_idx on wk_assignments (srs_stage);

-- Audit trail: one row per sync run.
create table if not exists sync_runs (
    id          bigserial primary key,
    started_at  timestamptz not null,
    finished_at timestamptz,
    status      text not null default 'running',      -- running | ok | error
    counts      jsonb not null default '{}'::jsonb,   -- json {subjects, review_stats, assignments}
    error       text
);
