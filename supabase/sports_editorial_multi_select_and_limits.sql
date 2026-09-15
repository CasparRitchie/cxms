-- Multi-event and multi-gender metadata plus editorial length safeguards.
-- Apply after sports_editorial_multi_sport_catalogue.sql.

alter table public.sports_editorial_submissions
  add column if not exists event_names text[] not null default '{}',
  add column if not exists genders text[] not null default '{}',
  add column if not exists fis_event_discipline_codes text[] not null default '{}';

update public.sports_editorial_submissions
set event_names = array[event_name]
where cardinality(event_names) = 0 and event_name is not null and event_name <> '';

update public.sports_editorial_submissions
set genders = array[gender]
where cardinality(genders) = 0 and gender is not null and gender <> '';

update public.sports_editorial_submissions
set fis_event_discipline_codes = array[fis_event_discipline_code]
where cardinality(fis_event_discipline_codes) = 0
  and fis_event_discipline_code is not null and fis_event_discipline_code <> '';

alter table public.sports_editorial_submissions
  drop constraint if exists sports_editorial_submissions_title_length_check,
  drop constraint if exists sports_editorial_submissions_working_notes_length_check,
  drop constraint if exists sports_editorial_submissions_unused_stats_length_check;

alter table public.sports_editorial_submissions
  add constraint sports_editorial_submissions_title_length_check check (char_length(title) <= 160) not valid,
  add constraint sports_editorial_submissions_working_notes_length_check check (char_length(coalesce(working_notes, '')) <= 10000) not valid,
  add constraint sports_editorial_submissions_unused_stats_length_check check (char_length(coalesce(unused_stats, '')) <= 2500) not valid;

alter table public.sports_editorial_stats
  drop constraint if exists sports_editorial_stats_text_length_check;

alter table public.sports_editorial_stats
  add constraint sports_editorial_stats_text_length_check check (
    char_length(coalesce(nullif(edited_text, ''), stat_text)) <= 5000
  ) not valid;
