-- Kani Sensei — Phase 4: typed drills, ghost reviews, leech clinic.
-- Extends the Phase 2 quiz tables; does not restructure existing ones.
-- Apply via: psql "$DATABASE_URL" -f migrations/002_drills.sql
-- The drill API also CREATE TABLE IF NOT EXISTS on first use so a rolling
-- deploy still works if this file hasn't been applied yet.

create table if not exists drill_sessions (
    id              uuid primary key,
    kind            text not null,              -- recall | reverse | mc | speed
    pool            text not null,              -- decay | burned | leeches | due | misses
    min_level       integer not null,
    max_level       integer not null,
    question_count  integer not null,
    created_at      timestamptz not null default now(),
    finished_at     timestamptz,
    score_correct   integer not null default 0,
    score_total     integer not null default 0,
    combo_best      integer not null default 0,
    meta            jsonb not null default '{}'::jsonb
);
create index if not exists drill_sessions_created_idx on drill_sessions (created_at desc);

create table if not exists drill_questions (
    id                  uuid primary key,
    session_id          uuid not null references drill_sessions (id) on delete cascade,
    position            integer not null,
    subject_id          bigint not null references wk_subjects (id),
    prompt_type         text not null,          -- meaning | reading | reverse
    characters          text,
    object_type         text not null,
    level               integer not null,
    decay_score         integer not null default 0,
    correct_answer      text not null,
    accepted_answers    jsonb not null default '[]'::jsonb,
    choices             jsonb not null default '[]'::jsonb,
    correct_index       integer,
    answered_text       text,
    answered_index      integer,
    is_correct          boolean,
    answered_at         timestamptz,
    unique (session_id, position)
);
create index if not exists drill_questions_session_idx on drill_questions (session_id);

-- Local "Sensei notebook": items this app has seen you miss, independent of WK.
create table if not exists drill_misses (
    subject_id      bigint primary key references wk_subjects (id),
    miss_count      integer not null default 0,
    hit_count       integer not null default 0,
    last_missed_at  timestamptz,
    last_prompt_type text,
    last_answer     text
);
