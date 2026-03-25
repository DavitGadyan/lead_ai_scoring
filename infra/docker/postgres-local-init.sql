create table if not exists contacts (
  id text primary key,
  full_name text not null,
  email text not null,
  company_name text,
  job_title text,
  industry text,
  country text,
  notes text
);

create table if not exists companies (
  id text primary key,
  name text not null,
  domain text,
  industry text,
  employee_count int,
  country text,
  notes text
);

insert into companies (id, name, domain, industry, employee_count, country, notes) values
  ('pg-comp-1', 'Northwind Health', 'northwind-health.example', 'Healthcare', 280, 'USA', 'Primary healthcare account'),
  ('pg-comp-2', 'Apex Logistics', 'apex-logistics.example', 'Logistics', 640, 'Canada', 'Expanding operations team'),
  ('pg-comp-3', 'BrightPath AI', 'brightpath-ai.example', 'Software', 95, 'UK', 'High-growth AI startup')
on conflict (id) do nothing;

insert into contacts (id, full_name, email, company_name, job_title, industry, country, notes) values
  ('pg-contact-1', 'Ava Patel', 'ava.patel@northwind-health.example', 'Northwind Health', 'VP Operations', 'Healthcare', 'USA', 'Interested in revenue automation'),
  ('pg-contact-2', 'Liam Carter', 'liam.carter@apex-logistics.example', 'Apex Logistics', 'Director of Sales', 'Logistics', 'Canada', 'Needs CRM consolidation'),
  ('pg-contact-3', 'Mia Chen', 'mia.chen@brightpath-ai.example', 'BrightPath AI', 'Revenue Operations Manager', 'Software', 'UK', 'Asked about lead routing'),
  ('pg-contact-4', 'Noah Diaz', 'noah.diaz@northwind-health.example', 'Northwind Health', 'Sales Manager', 'Healthcare', 'USA', 'Wants follow-up workflow'),
  ('pg-contact-5', 'Emma Ross', 'emma.ross@apex-logistics.example', 'Apex Logistics', 'RevOps Analyst', 'Logistics', 'Canada', 'Reviewing contact enrichment')
on conflict (id) do nothing;
