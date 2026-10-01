-- Dhaga & Co. Returns Insight: database schema.
-- Run this once in the Supabase SQL editor (or with psql). Safe to re-run.

create extension if not exists pgcrypto;  -- gen_random_uuid() on older Postgres

create table if not exists vendors (
  vendor_id text primary key,
  name text not null,
  city text
);

create table if not exists skus (
  sku_id text primary key,
  vendor_id text references vendors(vendor_id),
  category text check (category in ('womenswear','kidswear','mens')),
  product_name text,
  is_live boolean default true          -- pulled SKUs keep their vendor
);

create table if not exists orders (
  order_id text primary key,
  order_date date not null,
  payment_mode text check (payment_mode in ('cod','prepaid'))
);

create table if not exists order_lines (
  order_line_id text primary key,
  order_id text references orders(order_id),
  sku_id text references skus(sku_id),
  size text,
  quantity int not null default 1
);

create table if not exists returns (
  return_id text primary key,
  order_line_id text,                   -- nullable on purpose: tests the unmatched path
  return_date date not null,
  dropdown_reason text not null,        -- 'Other' for the rows we process
  other_text text,
  human_label text                      -- filled only for the labelled eval subset
);

create table if not exists pipeline_runs (
  run_id uuid primary key default gen_random_uuid(),
  started_at timestamptz default now(),
  finished_at timestamptz,
  status text,                          -- running | done | failed
  model_a_id text, model_b_id text,
  counts jsonb,                         -- processed, junk, unmatched, routed, unclassified
  cost_usd numeric,
  -- Added to the planned schema:
  period_start date,                    -- optional order-date filter the run was started with
  period_end date,
  params jsonb,                         -- thresholds used, so old runs still display consistently
  error text                            -- why a failed run failed (plain text, no stack trace)
);

create table if not exists return_classifications (
  run_id uuid references pipeline_runs(run_id),
  return_id text references returns(return_id),
  status text,                          -- classified | junk | unmatched | unclassified
  reason text, fit_direction text, fit_area text, secondary_reason text,
  confidence numeric, gist_en text,
  model_used text,                      -- A | B | none
  error text,
  primary key (run_id, return_id)
);

create table if not exists vendor_briefs (
  run_id uuid references pipeline_runs(run_id),
  vendor_id text references vendors(vendor_id),
  brief jsonb,
  status text,                          -- ok | rejected_numbers_mismatch | failed
  primary key (run_id, vendor_id)
);

create index if not exists order_lines_sku_idx on order_lines (sku_id);
create index if not exists order_lines_order_idx on order_lines (order_id);
create index if not exists returns_order_line_idx on returns (order_line_id);
create index if not exists pipeline_runs_started_idx on pipeline_runs (started_at desc);

-- Supabase exposes every table in `public` through its REST API to anyone holding the
-- project's publishable key. Row level security with no policies shuts that door.
-- The backend connects as the table owner, which is not subject to these checks.
alter table vendors enable row level security;
alter table skus enable row level security;
alter table orders enable row level security;
alter table order_lines enable row level security;
alter table returns enable row level security;
alter table pipeline_runs enable row level security;
alter table return_classifications enable row level security;
alter table vendor_briefs enable row level security;
