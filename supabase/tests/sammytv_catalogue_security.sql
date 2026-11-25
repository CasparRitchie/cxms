-- Run AFTER sammytv_catalogue.sql on a staging CXMS/SammyTV database.
-- All fixtures are synthetic and rolled back. A failed assertion aborts the run.
begin;

do $$
declare
  t text;
  family_a uuid := gen_random_uuid();
  family_b uuid := gen_random_uuid();
  parent_a uuid := gen_random_uuid();
  viewer_a uuid := gen_random_uuid();
  parent_b uuid := gen_random_uuid();
  channel_a uuid := gen_random_uuid();
  channel_b uuid := gen_random_uuid();
  video_a uuid := gen_random_uuid();
  category_a uuid := gen_random_uuid();
  n integer;
begin
  foreach t in array array['sammytv_families','sammytv_members','sammytv_profiles',
    'sammytv_categories','sammytv_channels','sammytv_videos','sammytv_video_categories'] loop
    if not exists (select 1 from pg_class c join pg_namespace ns on ns.oid = c.relnamespace
      where ns.nspname = 'public' and c.relname = t and c.relrowsecurity and c.relforcerowsecurity) then
      raise exception 'RLS missing on %', t;
    end if;
    if has_table_privilege('anon', 'public.' || t, 'SELECT,INSERT,UPDATE,DELETE')
      or has_table_privilege('authenticated', 'public.' || t, 'SELECT,INSERT,UPDATE,DELETE') then
      raise exception 'Unexpected browser access to %', t;
    end if;
  end loop;
  insert into public.sammytv_families(id) values (family_a), (family_b);
  insert into public.sammytv_members(id, family_id, role) values
    (parent_a, family_a, 'parent'), (viewer_a, family_a, 'viewer'), (parent_b, family_b, 'parent');
  insert into public.sammytv_channels(id, family_id, provider_channel_id, name) values
    (channel_a, family_a, 'UC' || repeat('a',22), 'Rail Journal'),
    (channel_b, family_b, 'UC' || repeat('b',22), 'Other family channel');
  insert into public.sammytv_categories(id, family_id, name, slug) values
    (category_a, family_a, 'Railways', 'railways');
  insert into public.sammytv_videos(id, family_id, channel_id, provider_video_id, title,
      description, available, embeddable, age_restricted, status, approved_by, approved_at) values
    (video_a, family_a, channel_a, 'AbCdEf123_-', 'Railway journey', 'A trip through hills', true, true, false, 'approved', parent_a, now()),
    (gen_random_uuid(), family_b, channel_b, 'BbCdEf123_-', 'Other family video', '', true, true, false, 'approved', parent_b, now());
  insert into public.sammytv_video_categories(family_id, video_id, category_id) values (family_a, video_a, category_a);
  insert into public.sammytv_videos(family_id, channel_id, provider_video_id, title,
      available, embeddable, age_restricted, status, approved_by, approved_at)
  select family_a, channel_a, lpad(s.n::text,11,'0'), 'Excluded fixture ' || s.n,
      s.n <> 4, s.n <> 5, s.n = 6,
      case s.n when 1 then 'pending' when 2 then 'hidden' when 3 then 'rejected' else 'approved' end,
      parent_a, now()
  from generate_series(1,6) s(n);
  insert into public.sammytv_videos(family_id, channel_id, provider_video_id, title,
      available, embeddable, age_restricted, is_live, status, approved_by, approved_at)
    values (family_a, channel_a, 'LIVE1234567', 'Live content is not in Phase 2', true, true, false, true, 'approved', parent_a, now());

  select count(*) into n from public.sammytv_catalogue(family_a);
  if n <> 1 then raise exception 'Catalogue leaked excluded or other-family videos: %', n; end if;
  select count(*) into n from public.sammytv_catalogue(family_a, p_query => 'hills', p_category_id => category_a);
  if n <> 1 then raise exception 'Description/category search failed'; end if;
  select count(*) into n from public.sammytv_catalogue(family_a, p_query => '%');
  if n <> 0 then raise exception 'Search interpreted a wildcard'; end if;
  select count(*) into n from public.sammytv_catalogue(family_a, p_channel_id => channel_b);
  if n <> 0 then raise exception 'Other-family channel leaked'; end if;

  begin
    insert into public.sammytv_profiles(family_id, member_id, nickname) values (family_b, viewer_a, 'Synthetic');
    raise exception 'Cross-family profile constraint failed';
  exception when foreign_key_violation then null;
  end;
  begin
    insert into public.sammytv_videos(family_id, channel_id, provider_video_id, title, status, approved_by, approved_at)
      values (family_a, channel_a, 'UNAPPROVED1', 'Viewer cannot approve', 'approved', viewer_a, now());
    raise exception 'Parent approval guard failed';
  exception when raise_exception then
    if sqlerrm <> 'SammyTV approval requires an active parent in the same family' then raise; end if;
  end;

  update public.sammytv_members set active = false where id = parent_a;
  select count(*) into n from public.sammytv_catalogue(family_a);
  if n <> 0 then raise exception 'Revoked parent approvals are still visible'; end if;
  update public.sammytv_members set active = true where id = parent_a;
  update public.sammytv_channels set enabled = false where id = channel_a;
  select count(*) into n from public.sammytv_channels(family_a);
  if n <> 0 then raise exception 'Disabled channel remains visible'; end if;
  update public.sammytv_channels set enabled = true where id = channel_a;
  update public.sammytv_videos set provider_video_id = 'NEWID123456' where id = video_a;
  if exists (select 1 from public.sammytv_videos where id = video_a and status = 'approved') then
    raise exception 'Changed video retained its approval';
  end if;
end;
$$;

-- Prove actual browser-role requests cannot read tables or invoke the service RPC.
set local role anon;
do $$
begin
  begin
    perform 1 from public.sammytv_videos limit 1;
    raise exception 'Anonymous table access unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
  begin
    perform 1 from public.sammytv_catalogue(gen_random_uuid());
    raise exception 'Anonymous RPC access unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
end;
$$;
reset role;
set local role authenticated;
do $$
begin
  begin
    perform 1 from public.sammytv_profiles limit 1;
    raise exception 'Authenticated browser table access unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
  begin
    perform 1 from public.sammytv_channels(gen_random_uuid());
    raise exception 'Authenticated browser RPC access unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
end;
$$;
reset role;
rollback;
