import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { registerServiceWorker } from "@/lib/sw-register";
import { initializeRevenueCat } from "@/lib/revenuecat";

registerServiceWorker();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Initialize RevenueCat AFTER first render so it never blocks the UI
setTimeout(() => {
  initializeRevenueCat().catch((error) => {
    console.error("[Kindred] RevenueCat initialization error:", error);
  });
}, 100);
