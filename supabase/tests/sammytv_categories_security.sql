-- Staging database only, after sammytv_categories.sql. All fixtures roll back.
begin;
do $$
declare
  fa uuid := gen_random_uuid(); fb uuid := gen_random_uuid();
  pa uuid := gen_random_uuid(); pb uuid := gen_random_uuid(); viewer uuid := gen_random_uuid();
  cat uuid; result record; sig text := 'public.sammytv_manage_category(uuid,uuid,integer,text,uuid,text,integer)';
begin
  if has_function_privilege('anon',sig,'EXECUTE') or has_function_privilege('authenticated',sig,'EXECUTE')
     or not has_function_privilege('service_role',sig,'EXECUTE') then
    raise exception 'Incorrect category management grants';
  end if;
  if (select p.prosecdef from pg_proc p where p.oid=sig::regprocedure) then
    raise exception 'Category management must be SECURITY INVOKER';
  end if;
  insert into public.sammytv_families(id) values(fa),(fb);
  insert into public.sammytv_members(id,family_id,role) values(pa,fa,'parent'),(pb,fb,'parent'),(viewer,fa,'viewer');
  set local role service_role;
  select * into result from public.sammytv_manage_category(fa,pa,1,'create',null,'Steam journeys',null);
  cat := result.category_id;
  if cat is null or not result.enabled or result.category_position <> 0 then raise exception 'Category not created'; end if;
  select * into result from public.sammytv_manage_category(fa,pa,1,'create',null,'STEAM JOURNEYS',null);
  if result.category_id <> cat then raise exception 'Case-insensitive duplicate category created'; end if;
  select * into result from public.sammytv_manage_category(fa,pa,1,'save',cat,'Railway adventures',12);
  if result.category_position <> 12 then raise exception 'Incorrect returned category order'; end if;
  if not exists(select 1 from public.sammytv_categories c where c.id=cat and c.name='Railway adventures' and c.position=12) then
    raise exception 'Category rename/order failed';
  end if;
  begin
    perform public.sammytv_manage_category(fb,pb,1,'archive',cat,'',null);
    raise exception 'Other family archived category';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_manage_category(fa,viewer,1,'create',null,'No access',null);
    raise exception 'Viewer created category';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_manage_category(fa,pa,2,'archive',cat,'',null);
    raise exception 'Revoked parent session edited category';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_manage_category(fa,pa,1,'create',null,'All',null);
    raise exception 'Reserved name created';
  exception when invalid_parameter_value then null; end;
  perform public.sammytv_manage_category(fa,pa,1,'archive',cat,'',null);
  if exists(select 1 from public.sammytv_categories c where c.id=cat and c.enabled) then
    raise exception 'Category archive failed';
  end if;
  begin
    perform public.sammytv_manage_category(fa,pa,1,'create',null,'Railway adventures',null);
    raise exception 'Create implicitly restored category';
  exception when invalid_parameter_value then null; end;
  perform public.sammytv_manage_category(fa,pa,1,'restore',cat,'',null);
  if not exists(select 1 from public.sammytv_categories c where c.id=cat and c.enabled and c.position=12) then
    raise exception 'Category restore failed';
  end if;
  -- Identical names are permitted in separate families, with separate UUIDs.
  select * into result from public.sammytv_manage_category(fb,pb,1,'create',null,'Railway adventures',null);
  if result.category_id=cat then raise exception 'Cross-family category reused'; end if;
  reset role;
end;
$$;
set local role anon;
do $$ begin
  begin
    perform public.sammytv_manage_category(null,null,1,'create',null,'Denied',null);
    raise exception 'Anonymous category management succeeded';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
  begin
    perform public.sammytv_manage_category(null,null,1,'create',null,'Denied',null);
    raise exception 'Browser category management succeeded';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
rollback;
