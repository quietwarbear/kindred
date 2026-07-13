import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { registerServiceWorker } from "@/lib/sw-register";
import { initializeRevenueCat } from "@/lib/revenuecat";
import { initAnalytics } from "@/lib/analytics";

registerServiceWorker();
initAnalytics();

const rootEl = document.getElementById("root");
const app = (
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Public routes ship as prerendered HTML (scripts/prerender.js) so crawlers
// see real content. Hydrate the snapshot for anonymous visitors; signed-in
// users get a fresh client render (no flash of the marketing page).
let hasSession = false;
try {
  hasSession = !!localStorage.getItem("gathering-cypher-auth");
} catch (e) { /* storage unavailable */ }

if (rootEl.hasChildNodes() && !hasSession) {
  ReactDOM.hydrateRoot(rootEl, app);
} else {
  if (rootEl.hasChildNodes()) rootEl.innerHTML = "";
  ReactDOM.createRoot(rootEl).render(app);
}

// Initialize RevenueCat AFTER first render so it never blocks the UI
setTimeout(() => {
  initializeRevenueCat().catch((error) => {
    console.error("[Kindred] RevenueCat initialization error:", error);
  });
}, 100);
