-- Phase 4c. Shared NPS Me project, after sammytv_moderation.sql.
-- Apply once before deploying camera support. No camera is approved or seeded.
begin;
alter table public.sammytv_videos
  add column live_camera boolean not null default false,
  add column camera_video_id text,
  add column camera_channel_id text,
  add constraint sammytv_camera_binding check (
    (not live_camera and camera_video_id is null and camera_channel_id is null)
    or (live_camera and camera_video_id is not null and camera_channel_id is not null
        and camera_video_id=provider_video_id and camera_channel_id ~ '^UC[A-Za-z0-9_-]{22}$')
  );

create or replace function public.sammytv_guard_approval() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
  if TG_OP='UPDATE' then
    if (new.provider,new.provider_video_id,new.channel_id,new.family_id,new.is_live)
       is distinct from (old.provider,old.provider_video_id,old.channel_id,old.family_id,old.is_live) then
      new.status := 'pending'; new.approved_by := null; new.approved_at := null;
    end if;
  end if;
  if new.status <> 'approved' then
    new.live_camera := false; new.camera_video_id := null; new.camera_channel_id := null;
  end if;
  if new.status='approved' then
    if not exists(select 1 from public.sammytv_members m
      where m.id=new.approved_by and m.family_id=new.family_id and m.role='parent' and m.active) then
      raise exception 'SammyTV approval requires an active parent in the same family';
    end if;
    if new.live_camera then
      if not new.is_live or new.camera_video_id is distinct from new.provider_video_id
         or not new.available or not new.embeddable or new.age_restricted
         or not exists(select 1 from public.sammytv_channels c
           where c.id=new.channel_id and c.family_id=new.family_id and c.enabled
             and c.provider_channel_id=new.camera_channel_id) then
        raise exception using errcode='22023',message='Invalid live-camera approval';
      end if;
    elsif new.is_live then
      raise exception using errcode='22023',message='Live streams require explicit camera approval';
    end if;
  end if;
  new.updated_at := clock_timestamp();
  return new;
end;
$$;

create function public.sammytv_video_visible(p_video public.sammytv_videos,p_channel public.sammytv_channels)
returns boolean language sql stable security invoker set search_path=pg_catalog as $$
  select (p_video).family_id=(p_channel).family_id and (p_video).channel_id=(p_channel).id and (p_channel).enabled
    and (p_video).provider='youtube' and (p_video).status='approved' and (p_video).approved_by is not null and (p_video).approved_at is not null
    and (p_video).available and (p_video).embeddable and not (p_video).age_restricted
    and ((not (p_video).is_live and not (p_video).live_camera) or
      ((p_video).is_live and (p_video).live_camera and (p_video).camera_video_id=(p_video).provider_video_id and (p_video).camera_channel_id=(p_channel).provider_channel_id))
    and exists(select 1 from public.sammytv_families f where f.id=(p_video).family_id and f.enabled)
    and exists(select 1 from public.sammytv_members m
      where m.id=(p_video).approved_by and m.family_id=(p_video).family_id and m.role='parent' and m.active);
$$;

-- New RPC names let the old deployment continue serving recordings during rollout.
create function public.sammytv_catalogue_v2(
  p_family_id uuid,p_video_id uuid default null,p_channel_id uuid default null,
  p_category_id uuid default null,p_query text default '',p_limit integer default 48,p_offset integer default 0
) returns table(
  id uuid,family_id uuid,title text,description text,duration_seconds integer,is_live boolean,
  provider text,provider_video_id text,status text,approved_at timestamptz,approved_by uuid,
  available boolean,embeddable boolean,age_restricted boolean,channel jsonb,categories jsonb,
  live_camera boolean,camera_video_id text,camera_channel_id text,updated_at timestamptz
) language sql stable security invoker set search_path=pg_catalog as $$
  select v.id,v.family_id,v.title,v.description,v.duration_seconds,v.is_live,v.provider,v.provider_video_id,
    v.status,v.approved_at,v.approved_by,v.available,v.embeddable,v.age_restricted,
    jsonb_build_object('id',c.id,'name',c.name,'family_id',c.family_id,'enabled',c.enabled,'provider_channel_id',c.provider_channel_id),
    coalesce((select jsonb_agg(jsonb_build_object('id',cat.id,'name',cat.name) order by cat.position,cat.name)
      from public.sammytv_video_categories vc join public.sammytv_categories cat
        on cat.id=vc.category_id and cat.family_id=vc.family_id
      where vc.video_id=v.id and vc.family_id=p_family_id and cat.enabled),'[]'::jsonb),
    v.live_camera,v.camera_video_id,v.camera_channel_id,v.updated_at
  from public.sammytv_videos v join public.sammytv_channels c on c.id=v.channel_id and c.family_id=v.family_id
  where v.family_id=p_family_id and public.sammytv_video_visible(v,c)
    and (p_video_id is null or v.id=p_video_id) and (p_channel_id is null or v.channel_id=p_channel_id)
    and (p_category_id is null or exists(select 1 from public.sammytv_video_categories vc
      join public.sammytv_categories cat on cat.id=vc.category_id and cat.family_id=vc.family_id
      where vc.video_id=v.id and vc.family_id=p_family_id and vc.category_id=p_category_id and cat.enabled))
    and (coalesce(trim(p_query),'')='' or strpos(lower(v.title || ' ' || v.description || ' ' || c.name),lower(left(trim(p_query),120)))>0)
  order by v.approved_at desc,v.id
  limit greatest(1,least(coalesce(p_limit,48),49)) offset greatest(0,least(coalesce(p_offset,0),10000));
