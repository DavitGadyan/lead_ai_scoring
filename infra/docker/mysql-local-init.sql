create table if not exists companies (
  id varchar(64) primary key,
  name varchar(255) not null,
  domain varchar(255),
  industry varchar(255),
  employee_count int,
  country varchar(128),
  notes text
);

create table if not exists contacts (
  id varchar(64) primary key,
  full_name varchar(255) not null,
  email varchar(255) not null,
  company_name varchar(255),
  job_title varchar(255),
  industry varchar(255),
  country varchar(128),
  notes text
);

insert ignore into companies (id, name, domain, industry, employee_count, country, notes) values
  ('my-comp-1', 'Blue Harbor Finance', 'blueharbor-finance.example', 'Financial Services', 410, 'USA', 'Local MySQL finance account'),
  ('my-comp-2', 'Nimbus Retail', 'nimbus-retail.example', 'Retail', 870, 'France', 'Interested in regional lead routing'),
  ('my-comp-3', 'Quantum Freight', 'quantum-freight.example', 'Logistics', 290, 'Singapore', 'Reviewing owner assignment rules');

insert ignore into contacts (id, full_name, email, company_name, job_title, industry, country, notes) values
  ('my-contact-1', 'Daniel Brooks', 'daniel.brooks@blueharbor-finance.example', 'Blue Harbor Finance', 'RevOps Director', 'Financial Services', 'USA', 'Looking for account prioritization'),
  ('my-contact-2', 'Harper Evans', 'harper.evans@nimbus-retail.example', 'Nimbus Retail', 'Head of CRM', 'Retail', 'France', 'Needs company rollup'),
  ('my-contact-3', 'Benjamin Reed', 'benjamin.reed@quantum-freight.example', 'Quantum Freight', 'Commercial Ops Manager', 'Logistics', 'Singapore', 'Asked about stale leads'),
  ('my-contact-4', 'Evelyn Price', 'evelyn.price@blueharbor-finance.example', 'Blue Harbor Finance', 'Marketing Ops Lead', 'Financial Services', 'USA', 'Campaign planning request'),
  ('my-contact-5', 'Lucas Turner', 'lucas.turner@nimbus-retail.example', 'Nimbus Retail', 'Sales Systems Analyst', 'Retail', 'France', 'Comparing connectors');
