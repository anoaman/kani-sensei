-- Kani Sensei — Phase 2: Warm-Up Quiz + assignment history snapshots.
-- Extends the Phase 0 spine; does not restructure existing tables.
-- Apply via: psql "$DATABASE_URL" -f migrations/001_quiz_and_snapshots.sql

-- Daily frozen copy of SRS + accuracy so Decay Map can detect real regression.
-- One row per subject per calendar day (UTC). Sync appends after upserting live state.
create table if not exists wk_assignment_snapshots (
    snap_date            date not null,
    subject_id           bigint not null references wk_subjects (id),
    srs_stage            integer,
    meaning_correct      integer,
    meaning_incorrect    integer,
    reading_correct      integer,
    reading_incorrect    integer,
    primary key (snap_date, subject_id)
);
create index if not exists wk_assignment_snapshots_subject_idx
    on wk_assignment_snapshots (subject_id, snap_date desc);

-- Warm-Up Quiz sessions (single-user for now; no user_id column yet).
create table if not exists quiz_sessions (
    id              uuid primary key,
    min_level       integer not null,
    max_level       integer not null,
    question_count  integer not null,
    created_at      timestamptz not null default now(),
    finished_at     timestamptz,
    score_correct   integer not null default 0,
    score_total     integer not null default 0,
    meta            jsonb not null default '{}'::jsonb
);

create table if not exists quiz_questions (
    id              uuid primary key,
    session_id      uuid not null references quiz_sessions (id) on delete cascade,
    position        integer not null,
    subject_id      bigint not null references wk_subjects (id),
    prompt_type     text not null,          -- meaning | reading
    characters      text,
    object_type     text not null,
    level           integer not null,
    decay_score     integer not null default 0,
    correct_answer  text not null,
    choices         jsonb not null,         -- json array of strings (shuffled)
    correct_index   integer not null,
    answered_index  integer,
    is_correct      boolean,
    answered_at     timestamptz,
    unique (session_id, position)
);
create index if not exists quiz_questions_session_idx on quiz_questions (session_id);
