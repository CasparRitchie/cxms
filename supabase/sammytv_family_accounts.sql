-- Phase 5. Shared NPS Me project, after identity, moderation and live-camera migrations.
-- Apply once before deploying. Existing users, family IDs and approvals are preserved.
begin;

create table public.sammytv_child_logins (
  member_id uuid primary key,
  family_id uuid not null,
  username text not null unique check(username ~ '^[a-z0-9][a-z0-9_.-]{2,31}$'),
  password_hash text not null check(password_hash ~ '^scrypt:32768:8:1\$' and length(password_hash) between 150 and 256),
  account_status text not null check(account_status in ('pending','active','disabled','declined')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default clock_timestamp(),
  foreign key(member_id,family_id) references public.sammytv_members(id,family_id) on delete cascade
);
create index sammytv_child_family on public.sammytv_child_logins(family_id,account_status,created_at);

create table public.sammytv_registration_codes (
  digest text primary key check(digest ~ '^[a-f0-9]{64}$'),
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  parent_id uuid not null,
  expires_at timestamptz not null default now()+interval '7 days',
  foreign key(parent_id,family_id) references public.sammytv_members(id,family_id) on delete cascade
);
create table public.sammytv_parent_invites (
  digest text primary key check(digest ~ '^[a-f0-9]{64}$'),
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  parent_id uuid not null,
  email text not null check(email=lower(trim(email)) and length(email) between 3 and 254),
  expires_at timestamptz not null default now()+interval '48 hours',
  foreign key(parent_id,family_id) references public.sammytv_members(id,family_id) on delete cascade
);
create table public.sammytv_auth_limits (
  bucket text primary key check(bucket ~ '^[a-f0-9]{64}$'),
  started_at timestamptz not null default clock_timestamp(),
  attempts integer not null check(attempts > 0)
);
create index sammytv_auth_limits_expiry on public.sammytv_auth_limits(started_at);

-- Cross-worker throttling. Buckets contain keyed digests, never raw IPs/logins.
create function public.sammytv_auth_limit(p_bucket text,p_limit integer,p_seconds integer)
returns table(allowed boolean) language plpgsql security invoker set search_path=pg_catalog as $$
declare n integer; moment timestamptz := clock_timestamp();
begin
  if p_limit not between 1 and 100 or p_seconds not between 60 and 86400 then
    raise exception using errcode='22023',message='Invalid limit';
  end if;
  delete from public.sammytv_auth_limits a where a.started_at < moment-interval '2 days';
  insert into public.sammytv_auth_limits as a(bucket,attempts,started_at) values(p_bucket,1,moment)
    on conflict(bucket) do update set
      attempts=case when a.started_at <= moment-make_interval(secs=>p_seconds) then 1 else least(a.attempts+1,101) end,
      started_at=case when a.started_at <= moment-make_interval(secs=>p_seconds) then moment else a.started_at end
    returning attempts into n;
  return query select n<=p_limit;
end;
$$;

create function public.sammytv_family_children(p_family uuid,p_parent uuid,p_session_version integer)
returns table(child_id uuid,username text,nickname text,account_status text,updated_at timestamptz)
language plpgsql security invoker set search_path=pg_catalog as $$
begin
  perform public.sammytv_require_parent(p_family,p_parent,p_session_version);
  return query select c.member_id,c.username,p.nickname,c.account_status,c.updated_at
    from public.sammytv_child_logins c join public.sammytv_profiles p on p.member_id=c.member_id and p.family_id=c.family_id
    where c.family_id=p_family order by c.created_at,c.member_id;
end;
$$;

create function public.sammytv_manage_child(
  p_family uuid,p_parent uuid,p_session_version integer,p_action text,
  p_child uuid default null,p_expected_updated_at timestamptz default null,
  p_username text default '',p_nickname text default '',p_password_hash text default ''
) returns table(child_id uuid) language plpgsql security invoker set search_path=pg_catalog as $$
declare target uuid; c public.sammytv_child_logins; outcome text;
begin
  perform pg_advisory_xact_lock(hashtextextended('sammytv:children:' || p_family::text,0));
  perform public.sammytv_require_parent(p_family,p_parent,p_session_version);
  if p_action is null or p_action not in ('create','approve','decline','disable','enable','reset_password') then
    raise exception using errcode='22023',message='Invalid child action';
  end if;
  if p_action in ('create','reset_password') and
    (p_password_hash is null or p_password_hash !~ '^scrypt:32768:8:1\$' or length(p_password_hash) not between 150 and 256) then
    raise exception using errcode='22023',message='Invalid password hash';
  end if;
  if p_action='create' then
    if p_username is null or p_username !~ '^[a-z0-9][a-z0-9_.-]{2,31}$'
       or p_nickname is null or length(trim(p_nickname)) not between 1 and 40
       or p_nickname ~ '[[:cntrl:]]'
       or (select count(*) from public.sammytv_child_logins where family_id=p_family)>=50 then
      raise exception using errcode='22023',message='Invalid child account';
    end if;
    insert into public.sammytv_members(family_id,role) values(p_family,'viewer') returning id into target;
    insert into public.sammytv_profiles(family_id,member_id,nickname) values(p_family,target,trim(p_nickname));
    insert into public.sammytv_child_logins(member_id,family_id,username,password_hash,account_status)
      values(target,p_family,p_username,p_password_hash,'active');
  else
    select l.* into c from public.sammytv_child_logins l where l.member_id=p_child and l.family_id=p_family for update;
    if not found then raise exception using errcode='42501',message='Child unavailable'; end if;
    if c.updated_at is distinct from p_expected_updated_at then
      raise exception using errcode='40001',message='Account changed; reload';
    end if;
    target := c.member_id;
    outcome := c.account_status;
    if p_action in ('approve','decline') then
      if c.account_status <> 'pending' then raise exception using errcode='40001',message='Request already reviewed'; end if;
      outcome := case when p_action='approve' then 'active' else 'declined' end;
    elsif p_action='disable' and c.account_status='active' then outcome := 'disabled';
    elsif p_action='enable' and c.account_status='disabled' then outcome := 'active';
    elsif p_action <> 'reset_password' or c.account_status not in ('active','disabled') then
      raise exception using errcode='22023',message='Invalid account transition';
    end if;
    -- Revokes existing sessions on every management action, including password resets.
    update public.sammytv_members m set active=(outcome='active'),session_version=m.session_version+1
      where m.id=target and m.family_id=p_family and m.role='viewer';
    update public.sammytv_profiles p set enabled=(outcome='active') where p.member_id=target and p.family_id=p_family;
    update public.sammytv_child_logins l set account_status=outcome,
      password_hash=case when p_action='reset_password' then p_password_hash else l.password_hash end,
      updated_at=clock_timestamp() where l.member_id=target and l.family_id=p_family;
  end if;
  return query select target;
end;
$$;

create function public.sammytv_create_registration_code(p_family uuid,p_parent uuid,p_session_version integer,p_digest text)
returns table(created boolean) language plpgsql security invoker set search_path=pg_catalog as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('sammytv:registration:' || p_family::text,0));
  perform public.sammytv_require_parent(p_family,p_parent,p_session_version);
  delete from public.sammytv_registration_codes where family_id=p_family;
  insert into public.sammytv_registration_codes(digest,family_id,parent_id) values(p_digest,p_family,p_parent);
  return query select true;
