-- Add historical classification-depth provenance to existing FIS imports.
-- Run this before deploying application code that writes coverage_scope.

alter table public.sports_editorial_result_imports
  add column if not exists coverage_scope text not null default 'full_classification';

alter table public.sports_editorial_result_imports
  drop constraint if exists sports_editorial_result_imports_coverage_scope_check;

alter table public.sports_editorial_result_imports
  add constraint sports_editorial_result_imports_coverage_scope_check
  check (coverage_scope in ('full_classification','official_top_10','official_top_25','unknown_partial'));

update public.sports_editorial_result_imports
set coverage_scope = case
  when import_status in ('partial', 'failed') then 'unknown_partial'
  when season_code between 1967 and 1978 then 'official_top_10'
  when season_code between 1979 and 1991 then 'official_top_25'
  else 'full_classification'
end
where source_name = 'fis_official_results';

comment on column public.sports_editorial_result_imports.coverage_scope is
  'Depth exposed by the FIS archive: full classification, historical top 10/top 25, or unknown partial.';
