-- Kani Sensei platform — Phase 6: sentence index.
-- One row per WaniKani context sentence, with the words and kanji it contains.
-- Rebuilt at the end of a catalog sync. Apply via:
--   psql "$DATABASE_URL" -f migrations/004_sentences.sql
-- The app also creates this table on first use (CREATE TABLE IF NOT EXISTS).

create table if not exists reading_sentences (
    source_id   bigint not null,
    idx         integer not null,
    ja          text not null,
    en          text not null default '',
    level       integer not null,
    word_ids    bigint[] not null default '{}',
    kanji_ids   bigint[] not null default '{}',
    max_level   integer not null,
    listenable  boolean not null default false,
    primary key (source_id, idx)
);
create index if not exists reading_sentences_words_idx on reading_sentences using gin (word_ids);
create index if not exists reading_sentences_kanji_idx on reading_sentences using gin (kanji_ids);
create index if not exists reading_sentences_max_level_idx on reading_sentences (max_level);
