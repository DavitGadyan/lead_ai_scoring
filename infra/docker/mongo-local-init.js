db = db.getSiblingDB("leadscore_local");

db.contacts.insertMany([
  {
    id: "mg-contact-1",
    full_name: "Grace Cooper",
    email: "grace.cooper@atlas-biomed.example",
    company_name: "Atlas Biomed",
    job_title: "Revenue Operations Lead",
    industry: "Healthcare",
    country: "USA",
    notes: "Requested CRM and ERP summary"
  },
  {
    id: "mg-contact-2",
    full_name: "Henry Foster",
    email: "henry.foster@oakline-energy.example",
    company_name: "Oakline Energy",
    job_title: "Sales Director",
    industry: "Energy",
    country: "Canada",
    notes: "Needs contact ownership visibility"
  },
  {
    id: "mg-contact-3",
    full_name: "Isabella Ward",
    email: "isabella.ward@pixelcraft.example",
    company_name: "PixelCraft",
    job_title: "Growth Manager",
    industry: "Software",
    country: "UK",
    notes: "Interested in automation paths"
  },
  {
    id: "mg-contact-4",
    full_name: "Jack Hughes",
    email: "jack.hughes@atlas-biomed.example",
    company_name: "Atlas Biomed",
    job_title: "VP Sales",
    industry: "Healthcare",
    country: "USA",
    notes: "Wants weekly connector digest"
  },
  {
    id: "mg-contact-5",
    full_name: "Ella Bennett",
    email: "ella.bennett@oakline-energy.example",
    company_name: "Oakline Energy",
    job_title: "CRM Administrator",
    industry: "Energy",
    country: "Canada",
    notes: "Validating imported contacts"
  }
]);

db.companies.insertMany([
  {
    id: "mg-comp-1",
    name: "Atlas Biomed",
    domain: "atlas-biomed.example",
    industry: "Healthcare",
    employee_count: 240,
    country: "USA",
    notes: "Local Mongo healthcare company"
  },
  {
    id: "mg-comp-2",
    name: "Oakline Energy",
    domain: "oakline-energy.example",
    industry: "Energy",
    employee_count: 510,
    country: "Canada",
    notes: "Local Mongo energy company"
  },
  {
    id: "mg-comp-3",
    name: "PixelCraft",
    domain: "pixelcraft.example",
    industry: "Software",
    employee_count: 88,
    country: "UK",
    notes: "Local Mongo software company"
  }
]);