end;
$$;

-- Called only after server-side validation, hashing and persistent throttling.
-- A code authorises a pending request, never approval or catalogue access.
create function public.sammytv_request_child(p_digest text,p_username text,p_nickname text,p_password_hash text)
returns table(requested boolean) language plpgsql security invoker set search_path=pg_catalog as $$
declare code public.sammytv_registration_codes; target uuid;
begin
  select r.* into code from public.sammytv_registration_codes r
    join public.sammytv_members m on m.id=r.parent_id and m.family_id=r.family_id
    join public.sammytv_families f on f.id=r.family_id
    where r.digest=p_digest and r.expires_at>now() and m.active and m.role='parent' and f.enabled for share of r,m,f;
  if not found then return query select false; return; end if;
  -- Serialise capacity checks with parent-created accounts. Rotation uses its
  -- own lock and never waits for this one, avoiding a lock-order cycle.
  perform pg_advisory_xact_lock(hashtextextended('sammytv:children:' || code.family_id::text,0));
  if p_username is null or p_username !~ '^[a-z0-9][a-z0-9_.-]{2,31}$'
     or p_nickname is null or length(trim(p_nickname)) not between 1 and 40 or p_nickname ~ '[[:cntrl:]]'
     or p_password_hash is null or p_password_hash !~ '^scrypt:32768:8:1\$' or length(p_password_hash) not between 150 and 256
     or (select count(*) from public.sammytv_child_logins where family_id=code.family_id)>=50
     or (select count(*) from public.sammytv_child_logins where family_id=code.family_id and account_status='pending')>=20 then
    raise exception using errcode='22023',message='Request unavailable';
  end if;
  insert into public.sammytv_members(family_id,role,active) values(code.family_id,'viewer',false) returning id into target;
  insert into public.sammytv_profiles(family_id,member_id,nickname,enabled) values(code.family_id,target,trim(p_nickname),false);
  insert into public.sammytv_child_logins(member_id,family_id,username,password_hash,account_status)
    values(target,code.family_id,p_username,p_password_hash,'pending');
  return query select true;
