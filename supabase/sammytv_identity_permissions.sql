-- Repair existing Phase 3 installations in the shared NPS Me project only.
-- Supabase's service_role cannot SELECT auth.users directly. Give only the
-- existing, server-only provisioning function owner privileges for that check.
-- All table references in its body are schema-qualified. No table grants or
-- existing family/member records are changed. Safe to apply more than once.
begin;
alter function public.sammytv_provision_parent(uuid) owner to postgres;
alter function public.sammytv_provision_parent(uuid) security definer;
alter function public.sammytv_provision_parent(uuid) set search_path = pg_catalog;
revoke all on function public.sammytv_provision_parent(uuid) from public, anon, authenticated;
grant execute on function public.sammytv_provision_parent(uuid) to service_role;
commit;
