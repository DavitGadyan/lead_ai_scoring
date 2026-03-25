import { Suspense } from "react";

import { HubSpotCallbackClient } from "./hubspot-callback-client";

function HubSpotCallbackFallback() {
  return (
    <main className="page">
      <section className="card">
        <h1 className="title">HubSpot OAuth Callback</h1>
        <p className="muted">Loading...</p>
      </section>
    </main>
  );
}

export default function HubSpotCallbackPage() {
  return (
    <Suspense fallback={<HubSpotCallbackFallback />}>
      <HubSpotCallbackClient />
    </Suspense>
  );
}
