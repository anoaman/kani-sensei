-- Kani Sensei platform — Phase 6: recall tally on a finished passage.
-- Apply via: psql "$DATABASE_URL" -f migrations/005_recall.sql
-- The app also adds these columns on first use.

alter table reading_progress
    add column if not exists recall_correct integer,
    add column if not exists recall_total integer;
