import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  Home,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { toast } from "@/components/ui/sonner";

const OPERATION_KEY = "kindred:family-space-activation-operation";

const stableOperationKey = () => {
  const existing = window.sessionStorage.getItem(OPERATION_KEY);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `family-activation:${random}`;
  window.sessionStorage.setItem(OPERATION_KEY, value);
  return value;
};

const ACTION_COPY = {
  activate_family_space: [
    "Choose the name your family will keep",
    "Your reunion has enough verified participation to open the enduring family space.",
  ],
  create_reunion: [
    "Save the first reunion",
    "A persisted reunion is the foundation for this family space.",
  ],
  collect_verified_invitation_evidence: [
    "Let private invitations reach family",
    "An opened invitation, RSVP, or independently verified delivery counts. Copying a link does not.",
  ],
  receive_more_accepted_responses: [
    "Welcome a few more responses",
    "The family space becomes ready after the reunion has meaningful accepted participation.",
  ],
  invite_non_host_participation: [
    "Invite one family contribution",
    "A non-host RSVP, contribution, volunteer choice, or published memory completes readiness.",
  ],
  open_family_home: [
    "Open the family home",
    "This family space is already active and the reunion remains available.",
  ],
  continue_current_family_space: [
    "Continue to the family home",
    "This existing community was not explicitly created as a provisional reunion space.",
  ],
};

const ProgressRow = ({ complete, current, label, target }) => (
  <div className="flex items-center justify-between gap-4 rounded-2xl border border-border/70 bg-background/70 px-4 py-3">
    <div className="flex items-center gap-3">
      <CheckCircle2 className={`h-5 w-5 ${complete ? "text-emerald-600" : "text-muted-foreground"}`} />
      <span className="text-sm font-medium text-foreground">{label}</span>
    </div>
    <span className="text-sm tabular-nums text-muted-foreground">{Math.min(current, target)} / {target}</span>
  </div>
);

