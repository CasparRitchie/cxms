-- Phase 4b. Shared NPS Me project, after sammytv_moderation.sql.
-- Category management only. No seed data, table grants or video approvals.
begin;
create function public.sammytv_manage_category(
  p_family uuid, p_parent uuid, p_session_version integer,
  p_action text, p_category uuid, p_name text, p_position integer
) returns table(category_id uuid, category_name text, enabled boolean, category_position integer)
language plpgsql security invoker set search_path = pg_catalog as $$
declare current_category public.sammytv_categories; clean_name text; new_slug text; next_position integer;
begin
  perform public.sammytv_require_parent(p_family, p_parent, p_session_version);
  if p_action is null or p_action not in ('create','save','archive','restore') then
    raise exception using errcode='22023', message='Invalid category action';
  end if;
  -- Serialise category edits within the family, including duplicate creation.
  perform pg_advisory_xact_lock(hashtextextended('sammytv:categories:' || p_family::text,0));
  if p_action in ('create','save') then
    clean_name := trim(regexp_replace(p_name, '\s+', ' ', 'g'));
    if clean_name is null or length(clean_name) not between 1 and 60
       or lower(clean_name) in ('all','favourites') or p_name ~ '[[:cntrl:]]'
       or (p_position is not null and p_position not between 0 and 9999) then
      raise exception using errcode='22023', message='Invalid category name or position';
    end if;
  end if;
  if p_action = 'create' then
    select c.* into current_category from public.sammytv_categories c
      where c.family_id=p_family and lower(c.name)=lower(clean_name) for update;
    if found then
      if not current_category.enabled then
        raise exception using errcode='22023', message='Restore the existing archived category';
      end if;
      -- Creating an existing name is idempotent; preserve its order and slug.
    else
      select coalesce(max(c.position),-1)+1 into next_position from public.sammytv_categories c where c.family_id=p_family;
      new_slug := trim(both '-' from regexp_replace(lower(clean_name),'[^a-z0-9]+','-','g'));
      new_slug := coalesce(nullif(new_slug,''),'category') || '-' || substr(gen_random_uuid()::text,1,8);
      insert into public.sammytv_categories as c(family_id,name,slug,position)
        values(p_family,clean_name,new_slug,coalesce(p_position,least(next_position,9999)))
        returning c.* into current_category;
    end if;
  else
    select c.* into current_category from public.sammytv_categories c
      where c.id=p_category and c.family_id=p_family for update;
    if not found then
      raise exception using errcode='42501', message='Category unavailable';
    end if;
    if p_action='save' then
      update public.sammytv_categories c set name=clean_name, position=coalesce(p_position,c.position)
        where c.id=p_category and c.family_id=p_family returning c.* into current_category;
    else
      update public.sammytv_categories c set enabled=(p_action='restore')
        where c.id=p_category and c.family_id=p_family returning c.* into current_category;
    end if;
  end if;
  -- Associations and approval state are untouched by category edits/archiving.
  return query select current_category.id,current_category.name,current_category.enabled,current_category.position;
end;
$$;
revoke all on function public.sammytv_manage_category(uuid,uuid,integer,text,uuid,text,integer) from public,anon,authenticated;
grant execute on function public.sammytv_manage_category(uuid,uuid,integer,text,uuid,text,integer) to service_role;
notify pgrst, 'reload schema';
commit;
