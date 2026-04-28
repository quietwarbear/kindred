import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

// Public web fallback for https://heykindred.org/invite/:code
//
// On Android with verified App Links, the OS opens the app directly and
// this component never renders. Same for iOS with Universal Links once
// AASA is published. For everything else (desktop, browser-shared link,
// app not installed), this page tries the custom-scheme deep link
// (kindred://invite/:code) and falls back to store buttons.

const PLAY_STORE_URL =
  "https://play.google.com/store/apps/details?id=com.ubuntumarket.kindred";
const APP_STORE_URL =
  "https://apps.apple.com/app/heykindred/id6760608478";

export const InviteLandingPage = () => {
  const { code } = useParams();
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    if (!code) return;
    // Auto-attempt the custom scheme — if the app is installed, it opens.
    // If not, this is a no-op and the user sees the store buttons below.
    const t = setTimeout(() => {
      window.location.href = `kindred://invite/${code}`;
      setAttempted(true);
    }, 250);
    return () => clearTimeout(t);
  }, [code]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-amber-50 to-rose-50 px-6 py-16">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl p-8 text-center">
        <p className="text-xs uppercase tracking-[0.2em] text-rose-600 mb-2">heyKindred</p>
        <h1 className="text-3xl font-semibold text-slate-900 mb-3">You're invited</h1>
        <p className="text-slate-600 mb-6">
          Open the heyKindred app to accept your invite
          {code ? ` (code: ${code.toUpperCase()})` : ""}.
        </p>

        {code && (
          <div className="mb-6">
            <a
              href={`kindred://invite/${code}`}
              className="inline-block w-full rounded-full bg-rose-600 px-6 py-3 text-white font-semibold hover:bg-rose-700 transition"
            >
              Open in app
            </a>
            {attempted && (
              <p className="mt-3 text-xs text-slate-500">
                Didn't open? Install the app below, then tap this link again.
              </p>
            )}
          </div>
        )}

        <div className="space-y-3">
          <a
            href={PLAY_STORE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full rounded-full border border-slate-300 px-6 py-3 text-slate-900 font-medium hover:bg-slate-50 transition"
          >
            Get it on Google Play
          </a>
          <a
            href={APP_STORE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full rounded-full border border-slate-300 px-6 py-3 text-slate-900 font-medium hover:bg-slate-50 transition"
          >
            Download on the App Store
          </a>
        </div>
      </div>
    </div>
  );
};

export default InviteLandingPage;
