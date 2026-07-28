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
// see real content. Those snapshots are browser-captured rather than React
// server output, so they are replaced with a fresh client tree instead of
// being hydrated as though their markup were an exact SSR match.
if (rootEl.hasChildNodes()) rootEl.innerHTML = "";
ReactDOM.createRoot(rootEl).render(app);

// Initialize RevenueCat AFTER first render so it never blocks the UI.
setTimeout(() => {
  initializeRevenueCat().catch(() => {
    console.error("[Kindred] RevenueCat initialization failed");
  });
}, 100);
