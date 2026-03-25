# LeadScore AI

AI-powered lead scoring platform with two backend operating modes built around `OpenAI GPT`:

1. `n8n + FastAPI` for lower-scale orchestration and quick delivery
2. `Python + FastAPI + LangChain` for application-first development with `Docker`, `Kubernetes`, and `Terraform`

The backend supports automated ingestion from `SQL`, `NoSQL`, `Excel`, and `CSV` sources and stores normalized lead data plus scores in Postgres.

## Main Stack

- `Next.js` frontend dashboard
- `FastAPI` backend
- `LangChain + OpenAI GPT` for smart lead explanations
- `PostgreSQL` as the operational database
- `n8n` for workflow orchestration
- `Docker Compose` for local full-stack runs
- `Kubernetes` and `Terraform` for higher-scale deployment

## Two Backend Types

### Backend Type 1: n8n Setup

Use this when you want faster delivery and lightweight orchestration.

Flow:

- `n8n` triggers schedules or webhooks
- `n8n` calls the FastAPI endpoints
- `FastAPI` normalizes the data and scores the leads
- scores are stored in Postgres
- `n8n` can send notifications or push to CRM tools

Best for:

- MVPs
- lower traffic
- quick automations
- pilot rollouts

### Backend Type 2: Python + FastAPI + LangChain

Use this when you want a stronger custom backend and more scalable deployment.

Flow:

- source connectors load data from SQL, NoSQL, Excel, or CSV
- FastAPI normalizes the source records
- deterministic scoring calculates the numeric result
- `LangChain + OpenAI GPT` generates a smarter explanation and sales recommendation context
- the backend is packaged with Docker and deployed to Kubernetes

Best for:

- production-style systems
- custom business logic
- richer AI orchestration
- future worker/queue scaling

## Project Structure

```text
apps/
  api/                  FastAPI + LangChain backend
  web/                  Next.js frontend
infra/
  docker/               Docker Compose
  terraform/            Terraform for Kubernetes resources
k8s/                    Kubernetes manifests
sql/                    Database schema
workflows/
  n8n/                  n8n workflow templates
```

## Environment Setup

The backend now uses `apps/api/.env`.

Base values:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/leadscore
APP_NAME=LeadScore AI API
ENVIRONMENT=development
DEFAULT_SCORING_PROFILE=default_b2b
INTERNAL_ALERT_EMAIL=sales@leadscore.ai
OPENAI_API_KEY=replace-with-your-openai-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
LLM_ENABLED=true
```

Notes:

- set `OPENAI_API_KEY` to your real OpenAI key
- keep `OPENAI_BASE_URL` empty unless you use an OpenAI-compatible endpoint
- if `LLM_ENABLED=false` or the key is missing, the backend falls back to deterministic non-LLM explanations
- for a VM-friendly local connector stack, run `docker compose -f infra/docker/docker-compose.local-datastores.yml up -d` and use the matching connector URLs from your local environment

## Website Connection Management

The website now includes a dedicated `Sources` page where you can create and manage connectors directly from the UI.

Supported website-managed connectors:

- `Postgres`
- `Supabase`
- `MySQL`
- `MongoDB`
- `Excel`
- `CSV`
- `Zoho CRM` (OAuth: Server-based client)

From the website you can:

- create a connector
- test the connection before saving
- store the connector in the backend
- trigger a sync on demand
- review last sync timestamps

## Backend API

### Health

`GET /health`

### Register a Source

`POST /api/sources`

SQL source request body:

```json
{
  "name": "crm-postgres",
  "source_type": "sql",
  "is_active": true,
  "config": {
    "connection_url": "postgresql+psycopg://user:pass@host:5432/crm",
    "query": "select id, full_name, email, company, title, industry, country, employees, revenue, budget, notes from inbound_leads where processed = false"
  }
}
```

Supabase source request body:

```json
{
  "name": "supabase-leads",
  "source_type": "supabase",
  "is_active": true,
  "config": {
    "connection_url": "postgresql+psycopg://postgres:password@db.your-project.supabase.co:6543/postgres",
    "query": "select id, full_name, email, company, title, industry, country, employees, revenue, budget, notes from public.inbound_leads limit 100"
  }
}
```

MongoDB source request body:

```json
{
  "name": "mongo-leads",
  "source_type": "mongodb",
  "is_active": true,
  "config": {
    "connection_url": "mongodb://localhost:27017",
    "database": "sales",
    "collection": "leads",
    "filter": {
      "processed": false
    }
  }
}
```

Excel source request body:

```json
{
  "name": "excel-drop",
  "source_type": "excel",
  "is_active": true,
  "config": {
    "file_path": "/data/inbound_leads.xlsx",
    "sheet_name": 0
  }
}
```

### Sync a Source

`POST /api/sources/{source_id}/sync`

### List Sources

`GET /api/sources`

### Test a Source

`POST /api/sources/test`

Use this endpoint from the website before saving a connector.

### Direct Scoring

`POST /api/score/lead`

Useful for testing, manual debugging, and direct app integrations.

## Smart Scoring Design

The scoring engine uses a hybrid approach:

- Python computes numeric sub-scores and the weighted total
- `LangChain + OpenAI GPT` writes the explanation
- Postgres stores the raw import, normalized lead, and final score

Current weights:

```python
WEIGHTS = {
    "fit_score": 0.35,
    "intent_score": 0.25,
    "urgency_score": 0.15,
    "budget_score": 0.15,
    "authority_score": 0.10,
}
```

This keeps the system auditable while still making the output smarter than simple rules.

## Run the Python + FastAPI + LangChain Backend

### Local backend only

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd apps/web
touch .env.local
npm install
npm run dev
```

