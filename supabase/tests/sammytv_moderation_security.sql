-- Run on a STAGING database after sammytv_catalogue.sql and sammytv_moderation.sql.
-- Synthetic family/member fixtures only, no Auth users. Everything rolls back.
begin;
do $$
declare
  fa uuid := gen_random_uuid(); fb uuid := gen_random_uuid();
  pa uuid := gen_random_uuid(); pb uuid := gen_random_uuid(); va uuid := gen_random_uuid();
  ca uuid := gen_random_uuid(); cb uuid := gen_random_uuid();
  vid uuid; result record; stamp timestamptz; n integer; sig text;
  meta jsonb := jsonb_build_object('provider_video_id','AbCdEf123_-',
    'provider_channel_id','UC' || repeat('a',22),'channel_name','Synthetic railway',
    'title','Synthetic journey','description','Review fixture','duration_seconds',120,
    'available',true,'embeddable',true,'age_restricted',false,'is_live',false);
begin
  foreach sig in array array[
    'public.sammytv_require_parent(uuid,uuid,integer)',
    'public.sammytv_validate_metadata(jsonb)',
    'public.sammytv_import_video(uuid,uuid,integer,jsonb)',
    'public.sammytv_moderate_video(uuid,uuid,integer,uuid,timestamptz,text,jsonb,uuid[],text)'
  ] loop
    if has_function_privilege('anon',sig,'EXECUTE')
       or has_function_privilege('authenticated',sig,'EXECUTE')
       or not has_function_privilege('service_role',sig,'EXECUTE') then
      raise exception 'Incorrect moderation grants: %', sig;
    end if;
    if (select p.prosecdef from pg_proc p where p.oid = sig::regprocedure) then
      raise exception 'Moderation functions must run as invoker: %', sig;
    end if;
  end loop;
  insert into public.sammytv_families(id) values(fa),(fb);
  insert into public.sammytv_members(id,family_id,role) values(pa,fa,'parent'),(pb,fb,'parent'),(va,fa,'viewer');
  insert into public.sammytv_categories(id,family_id,name,slug) values(ca,fa,'Railways','railways'),(cb,fb,'Other','other');

  -- Exercise actual production role permissions, not postgres's bypass powers.
  set local role service_role;
  select * into result from public.sammytv_import_video(fa,pa,1,meta);
  vid := result.video_id;
  if not result.added or vid is null then raise exception 'Import failed'; end if;
  if exists(select 1 from public.sammytv_catalogue(fa)) then raise exception 'Import auto-approved'; end if;
  select * into result from public.sammytv_import_video(fa,pa,1,meta);
  if result.added or result.video_id <> vid then raise exception 'Duplicate import changed video'; end if;
  begin
    perform public.sammytv_import_video(fa,va,1,meta);
    raise exception 'Viewer imported a video';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_import_video(fb,pa,1,meta);
    raise exception 'Cross-family parent imported a video';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_import_video(fa,pa,2,meta);
    raise exception 'Revoked session imported a video';
  exception when insufficient_privilege then null; end;

  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  begin
    perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'approve',meta,array[cb],'');
    raise exception 'Cross-family category approved';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'approve',meta,array[]::uuid[],'');
    raise exception 'Uncategorised video approved';
  exception when invalid_parameter_value then null; end;
  begin
    perform public.sammytv_moderate_video(fb,pb,1,vid,stamp,'hide',null,array[]::uuid[],'');
    raise exception 'Other family removed a video';
  exception when insufficient_privilege then null; end;
  perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'approve',meta,array[ca],'Private fixture notes');
  select count(*) into n from public.sammytv_catalogue(fa);
  if n <> 1 then raise exception 'Approved video missing'; end if;
  if exists(select 1 from public.sammytv_catalogue(fb)) then raise exception 'Video leaked to another family'; end if;
  -- Duplicate imports must preserve approval and notes.
  perform public.sammytv_import_video(fa,pa,1,meta);
  if not exists(select 1 from public.sammytv_videos v where v.id=vid and v.status='approved'
    and v.moderation_notes='Private fixture notes') then raise exception 'Duplicate import reset moderation'; end if;
  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'hide',null,array[]::uuid[],'');
  if exists(select 1 from public.sammytv_catalogue(fa)) then raise exception 'Removed video still visible'; end if;
  -- Synthetic stamp mismatch proves concurrent update guard, even in one transaction.
  begin
    perform public.sammytv_moderate_video(fa,pa,1,vid,stamp-interval '1 second','approve',meta,array[ca],'');
    raise exception 'Stale approval succeeded';
  exception when serialization_failure then null; end;
  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'refresh',meta || '{"age_restricted":true}'::jsonb,array[]::uuid[],'');
  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  begin
    perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'approve',meta || '{"age_restricted":true}'::jsonb,array[ca],'');
    raise exception 'Age-restricted video approved';
  exception when invalid_parameter_value then null; end;
  -- Changed metadata cannot be silently approved even if all flags are eligible.
  begin
    perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'approve',meta,array[ca],'');
    raise exception 'Unreviewed metadata change approved';
  exception when serialization_failure then null; end;
  perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'refresh',meta,array[]::uuid[],'');
  select v.updated_at into stamp from public.sammytv_videos v where v.id=vid;
  perform public.sammytv_moderate_video(fa,pa,1,vid,stamp,'approve',meta,array[ca],'Restored');
  if not exists(select 1 from public.sammytv_catalogue(fa)) then raise exception 'Restore failed'; end if;
  reset role;
end;
$$;

set local role anon;
do $$ begin
  begin
    perform public.sammytv_import_video(null,null,1,'{}'::jsonb);
    raise exception 'Anonymous moderation succeeded';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
  begin
    perform public.sammytv_moderate_video(null,null,1,null,null,'hide',null,array[]::uuid[],'');
    raise exception 'Browser moderation succeeded';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
rollback;
