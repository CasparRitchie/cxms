# Trade Ledger pilot

Trade Ledger is isolated under `/trade-ledger` and `/workspace/trade-ledger`. It records sales and purchases, presents calendar-quarter summaries, and exports a versioned transaction CSV. It does not call HMRC or Otis.

## Production setup

1. Run `supabase/trade_ledger_pilot.sql` in the configured Supabase project.
2. Set `TRADE_LEDGER_ACCESS_PASSWORD` to a long, unique pilot password in Heroku.
3. Set `TRADE_LEDGER_ID` to a non-guessable identifier for this ledger.
4. Set `TRADE_LEDGER_ENABLED=1`. Set it to `0` for an immediate route-level kill switch.
5. Ensure the existing `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`, and `FLASK_SECRET_KEY` values are configured.

Do not use a shared or personal password. This single-password pilot is for one ledger and should be replaced by individual user accounts before supporting multiple businesses.

## Export boundary

The CSV is a stable Trade Ledger version 1.0 export, not a claimed Otis format. Obtain an official Otis template or a successful redacted sample before adding an Otis-specific adapter. Keep transaction storage independent from that external format.

## HMRC boundary

HMRC sandbox and production API integration are deliberately out of scope. A later phase must add OAuth, fraud-prevention headers, scopes, obligation handling, audit records, sandbox tests, and an explicit production-credentials review without changing the bookkeeping record model.
