-- Trade Ledger pilot. Isolated from every Sports Editorial table.
-- Run in the Supabase SQL Editor before enabling the production workspace.
create extension if not exists pgcrypto;

create table if not exists public.trade_ledger_transactions (
  id uuid primary key default gen_random_uuid(),
  ledger_id text not null,
  kind text not null check (kind in ('sale', 'purchase')),
  transaction_date date not null,
  contact text not null default '',
  reference text not null default '',
  description text not null,
  category text not null,
  amount numeric(12,2) not null check (amount >= 0),
  cis_deduction numeric(12,2) not null default 0 check (cis_deduction >= 0 and cis_deduction <= amount),
  received_amount numeric(12,2) not null default 0 check (received_amount >= 0),
  payment_method text not null default '',
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists trade_ledger_transactions_ledger_date_idx
  on public.trade_ledger_transactions (ledger_id, transaction_date desc, created_at desc);

alter table public.trade_ledger_transactions enable row level security;
-- The Flask server uses the service-role key and enforces access. No anon policy is created.
grant usage on schema public to service_role;
grant select, insert, update, delete on public.trade_ledger_transactions to service_role;
