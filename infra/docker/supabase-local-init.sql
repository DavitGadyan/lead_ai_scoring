create schema if not exists public;

create table if not exists public.contacts (
  id text primary key,
  full_name text not null,
  email text not null,
  company_name text,
  job_title text,
  industry text,
  country text,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.companies (
  id text primary key,
  name text not null,
  domain text,
  industry text,
  employee_count int,
  country text,
  notes text,
  created_at timestamptz not null default now()
);

insert into public.companies (id, name, domain, industry, employee_count, country, notes) values
  ('sb-comp-1', 'Helio Care', 'helio-care.example', 'Healthcare', 320, 'USA', 'Local Supabase healthcare company'),
  ('sb-comp-2', 'Vertex Commerce', 'vertex-commerce.example', 'Retail', 540, 'Germany', 'European commerce account'),
  ('sb-comp-3', 'Signal Works', 'signal-works.example', 'Software', 120, 'Australia', 'Evaluating cross-CRM reporting')
on conflict (id) do nothing;

insert into public.contacts (id, full_name, email, company_name, job_title, industry, country, notes) values
  ('sb-contact-1', 'Sophia Miller', 'sophia.miller@helio-care.example', 'Helio Care', 'VP Growth', 'Healthcare', 'USA', 'Requested nurture campaign'),
  ('sb-contact-2', 'Ethan Walker', 'ethan.walker@vertex-commerce.example', 'Vertex Commerce', 'Head of Partnerships', 'Retail', 'Germany', 'Asked about account scoring'),
  ('sb-contact-3', 'Olivia Scott', 'olivia.scott@signal-works.example', 'Signal Works', 'Operations Lead', 'Software', 'Australia', 'Wants connector summary'),
  ('sb-contact-4', 'James Lee', 'james.lee@helio-care.example', 'Helio Care', 'Sales Ops Manager', 'Healthcare', 'USA', 'Follow-up reminder workflow'),
  ('sb-contact-5', 'Charlotte Young', 'charlotte.young@vertex-commerce.example', 'Vertex Commerce', 'CRM Admin', 'Retail', 'Germany', 'Asked about source dedupe')
on conflict (id) do nothing;
