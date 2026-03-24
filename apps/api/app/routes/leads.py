import json
import secrets

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse

from ..oauth import (
    build_hubspot_authorize_url,
    exchange_hubspot_code,
    exchange_zoho_code,
    prepare_zoho_authorize,
    resolve_zoho_authorize_credentials,
    zoho_token_accounts_host,
)
from ..llm import build_workspace_chat_response, generate_workspace_chat_reply
from ..memory import (
    append_workspace_conversation,
    get_workspace_memory,
    ingest_connector_preview,
    save_workspace_memory,
)
from ..schemas import (
    HubSpotAuthorizeRequest,
    HubSpotAuthorizeResponse,
    HubSpotBrowseRequest,
    HubSpotBrowseResponse,
    HubSpotExchangeRequest,
    HubSpotTokenResponse,
    HubSpotPreviewResponse,
    ImportResult,
    LeadBatchIn,
    LeadCanonical,
    LeadScoreOut,
    LeadScoreRecord,
    PostgresSyncRequest,
    ProviderDefinition,
    SourceIn,
    SourceRecord,
    SourceSyncResult,
    SourceTestResult,
    WorkspaceChatRequest,
    WorkspaceChatResponse,
    WorkspaceConnectorPreviewIngestRequest,
    WorkspaceMemoryState,
    WorkspaceMemoryUpsertRequest,
    ZohoAuthorizeRequest,
    ZohoAuthorizeResponse,
)
from ..zoho_oauth_state import pop_zoho_oauth_pending
from ..services import (
    build_import_result,
    create_source,
    browse_hubspot,
    list_provider_definitions,
    list_sources,
    list_recent_scores,
    parse_excel,
    parse_postgres_sync,
    persist_batch,
    persist_lead_and_score,
    preview_hubspot_source,
    sync_source,
    test_source,
)

router = APIRouter(prefix="/api", tags=["lead-scoring"])

ZOHO_OAUTH_MESSAGE_TYPE = "leadscore:zoho-oauth"


@router.post("/score/lead", response_model=LeadScoreOut)
def score_single_lead(payload: LeadCanonical) -> LeadScoreOut:
    return persist_lead_and_score(payload)


@router.post("/score/batch", response_model=list[LeadScoreOut])
def score_batch(payload: LeadBatchIn) -> list[LeadScoreOut]:
    return persist_batch(payload.leads)


@router.post("/oauth/hubspot/authorize", response_model=HubSpotAuthorizeResponse)
def create_hubspot_authorize_url(payload: HubSpotAuthorizeRequest) -> HubSpotAuthorizeResponse:
    authorize_url, state = build_hubspot_authorize_url(
        client_id=payload.client_id,
        redirect_uri=payload.redirect_uri,
        scope=payload.scope,
        optional_scope=payload.optional_scope,
    )
    return HubSpotAuthorizeResponse(authorize_url=authorize_url, state=state)


@router.post("/oauth/hubspot/exchange", response_model=HubSpotTokenResponse)
def exchange_hubspot_oauth_code(payload: HubSpotExchangeRequest) -> HubSpotTokenResponse:
    try:
        return exchange_hubspot_code(
            client_id=payload.client_id,
            client_secret=payload.client_secret,
            redirect_uri=payload.redirect_uri,
            code=payload.code,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/oauth/zoho/authorize", response_model=ZohoAuthorizeResponse)
def zoho_oauth_authorize(payload: ZohoAuthorizeRequest) -> ZohoAuthorizeResponse:
    client_id, client_secret, accounts_host, redirect_uri = resolve_zoho_authorize_credentials(
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        redirect_uri=payload.redirect_uri,
        accounts_host=payload.zoho_accounts_host,
    )
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="Zoho client_id and client_secret are required (Connect form or ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET in API .env).",
        )
    if not redirect_uri:
        raise HTTPException(
            status_code=400,
            detail="Zoho redirect_uri is required (Connect form or ZOHO_REDIRECT_URI in API .env, e.g. http://localhost:8000/api/oauth/zoho/callback).",
        )
    state = secrets.token_urlsafe(24)
    authorize_url = prepare_zoho_authorize(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=payload.scope.strip(),
        accounts_host=accounts_host,
        state=state,
    )
    return ZohoAuthorizeResponse(authorize_url=authorize_url, state=state)


