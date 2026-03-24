# Zoho CRM integration (OAuth)

This app connects to **Zoho CRM** using a **Server-based** OAuth client. This path is **separate from HubSpot**: there are no Zoho-specific “Load contacts” buttons; use **Test connection** and **Save source** after OAuth.
 The browser opens Zoho’s consent screen; after you approve, Zoho redirects to **your API** at `/api/oauth/zoho/callback`, which exchanges the code for tokens and posts them back to the Connect Systems UI.

## 1. Zoho API Console

1. Create a client with **Client type: Server-based Applications**.
2. **Homepage URL**: your product URL (e.g. `https://yourdomain.com`).
3. **Authorized Redirect URI**: must match **exactly** what you use in LeadScore (see below).
4. Create the client and copy **Client ID** and **Client Secret**.

### Redirect URI examples

- Local API: `http://localhost:8000/api/oauth/zoho/callback`
- Production: `https://<your-api-host>/api/oauth/zoho/callback`

The frontend defaults to `{NEXT_PUBLIC_API_BASE_URL}/api/oauth/zoho/callback` if you leave the Redirect URI field empty when clicking **Connect Zoho CRM**.

## 2. Scopes

Default scopes requested by the UI:

`ZohoCRM.modules.leads.READ ZohoCRM.modules.contacts.READ`

You can change them in **OAuth scopes (space-separated)** on the Zoho CRM form. Add `...WRITE` only if you need to update CRM records from this app.

## 3. Data center

If your org is not on `zoho.com`, set **Zoho accounts host** to the correct accounts hostname, for example:

| Region   | Host                 |
|----------|----------------------|
| US       | `accounts.zoho.com`  |
| EU       | `accounts.zoho.eu`   |
| India    | `accounts.zoho.in`   |
| Australia| `accounts.zoho.com.au` |

## 4. Optional: API `.env` (recommended for secrets)

In `apps/api/.env` you can set:

| Variable | Purpose |
|----------|---------|
| `ZOHO_CLIENT_ID` | Client ID from Zoho (form can be left blank) |
| `ZOHO_CLIENT_SECRET` | Client secret (never sent from the browser if omitted in the form) |
| `ZOHO_ACCOUNTS_HOST` | e.g. `accounts.zoho.com` or `accounts.zoho.eu` |
| `ZOHO_REDIRECT_URI` | Exact callback URL, e.g. `http://localhost:8000/api/oauth/zoho/callback` |

If these are set, **Connect Zoho CRM** still works with empty Client ID / Secret fields. Values in the form override `.env` when provided. Token refresh during sync uses saved source config first, then falls back to `.env` for client id/secret.

## 5. In LeadScore (GUI)

1. Open **Connect Systems**.
2. Choose **Zoho CRM** as the source type.
3. Paste **Client ID** / **Client Secret** in the form *or* rely on `ZOHO_CLIENT_ID` / `ZOHO_CLIENT_SECRET` in `apps/api/.env`. Set **Authorized Redirect URI** / **Zoho accounts host** if not using `.env` defaults.
4. Click **Connect Zoho CRM** and complete login/consent in the popup.
5. Click **Test connection** — this loads normalized preview rows into **workspace memory** (Redis when configured) so the **Talk to AI** tab can answer questions about your contacts/leads.
6. **Save source** (requires Postgres with `leadscore` DB for persistence).
7. Use **Sync now** on the saved connector when you want to import leads into the scoring database.

## 6. `invalid_code` on token exchange

If you see **Zoho token error: invalid_code**, Zoho rejected the authorization `code`. Common causes:

1. **Token URL data center** — Zoho adds `accounts-server=https://accounts.zoho.eu` (etc.) to the callback for EU and other regions. The code must be exchanged at **that** host’s `/oauth/v2/token`, not `accounts.zoho.com`. LeadScore reads `accounts-server` from the callback and uses it automatically; you can still set **Zoho accounts host** to `accounts.zoho.eu` in the form or `.env` so the authorize URL starts on the correct DC.
2. **Redirect URI mismatch** — The `redirect_uri` sent to `/oauth/v2/token` must be **byte-for-byte identical** to the one in the authorize URL and in Zoho API Console (including `http` vs `https`, trailing slash, port `8000`, path).
3. **Code already used or expired** — The code is **one-time** and short-lived. Don’t refresh the callback page; click **Connect Zoho CRM** again and complete login once.

## 7. Technical notes

- OAuth **state** and **client_secret** are held in server memory for ~10 minutes during the authorize step only (restart clears pending states).
- Saved sources store `access_token`, `refresh_token`, `base_url` (CRM API domain from Zoho), `zoho_accounts_host`, `client_id`, and `client_secret` for refresh.
- **Module** (e.g. `Leads` or `Contacts`) controls which CRM module is read on test/sync.

