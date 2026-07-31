-- Anonymous field observations used to calibrate level-crossing TD berths.
-- Safe to run in Supabase SQL Editor. No public read or write policy is created.

create table if not exists public.level_crossing_observations (
  id text primary key,
  crossing_id text not null check (crossing_id in ('whyke-road', 'basin-road', 'stockbridge-road')),
  crossing_name text not null,
  what3words text not null,
  state text not null check (state in ('OPEN', 'CLOSING', 'CLOSED', 'OPENING', 'TRAIN_PASSED')),
  event_kind text not null default 'quick' check (event_kind in ('quick', 'watch')),
  observed_at timestamptz not null,
  received_at timestamptz not null default now(),
  session_id text,
  note text check (char_length(note) <= 300),
  client_prediction jsonb not null default '{}'::jsonb,
  td_snapshot jsonb not null default '{}'::jsonb
);

create index if not exists level_crossing_observations_crossing_time_idx
  on public.level_crossing_observations(crossing_id, observed_at desc);
create index if not exists level_crossing_observations_session_idx
  on public.level_crossing_observations(session_id, observed_at)
  where session_id is not null;

alter table public.level_crossing_observations enable row level security;
grant usage on schema public to service_role;
grant select, insert, update on table public.level_crossing_observations to service_role;
