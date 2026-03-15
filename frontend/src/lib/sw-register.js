export function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker
        .register("/sw.js")
        .then((reg) => {
          console.log("[Kindred] SW registered:", reg.scope);
          // Check for updates every 60s
          setInterval(() => reg.update(), 60_000);
        })
        .catch((err) => console.warn("[Kindred] SW registration failed:", err));
    });
  }
}

let deferredPrompt = null;

export function setupInstallPrompt(onReady) {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    onReady?.(true);
  });
}

export async function triggerInstall() {
  if (!deferredPrompt) return false;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  deferredPrompt = null;
  return outcome === "accepted";
}

export function isStandalone() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}
