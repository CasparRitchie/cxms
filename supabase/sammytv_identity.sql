-- Phase 3, shared NPS Me project. Apply after sammytv_catalogue.sql.
begin;
create table public.sammytv_parent_identities (
 identity_id uuid primary key references auth.users(id) on delete cascade,
 member_id uuid not null unique, family_id uuid not null,
 foreign key(member_id,family_id) references public.sammytv_members(id,family_id) on delete cascade
);
create table public.sammytv_pairings (
 digest text primary key check(digest ~ '^[a-f0-9]{64}$'),
 family_id uuid not null references public.sammytv_families(id) on delete cascade,
 parent_id uuid not null, expires_at timestamptz not null default now()+interval '10 minutes',
 foreign key(parent_id,family_id) references public.sammytv_members(id,family_id) on delete cascade
);
create function public.sammytv_provision_parent(p_identity uuid)
returns table(member_id uuid,family_id uuid,profile_id uuid,session_version integer)
-- Only this RPC needs owner privileges to check auth.users. It is executable
-- only by service_role; callers must first verify the parent's password/email.
language plpgsql security definer set search_path=pg_catalog as $$
declare f uuid; m uuid;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_identity::text,0));
 if not exists(select 1 from auth.users where id=p_identity and email_confirmed_at is not null) then
 raise exception 'Verified identity required'; end if;
 select i.family_id,i.member_id into f,m from public.sammytv_parent_identities i where identity_id=p_identity;
 if m is null then
 insert into public.sammytv_families default values returning id into f;
 insert into public.sammytv_members(family_id,role) values(f,'parent') returning id into m;
 insert into public.sammytv_parent_identities values(p_identity,m,f);
 insert into public.sammytv_profiles(family_id,member_id,nickname) values(f,m,'Parent');
 insert into public.sammytv_categories(family_id,name,slug,position) values
 (f,'Trains','trains',0),(f,'Planes','planes',1),(f,'Lucas Ivkovic','lucas-ivkovic',2),
 (f,'Comedy','comedy',3),(f,'Live cameras','live-cameras',4);
 end if;
 return query select m,f,pf.id,mb.session_version from public.sammytv_members mb
 join public.sammytv_families fa on fa.id=mb.family_id
 join public.sammytv_profiles pf on pf.member_id=mb.id and pf.family_id=mb.family_id
 where mb.id=m and mb.family_id=f and mb.active and mb.role='parent' and fa.enabled and pf.enabled
 order by pf.created_at limit 1;
end $$;
alter function public.sammytv_provision_parent(uuid) owner to postgres;
create function public.sammytv_create_pairing(p_family uuid,p_parent uuid,p_digest text)
returns table(created boolean) language plpgsql security invoker set search_path=pg_catalog,public as $$
begin
 perform 1 from public.sammytv_members m join public.sammytv_families f on f.id=m.family_id
 where m.id=p_parent and m.family_id=p_family and m.role='parent' and m.active and f.enabled for update of m;
 if not found then raise exception 'Parent access required'; end if;
 delete from public.sammytv_pairings where family_id=p_family and parent_id=p_parent;
 insert into public.sammytv_pairings(digest,family_id,parent_id) values(p_digest,p_family,p_parent);
 return query select true;
end $$;
create function public.sammytv_redeem_pairing(p_digest text)
returns table(member_id uuid,family_id uuid,profile_id uuid,session_version integer)
language plpgsql security invoker set search_path=pg_catalog,public as $$
declare pairing public.sammytv_pairings; m uuid; p uuid;
begin
 delete from public.sammytv_pairings where digest=p_digest returning * into pairing;
 if not found or pairing.expires_at <= now() then return; end if;
 if not exists(select 1 from public.sammytv_members mb join public.sammytv_families f on f.id=mb.family_id
 where mb.id=pairing.parent_id and mb.family_id=pairing.family_id and mb.active and mb.role='parent' and f.enabled) then return; end if;
 insert into public.sammytv_members(family_id,role) values(pairing.family_id,'viewer') returning id into m;
 insert into public.sammytv_profiles(family_id,member_id,nickname) values(pairing.family_id,m,'Viewer') returning id into p;
 return query select m,pairing.family_id,p,1;
end $$;
alter table public.sammytv_parent_identities enable row level security;
alter table public.sammytv_parent_identities force row level security;
alter table public.sammytv_pairings enable row level security;
alter table public.sammytv_pairings force row level security;
revoke all on public.sammytv_parent_identities,public.sammytv_pairings from public,anon,authenticated;
grant select,insert,update,delete on public.sammytv_parent_identities,public.sammytv_pairings to service_role;
revoke all on function public.sammytv_provision_parent(uuid),public.sammytv_create_pairing(uuid,uuid,text),public.sammytv_redeem_pairing(text) from public,anon,authenticated;
grant execute on function public.sammytv_provision_parent(uuid),public.sammytv_create_pairing(uuid,uuid,text),public.sammytv_redeem_pairing(text) to service_role;
commit;
