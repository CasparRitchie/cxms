-- Add an explicit FIS season ending year to existing Sports Editorial workspaces.
alter table public.sports_editorial_submissions
  add column if not exists season_code integer;

update public.sports_editorial_submissions
set season_code = case
  when extract(month from event_date) >= 7 then extract(year from event_date)::integer + 1
  else extract(year from event_date)::integer
end
where season_code is null and event_date is not null;

create index if not exists sports_editorial_submissions_workspace_season_idx
  on public.sports_editorial_submissions (workspace_id, season_code, event_date);

comment on column public.sports_editorial_submissions.season_code is
  'Four-digit year in which the sporting season ends; for example 2027 for 2026/27.';