end;
$$;

-- Credentials are read by the server only, never projected into a page/API.
create function public.sammytv_child_credentials(p_username text)
returns table(child_id uuid,password_hash text) language sql stable security invoker set search_path=pg_catalog as $$
  select c.member_id,c.password_hash from public.sammytv_child_logins c
    join public.sammytv_members m on m.id=c.member_id and m.family_id=c.family_id
    join public.sammytv_families f on f.id=c.family_id
    where c.username=p_username and c.account_status='active' and m.active and m.role='viewer' and f.enabled;
$$;
create function public.sammytv_child_session(p_child uuid,p_expected_hash text)
returns table(member_id uuid,family_id uuid,profile_id uuid,session_version integer)
language plpgsql security invoker set search_path=pg_catalog as $$
begin
  -- Snapshot comparison closes the password-reset/disable race during scrypt.
  return query select m.id,m.family_id,p.id,m.session_version from public.sammytv_child_logins c
    join public.sammytv_members m on m.id=c.member_id and m.family_id=c.family_id
    join public.sammytv_profiles p on p.member_id=m.id and p.family_id=m.family_id
    join public.sammytv_families f on f.id=m.family_id
    where c.member_id=p_child and c.password_hash=p_expected_hash and c.account_status='active'
      and m.active and m.role='viewer' and p.enabled and f.enabled for share of c,m,p,f;
end;
$$;

create function public.sammytv_create_parent_invite(p_family uuid,p_parent uuid,p_session_version integer,p_digest text,p_email text)
returns table(created boolean) language plpgsql security invoker set search_path=pg_catalog as $$
begin
  perform public.sammytv_require_parent(p_family,p_parent,p_session_version);
  if p_email is null or length(p_email) not between 3 and 254 or p_email <> lower(trim(p_email)) or position('@' in p_email)<2 then
    raise exception using errcode='22023',message='Invalid email';
  end if;
  delete from public.sammytv_parent_invites where expires_at<=now() or (family_id=p_family and email=p_email);
  if (select count(*) from public.sammytv_parent_invites where family_id=p_family)>=20 then
    raise exception using errcode='22023',message='Too many invitations';
  end if;
  insert into public.sammytv_parent_invites(digest,family_id,parent_id,email) values(p_digest,p_family,p_parent,p_email);
  return query select true;
end;
$$;

