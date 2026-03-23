create extension if not exists pgcrypto;

create table if not exists data_sources (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  source_type text not null,
  config jsonb not null,
  is_active boolean not null default true,
  last_synced_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists lead_raw_imports (
  id uuid primary key default gen_random_uuid(),
  source_type text not null,
  source_name text not null,
  external_id text,
  payload_row jsonb not null,
  imported_at timestamptz not null default now(),
  status text not null default 'pending'
);

create table if not exists leads_normalized (
  id uuid primary key default gen_random_uuid(),
  raw_import_id uuid not null references lead_raw_imports(id) on delete cascade,
  full_name text,
  email text,
  company text,
  job_title text,
  industry text,
  country text,
  employee_count int,
  annual_revenue numeric,
  budget_range text,
  notes text,
  source_name text not null,
  created_at timestamptz not null default now()
);

create table if not exists lead_scores (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references leads_normalized(id) on delete cascade,
  fit_score int not null check (fit_score between 0 and 100),
  intent_score int not null check (intent_score between 0 and 100),
  urgency_score int not null check (urgency_score between 0 and 100),
  budget_score int not null check (budget_score between 0 and 100),
  authority_score int not null check (authority_score between 0 and 100),
  overall_score numeric not null,
  recommended_action text not null,
  explanation text not null,
  scored_at timestamptz not null default now()
);
