-- Additive range annotations for Sports Editorial entity links.
-- Apply after sports_editorial_pilot.sql. Safe to run more than once.

alter table public.sports_editorial_stat_entities
  add column if not exists mention_start integer,
  add column if not exists mention_end integer;

alter table public.sports_editorial_stat_entities
  drop constraint if exists sports_editorial_stat_entities_mention_range_check;

alter table public.sports_editorial_stat_entities
  add constraint sports_editorial_stat_entities_mention_range_check check (
    (mention_start is null and mention_end is null)
    or (mention_start >= 0 and mention_end > mention_start)
  );

comment on column public.sports_editorial_stat_entities.mention_start is
  'Zero-based start offset in the statistic plain text for this inline entity annotation.';

comment on column public.sports_editorial_stat_entities.mention_end is
  'Exclusive end offset in the statistic plain text for this inline entity annotation.';
