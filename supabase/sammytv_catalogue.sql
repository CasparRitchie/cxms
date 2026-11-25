-- SammyTV Phase 2. Apply only to the CXMS/SammyTV Supabase project.
-- No changes to other applications, no sample users, no sample approvals.
begin;

create table public.sammytv_families (
  id uuid primary key default gen_random_uuid(),
  brand_name text not null default 'SammyTV' check (length(brand_name) between 1 and 60),
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);

-- Separate app identities: never sports workspace users, cookies or roles.
-- Phase 3 will link verified parent identities and provision viewer sessions.
create table public.sammytv_members (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  role text not null check (role in ('parent', 'viewer')),
  active boolean not null default true,
  session_version integer not null default 1 check (session_version > 0),
  created_at timestamptz not null default now(),
  unique (id, family_id)
);

create table public.sammytv_profiles (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  member_id uuid not null,
  nickname text not null check (length(nickname) between 1 and 40),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (id, family_id),
  foreign key (member_id, family_id) references public.sammytv_members(id, family_id) on delete cascade
);

create table public.sammytv_categories (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  name text not null check (length(name) between 1 and 60 and lower(name) not in ('all', 'favourites')),
  slug text not null check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  position integer not null default 0,
  enabled boolean not null default true,
  unique (id, family_id),
  unique (family_id, slug)
);
create unique index sammytv_category_name_idx on public.sammytv_categories(family_id, lower(name));

create table public.sammytv_channels (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  provider text not null default 'youtube' check (provider = 'youtube'),
  provider_channel_id text not null check (provider_channel_id ~ '^UC[A-Za-z0-9_-]{22}$'),
  name text not null check (length(name) between 1 and 200),
  enabled boolean not null default true,
  favourite_creator boolean not null default false,
  created_at timestamptz not null default now(),
  unique (id, family_id),
  unique (family_id, provider, provider_channel_id)
);

create table public.sammytv_videos (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  channel_id uuid not null,
  provider text not null default 'youtube' check (provider = 'youtube'),
  provider_video_id text not null check (provider_video_id ~ '^[A-Za-z0-9_-]{11}$'),
  title text not null check (length(title) between 1 and 300),
  description text not null default '' check (length(description) <= 10000),
  duration_seconds integer not null default 0 check (duration_seconds >= 0),
  is_live boolean not null default false,
  embeddable boolean not null default false,
  age_restricted boolean not null default true,
  available boolean not null default false,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected', 'hidden')),
  approved_by uuid,
  approved_at timestamptz,
  moderation_notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, family_id),
  unique (family_id, provider, provider_video_id),
  foreign key (channel_id, family_id) references public.sammytv_channels(id, family_id),
  foreign key (approved_by, family_id) references public.sammytv_members(id, family_id),
  check (status <> 'approved' or (approved_by is not null and approved_at is not null))
);

create table public.sammytv_video_categories (
  family_id uuid not null references public.sammytv_families(id) on delete cascade,
  video_id uuid not null,
  category_id uuid not null,
  primary key (family_id, video_id, category_id),
  foreign key (video_id, family_id) references public.sammytv_videos(id, family_id) on delete cascade,
  foreign key (category_id, family_id) references public.sammytv_categories(id, family_id) on delete cascade
);

create index sammytv_videos_catalogue_idx on public.sammytv_videos(family_id, approved_at desc, id)
  where status = 'approved' and available and embeddable and not age_restricted and not is_live;
create index sammytv_video_category_idx on public.sammytv_video_categories(family_id, category_id, video_id);
create index sammytv_profiles_member_idx on public.sammytv_profiles(family_id, member_id);
create index sammytv_channels_family_idx on public.sammytv_channels(family_id, enabled);

-- An approval must name an active parent from the SAME family.
-- Changing the underlying video/channel or its content flags invalidates approval.
create function public.sammytv_guard_approval() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  if TG_OP = 'UPDATE' then
    if (new.provider, new.provider_video_id, new.channel_id, new.family_id, new.is_live)
       is distinct from (old.provider, old.provider_video_id, old.channel_id, old.family_id, old.is_live) then
      new.status := 'pending';
      new.approved_by := null;
      new.approved_at := null;
    end if;
  end if;
  if new.status = 'approved' and not exists (
    select 1 from public.sammytv_members m
    where m.id = new.approved_by and m.family_id = new.family_id and m.role = 'parent' and m.active
  ) then
    raise exception 'SammyTV approval requires an active parent in the same family';
  end if;
  new.updated_at := now();
  return new;
end;
$$;
create trigger sammytv_video_approval before insert or update on public.sammytv_videos
  for each row execute function public.sammytv_guard_approval();

