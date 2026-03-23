# n8n Workflows

This folder contains starter workflow exports for the lower-scale backend path.

## Recommended n8n flows

1. `source_sync.json`
   - Triggers a registered source sync by calling `POST /api/sources/{source_id}/sync`.
   - Works well with schedules, button clicks, or upstream triggers.
   - Keeps connector logic, scoring, and `OpenAI GPT` usage in the FastAPI backend instead of duplicating it in n8n.

2. `excel_import.json`
   - Exposes a webhook entrypoint for Excel-triggered imports.
   - Calls the FastAPI endpoint at `POST /api/imports/excel`.
   - Returns a small import summary to the caller.

## Before importing

Set these variables in n8n:

- `API_BASE_URL=http://api:8000`
- `PG_HOST=postgres`
- `PG_PORT=5432`
- `PG_DATABASE=leadscore`
- `PG_USER=postgres`
- `PG_PASSWORD=postgres`

## Why keep n8n thin

Use n8n for orchestration, schedules, and notifications.

Keep the actual scoring, normalization, and LangChain/OpenAI logic in FastAPI so both backend types share one source of truth.
