-- Make athletes already present in the local official-results archive available
-- to entity autocomplete. This is local catalogue maintenance; it makes no FIS
-- request and is safe to run more than once.

insert into public.sports_editorial_entities (
  workspace_id,
  entity_type,
  name,
  canonical_id,
  canonical_url,
  country_code,
  metadata
)
select distinct on (result.workspace_id, result.fis_code)
  result.workspace_id,
  'athlete',
  result.athlete_name,
  result.fis_code::text,
  case
    when result.competitor_id is not null then
      'https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid='
      || result.competitor_id::text || '&sectorcode=AL'
    else null
  end,
  result.nation_code,
  jsonb_build_object(
    'competitor_id', result.competitor_id,
    'source_name', 'fis_official_results'
  )
from public.sports_editorial_results result
where result.athlete_name <> ''
order by result.workspace_id, result.fis_code, result.imported_at desc
on conflict (workspace_id, entity_type, canonical_id) do update set
  name = excluded.name,
  canonical_url = coalesce(excluded.canonical_url, public.sports_editorial_entities.canonical_url),
  country_code = excluded.country_code,
  metadata = public.sports_editorial_entities.metadata || excluded.metadata;
