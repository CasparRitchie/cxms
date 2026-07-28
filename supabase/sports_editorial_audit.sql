-- Additive audit trail for workflow, publication and lock interventions.
create table if not exists public.sports_editorial_audit_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  submission_id uuid not null references public.sports_editorial_submissions(id) on delete cascade,
  actor_user_id uuid references public.app_users(id) on delete set null,
  actor_name text,
  action text not null check (action in (
    'force_unlock', 'published', 'withdrawn', 'returned_to_in_progress'
  )),
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists sports_editorial_audit_submission_idx
  on public.sports_editorial_audit_events (workspace_id, submission_id, created_at desc);

alter table public.sports_editorial_audit_events enable row level security;
revoke all on public.sports_editorial_audit_events from anon, authenticated;
grant all on public.sports_editorial_audit_events to service_role;