$$;

create function public.sammytv_channels_v2(p_family_id uuid)
returns table(id uuid,name text) language sql stable security invoker set search_path=pg_catalog as $$
  select c.id,c.name from public.sammytv_channels c where c.family_id=p_family_id and exists(
    select 1 from public.sammytv_videos v where v.family_id=p_family_id and v.channel_id=c.id
      and public.sammytv_video_visible(v,c)) order by c.name,c.id;
$$;

create function public.sammytv_approve_camera(
  p_family uuid,p_parent uuid,p_session_version integer,p_video uuid,p_expected_updated_at timestamptz,
  p_metadata jsonb,p_categories uuid[],p_notes text,p_confirmed boolean
) returns table(video_id uuid,video_status text)
language plpgsql security invoker set search_path=pg_catalog as $$
declare v public.sammytv_videos; ch public.sammytv_channels;
begin
  perform public.sammytv_require_parent(p_family,p_parent,p_session_version);
  perform public.sammytv_validate_metadata(p_metadata);
  if p_confirmed is distinct from true or p_metadata->>'broadcast_state' is distinct from 'live'
     or p_metadata->>'is_live' is distinct from 'true' or length(coalesce(p_notes,''))>10000
     or coalesce(cardinality(p_categories),0) not between 1 and 50 then
    raise exception using errcode='22023',message='Explicit approval of a running camera required';
  end if;
  select vid.* into v from public.sammytv_videos vid where vid.id=p_video and vid.family_id=p_family for update;
  if not found then raise exception using errcode='42501',message='Video unavailable'; end if;
  if v.updated_at is distinct from p_expected_updated_at then
    raise exception using errcode='40001',message='Video changed; review again';
  end if;
  select c.* into ch from public.sammytv_channels c where c.id=v.channel_id and c.family_id=p_family for share;
  if v.provider_video_id is distinct from p_metadata->>'provider_video_id'
     or ch.provider_channel_id is distinct from p_metadata->>'provider_channel_id'
     or not ch.enabled or p_metadata->>'available' is distinct from 'true'
     or p_metadata->>'embeddable' is distinct from 'true' or p_metadata->>'age_restricted' is distinct from 'false' then
    raise exception using errcode='22023',message='Camera unavailable for approval';
  end if;
  if (v.title,v.description,v.available,v.embeddable,v.age_restricted,v.is_live)
     is distinct from (p_metadata->>'title',p_metadata->>'description',(p_metadata->>'available')::boolean,
       (p_metadata->>'embeddable')::boolean,(p_metadata->>'age_restricted')::boolean,(p_metadata->>'is_live')::boolean) then
    raise exception using errcode='40001',message='Metadata changed; review again';
  end if;
  perform 1 from public.sammytv_categories cat where cat.family_id=p_family and cat.enabled and cat.id=any(p_categories) for share;
  if exists(select 1 from unnest(p_categories) wanted(id) where not exists(
    select 1 from public.sammytv_categories cat where cat.id=wanted.id and cat.family_id=p_family and cat.enabled)) then
    raise exception using errcode='22023',message='Invalid category';
  end if;
  delete from public.sammytv_video_categories vc where vc.family_id=p_family and vc.video_id=p_video;
  insert into public.sammytv_video_categories(family_id,video_id,category_id)
    select p_family,p_video,wanted.id from (select distinct unnest(p_categories) id) wanted;
  update public.sammytv_videos set status='approved',approved_by=p_parent,approved_at=now(),
    live_camera=true,camera_video_id=v.provider_video_id,camera_channel_id=ch.provider_channel_id,
    duration_seconds=(p_metadata->>'duration_seconds')::integer,moderation_notes=coalesce(p_notes,'')
    where id=p_video and family_id=p_family;
  return query select p_video,'approved'::text;
end;
$$;

revoke all on function public.sammytv_video_visible(public.sammytv_videos,public.sammytv_channels),
  public.sammytv_catalogue_v2(uuid,uuid,uuid,uuid,text,integer,integer),public.sammytv_channels_v2(uuid),
  public.sammytv_approve_camera(uuid,uuid,integer,uuid,timestamptz,jsonb,uuid[],text,boolean)
  from public,anon,authenticated;
grant execute on function public.sammytv_video_visible(public.sammytv_videos,public.sammytv_channels),
  public.sammytv_catalogue_v2(uuid,uuid,uuid,uuid,text,integer,integer),public.sammytv_channels_v2(uuid),
  public.sammytv_approve_camera(uuid,uuid,integer,uuid,timestamptz,jsonb,uuid[],text,boolean)
  to service_role;
notify pgrst,'reload schema';
commit;
