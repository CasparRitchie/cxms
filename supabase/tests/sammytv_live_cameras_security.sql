-- STAGING only, after sammytv_live_cameras.sql. All synthetic fixtures roll back.
begin;
do $$
declare
  fa uuid := gen_random_uuid(); fb uuid := gen_random_uuid();
  pa uuid := gen_random_uuid(); pb uuid := gen_random_uuid(); viewer uuid := gen_random_uuid();
  ca uuid := gen_random_uuid(); cb uuid := gen_random_uuid(); vid uuid; result record;
  stamp timestamptz; sig text; state text;
  meta jsonb := jsonb_build_object('provider_video_id','AbCdEf123_-',
    'provider_channel_id','UC' || repeat('a',22),'channel_name','Synthetic camera operator',
    'title','Synthetic station camera','description','Camera fixture','duration_seconds',0,
    'available',true,'embeddable',true,'age_restricted',false,'is_live',true,'broadcast_state','live');
begin
  foreach sig in array array[
    'public.sammytv_catalogue_v2(uuid,uuid,uuid,uuid,text,integer,integer)',
    'public.sammytv_channels_v2(uuid)',
    'public.sammytv_video_visible(public.sammytv_videos,public.sammytv_channels)',
    'public.sammytv_approve_camera(uuid,uuid,integer,uuid,timestamptz,jsonb,uuid[],text,boolean)'
  ] loop
    if has_function_privilege('anon',sig,'EXECUTE') or has_function_privilege('authenticated',sig,'EXECUTE')
       or not has_function_privilege('service_role',sig,'EXECUTE') then
      raise exception 'Incorrect camera function grants: %',sig;
    end if;
    if (select p.prosecdef from pg_proc p where p.oid=sig::regprocedure) then
      raise exception 'Camera functions must run as invoker: %',sig;
    end if;
  end loop;
  insert into public.sammytv_families(id) values(fa),(fb);
  insert into public.sammytv_members(id,family_id,role) values(pa,fa,'parent'),(pb,fb,'parent'),(viewer,fa,'viewer');
  insert into public.sammytv_categories(id,family_id,name,slug)
    values(ca,fa,'Live Cameras','live-cameras'),(cb,fb,'Other cameras','other-cameras');
  set local role service_role;
  select * into result from public.sammytv_import_video(fa,pa,1,meta);
  vid := result.video_id;
  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  if exists(select 1 from public.sammytv_catalogue_v2(fa)) then raise exception 'Imported camera visible'; end if;
  begin
    perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'approve',meta,array[ca],'');
    raise exception 'Ordinary approval allowed livestream';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,meta,array[ca],'',false);
    raise exception 'Camera approved without confirmation';
  exception when invalid_parameter_value then null; end;
  foreach state in array array['upcoming','unconfirmed','ended','recording'] loop
    begin
      perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,
        jsonb_set(meta,'{broadcast_state}',to_jsonb(state)),array[ca],'',true);
      raise exception 'Non-running camera approved';
    exception when invalid_parameter_value then null; end;
  end loop;
  begin
    perform public.sammytv_approve_camera(fa,viewer,1,vid,stamp,meta,array[ca],'',true);
    raise exception 'Viewer approved camera';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_approve_camera(fb,pb,1,vid,stamp,meta,array[cb],'',true);
    raise exception 'Other family approved camera';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_approve_camera(fa,pa,2,vid,stamp,meta,array[ca],'',true);
    raise exception 'Revoked session approved camera';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,meta,array[cb],'',true);
    raise exception 'Other family category accepted';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,meta || '{"embeddable":false}'::jsonb,array[ca],'',true);
    raise exception 'Embedding restriction bypassed';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,meta || '{"age_restricted":true}'::jsonb,array[ca],'',true);
    raise exception 'Age restriction bypassed';
  exception when invalid_parameter_value then null; end;
  perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,meta,array[ca],'Reviewed camera',true);
  if not exists(select 1 from public.sammytv_catalogue_v2(fa) v where v.id=vid and v.live_camera
      and v.camera_video_id=meta->>'provider_video_id' and v.camera_channel_id=meta->>'provider_channel_id') then
    raise exception 'Approved camera missing or binding incorrect';
  end if;
  if exists(select 1 from public.sammytv_catalogue(fa)) or exists(select 1 from public.sammytv_catalogue_v2(fb)) then
    raise exception 'Camera leaked through old RPC or other family';
  end if;
  if not exists(select 1 from public.sammytv_channels_v2(fa)) then raise exception 'Camera channel missing'; end if;
  begin
    perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,meta,array[ca],'',true);
    raise exception 'Stale camera approval accepted';
  exception when serialization_failure then null; end;
  update public.sammytv_members set active=false where id=pa;
  if exists(select 1 from public.sammytv_catalogue_v2(fa)) then raise exception 'Revoked parent approval visible'; end if;
  update public.sammytv_members set active=true where id=pa;
  update public.sammytv_channels set provider_channel_id='UC' || repeat('b',22) where family_id=fa;
  if exists(select 1 from public.sammytv_catalogue_v2(fa)) then raise exception 'Changed camera creator visible'; end if;
  update public.sammytv_channels set provider_channel_id=meta->>'provider_channel_id' where family_id=fa;
  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'hide',null,array[]::uuid[],'');
  if exists(select 1 from public.sammytv_videos v where v.id=vid and
    (v.live_camera or v.camera_video_id is not null or v.camera_channel_id is not null)) then
    raise exception 'Removal retained camera approval';
  end if;
  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  perform public.sammytv_approve_camera(fa,pa,1,vid,stamp,meta,array[ca],'',true);
  update public.sammytv_videos set provider_video_id='ZyXwVu987_-' where id=vid;
  if exists(select 1 from public.sammytv_videos v where v.id=vid and
    (v.status='approved' or v.live_camera or v.approved_by is not null)) then
    raise exception 'Changed stream retained approval';
  end if;
  reset role;
end;
$$;
rollback;
