-- Persistent official FIS classifications for Sports Editorial research.
-- Additive and safe to review/run independently of the stat-sheet publishing tables.

create table if not exists public.sports_editorial_result_imports (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  race_id bigint not null,
  event_id bigint,
  season_code integer,
  discipline_code text not null default 'AL',
  event_code text,
  category_code text,
  gender text check (gender in ('W','M','X')),
  venue text,
  nation_code text,
  race_date date,
  source_url text not null,
  source_name text not null default 'fis_official_results',
  import_status text not null default 'complete' check (import_status in ('complete','partial','failed')),
  row_count integer not null default 0 check (row_count >= 0),
  source_hash text,
  last_error text,
  imported_at timestamptz not null default now(),
  refreshed_at timestamptz not null default now(),
  unique (workspace_id, race_id)
);

create table if not exists public.sports_editorial_results (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  race_id bigint not null,
  fis_code bigint not null,
  competitor_id bigint,
  athlete_name text not null,
  nation_code text not null,
  bib integer,
  birth_year integer,
  place integer check (place is null or place > 0),
  result_status text not null default 'finished'
    check (result_status in ('finished','did_not_qualify','did_not_finish','did_not_start','disqualified')),
  total_time text,
  diff_time text,
  fis_points numeric,
  cup_points numeric,
  source_url text not null,
  imported_at timestamptz not null default now(),
  unique (workspace_id, race_id, fis_code),
  foreign key (workspace_id, race_id)
    references public.sports_editorial_result_imports(workspace_id, race_id)
    on delete cascade
);

create index if not exists sports_editorial_result_imports_coverage_idx
  on public.sports_editorial_result_imports(workspace_id, race_date desc, season_code, event_code, gender);
create index if not exists sports_editorial_result_imports_venue_idx
  on public.sports_editorial_result_imports(workspace_id, venue, race_date desc);
create index if not exists sports_editorial_results_athlete_idx
  on public.sports_editorial_results(workspace_id, fis_code, race_id);
create index if not exists sports_editorial_results_nation_place_idx
  on public.sports_editorial_results(workspace_id, nation_code, place, race_id);

alter table public.sports_editorial_result_imports enable row level security;
alter table public.sports_editorial_results enable row level security;

-- The Flask server keeps the service key server-side and applies workspace scoping.
-- No anon/authenticated policies are added.
grant select, insert, update, delete on table
  public.sports_editorial_result_imports,
  public.sports_editorial_results
to service_role;

comment on table public.sports_editorial_result_imports is
  'One auditable refresh record per official FIS competition classification.';
comment on table public.sports_editorial_results is
  'Normalised athlete classifications used for evidence-backed editorial research.';
