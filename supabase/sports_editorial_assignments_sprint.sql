-- Additive migration for assigned stat-sheet workflow. Safe to run more than once.
alter table public.sports_editorial_submissions
  add column if not exists amp_id text,
  add column if not exists client_name text not null default 'FIS',
  add column if not exists researcher_user_id uuid,
  add column if not exists sub_editor_user_id uuid,
  add column if not exists publication_deadline date,
  add column if not exists researcher_deadline date,
  add column if not exists working_notes text,
  add column if not exists unused_stats text,
  add column if not exists last_modified_by_user_id uuid,
  add column if not exists last_modified_by_name text;

update public.sports_editorial_submissions
set researcher_user_id = author_user_id
where researcher_user_id is null and author_user_id is not null;

alter table public.sports_editorial_memberships
  drop constraint if exists sports_editorial_memberships_editorial_role_check;
update public.sports_editorial_memberships
set editorial_role = 'researcher'
where editorial_role = 'journalist';
alter table public.sports_editorial_memberships
  add constraint sports_editorial_memberships_editorial_role_check
  check (editorial_role in ('researcher', 'sub_editor', 'supervisor', 'fis_specialist'));

update public.sports_editorial_stats set content_type = 'section' where content_type = 'heading';
alter table public.sports_editorial_stats
  drop constraint if exists sports_editorial_stats_content_type_check;
alter table public.sports_editorial_stats
  add constraint sports_editorial_stats_content_type_check
  check (content_type in ('stat', 'section'));

create index if not exists sports_editorial_submissions_researcher_idx
  on public.sports_editorial_submissions(workspace_id, researcher_user_id, status, updated_at desc);
create index if not exists sports_editorial_submissions_sub_editor_idx
  on public.sports_editorial_submissions(workspace_id, sub_editor_user_id, status, updated_at desc);

create or replace function public.sports_editorial_provision_user(
  p_workspace_id uuid,
  p_email text,
  p_full_name text,
  p_password_hash text,
  p_editorial_role text
)
returns table (
  user_id uuid,
  existing_account boolean
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid;
  v_existing boolean := false;
begin
  if p_editorial_role not in (
    'researcher',
    'sub_editor',
    'supervisor',
    'fis_specialist'
  ) then
    raise exception 'Invalid Sports Editorial role';
  end if;

  select au.id
  into v_user_id
  from public.app_users as au
  where lower(au.email) = lower(trim(p_email))
  limit 1;

  if v_user_id is null then
    insert into public.app_users (
      email,
      password_hash,
      full_name,
      is_active
    )
    values (
      lower(trim(p_email)),
      p_password_hash,
      nullif(trim(p_full_name), ''),
      true
    )
    returning id into v_user_id;
  else
    v_existing := true;
  end if;

  if not exists (
    select 1
    from public.workspace_members as wm
    where wm.workspace_id = p_workspace_id
      and wm.user_id = v_user_id
  ) then
    insert into public.workspace_members (
      workspace_id,
      user_id,
      email,
      role
    )
    values (
      p_workspace_id,
      v_user_id,
      lower(trim(p_email)),
      'member'
    );
  end if;

  insert into public.sports_editorial_memberships (
    workspace_id,
    user_id,
    editorial_role,
    is_active
  )
  values (
    p_workspace_id,
    v_user_id,
    p_editorial_role,
    true
  )
  on conflict on constraint
    sports_editorial_memberships_workspace_id_user_id_key
  do update
  set
    editorial_role = excluded.editorial_role,
    is_active = true;

  return query
  select
    v_user_id,
    v_existing;
end;
$$;

revoke all
on function public.sports_editorial_provision_user(
  uuid,
  text,
  text,
  text,
  text
)
from public, anon, authenticated;

grant execute
on function public.sports_editorial_provision_user(
  uuid,
  text,
  text,
  text,
  text
)
to service_role;
