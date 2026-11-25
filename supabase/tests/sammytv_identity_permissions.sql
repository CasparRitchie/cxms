-- Read-only regression check after the Phase 3 permissions repair.
-- Run in the shared NPS Me SQL Editor as postgres. Creates no users or records.
begin;
do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_proc p
    where p.oid = 'public.sammytv_provision_parent(uuid)'::regprocedure
      and p.prosecdef
      and pg_catalog.pg_get_userbyid(p.proowner) = 'postgres'
      and p.proconfig @> array['search_path=pg_catalog']
  ) then
    raise exception 'Parent provisioning must use its restricted owner context';
  end if;
  if pg_catalog.has_function_privilege('anon', 'public.sammytv_provision_parent(uuid)', 'EXECUTE')
     or pg_catalog.has_function_privilege('authenticated', 'public.sammytv_provision_parent(uuid)', 'EXECUTE')
     or not pg_catalog.has_function_privilege('service_role', 'public.sammytv_provision_parent(uuid)', 'EXECUTE') then
    raise exception 'Only the server role should be granted parent provisioning';
  end if;
end $$;
set local role service_role;
do $$
begin
  -- NULL matches no identity: the RPC must reach its verified-identity guard,
  -- rather than fail with permission denied on auth.users. No rows are written.
  begin
    perform public.sammytv_provision_parent(null);
    raise exception 'Missing identities must be rejected';
  exception when raise_exception then
    if sqlerrm <> 'Verified identity required' then
      raise;
    end if;
  end;
end $$;
rollback;