-- Fixed SQL with typed parameters; no raw SQL or PostgREST syntax from search input.
-- Provider IDs are returned only to the server, which projects viewer-safe fields.
create function public.sammytv_catalogue(
  p_family_id uuid, p_video_id uuid default null, p_channel_id uuid default null,
  p_category_id uuid default null, p_query text default '', p_limit integer default 48,
  p_offset integer default 0
) returns table (
  id uuid, family_id uuid, title text, description text, duration_seconds integer,
  is_live boolean, provider text, provider_video_id text, status text,
  approved_at timestamptz, approved_by uuid, available boolean, embeddable boolean,
  age_restricted boolean, channel jsonb, categories jsonb
) language sql stable security invoker set search_path = pg_catalog, public as $$
  select v.id, v.family_id, v.title, v.description, v.duration_seconds, v.is_live,
    v.provider, v.provider_video_id, v.status, v.approved_at, v.approved_by,
    v.available, v.embeddable, v.age_restricted,
    jsonb_build_object('id', c.id, 'name', c.name, 'family_id', c.family_id, 'enabled', c.enabled),
    coalesce((select jsonb_agg(jsonb_build_object('id', cat.id, 'name', cat.name) order by cat.position, cat.name)
      from public.sammytv_video_categories vc
      join public.sammytv_categories cat on cat.id = vc.category_id and cat.family_id = vc.family_id
      where vc.video_id = v.id and vc.family_id = p_family_id and cat.enabled), '[]'::jsonb)
  from public.sammytv_videos v
  join public.sammytv_channels c on c.id = v.channel_id and c.family_id = v.family_id
  join public.sammytv_families f on f.id = v.family_id
  where v.family_id = p_family_id and f.enabled and c.enabled
    and v.status = 'approved' and v.approved_at is not null and v.approved_by is not null
    and v.available and v.embeddable and not v.age_restricted and not v.is_live
    and exists (select 1 from public.sammytv_members m where m.id = v.approved_by
      and m.family_id = p_family_id and m.role = 'parent' and m.active)
    and (p_video_id is null or v.id = p_video_id)
    and (p_channel_id is null or v.channel_id = p_channel_id)
    and (p_category_id is null or exists (
      select 1 from public.sammytv_video_categories vc
      join public.sammytv_categories cat on cat.id = vc.category_id and cat.family_id = vc.family_id
      where vc.video_id = v.id and vc.family_id = p_family_id and vc.category_id = p_category_id and cat.enabled))
    and (coalesce(trim(p_query), '') = '' or strpos(lower(v.title || ' ' || v.description || ' ' || c.name), lower(left(trim(p_query),120))) > 0)
  order by v.approved_at desc, v.id
  limit greatest(1, least(coalesce(p_limit,48),49)) offset greatest(0, least(coalesce(p_offset,0),10000));
$$;

create function public.sammytv_channels(p_family_id uuid)
returns table (id uuid, name text)
language sql stable security invoker set search_path = pg_catalog, public as $$
  select c.id, c.name from public.sammytv_channels c
  join public.sammytv_families f on f.id = c.family_id
  where c.family_id = p_family_id and c.enabled and f.enabled and exists (
    select 1 from public.sammytv_videos v
    join public.sammytv_members m on m.id = v.approved_by and m.family_id = v.family_id
    where v.channel_id = c.id and v.family_id = p_family_id and v.status = 'approved'
      and v.approved_at is not null and v.available and v.embeddable
      and not v.age_restricted and not v.is_live and m.role = 'parent' and m.active
  ) order by c.name, c.id;
$$;

-- Browser roles have NO table access, even if signed into another CXMS application.
-- RLS is deny-all: Flask uses the existing server-only service role and MUST scope
-- every call to a verified family/profile. Never send this key to the client.
do $$
declare t text;
begin
  foreach t in array array['sammytv_families','sammytv_members','sammytv_profiles',
    'sammytv_categories','sammytv_channels','sammytv_videos','sammytv_video_categories'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on table public.%I from public, anon, authenticated', t);
    execute format('grant select, insert, update, delete on table public.%I to service_role', t);
  end loop;
end;
$$;
revoke all on function public.sammytv_guard_approval() from public, anon, authenticated;
revoke all on function public.sammytv_catalogue(uuid, uuid, uuid, uuid, text, integer, integer) from public, anon, authenticated;
revoke all on function public.sammytv_channels(uuid) from public, anon, authenticated;
grant execute on function public.sammytv_catalogue(uuid, uuid, uuid, uuid, text, integer, integer) to service_role;
grant execute on function public.sammytv_channels(uuid) to service_role;
commit;
