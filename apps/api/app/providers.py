from .schemas import ProviderDefinition, ProviderField


PROVIDERS: list[ProviderDefinition] = [
    ProviderDefinition(
        key="hubspot",
        label="HubSpot",
        category="crm",
        description="Connect HubSpot with OAuth using client ID and client secret, then read contacts or lead-like records.",
        recommended_order=1,
        fields=[
            ProviderField(key="client_id", label="Client ID", required=True, secret=False),
            ProviderField(key="client_secret", label="Client Secret", required=True, secret=True),
            ProviderField(
                key="redirect_uri",
                label="Redirect URI",
                required=True,
                placeholder="http://localhost:3000/integrations/hubspot/callback",
                help_text="This must match the redirect URL configured in your HubSpot app.",
            ),
            ProviderField(key="object_name", label="Object Name", placeholder="contacts", help_text="Usually contacts."),
            ProviderField(key="params", label="Query Params JSON", kind="json", placeholder='{"limit": 100}')
        ],
    ),
    ProviderDefinition(
        key="salesforce",
        label="Salesforce",
        category="crm",
        description="Query lead or contact objects from Salesforce using SOQL.",
        recommended_order=2,
        fields=[
            ProviderField(key="base_url", label="Instance URL", required=True, placeholder="https://your-instance.my.salesforce.com"),
            ProviderField(key="access_token", label="Access Token", required=True, secret=True),
            ProviderField(key="query", label="SOQL Query", required=True, kind="textarea", placeholder="SELECT Id, Name, Company, Email, Title, LeadSource FROM Lead LIMIT 100"),
        ],
    ),
    ProviderDefinition(
        key="dynamics365",
        label="Dynamics 365 Sales",
        category="crm",
        description="Read leads from Microsoft Dynamics 365 Sales via the OData API.",
        recommended_order=3,
        fields=[
            ProviderField(key="base_url", label="Environment URL", required=True, placeholder="https://your-org.crm.dynamics.com"),
            ProviderField(key="access_token", label="Access Token", required=True, secret=True),
            ProviderField(key="object_name", label="Entity Name", placeholder="leads"),
            ProviderField(key="params", label="Query Params JSON", kind="json", placeholder='{"$top": 100}')
        ],
    ),
    ProviderDefinition(
        key="zoho",
        label="Zoho CRM",
        category="crm",
        description="Connect with Zoho OAuth (Server-based client). Tokens and API domain are filled after you authorize.",
        recommended_order=4,
        fields=[
            ProviderField(
                key="client_id",
                label="Client ID",
                required=False,
                secret=False,
                help_text="Optional if ZOHO_CLIENT_ID is set in the API .env file.",
            ),
            ProviderField(
                key="client_secret",
                label="Client Secret",
                required=False,
                secret=True,
                help_text="Optional if ZOHO_CLIENT_SECRET is set in the API .env file.",
            ),
            ProviderField(
                key="redirect_uri",
                label="Authorized Redirect URI",
                required=True,
                placeholder="http://localhost:8000/api/oauth/zoho/callback",
                help_text="Must match exactly what you registered in Zoho API Console (your backend callback URL).",
            ),
            ProviderField(
                key="zoho_accounts_host",
                label="Zoho accounts host",
                placeholder="accounts.zoho.com",
                help_text="Use accounts.zoho.eu, accounts.zoho.in, etc. if your org is in another data center.",
            ),
            ProviderField(
                key="oauth_scope",
                label="OAuth scopes (space-separated)",
                kind="textarea",
                placeholder="ZohoCRM.modules.leads.READ ZohoCRM.modules.contacts.READ",
                help_text="Requested during Connect Zoho CRM. Add .WRITE scopes only if you need to update records.",
            ),
            ProviderField(key="object_name", label="Module", placeholder="Leads", help_text="CRM module to sync, e.g. Leads or Contacts."),
            ProviderField(key="params", label="Query Params JSON", kind="json", placeholder='{"per_page": 100}'),
        ],
    ),
    ProviderDefinition(
        key="pipedrive",
        label="Pipedrive",
        category="crm",
        description="Read lead or person data from Pipedrive.",
        recommended_order=5,
        fields=[
            ProviderField(key="base_url", label="API Base URL", placeholder="https://your-company.pipedrive.com/api/v1"),
            ProviderField(key="api_key", label="API Token", required=True, secret=True),
            ProviderField(key="object_name", label="Resource", placeholder="leads"),
        ],
    ),
    ProviderDefinition(
        key="freshsales",
        label="Freshsales",
        category="crm",
        description="Read lead records from Freshsales CRM.",
        recommended_order=6,
        fields=[
            ProviderField(key="base_url", label="API Base URL", required=True, placeholder="https://your-domain.myfreshworks.com/crm/sales/api"),
            ProviderField(key="api_key", label="API Key", required=True, secret=True),
            ProviderField(key="object_name", label="Resource", placeholder="leads"),
        ],
    ),
    ProviderDefinition(
        key="mondaycrm",
        label="monday CRM",
        category="crm",
        description="Query lead-related items from monday CRM using GraphQL.",
        recommended_order=7,
        fields=[
            ProviderField(key="access_token", label="API Token", required=True, secret=True),
            ProviderField(key="query", label="GraphQL Query", required=True, kind="textarea", placeholder="{ boards(ids: 123){ items_page(limit: 100){ items { id name column_values { text }}}}}"),
        ],
    ),
    ProviderDefinition(
        key="odoo",
        label="Odoo CRM",
        category="crm",
        description="Read CRM leads from Odoo JSON-RPC or REST proxy endpoints.",
        recommended_order=8,
        fields=[
            ProviderField(key="base_url", label="Base URL", required=True, placeholder="https://odoo.example.com"),
            ProviderField(key="api_key", label="API Key or Password", required=True, secret=True),
            ProviderField(key="client_id", label="Database/User", placeholder="db-or-user"),
            ProviderField(key="object_name", label="Model", placeholder="crm.lead"),
        ],
    ),
    ProviderDefinition(
        key="netsuite",
        label="Oracle NetSuite CRM",
        category="enterprise",
        description="Read lead records from NetSuite REST APIs.",
        recommended_order=9,
        fields=[
            ProviderField(key="base_url", label="Account Base URL", required=True),
            ProviderField(key="access_token", label="Access Token", required=True, secret=True),
            ProviderField(key="object_name", label="Record Type", placeholder="lead"),
        ],
    ),
    ProviderDefinition(
        key="oracle_sales",
        label="Oracle Sales",
        category="enterprise",
        description="Read lead and prospect records from Oracle Sales APIs.",
        recommended_order=10,
        fields=[
            ProviderField(key="base_url", label="API Base URL", required=True),
            ProviderField(key="access_token", label="Access Token", required=True, secret=True),
            ProviderField(key="object_name", label="Resource", placeholder="leads"),
        ],
    ),
    ProviderDefinition(
        key="sap_sales_cloud",
        label="SAP Sales Cloud",
        category="enterprise",
        description="Read lead and opportunity records from SAP Sales Cloud.",
        recommended_order=11,
        fields=[
            ProviderField(key="base_url", label="API Base URL", required=True),
            ProviderField(key="access_token", label="Access Token", required=True, secret=True),
            ProviderField(key="object_name", label="Resource", placeholder="LeadCollection"),
        ],
    ),
    ProviderDefinition(
        key="postgres",
        label="Postgres",
        category="database",
        description="Read lead rows directly from Postgres.",
        recommended_order=12,
        fields=[
            ProviderField(key="connection_url", label="Connection URL", required=True, secret=True),
            ProviderField(key="query", label="SQL Query", required=True, kind="textarea"),
        ],
    ),
    ProviderDefinition(
        key="supabase",
        label="Supabase",
        category="database",
        description="Read lead rows from Supabase Postgres.",
        recommended_order=13,
        fields=[
            ProviderField(key="connection_url", label="Connection URL", required=True, secret=True),
            ProviderField(key="query", label="SQL Query", required=True, kind="textarea"),
        ],
    ),
    ProviderDefinition(
        key="mysql",
        label="MySQL",
        category="database",
        description="Read lead rows directly from MySQL.",
        recommended_order=14,
        fields=[
            ProviderField(key="connection_url", label="Connection URL", required=True, secret=True),
            ProviderField(key="query", label="SQL Query", required=True, kind="textarea"),
        ],
    ),
    ProviderDefinition(
        key="mongodb",
        label="MongoDB",
        category="database",
        description="Read lead documents from MongoDB collections.",
        recommended_order=15,
        fields=[
            ProviderField(key="connection_url", label="Connection URL", required=True, secret=True),
            ProviderField(key="database", label="Database", required=True),
            ProviderField(key="collection", label="Collection", required=True),
            ProviderField(key="filter", label="Filter JSON", kind="json", placeholder='{"processed": false}')
        ],
    ),
    ProviderDefinition(
        key="excel",
        label="Excel File",
        category="file",
        description="Read lead rows from Excel files available to the backend.",
        recommended_order=16,
        fields=[
            ProviderField(key="file_path", label="File Path", required=True),
            ProviderField(key="sheet_name", label="Sheet Name / Index")
        ],
    ),
    ProviderDefinition(
        key="csv",
        label="CSV File",
        category="file",
        description="Read lead rows from CSV files available to the backend.",
        recommended_order=17,
        fields=[
            ProviderField(key="file_path", label="File Path", required=True)
        ],
    ),
]
