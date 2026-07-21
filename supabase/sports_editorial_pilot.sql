-- Sports Editorial Pilot: isolated tables for temporary use in the NPS Me project.
-- Safe to run in Supabase SQL Editor. This does not alter existing NPS tables.
-- Before production, use a customer-owned project, user-scoped RLS, and Supabase Auth.

create extension if not exists pgcrypto;

create table if not exists public.sports_editorial_memberships (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  user_id uuid not null,
  editorial_role text not null check (editorial_role in ('journalist', 'sub_editor')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (workspace_id, user_id)
);

create table if not exists public.sports_editorial_submissions (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  author_user_id uuid,
  title text not null,
  sport text not null default 'alpine_skiing' check (sport = 'alpine_skiing'),
  competition text,
  event_name text,
  gender text check (gender in ('W', 'M', 'X')),
  location text,
  event_date date,
  fis_event_ids bigint[] not null default '{}',
  fis_external_id text not null,
  author_name text not null,
  author_email text,
  status text not null default 'draft' check (status in ('draft','submitted','in_review','changes_requested','approved','exported')),
  editor_notes text,
  fis_publication jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  submitted_at timestamptz,
  approved_at timestamptz,
  unique (workspace_id, fis_external_id)
);

create table if not exists public.sports_editorial_stats (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.sports_editorial_submissions(id) on delete cascade,
  sort_order integer not null default 0,
  content_type text not null default 'stat' check (content_type in ('stat','section','heading')),
  stat_text text not null,
  edited_text text,
  editor_comment text,
  tags text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.sports_editorial_entities (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  entity_type text not null check (entity_type in ('athlete','country','event','competition')),
  name text not null,
  canonical_id text,
  canonical_url text,
  country_code text,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create table if not exists public.sports_editorial_stat_entities (
  id uuid primary key default gen_random_uuid(),
  stat_id uuid not null references public.sports_editorial_stats(id) on delete cascade,
  entity_id uuid not null references public.sports_editorial_entities(id) on delete cascade,
  relationship_type text not null default 'mentions',
  created_at timestamptz not null default now(),
  unique (stat_id, entity_id, relationship_type)
);

create index if not exists sports_editorial_submissions_workspace_status_idx on public.sports_editorial_submissions(workspace_id, status, submitted_at desc);
create index if not exists sports_editorial_stats_submission_order_idx on public.sports_editorial_stats(submission_id, sort_order);
create index if not exists sports_editorial_entities_workspace_name_idx on public.sports_editorial_entities(workspace_id, entity_type, name);

alter table public.sports_editorial_memberships enable row level security;
alter table public.sports_editorial_submissions enable row level security;
alter table public.sports_editorial_stats enable row level security;
alter table public.sports_editorial_entities enable row level security;
alter table public.sports_editorial_stat_entities enable row level security;

-- The pilot Flask server uses the service-role key and enforces workspace access.
-- No public/anon policies are deliberately created.

-- After creating a user through the existing NPS Me process, grant pilot access:
-- insert into public.sports_editorial_memberships (workspace_id, user_id, editorial_role)
-- values ('YOUR_WORKSPACE_UUID', 'YOUR_APP_USER_UUID', 'sub_editor');
