import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { registerServiceWorker } from "@/lib/sw-register";
import { initializeRevenueCat } from "@/lib/revenuecat";

registerServiceWorker();

// Initialize RevenueCat for iOS
initializeRevenueCat().catch((error) => {
  console.error("[Kindred] RevenueCat initialization error:", error);
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
