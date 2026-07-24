-- Creation lifecycle: database-backed AMP allocation.
-- Apply after the existing Sports Editorial pilot migrations.

create sequence if not exists public.sports_editorial_amp_id_seq
  as bigint
  minvalue 560001
  maxvalue 999999
  start with 560001;

alter sequence public.sports_editorial_amp_id_seq
  minvalue 560001
  maxvalue 999999;

do $$
declare
  v_existing_max bigint;
begin
  select max(amp_id::bigint)
    into v_existing_max
  from public.sports_editorial_submissions
  where amp_id ~ '^[0-9]{6}$';

  if v_existing_max is null or v_existing_max < 560001 then
    perform setval('public.sports_editorial_amp_id_seq', 560001, false);
  else
    perform setval('public.sports_editorial_amp_id_seq', v_existing_max, true);
  end if;
end $$;

alter table public.sports_editorial_submissions
  alter column amp_id set default
    lpad(nextval('public.sports_editorial_amp_id_seq')::text, 6, '0');

create unique index if not exists sports_editorial_submissions_amp_id_key
  on public.sports_editorial_submissions (amp_id)
  where amp_id is not null and amp_id <> '';

comment on sequence public.sports_editorial_amp_id_seq is
  'Atomic six-digit AMP ID allocator. Keep application allocation isolated because AMP may change the format.';

grant usage, select on sequence public.sports_editorial_amp_id_seq to service_role;
