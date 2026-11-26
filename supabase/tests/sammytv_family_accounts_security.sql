-- STAGING only, after sammytv_family_accounts.sql. Synthetic users; no emails sent.
-- All fixtures, including auth.users entries, are rolled back.
begin;
do $$
declare
  fa uuid:=gen_random_uuid(); fb uuid:=gen_random_uuid(); pa uuid:=gen_random_uuid(); pb uuid:=gen_random_uuid();
  child uuid; pending_child uuid; stamp timestamptz; result record; sig regprocedure;
  identity_a uuid:=gen_random_uuid(); identity_b uuid:=gen_random_uuid();
  login text:='test_' || replace(gen_random_uuid()::text,'-','');
  -- Values meet the hash format contract. HTTP tests exercise real scrypt.
  hashed text:='scrypt:32768:8:1$abcdefghijklmnop$' || repeat('a',128);
  new_hash text:='scrypt:32768:8:1$abcdefghijklmnop$' || repeat('b',128);
begin
  login:=left(login,32);
  for sig in select p.oid::regprocedure from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname=any(array[
      'sammytv_auth_limit','sammytv_family_children','sammytv_manage_child','sammytv_create_registration_code',
      'sammytv_request_child','sammytv_child_credentials','sammytv_child_session','sammytv_create_parent_invite',
      'sammytv_accept_parent_invite','sammytv_existing_parent','sammytv_family_parents']) loop
    if has_function_privilege('anon',sig,'EXECUTE') or has_function_privilege('authenticated',sig,'EXECUTE')
       or not has_function_privilege('service_role',sig,'EXECUTE') then
      raise exception 'Incorrect family function permissions: %',sig;
    end if;
  end loop;
  if has_table_privilege('anon','public.sammytv_child_logins','SELECT')
     or has_table_privilege('authenticated','public.sammytv_child_logins','SELECT') then
    raise exception 'Child credentials accessible to browser roles';
  end if;
  insert into public.sammytv_families(id) values(fa),(fb);
  insert into public.sammytv_members(id,family_id,role) values(pa,fa,'parent'),(pb,fb,'parent');
  insert into public.sammytv_profiles(family_id,member_id,nickname) values(fa,pa,'Parent A'),(fb,pb,'Parent B');
  -- Minimal Auth fixtures only for the invitation's verified-email boundary.
  insert into auth.users(id,email,email_confirmed_at) values
    (identity_a,'sammytv-test-' || identity_a::text || '@example.test',now()),
    (identity_b,'sammytv-test-' || identity_b::text || '@example.test',now());
  set local role service_role;
  select * into result from public.sammytv_manage_child(fa,pa,1,'create',null,null,login,'Test viewer',hashed);
  child:=result.child_id;
  if not exists(select 1 from public.sammytv_child_credentials(login)) then raise exception 'Created child cannot authenticate'; end if;
  if not exists(select 1 from public.sammytv_child_session(child,hashed) s where s.family_id=fa) then
    raise exception 'Child session missing or wrong family';
  end if;
  if exists(select 1 from public.sammytv_child_session(child,new_hash)) then raise exception 'Wrong hash snapshot accepted'; end if;
  begin
    perform public.sammytv_family_children(fa,child,1);
    raise exception 'Child read family management';
  exception when insufficient_privilege then null; end;
  if exists(select 1 from public.sammytv_family_children(fb,pb,1) c where c.child_id=child) then
    raise exception 'Child exposed in other family';
  end if;
  select c.updated_at into stamp from public.sammytv_family_children(fa,pa,1) c where c.child_id=child;
  begin
    perform public.sammytv_manage_child(fb,pb,1,'disable',child,stamp);
    raise exception 'Other family disabled child';
  exception when insufficient_privilege then null; end;
  begin
    perform public.sammytv_manage_child(fa,pa,2,'disable',child,stamp);
    raise exception 'Revoked parent session managed child';
  exception when insufficient_privilege then null; end;
  perform public.sammytv_manage_child(fa,pa,1,'reset_password',child,stamp,'','',new_hash);
  if exists(select 1 from public.sammytv_child_session(child,hashed)) then raise exception 'Old password snapshot survived reset'; end if;
  if not exists(select 1 from public.sammytv_child_session(child,new_hash) s where s.session_version=2) then
    raise exception 'Reset did not advance session version';
  end if;
  begin
    perform public.sammytv_manage_child(fa,pa,1,'disable',child,stamp);
    raise exception 'Stale child form accepted';
  exception when serialization_failure then null; end;
  select c.updated_at into stamp from public.sammytv_family_children(fa,pa,1) c where c.child_id=child;
  perform public.sammytv_manage_child(fa,pa,1,'disable',child,stamp);
  if exists(select 1 from public.sammytv_child_credentials(login)) or exists(select 1 from public.sammytv_child_session(child,new_hash)) then
    raise exception 'Disabled child can sign in';
  end if;
  if exists(select 1 from public.sammytv_members m where m.id=child and m.active) then raise exception 'Disabled membership still active'; end if;
  select c.updated_at into stamp from public.sammytv_family_children(fa,pa,1) c where c.child_id=child;
  perform public.sammytv_manage_child(fa,pa,1,'enable',child,stamp);
  if not exists(select 1 from public.sammytv_child_session(child,new_hash) s where s.session_version=4) then
    raise exception 'Restore did not issue a new session version';
  end if;

  perform public.sammytv_create_registration_code(fa,pa,1,repeat('a',64));
  select * into result from public.sammytv_request_child(repeat('a',64),left(login,29)||'_p','Pending viewer',hashed);
  if not result.requested then raise exception 'Registration request failed'; end if;
  select c.child_id,c.updated_at into pending_child,stamp from public.sammytv_family_children(fa,pa,1) c where c.account_status='pending';
  if pending_child is null or exists(select 1 from public.sammytv_child_session(pending_child,hashed)) then
    raise exception 'Pending request granted access';
  end if;
  perform public.sammytv_manage_child(fa,pa,1,'approve',pending_child,stamp);
  if not exists(select 1 from public.sammytv_child_session(pending_child,hashed) s where s.family_id=fa) then
    raise exception 'Approved request cannot sign in';
  end if;
  perform public.sammytv_create_registration_code(fa,pa,1,repeat('b',64));
  select * into result from public.sammytv_request_child(repeat('a',64),left(login,29)||'_q','Blocked viewer',hashed);
  if result.requested then raise exception 'Old registration code still works'; end if;
  update public.sammytv_registration_codes set expires_at=now()-interval '1 minute' where family_id=fa;
  select * into result from public.sammytv_request_child(repeat('b',64),left(login,29)||'_q','Blocked viewer',hashed);
  if result.requested then raise exception 'Expired registration code works'; end if;

  perform public.sammytv_create_parent_invite(fa,pa,1,repeat('c',64),'sammytv-test-' || identity_a::text || '@example.test');
  begin
    perform public.sammytv_accept_parent_invite(identity_b,repeat('c',64));
    raise exception 'Wrong verified email accepted invitation';
  exception when insufficient_privilege then null; end;
  select * into result from public.sammytv_accept_parent_invite(identity_a,repeat('c',64));
  if result.family_id is distinct from fa then raise exception 'Invited parent got wrong family'; end if;
  if not exists(select 1 from public.sammytv_existing_parent(identity_a) s where s.family_id=fa) then
    raise exception 'Invited parent cannot return';
  end if;
  if (select count(*) from public.sammytv_family_parents(fa,pa,1))<>2 then raise exception 'Shared family missing parent'; end if;
  begin
    perform public.sammytv_accept_parent_invite(identity_a,repeat('c',64));
    raise exception 'Invitation reused';
  exception when insufficient_privilege then null; end;
  perform public.sammytv_create_parent_invite(fb,pb,1,repeat('d',64),'sammytv-test-' || identity_a::text || '@example.test');
  begin
    perform public.sammytv_accept_parent_invite(identity_a,repeat('d',64));
    raise exception 'Two families implicitly merged';
  exception when invalid_parameter_value then null; end;

  select * into result from public.sammytv_auth_limit(repeat('e',64),2,60);
  if not result.allowed then raise exception 'First auth attempt denied'; end if;
  perform public.sammytv_auth_limit(repeat('e',64),2,60);
  select * into result from public.sammytv_auth_limit(repeat('e',64),2,60);
  if result.allowed then raise exception 'Persistent throttle did not block'; end if;
  reset role;
end;
$$;
rollback;