@router.get("/oauth/zoho/callback", response_class=HTMLResponse)
def zoho_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    accounts_server: str | None = Query(None, alias="accounts-server"),
) -> HTMLResponse:
    err = error or error_description
    if err:
        payload = json.dumps({"type": ZOHO_OAUTH_MESSAGE_TYPE, "error": err})
        return HTMLResponse(
            f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Zoho OAuth</title></head><body>
<script>
if (window.opener) {{
  window.opener.postMessage({payload}, "*");
}}
window.close();
</script>
<p>Authorization was denied. You can close this window.</p>
</body></html>"""
        )

    pending = pop_zoho_oauth_pending(state or "")
    if not pending or not code:
        return HTMLResponse(
            "<!DOCTYPE html><html><body><p>Invalid or expired OAuth state. Close this window and start "
            "Zoho OAuth again from the app.</p></body></html>",
            status_code=400,
        )

    token_host = zoho_token_accounts_host(
        callback_accounts_server=accounts_server,
        pending_host=pending.accounts_host,
    )
    try:
        tokens = exchange_zoho_code(
            client_id=pending.client_id,
            client_secret=pending.client_secret,
            redirect_uri=pending.redirect_uri,
            code=code,
            accounts_host=token_host,
        )
    except Exception as exc:
        payload = json.dumps({"type": ZOHO_OAUTH_MESSAGE_TYPE, "error": str(exc)})
        return HTMLResponse(
            f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Zoho OAuth</title></head><body>
<script>
if (window.opener) {{
  window.opener.postMessage({payload}, "*");
}}
window.close();
</script>
<p>Token exchange failed. You can close this window.</p>
</body></html>"""
        )

    api_domain = tokens.api_domain or "https://www.zohoapis.com"
    if api_domain and not str(api_domain).startswith("http"):
        api_domain = f"https://{api_domain}"

    data = {
        "type": ZOHO_OAUTH_MESSAGE_TYPE,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "api_domain": api_domain,
        "zoho_accounts_host": token_host,
        "expires_in": tokens.expires_in,
    }
    payload = json.dumps(data)
    return HTMLResponse(
        f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Zoho OAuth</title></head><body>
<script>
if (window.opener) {{
  window.opener.postMessage({payload}, "*");
}}
window.close();
</script>
<p>Connected to Zoho. You can close this window.</p>
</body></html>"""
    )


@router.post("/hubspot/preview", response_model=HubSpotPreviewResponse)
def preview_hubspot(payload: SourceIn) -> HubSpotPreviewResponse:
    try:
        return preview_hubspot_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/hubspot/browse", response_model=HubSpotBrowseResponse)
def browse_hubspot_records(payload: HubSpotBrowseRequest) -> HubSpotBrowseResponse:
    try:
        return browse_hubspot(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspace-memory/{session_id}", response_model=WorkspaceMemoryState)
def get_workspace_memory_state(session_id: str) -> WorkspaceMemoryState:
    return get_workspace_memory(session_id)


@router.post("/workspace-memory", response_model=WorkspaceMemoryState)
def upsert_workspace_memory(payload: WorkspaceMemoryUpsertRequest) -> WorkspaceMemoryState:
    return save_workspace_memory(payload)


@router.post("/workspace-memory/connector-preview", response_model=WorkspaceMemoryState)
def workspace_memory_connector_preview(payload: WorkspaceConnectorPreviewIngestRequest) -> WorkspaceMemoryState:
    try:
        return ingest_connector_preview(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspace-chat", response_model=WorkspaceChatResponse)
def workspace_chat(payload: WorkspaceChatRequest) -> WorkspaceChatResponse:
    memory = get_workspace_memory(payload.session_id)
    answer = generate_workspace_chat_reply(payload.message, memory)
    updated_memory = append_workspace_conversation(payload, answer)
    response = build_workspace_chat_response(payload.message, updated_memory)
    return response.model_copy(update={"answer": answer, "memory": updated_memory})


@router.post("/sources", response_model=SourceRecord)
def register_source(payload: SourceIn) -> SourceRecord:
    try:
        return create_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sources/test", response_model=SourceTestResult)
def test_registered_source(payload: SourceIn) -> SourceTestResult:
    try:
        return test_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/providers", response_model=list[ProviderDefinition])
def get_provider_catalog() -> list[ProviderDefinition]:
    return list_provider_definitions()


@router.get("/sources", response_model=list[SourceRecord])
def get_sources() -> list[SourceRecord]:
    return list_sources()


@router.post("/sources/{source_id}/sync", response_model=SourceSyncResult)
def sync_registered_source(source_id: str) -> SourceSyncResult:
    try:
        return sync_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/leads", response_model=list[LeadScoreRecord])
def recent_leads() -> list[LeadScoreRecord]:
    return list_recent_scores()


@router.post("/imports/excel", response_model=ImportResult)
async def import_excel(file: UploadFile = File(...)) -> ImportResult:
    content = await file.read()
    leads = parse_excel(content, source_name=file.filename or "excel_upload")
    persist_batch(leads)
    return build_import_result(leads, source_type="excel", source_name=file.filename or "excel_upload")


@router.post("/imports/postgres-sync", response_model=ImportResult)
def import_postgres(payload: PostgresSyncRequest) -> ImportResult:
    leads = parse_postgres_sync(payload)
    persist_batch(leads)
    return build_import_result(leads, source_type="postgres", source_name=payload.source_name)
