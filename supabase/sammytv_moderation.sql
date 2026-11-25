-- Phase 4a. Apply once to the shared NPS Me project after Phase 3.
-- Adds only server-only SammyTV functions. No table grants, users or seed videos.
begin;

create function public.sammytv_require_parent(p_family uuid, p_parent uuid, p_session_version integer)
returns void language plpgsql security invoker set search_path = pg_catalog as $$
begin
  perform 1 from public.sammytv_members m
  join public.sammytv_families f on f.id = m.family_id
  where m.id = p_parent and m.family_id = p_family and m.role = 'parent'
    and m.active and f.enabled and m.session_version = p_session_version
  for share of m, f;
  if not found then
    raise exception using errcode = '42501', message = 'Active parent required';
  end if;
end;
$$;

create function public.sammytv_validate_metadata(p_metadata jsonb)
returns void language plpgsql security invoker set search_path = pg_catalog as $$
declare k text;
begin
  if jsonb_typeof(p_metadata) is distinct from 'object' then
    raise exception using errcode = '22023', message = 'Invalid metadata';
  end if;
  foreach k in array array['provider_video_id','provider_channel_id','title','description','channel_name'] loop
    if jsonb_typeof(p_metadata->k) is distinct from 'string' then
      raise exception using errcode = '22023', message = 'Invalid metadata';
    end if;
  end loop;
  foreach k in array array['available','embeddable','age_restricted','is_live'] loop
    if jsonb_typeof(p_metadata->k) is distinct from 'boolean' then
      raise exception using errcode = '22023', message = 'Invalid metadata';
    end if;
  end loop;
  if (p_metadata->>'provider_video_id') !~ '^[A-Za-z0-9_-]{11}$'
     or (p_metadata->>'provider_channel_id') !~ '^UC[A-Za-z0-9_-]{22}$'
     or length(trim(p_metadata->>'title')) not between 1 and 300
     or length(p_metadata->>'description') > 10000
     or length(trim(p_metadata->>'channel_name')) not between 1 and 200
     or jsonb_typeof(p_metadata->'duration_seconds') is distinct from 'number'
     or (p_metadata->>'duration_seconds') !~ '^[0-9]{1,10}$' then
    raise exception using errcode = '22023', message = 'Invalid metadata';
  end if;
  if (p_metadata->>'duration_seconds')::numeric > 2147483647 then
    raise exception using errcode = '22023', message = 'Invalid duration';
  end if;
end;
$$;

create function public.sammytv_import_video(
  p_family uuid, p_parent uuid, p_session_version integer, p_metadata jsonb
) returns table(video_id uuid, added boolean)
language plpgsql security invoker set search_path = pg_catalog as $$
declare c uuid; v uuid;
begin
  perform public.sammytv_require_parent(p_family, p_parent, p_session_version);
  perform public.sammytv_validate_metadata(p_metadata);
  -- Importing another video never enables a disabled channel or approves uploads.
  insert into public.sammytv_channels(family_id, provider_channel_id, name)
    values(p_family, p_metadata->>'provider_channel_id', p_metadata->>'channel_name')
    on conflict (family_id, provider, provider_channel_id) do nothing;
  select ch.id into c from public.sammytv_channels ch
    where ch.family_id = p_family and ch.provider = 'youtube'
      and ch.provider_channel_id = p_metadata->>'provider_channel_id';
  insert into public.sammytv_videos as imported(family_id, channel_id, provider_video_id,
    title, description, duration_seconds, available, embeddable, age_restricted, is_live)
    values(p_family, c, p_metadata->>'provider_video_id', p_metadata->>'title',
      p_metadata->>'description', (p_metadata->>'duration_seconds')::integer,
      (p_metadata->>'available')::boolean, (p_metadata->>'embeddable')::boolean,
      (p_metadata->>'age_restricted')::boolean, (p_metadata->>'is_live')::boolean)
    on conflict (family_id, provider, provider_video_id) do nothing
    returning imported.id into v;
  if v is not null then
    return query select v, true;
  else
    -- Repeated imports preserve the existing status, notes and categories.
    return query select existing.id, false from public.sammytv_videos existing
      where existing.family_id = p_family and existing.provider = 'youtube'
        and existing.provider_video_id = p_metadata->>'provider_video_id';
  end if;
end;
$$;

