export async function updateServiceWorker() {
  if (!("serviceWorker" in navigator)) return;

  try {
    // Registrations can be invalidated while a tab remains open (notably in
    // Mobile Safari). Resolve the current registration for every update
    // instead of retaining the object returned when the page first loaded.
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) return;
    await registration.update();
  } catch (err) {
    // A service-worker refresh is opportunistic. Never turn a browser
    // lifecycle race into an unhandled rejection or a user-facing failure.
    console.warn("[Kindred] SW update skipped:", err);
  }
}

export function registerServiceWorker() {
  if (process.env.NODE_ENV !== "production") return;
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker
        .register("/sw.js")
        .then((reg) => {
          console.log("[Kindred] SW registered:", reg.scope);
          // Check for updates every 60s
          setInterval(() => void updateServiceWorker(), 60_000);
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