Then open:

- `http://localhost:3000`
- go to the `Sources` page in the top navigation
- create a connector for `Postgres`, `Supabase`, `MySQL`, `MongoDB`, `Excel`, or `CSV`

### Full stack with Docker

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

This starts:

- frontend on `http://localhost:3000`
- API on `http://localhost:8000`
- n8n on `http://localhost:5678`
- Postgres on `localhost:5432`

## n8n Setup Instructions

Starter files live in `workflows/n8n`.

Recommended process:

1. Start the stack with Docker Compose
2. Open `http://localhost:5678`
3. Set environment variables in n8n:
   - `API_BASE_URL=http://api:8000`
   - `SOURCE_ID=<your-source-id>`
4. Register a source using the FastAPI backend
5. Import `workflows/n8n/source_sync.json`
6. Run it on a schedule to trigger `POST /api/sources/{source_id}/sync`
7. Add Slack, email, HubSpot, or CRM nodes after the sync step

Use `workflows/n8n/excel_import.json` if you want a webhook-driven file import path.

## Docker Support

The main local stack is defined in `infra/docker/docker-compose.yml`.

Important detail:

- the API service reads `apps/api/.env`
- Docker overrides `DATABASE_URL` to use the containerized Postgres service
- your `OPENAI_API_KEY` still comes from `apps/api/.env`

## Kubernetes Support

Apply the manifests:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/web-deployment.yaml
kubectl apply -f k8s/web-service.yaml
kubectl apply -f k8s/network-policy.yaml
kubectl apply -f k8s/api-hpa.yaml
kubectl apply -f k8s/ingress.yaml
```

Create the runtime secret first:

```bash
kubectl -n leadscore create secret generic leadscore-secrets \
  --from-literal=DATABASE_URL='postgresql://user:pass@host:5432/leadscore' \
  --from-literal=OPENAI_API_KEY='your-openai-key' \
  --from-literal=OPENAI_MODEL='gpt-4o-mini' \
  --from-literal=OPENAI_BASE_URL=''
```

The API deployment is already wired to read:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`
- `LLM_ENABLED`

## Terraform Support

Terraform files live in `infra/terraform`.

Terraform run:

```bash
cd infra/terraform
terraform init
terraform apply \
  -var="database_url=postgresql://user:pass@host:5432/leadscore" \
  -var="openai_api_key=your-openai-key" \
  -var="openai_model=gpt-4o-mini"
```

Terraform creates:

- namespace
- runtime secret
- API deployment and service
- web deployment and service

## Supported Input Sources

### SQL

- `postgres`
- `mysql`
- `sqlite`
- generic `sql`

### NoSQL

- `mongodb`
- generic `nosql`

### Files

- `excel`
- `csv`

The backend auto-maps common source columns like `title`, `employees`, `revenue`, and `budget` into the canonical lead schema.

## Suggested Next Steps

- add background workers for very large imports
- add queue-based scoring jobs for heavy concurrency
- add authentication and team management
- add CRM webhooks for Salesforce or HubSpot
- add pgvector for similarity-based lead enrichment
