-- Kani Sensei platform — Phase 5: readings and the full subject catalog.
-- wk_catalog is the entire WaniKani subject list (levels 1–60), kept apart
-- from wk_subjects so locked items never leak into drills, quizzes, or courses.
-- Apply via: psql "$DATABASE_URL" -f migrations/003_reading.sql
-- The app also creates these tables on first use (CREATE TABLE IF NOT EXISTS).

create table if not exists wk_catalog (
    id                 bigint primary key,
    object_type        text not null,
    level              integer not null,
    characters         text,
    slug               text,
    primary_meaning    text,
    meanings           jsonb not null default '[]'::jsonb,
    readings           jsonb not null default '[]'::jsonb,
    parts_of_speech    jsonb not null default '[]'::jsonb,
    context_sentences  jsonb not null default '[]'::jsonb,
    component_ids      bigint[] not null default '{}',
    amalgamation_ids   bigint[] not null default '{}',
    similar_ids        bigint[] not null default '{}',
    audio_url          text,
    lesson_position    integer,
    synced_at          timestamptz
);
create index if not exists wk_catalog_level_idx on wk_catalog (level);
create index if not exists wk_catalog_type_idx on wk_catalog (object_type);

create table if not exists reading_passages (
    id            text primary key,
    kind          text not null,                  -- level | daily | custom
    level         integer,
    day           date,
    idx           integer,
    title         text,
    sentences     jsonb not null,                 -- [{ja, en, source_id}]
    covers        bigint[] not null default '{}',
    plan_version  integer not null default 1,
    created_at    timestamptz not null default now()
);
create index if not exists reading_passages_level_idx on reading_passages (kind, level);
create index if not exists reading_passages_day_idx on reading_passages (day);

create table if not exists reading_progress (
    passage_id      text primary key,
    opened_at       timestamptz,
    finished_at     timestamptz,
    lookups         bigint[] not null default '{}',
    quiz_correct    integer,
    quiz_total      integer,
    listen_correct  integer,
    listen_total    integer,
    recall_correct  integer,
    recall_total    integer,
    updated_at      timestamptz
);
