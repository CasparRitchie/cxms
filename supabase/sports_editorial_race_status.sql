-- Race-level cancellation and stat-sheet linkage.
-- Apply after sports_editorial_stat_sheet_administration.sql. Additive and safe to rerun.

alter table public.sports_editorial_submissions
  add column if not exists fis_race_ids bigint[] not null default '{}';

create index if not exists sports_editorial_submissions_fis_race_ids_idx
  on public.sports_editorial_submissions using gin (fis_race_ids);

-- Race status remains attached to the canonical competition entity. The
-- application preserves manual_* metadata when refreshing official FIS data.
