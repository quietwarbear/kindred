import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { API_URL } from "@/lib/api";

// Public, no-account RSVP page for https://heykindred.org/rsvp/:token
// The token is an event invite's uuid4 id. Designed to be elder-friendly:
// large type, few words, three big tap targets, no sign-in required.

const APP_STORE_URL = "https://apps.apple.com/app/heykindred/id6760608478";

const OPTIONS = [
  { value: "going", label: "I'm coming", sub: "Count me in" },
  { value: "maybe", label: "Maybe", sub: "I'm not sure yet" },
  { value: "not-going", label: "Can't make it", sub: "Sorry to miss it" },
];

const formatWhen = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso;
  }
};

export const PublicRSVPPage = () => {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/public/rsvp/${token}`);
      if (!res.ok) throw new Error("not found");
      setData(await res.json());
    } catch {
      setError("We couldn't find this invitation. Ask whoever invited you for a fresh link.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const submit = async (statusValue) => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/public/rsvp/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: statusValue, guests: 0 }),
      });
      if (!res.ok) throw new Error("save failed");
      setData(await res.json());
      setSaved(true);
    } catch {
      setError("Something went wrong saving your reply. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const shell = (children) => (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-amber-50 to-rose-50 px-6 py-16">
      <div className="w-full max-w-md rounded-3xl bg-white shadow-xl p-8 sm:p-10 text-center">
        <p className="text-sm uppercase tracking-[0.2em] text-rose-600 mb-4">heyKindred</p>
        {children}
      </div>
    </div>
  );

  if (loading) {
    return shell(<p className="text-xl text-slate-600">Loading your invitation…</p>);
  }

  if (error && !data) {
    return shell(
      <>
        <h1 className="text-2xl font-semibold text-slate-900 mb-3">Invitation not found</h1>
        <p className="text-lg text-slate-600">{error}</p>
      </>
    );
  }

  const g = data?.gathering || {};
  const current = data?.rsvp_status && data.rsvp_status !== "pending" ? data.rsvp_status : null;

  return shell(
    <>
      {data?.invitee_name ? (
        <p className="text-lg text-slate-500 mb-1">Hello {data.invitee_name},</p>
      ) : null}
      <h1 className="text-3xl font-semibold text-slate-900 mb-2">You're invited</h1>
      {data?.community_name ? (
        <p className="text-base text-rose-700 mb-5">from {data.community_name}</p>
      ) : null}

      <div className="rounded-2xl bg-slate-50 px-5 py-5 mb-7 text-left">
        <p className="text-2xl font-semibold text-slate-900 leading-snug">{g.title}</p>
        {g.start_at ? <p className="mt-2 text-lg text-slate-700">{formatWhen(g.start_at)}</p> : null}
        {g.location ? <p className="mt-1 text-lg text-slate-600">{g.location}</p> : null}
        {g.zoom_link ? (
          <a href={g.zoom_link} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-base font-medium text-rose-600 underline">
            Join link
          </a>
        ) : null}
      </div>

      {saved ? (
        <div className="rounded-2xl bg-emerald-50 px-5 py-5 mb-6">
          <p className="text-xl font-semibold text-emerald-800">
            {current === "going" ? "Wonderful — you're coming!" : current === "maybe" ? "Thanks — we've marked you as maybe." : "Thanks for letting us know."}
          </p>
          <p className="mt-1 text-base text-emerald-700">You can change your answer anytime on this page.</p>
        </div>
      ) : (
        <p className="text-lg text-slate-700 mb-5">Will you be there?</p>
      )}

      <div className="space-y-3">
        {OPTIONS.map((opt) => {
          const active = current === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={saving}
              onClick={() => submit(opt.value)}
              data-testid={`public-rsvp-${opt.value}`}
              className={`block w-full rounded-full px-6 py-4 text-lg font-semibold transition disabled:opacity-60 ${
                active
                  ? "bg-rose-600 text-white"
                  : "border-2 border-slate-200 text-slate-900 hover:border-rose-300 hover:bg-rose-50"
              }`}
            >
              {opt.label}
              <span className={`ml-2 text-sm font-normal ${active ? "text-rose-100" : "text-slate-500"}`}>{opt.sub}</span>
            </button>
          );
        })}
      </div>

      {error ? <p className="mt-4 text-base text-rose-600">{error}</p> : null}

      <p className="mt-8 text-sm text-slate-500">
        Want photos, stories, and the full circle?{" "}
        <a href={APP_STORE_URL} target="_blank" rel="noopener noreferrer" className="font-medium text-rose-600 underline">
          Get the heyKindred app
        </a>
      </p>
    </>
  );
};

export default PublicRSVPPage;
