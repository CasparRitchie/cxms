-- Additive, repeatable edit checkout support for Sports Editorial.
alter table public.sports_editorial_submissions
  add column if not exists lock_user_id uuid references public.app_users(id) on delete set null,
  add column if not exists lock_user_name text,
  add column if not exists lock_token uuid,
  add column if not exists lock_acquired_at timestamptz,
  add column if not exists lock_last_active_at timestamptz,
  add column if not exists lock_version bigint not null default 0;

create or replace function public.sports_editorial_acquire_edit_lock(
  p_workspace_id uuid, p_submission_id uuid, p_user_id uuid,
  p_user_name text, p_timeout_seconds integer
) returns setof public.sports_editorial_submissions
language plpgsql security definer set search_path = public as $$
begin
  return query
  update public.sports_editorial_submissions s
     set lock_user_id = p_user_id,
         lock_user_name = nullif(trim(p_user_name), ''),
         lock_token = case when s.lock_user_id = p_user_id
                           then s.lock_token else gen_random_uuid() end,
         lock_acquired_at = case when s.lock_user_id = p_user_id
                                  then s.lock_acquired_at else now() end,
         lock_last_active_at = now(),
         lock_version = case when s.lock_user_id = p_user_id
                              then s.lock_version else s.lock_version + 1 end,
         status = case when s.status = 'submitted' then 'in_review' else s.status end,
         updated_at = case when s.status = 'submitted' then now() else s.updated_at end,
         last_modified_by_user_id = case when s.status = 'submitted' then p_user_id else s.last_modified_by_user_id end,
         last_modified_by_name = case when s.status = 'submitted' then nullif(trim(p_user_name), '') else s.last_modified_by_name end
   where s.id = p_submission_id
     and s.workspace_id = p_workspace_id
     and (s.lock_user_id is null
          or s.lock_user_id = p_user_id)
  returning s.*;
end $$;

create or replace function public.sports_editorial_heartbeat_edit_lock(
  p_workspace_id uuid, p_submission_id uuid, p_user_id uuid,
  p_lock_token uuid, p_timeout_seconds integer
) returns setof public.sports_editorial_submissions
language sql security definer set search_path = public as $$
  update public.sports_editorial_submissions
     set lock_last_active_at = now()
   where id = p_submission_id and workspace_id = p_workspace_id
     and lock_user_id = p_user_id and lock_token = p_lock_token
  returning *;
$$;

create or replace function public.sports_editorial_force_unlock(
  p_workspace_id uuid, p_submission_id uuid
) returns setof public.sports_editorial_submissions
language sql security definer set search_path = public as $$
  update public.sports_editorial_submissions
     set lock_user_id = null, lock_user_name = null, lock_token = null,
         lock_acquired_at = null, lock_last_active_at = null,
         lock_version = lock_version + 1
   where id = p_submission_id and workspace_id = p_workspace_id
  returning *;
$$;

revoke all on function public.sports_editorial_acquire_edit_lock(uuid,uuid,uuid,text,integer) from public, anon, authenticated;
revoke all on function public.sports_editorial_heartbeat_edit_lock(uuid,uuid,uuid,uuid,integer) from public, anon, authenticated;
revoke all on function public.sports_editorial_force_unlock(uuid,uuid) from public, anon, authenticated;
grant execute on function public.sports_editorial_acquire_edit_lock(uuid,uuid,uuid,text,integer) to service_role;
grant execute on function public.sports_editorial_heartbeat_edit_lock(uuid,uuid,uuid,uuid,integer) to service_role;
grant execute on function public.sports_editorial_force_unlock(uuid,uuid) to service_role;
