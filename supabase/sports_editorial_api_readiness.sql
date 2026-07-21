-- Additive API-readiness fields for an existing Sports Editorial Pilot database.
-- Safe to run more than once in the Supabase SQL Editor.

alter table public.sports_editorial_submissions
  add column if not exists fis_submission_notes text;

alter table public.sports_editorial_stat_entities
  add column if not exists mention_text text;

comment on column public.sports_editorial_submissions.fis_submission_notes is
  'Optional note sent to the FIS media team; separate from internal editor_notes.';

comment on column public.sports_editorial_stat_entities.mention_text is
  'Exact visible text converted to an inline FIS entity marker; null means attachment-only.';