create function public.sammytv_moderate_video(
  p_family uuid, p_parent uuid, p_session_version integer, p_video uuid,
  p_expected_updated_at timestamptz, p_action text, p_metadata jsonb,
  p_categories uuid[], p_notes text
) returns table(video_id uuid, status text)
language plpgsql security invoker set search_path = pg_catalog as $$
declare v public.sammytv_videos; ch public.sammytv_channels; outcome text;
begin
  perform public.sammytv_require_parent(p_family, p_parent, p_session_version);
  if p_action is null or p_action not in ('approve','hide','refresh')
     or length(coalesce(p_notes,'')) > 10000 then
    raise exception using errcode = '22023', message = 'Invalid moderation action';
  end if;
  select vid.* into v from public.sammytv_videos vid
    where vid.id = p_video and vid.family_id = p_family for update;
  if not found then
    raise exception using errcode = '42501', message = 'Video unavailable';
  end if;
  if v.updated_at is distinct from p_expected_updated_at then
    raise exception using errcode = '40001', message = 'Video changed; review again';
  end if;
  if p_action = 'hide' then
    update public.sammytv_videos set status = 'hidden', approved_by = null, approved_at = null
      where id = p_video and family_id = p_family;
    return query select p_video, 'hidden'::text;
    return;
  end if;
  perform public.sammytv_validate_metadata(p_metadata);
  select c.* into ch from public.sammytv_channels c
    where c.id = v.channel_id and c.family_id = p_family for share;
  if v.provider_video_id is distinct from p_metadata->>'provider_video_id'
     or ch.provider_channel_id is distinct from p_metadata->>'provider_channel_id' then
    raise exception using errcode = '22023', message = 'Video identity changed';
  end if;
  -- Refresh always removes approval, including when a provider flag changes.
  if p_action = 'refresh' then
    outcome := 'pending';
  else
    if not ch.enabled or not (p_metadata->>'available')::boolean
       or not (p_metadata->>'embeddable')::boolean
       or (p_metadata->>'age_restricted')::boolean or (p_metadata->>'is_live')::boolean
       or coalesce(cardinality(p_categories),0) not between 1 and 50 then
      raise exception using errcode = '22023', message = 'Video cannot be approved';
    end if;
    -- Lock categories so disabling one cannot race this approval.
    perform 1 from public.sammytv_categories cat
      where cat.family_id = p_family and cat.enabled and cat.id = any(p_categories) for share;
    if exists(select 1 from unnest(p_categories) wanted(id)
      where not exists(select 1 from public.sammytv_categories cat
        where cat.id = wanted.id and cat.family_id = p_family and cat.enabled)) then
      raise exception using errcode = '22023', message = 'Invalid category';
    end if;
    -- The parent must approve the metadata they actually reviewed.
    if (v.title, v.description, v.duration_seconds, v.available, v.embeddable, v.age_restricted, v.is_live)
       is distinct from (p_metadata->>'title', p_metadata->>'description',
         (p_metadata->>'duration_seconds')::integer, (p_metadata->>'available')::boolean,
         (p_metadata->>'embeddable')::boolean, (p_metadata->>'age_restricted')::boolean,
         (p_metadata->>'is_live')::boolean) then
      raise exception using errcode = '40001', message = 'Metadata changed; review again';
    end if;
    outcome := 'approved';
    delete from public.sammytv_video_categories vc where vc.family_id = p_family and vc.video_id = p_video;
    insert into public.sammytv_video_categories(family_id, video_id, category_id)
      select p_family, p_video, wanted.id from (select distinct unnest(p_categories) id) wanted;
  end if;
  update public.sammytv_videos set title = p_metadata->>'title', description = p_metadata->>'description',
    duration_seconds = (p_metadata->>'duration_seconds')::integer,
    available = (p_metadata->>'available')::boolean, embeddable = (p_metadata->>'embeddable')::boolean,
    age_restricted = (p_metadata->>'age_restricted')::boolean, is_live = (p_metadata->>'is_live')::boolean,
    status = outcome, approved_by = case when outcome = 'approved' then p_parent else null end,
    approved_at = case when outcome = 'approved' then now() else null end,
    moderation_notes = case when outcome = 'approved' then coalesce(p_notes,'') else v.moderation_notes end
    where id = p_video and family_id = p_family;
  return query select p_video, outcome;
end;
$$;

revoke all on function public.sammytv_require_parent(uuid,uuid,integer),
  public.sammytv_validate_metadata(jsonb), public.sammytv_import_video(uuid,uuid,integer,jsonb),
  public.sammytv_moderate_video(uuid,uuid,integer,uuid,timestamptz,text,jsonb,uuid[],text)
  from public, anon, authenticated;
grant execute on function public.sammytv_require_parent(uuid,uuid,integer),
  public.sammytv_validate_metadata(jsonb), public.sammytv_import_video(uuid,uuid,integer,jsonb),
  public.sammytv_moderate_video(uuid,uuid,integer,uuid,timestamptz,text,jsonb,uuid[],text)
  to service_role;
notify pgrst, 'reload schema';
commit;
