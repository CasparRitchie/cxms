-- Supervisor stat-sheet administration and the internal FIS review handoff.
-- Apply after sports_editorial_fis_specialist_workflow.sql. Additive and safe to rerun.

alter table public.sports_editorial_submissions
  add column if not exists is_active boolean not null default true,
  add column if not exists race_status text not null default 'scheduled',
  add column if not exists race_status_source text not null default 'manual',
  add column if not exists fis_race_status text,
  add column if not exists fis_race_status_checked_at timestamptz;

alter table public.sports_editorial_submissions
  drop constraint if exists sports_editorial_submissions_race_status_check;
alter table public.sports_editorial_submissions
  add constraint sports_editorial_submissions_race_status_check
  check (race_status in ('scheduled','cancelled'));

alter table public.sports_editorial_submissions
  drop constraint if exists sports_editorial_submissions_status_check;
alter table public.sports_editorial_submissions
  add constraint sports_editorial_submissions_status_check
  check (status in ('draft','submitted','in_review','changes_requested','approved','fis_review','exported'));

create index if not exists sports_editorial_submissions_active_status_idx
  on public.sports_editorial_submissions (workspace_id, is_active, status, updated_at desc);

create or replace function public.sports_editorial_administer_submission(
  p_workspace_id uuid,
  p_submission_id uuid,
  p_status text default null,
  p_is_active boolean default null,
  p_race_status text default null,
  p_race_status_source text default null,
  p_invalidate_lock boolean default false
)
returns setof public.sports_editorial_submissions
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  update public.sports_editorial_submissions as s
     set status = coalesce(p_status, s.status),
         is_active = coalesce(p_is_active, s.is_active),
         race_status = coalesce(p_race_status, s.race_status),
         race_status_source = coalesce(p_race_status_source, s.race_status_source),
         lock_user_id = case when p_invalidate_lock then null else s.lock_user_id end,
         lock_user_name = case when p_invalidate_lock then null else s.lock_user_name end,
         lock_token = case when p_invalidate_lock then null else s.lock_token end,
         lock_acquired_at = case when p_invalidate_lock then null else s.lock_acquired_at end,
         lock_last_active_at = case when p_invalidate_lock then null else s.lock_last_active_at end,
         lock_version = case when p_invalidate_lock then coalesce(s.lock_version, 0) + 1 else s.lock_version end,
         updated_at = now()
   where s.workspace_id = p_workspace_id and s.id = p_submission_id
   returning s.*;
end;
$$;

revoke all on function public.sports_editorial_administer_submission(uuid,uuid,text,boolean,text,text,boolean)
from public, anon, authenticated;
grant execute on function public.sports_editorial_administer_submission(uuid,uuid,text,boolean,text,text,boolean)
to service_role;

alter table public.sports_editorial_audit_events
  drop constraint if exists sports_editorial_audit_events_action_check;
alter table public.sports_editorial_audit_events
  add constraint sports_editorial_audit_events_action_check check (action in (
    'force_unlock','published','withdrawn','returned_to_in_progress',
    'stat_sheet_administered','stat_sheet_inactivated','stat_sheet_reactivated',
    'race_cancelled','race_reinstated','status_overridden',
    'fis_specialist_assigned','sent_to_fis_review','fis_review_withdrawn'
  ));
