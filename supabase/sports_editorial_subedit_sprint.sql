-- Additive, repeatable migration for the accepted/locked sub-edit workflow.
alter table public.sports_editorial_stats
  add column if not exists accepted_at timestamptz;

alter table public.sports_editorial_stats
  add column if not exists accepted_by_user_id uuid references public.app_users(id) on delete set null;
