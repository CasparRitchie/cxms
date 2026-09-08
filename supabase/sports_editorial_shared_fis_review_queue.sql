-- Replace individual FIS Specialist allocation with a shared workspace queue.
-- Apply after the previously deployed sports_editorial_stat_sheet_administration.sql.

drop function if exists public.sports_editorial_administer_submission(
  uuid, uuid, text, boolean, text, text, boolean, uuid, boolean
);

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

-- Assignment is no longer part of the workflow. Existing values are deliberately
-- discarded: every active FIS Specialist in the workspace now shares the queue.
alter table public.sports_editorial_submissions
  drop column if exists fis_specialist_user_id;
