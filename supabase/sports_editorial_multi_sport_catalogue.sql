-- Expand Sports Editorial beyond the original Alpine-only pilot.
-- Apply after sports_editorial_pilot.sql and before deploying the multi-sport app.

alter table public.sports_editorial_submissions
  drop constraint if exists sports_editorial_submissions_sport_check;

alter table public.sports_editorial_submissions
  add constraint sports_editorial_submissions_sport_check check (sport in (
    'alpine_skiing', 'ski_jumping', 'cross_country_skiing', 'nordic_combined',
    'freestyle', 'freeski_park_and_pipe', 'freestyle_ski_cross',
    'snowboard_cross', 'snowboard_park_and_pipe', 'snowboard_alpine'
  ));

alter table public.sports_editorial_submissions
  add column if not exists fis_discipline_code text,
  add column if not exists fis_event_discipline_code text;

update public.sports_editorial_submissions
set fis_discipline_code = 'AL'
where sport = 'alpine_skiing' and fis_discipline_code is null;

comment on column public.sports_editorial_submissions.fis_discipline_code is
  'FIS sport/discipline code used by the Media Stat Sheets API, for example AL, JP or CC.';

comment on column public.sports_editorial_submissions.fis_event_discipline_code is
  'Event-level FIS discipline code from the editorial catalogue, for example SL, GS or LH.';
