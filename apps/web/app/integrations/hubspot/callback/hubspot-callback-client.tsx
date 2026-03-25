"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

const HUBSPOT_OAUTH_MESSAGE = "leadscore:hubspot-oauth";

export function HubSpotCallbackClient() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const code = searchParams.get("code");
    const error = searchParams.get("error") ?? searchParams.get("error_description");

    if (window.opener) {
      window.opener.postMessage(
        {
          type: HUBSPOT_OAUTH_MESSAGE,
          code,
          error
        },
        window.location.origin
      );
      window.close();
    }
  }, [searchParams]);

  return (
    <main className="page">
      <section className="card">
        <h1 className="title">HubSpot OAuth Callback</h1>
        <p className="muted">
          Completing authentication. If this window does not close automatically, return to the main app and retry the
          connector flow.
        </p>
      </section>
    </main>
  );
}