-- Only this function needs auth.users access, mirroring existing parent provision.
-- A verified Supabase login is required before the server calls it.
create function public.sammytv_accept_parent_invite(p_identity uuid,p_digest text)
returns table(member_id uuid,family_id uuid,profile_id uuid,session_version integer)
language plpgsql security definer set search_path=pg_catalog as $$
declare invite public.sammytv_parent_invites; email_address text; target uuid; existing_family uuid;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_identity::text,0));
  select lower(u.email) into email_address from auth.users u where u.id=p_identity and u.email_confirmed_at is not null;
  if email_address is null then raise exception using errcode='42501',message='Verified parent required'; end if;
  select i.* into invite from public.sammytv_parent_invites i
    join public.sammytv_members m on m.id=i.parent_id and m.family_id=i.family_id
    join public.sammytv_families f on f.id=i.family_id
    where i.digest=p_digest and i.email=email_address and i.expires_at>now() and m.active and m.role='parent' and f.enabled
    for update of i for share of m,f;
  if not found then raise exception using errcode='42501',message='Invitation unavailable'; end if;
  select i.member_id,i.family_id into target,existing_family from public.sammytv_parent_identities i where i.identity_id=p_identity;
  if target is not null then
    if existing_family<>invite.family_id then
      raise exception using errcode='22023',message='Parent already belongs to another family';
    end if;
  else
    insert into public.sammytv_members(family_id,role) values(invite.family_id,'parent') returning id into target;
    insert into public.sammytv_parent_identities(identity_id,member_id,family_id) values(p_identity,target,invite.family_id);
    insert into public.sammytv_profiles(family_id,member_id,nickname) values(invite.family_id,target,'Parent');
  end if;
  delete from public.sammytv_parent_invites where digest=p_digest;
  return query select m.id,m.family_id,p.id,m.session_version from public.sammytv_members m
    join public.sammytv_profiles p on p.member_id=m.id and p.family_id=m.family_id
    where m.id=target and m.active and m.role='parent' and p.enabled order by p.created_at limit 1;
end;
$$;
alter function public.sammytv_accept_parent_invite(uuid,text) owner to postgres;

-- Existing invited parents can sign in without broadening the bootstrap allowlist.
create function public.sammytv_existing_parent(p_identity uuid)
returns table(member_id uuid,family_id uuid,profile_id uuid,session_version integer)
language sql stable security invoker set search_path=pg_catalog as $$
  select m.id,m.family_id,p.id,m.session_version from public.sammytv_parent_identities i
    join public.sammytv_members m on m.id=i.member_id and m.family_id=i.family_id
    join public.sammytv_profiles p on p.member_id=m.id and p.family_id=m.family_id
    join public.sammytv_families f on f.id=m.family_id
    where i.identity_id=p_identity and m.active and m.role='parent' and p.enabled and f.enabled
    order by p.created_at limit 1;
$$;

create function public.sammytv_family_parents(p_family uuid,p_parent uuid,p_session_version integer)
returns table(parent_id uuid,nickname text) language plpgsql security invoker set search_path=pg_catalog as $$
begin
  perform public.sammytv_require_parent(p_family,p_parent,p_session_version);
  return query select m.id,p.nickname from public.sammytv_members m
    join public.sammytv_profiles p on p.member_id=m.id and p.family_id=m.family_id
    where m.family_id=p_family and m.active and m.role='parent' and p.enabled order by m.created_at;
end;
$$;

do $$ declare tab text; sig regprocedure; begin
  foreach tab in array array['sammytv_child_logins','sammytv_registration_codes','sammytv_parent_invites','sammytv_auth_limits'] loop
    execute format('alter table public.%I enable row level security',tab);
    execute format('alter table public.%I force row level security',tab);
    execute format('revoke all on public.%I from public,anon,authenticated',tab);
    execute format('grant select,insert,update,delete on public.%I to service_role',tab);
  end loop;
  -- Exact names: do not change grants on other applications or prior functions.
  for sig in select p.oid::regprocedure from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname=any(array[
      'sammytv_auth_limit','sammytv_family_children','sammytv_manage_child','sammytv_create_registration_code',
      'sammytv_request_child','sammytv_child_credentials','sammytv_child_session','sammytv_create_parent_invite',
      'sammytv_accept_parent_invite','sammytv_existing_parent','sammytv_family_parents']) loop
    execute format('revoke all on function %s from public,anon,authenticated',sig);
    execute format('grant execute on function %s to service_role',sig);
  end loop;
end $$;
notify pgrst,'reload schema';
commit;