export const FamilySpaceActivationPage = ({ onSessionRefresh, session }) => {
  const navigate = useNavigate();
  const [readiness, setReadiness] = useState(null);
  const [familyName, setFamilyName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [unauthorized, setUnauthorized] = useState(false);
  const [success, setSuccess] = useState(false);
  const [online, setOnline] = useState(() => navigator.onLine);
  const viewedRef = useRef(false);

  const load = useCallback(async () => {
    if (!session?.token) return;
    setLoading(true);
    setLoadError("");
    try {
      const payload = await apiRequest("/family-space/activation", {
        token: session.token,
      });
      setReadiness(payload);
    } catch (error) {
      if (error.response?.status === 403) {
        setUnauthorized(true);
      } else {
        setLoadError(
          error.response?.data?.detail?.message
          || error.response?.data?.detail
          || "Family-space readiness could not be loaded."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [session?.token]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const updateOnline = () => setOnline(navigator.onLine);
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
    return () => {
      window.removeEventListener("online", updateOnline);
      window.removeEventListener("offline", updateOnline);
    };
  }, []);

  useEffect(() => {
    if (!readiness || viewedRef.current) return;
    viewedRef.current = true;
    trackReunionEvent("family_space_activation_viewed", {
      source: "family_activation",
      readiness_category: readiness.readiness_status,
      verified_invite_count: readiness.aggregate_counts?.verified_invitations || 0,
      accepted_count: readiness.aggregate_counts?.accepted_responses || 0,
      non_host_participation_count: readiness.aggregate_counts?.non_host_participants || 0,
      elapsed_day_bucket: readiness.elapsed_day_bucket,
    });
  }, [readiness]);

  const action = useMemo(
    () => ACTION_COPY[readiness?.next_action?.code] || ACTION_COPY.continue_current_family_space,
    [readiness?.next_action?.code]
  );

  if (!session?.token) return <Navigate replace to="/login?intent=reunion" />;

  const defer = () => {
    trackReunionEvent("family_space_activation_deferred", {
      source: "family_activation",
      readiness_category: readiness?.readiness_status || "unknown",
      result: "deferred",
    });
    navigate("/home");
  };

  const activate = async (event) => {
    event.preventDefault();
    if (!online) {
      toast.info("Reconnect before activating the family space.");
      return;
    }
    if (!familyName.trim()) {
      toast.error("Choose the family-space name you want to keep.");
      return;
    }
    setBusy(true);
    try {
      await apiRequest("/family-space/activation", {
        method: "POST",
        token: session.token,
        data: {
          family_space_name: familyName,
          expected_revision: readiness.lifecycle_revision,
          idempotency_key: stableOperationKey(),
        },
      });
      window.sessionStorage.removeItem(OPERATION_KEY);
      setSuccess(true);
      trackReunionEvent("family_space_activated", {
        source: "family_activation",
        readiness_category: "ready",
        result: "success",
      });
      await onSessionRefresh?.();
      window.setTimeout(() => navigate("/home"), 700);
    } catch (error) {
      const code = error.response?.data?.detail?.code || "activation_failed";
      if (error.response?.status === 409) {
        window.sessionStorage.removeItem(OPERATION_KEY);
        trackReunionEvent("family_space_activation_conflict", {
          source: "family_activation",
          readiness_category: readiness?.readiness_status || "unknown",
          result: "conflict",
        });
        await load();
        toast.info(
          code === "family_space_already_active"
            ? "This family space is already active."
            : "The family space changed. Review the latest state before trying again."
        );
      } else {
        toast.error(
          error.response?.data?.detail?.message
          || "The family space could not be activated."
        );
      }
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center" aria-busy="true">
        <p className="text-sm text-muted-foreground">Checking family-space readiness…</p>
      </div>
    );
  }

  if (unauthorized) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-5">
        <section className="archival-card max-w-lg text-center" role="alert">
          <LockKeyhole className="mx-auto h-8 w-8 text-primary" />
          <h1 className="mt-4 font-display text-3xl">Organizer access required</h1>
          <p className="mt-3 text-sm text-muted-foreground">Only a host or organizer in this family space can activate it.</p>
          <Button className="mt-5" onClick={() => navigate("/home")} type="button" variant="outline">Return home</Button>
        </section>
      </div>
    );
  }

  if (loadError || !readiness) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-5">
        <section className="archival-card max-w-lg text-center" role="alert">
          <h1 className="font-display text-3xl">Readiness unavailable</h1>
          <p className="mt-3 text-sm text-muted-foreground">{loadError}</p>
          <Button className="mt-5" onClick={load} type="button" variant="outline"><RefreshCw className="mr-2 h-4 w-4" /> Try again</Button>
        </section>
      </div>
    );
  }

  if (success) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-5" data-ph-no-capture="true">
        <section className="archival-card max-w-xl text-center" role="status">
          <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-600" />
          <p className="eyebrow-text mt-5">Family space activated</p>
          <h1 className="mt-3 font-display text-4xl">Your family home is ready.</h1>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">Your reunion, invitations, members, responses, memories, and history are right where you left them.</p>
        </section>
      </div>
    );
  }

  const counts = readiness.aggregate_counts || {};
  const alreadyActive = readiness.lifecycle_state === "active";
  const legacy = readiness.lifecycle_state === "legacy_unchanged";

  return (
    <div className="app-canvas min-h-screen py-6 sm:py-10" data-ph-no-capture="true" data-testid="family-space-activation-page">
      <main className="page-section space-y-6">
        <header className="archival-card overflow-hidden p-0">
          <div className="grid lg:grid-cols-[1.1fr_0.9fr]">
            <div className="p-6 sm:p-9">
              <p className="eyebrow-text">From reunion plan to family home</p>
              <h1 className="mt-3 font-display text-4xl leading-tight text-foreground sm:text-5xl">Keep gathering after the reunion.</h1>
              <p className="mt-5 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">Activation changes only the enduring display name and lifecycle state. It does not move, recreate, or rewrite family content.</p>
            </div>
            <div className="bg-stone-950 p-6 text-white sm:p-9">
              <p className="eyebrow-text text-orange-200">One next step</p>
              <h2 className="mt-4 font-display text-3xl">{action[0]}</h2>
              <p className="mt-3 text-sm leading-7 text-stone-300">{action[1]}</p>
            </div>
          </div>
        </header>

        <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <article className="archival-card">
            <div className="flex items-center gap-3">
              <Users className="h-5 w-5 text-primary" />
              <div>
                <p className="eyebrow-text">Readiness</p>
                <h2 className="mt-2 font-display text-3xl">Meaningful participation, not link copying</h2>
              </div>
            </div>
            <div className="mt-6 space-y-3">
              <ProgressRow complete={(counts.verified_invitations || 0) >= 3} current={counts.verified_invitations || 0} label="Invitations opened, answered, or delivery-verified" target={3} />
              <ProgressRow complete={(counts.accepted_responses || 0) >= 2} current={counts.accepted_responses || 0} label="Accepted reunion responses" target={2} />
              <ProgressRow complete={(counts.non_host_participants || 0) >= 1} current={counts.non_host_participants || 0} label="Non-host participants" target={1} />
            </div>
            <p className="mt-5 flex items-start gap-2 text-xs leading-5 text-muted-foreground"><Clock3 className="mt-0.5 h-4 w-4 shrink-0" /> Queued email and copied links never count as delivery evidence.</p>
          </article>

          <article className="archival-card">
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-emerald-600" />
              <div>
                <p className="eyebrow-text">Private by membership</p>
                <h2 className="mt-2 font-display text-3xl">Everything already shared stays together.</h2>
              </div>
            </div>
            <ul className="mt-6 space-y-3 text-sm leading-7 text-muted-foreground">
              <li>• Existing members keep the same roles and permissions.</li>
              <li>• Reunion invitations, credentials, RSVPs, itinerary, and public links do not change.</li>
              <li>• Memory capsules, timeline history, subcommunities, and subscription state remain attached to the same family space.</li>
              <li>• No message is sent and no payment or provider call is required.</li>
            </ul>
          </article>
        </section>

        {alreadyActive || legacy || !readiness.ready ? (
          <section className="archival-card text-center" data-testid="family-space-nonactivatable-state">
            <Home className="mx-auto h-7 w-7 text-primary" />
            <h2 className="mt-4 font-display text-3xl">{alreadyActive ? "This family space is active." : legacy ? "Your existing family space continues unchanged." : "Keep using every reunion tool while readiness grows."}</h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">Deferring does not remove access to reunion planning, attendee hubs, memory capsules, or the family home.</p>
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <Button onClick={() => navigate("/home")} type="button">Open family home <ArrowRight className="ml-2 h-4 w-4" /></Button>
              {!alreadyActive && !legacy ? <Button onClick={load} type="button" variant="outline"><RefreshCw className="mr-2 h-4 w-4" /> Refresh readiness</Button> : null}
            </div>
          </section>
        ) : (
          <section className="archival-card" data-testid="family-space-name-card">
            <p className="eyebrow-text">The one enduring detail</p>
            <h2 className="mt-3 font-display text-3xl">What should your family call this space?</h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">Choose the private display name authorized members will see. Location, motto, profiles, subcommunities, invitations, and payment can all stay exactly as they are.</p>
            <form className="mt-6 space-y-5" onSubmit={activate}>
              <label className="block max-w-2xl">
                <span className="field-label">Family-space name</span>
                <Input
                  autoComplete="off"
                  className="field-input"
                  data-testid="family-space-name-input"
                  disabled={busy}
                  maxLength={80}
                  onChange={(event) => setFamilyName(event.target.value)}
                  placeholder="The Johnson Family"
                  required
                  value={familyName}
                />
              </label>
              <div className="flex flex-wrap gap-3">
                <Button data-testid="family-space-activate-button" disabled={busy || !familyName.trim() || !online} type="submit">{busy ? "Activating…" : "Activate family space"}</Button>
                <Button data-testid="family-space-defer-button" disabled={busy} onClick={defer} type="button" variant="outline">Decide later</Button>
              </div>
              {!online ? <p className="text-sm text-amber-700" role="status">Reconnect to activate. Your reunion tools remain available offline where already supported.</p> : null}
            </form>
          </section>
        )}
      </main>
    </div>
  );
};

export default FamilySpaceActivationPage;
