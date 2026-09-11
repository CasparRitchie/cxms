-- Allow the editorial sheet to distinguish Mixed (X) from Open (O).
-- Apply to existing Sports Editorial databases before saving Open sheets.
alter table public.sports_editorial_submissions
  drop constraint if exists sports_editorial_submissions_gender_check;

alter table public.sports_editorial_submissions
  add constraint sports_editorial_submissions_gender_check
  check (gender in ('W', 'M', 'X', 'O'));
