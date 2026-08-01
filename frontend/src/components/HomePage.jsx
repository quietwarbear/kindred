import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, BellRing, CheckCheck, CircleAlert, CloudOff, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { toast } from "@/components/ui/sonner";

const ACTION_COPY = {
  activate_family_space: ["Name and open your family space", "Your reunion has enough verified participation to become an enduring private family space.", "Complete family setup"],
  finish_reunion_draft: ["Finish the reunion draft", "Complete the remaining reunion details before inviting family.", "Continue the draft"],
  prepare_first_invitation: ["Bring the first person in", "Prepare or safely share the reunion’s first private invitation.", "Open invitation controls"],
  review_family_access_requests: ["Review a family access request", "A reunion guest is waiting for an organizer decision.", "Review privately"],
  resolve_rsvp_attention: ["Check reunion responses", "A response deadline or missing reply needs organizer attention.", "Open response planning"],
  complete_command_task: ["Move reunion planning forward", "Your organizer command center has one clear next task.", "Continue planning"],
  review_recap: ["Review the reunion recap", "A completed reunion is ready for a private family recap decision.", "Open recap"],
  review_gathering_proposal: ["Review a gathering idea", "A private family suggestion is waiting for organizer review.", "Review proposal"],
  continue_converted_draft: ["Continue the next private draft", "An accepted gathering idea is ready for careful organizer planning.", "Open private draft"],
  open_command_center: ["Open reunion planning", "Return to the active organizer command center.", "Open command center"],
  confirm_family_access: ["Confirm your family access", "Your organizer approved access to this existing private family space.", "Confirm access"],
  complete_reunion_rsvp: ["Share your reunion response", "Let the family know your own plans without exposing anyone else’s response.", "Complete my RSVP"],
  complete_activity_responses: ["Finish activity responses", "One or more published reunion activities still need your answer.", "Open my itinerary"],
  review_updated_itinerary: ["Review the updated itinerary", "The published reunion plan has an update ready for you.", "Review itinerary"],
  manage_contribution: ["Choose or review a contribution", "See available food and volunteer needs, plus only your own commitments.", "Open contributions"],
  respond_to_gathering_pulse: ["Respond to a family gathering idea", "Share one private interest response and see anonymous totals.", "Respond privately"],
  continue_memory_contribution: ["Continue your private memory", "A reunion story draft is waiting for you.", "Continue memory"],
  view_published_recap: ["See the newly published recap", "A private reunion recap is ready for family members.", "Open recap"],
  check_family_access_status: ["Check your family access status", "Your own private access request has an update or is still waiting.", "Check status"],
  open_family_home: ["You’re caught up", "There is no urgent family action right now. The rest of your private family space is ready when you are.", "Browse family activity"],
};

const STATIC_DESTINATIONS = {
  family_access: "/family/join",
  family_activation: "/family/activate",
  family_home: "/activity",
  gathering_proposals: "/proposals",
  gatherings: "/gatherings",
};

const RECENT_CHANGE_COPY = {
  family_access: "Your family access status changed.",
  family_update: "Something changed in your private family space.",
  gathering_update: "A gathering update is ready.",
  organizer_review: "A private organizer review needs attention.",
  reunion_recap: "A private reunion recap is ready.",
  gathering_pulse: "A family gathering pulse is open.",
};

const roleLabel = (value) => {
  if (value === "organizer" || value === "host") return "Organizer Today";
  if (value === "new_member") return "Welcome to your family space";
  return "Family Today";
};

export const HomePage = ({ token, todayData, todayLoading, todayError, onRetryToday }) => {
  const navigate = useNavigate();
  const [busy, setBusy] = useState("");
  const [offline, setOffline] = useState(() => typeof navigator !== "undefined" && !navigator.onLine);
  const viewedRef = useRef(false);
  const shownCodeRef = useRef("");

  useEffect(() => {
    const goOnline = () => setOffline(false);
    const goOffline = () => setOffline(true);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  useEffect(() => {
    if (!todayData || viewedRef.current) return;
    viewedRef.current = true;
    trackReunionEvent("family_today_viewed", {
      source: "family_today",
      viewer_role: todayData.viewer_role,
      lifecycle_state: todayData.lifecycle_state,
    });
  }, [todayData]);

  useEffect(() => {
    const code = todayData?.primary_action_code;
    if (!code || shownCodeRef.current === code) return;
    shownCodeRef.current = code;
    trackReunionEvent("family_today_primary_action_shown", {
      source: "family_today",
      viewer_role: todayData.viewer_role,
      lifecycle_state: todayData.lifecycle_state,
      action_code: code,
    });
  }, [todayData]);

  useEffect(() => {
    (todayData?.milestone_codes || []).forEach((code) => {
      const key = `kindred:today-milestone:${code}`;
      if (window.sessionStorage.getItem(key)) return;
      window.sessionStorage.setItem(key, "seen");
      if (code === "first_rsvp_received") {
        trackReunionEvent("first_rsvp_received", { source: "family_today", viewer_role: "organizer" });
        trackReunionEvent("organizer_return_after_first_rsvp", { source: "family_today", viewer_role: "organizer" });
      }
    });
  }, [todayData]);

  const selectAction = useCallback(async (action, isPrimary = false) => {
    if (!action || offline) return;
    setBusy(action.code);
    if (isPrimary) {
      trackReunionEvent("family_today_primary_action_selected", {
        source: "family_today",
        viewer_role: todayData?.viewer_role,
        lifecycle_state: todayData?.lifecycle_state,
        action_code: action.code,
      });
    }
    try {
      if (action.action_reference) {
        const payload = await apiRequest(`/today/actions/${action.action_reference}`, { token });
        if (!String(payload.destination || "").startsWith("/")) throw new Error("Unsafe Today destination");
        navigate(payload.destination);
      } else {
        navigate(STATIC_DESTINATIONS[action.destination_category] || "/home");
      }
    } catch (error) {
      if (error.response?.status === 404) {
        toast.error("That family action changed. Today has been refreshed.");
        await onRetryToday?.();
      } else {
        toast.error("That family action is temporarily unavailable.");
      }
    } finally {
      setBusy("");
    }
  }, [navigate, offline, onRetryToday, todayData?.lifecycle_state, todayData?.viewer_role, token]);

  const markRecentRead = async () => {
    setBusy("mark-read");
    try {
      await apiRequest("/notifications/mark-read", { method: "POST", token });
      await onRetryToday?.();
    } catch {
      toast.error("Recent changes could not be marked read.");
    } finally {
      setBusy("");
    }
  };

  if (todayLoading) {
    return <section className="archival-card" aria-busy="true" data-testid="today-loading"><p className="eyebrow-text">Family Today</p><h1 className="mt-3 font-display text-4xl">Finding what matters now…</h1></section>;
  }

  if (todayError || !todayData || !todayData.primary_action) {
    return (
      <section className="archival-card text-center" data-testid="today-error">
        <CircleAlert className="mx-auto h-8 w-8 text-primary" />
        <h1 className="mt-4 font-display text-4xl">Today needs a fresh look</h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-muted-foreground">Your family data was not changed. Try the private Today view again when the connection is ready.</p>
        <Button className="mt-5" onClick={onRetryToday} type="button" variant="outline"><RefreshCw className="mr-2 h-4 w-4" />Try again</Button>
      </section>
    );
  }

  const primary = todayData.primary_action;
  const primaryCopy = ACTION_COPY[primary.code] || ACTION_COPY.open_family_home;
  const unreadRecent = todayData.recent_changes.some((item) => !item.is_read);

  return (
    <div className="space-y-6" data-ph-no-capture="true" data-testid="family-today-page">
      {offline ? (
        <div className="soft-panel flex items-center gap-3" role="status" data-testid="today-offline-state">
          <CloudOff className="h-5 w-5 text-primary" />
          <p className="text-sm text-muted-foreground">You’re offline. Today remains visible, but actions wait for a private connection.</p>
        </div>
      ) : null}

      <section className="archival-card overflow-hidden" data-testid="today-primary-card">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="eyebrow-text">{roleLabel(todayData.viewer_role)}</p>
            <h1 className="mt-3 font-display text-4xl leading-tight text-foreground sm:text-5xl">{primaryCopy[0]}</h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">{primaryCopy[1]}</p>
            <Button className="mt-6" disabled={offline || Boolean(busy)} onClick={() => selectAction(primary, true)} type="button">
              {busy === primary.code ? "Opening…" : primaryCopy[2]} <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
          <div className="soft-panel flex max-w-sm items-start gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 text-primary" />
            <div><p className="text-sm font-semibold">One clear next step</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Built from your current role and only the private family information you may access.</p></div>
          </div>
        </div>
      </section>

      {todayData.secondary_actions.length ? (
        <section className="archival-card" aria-labelledby="today-secondary-heading">
          <p className="eyebrow-text">After that</p>
          <h2 className="mt-2 font-display text-3xl" id="today-secondary-heading">A few things close behind</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            {todayData.secondary_actions.map((action) => {
              const copy = ACTION_COPY[action.code] || ACTION_COPY.open_family_home;
              return (
                <button className="soft-panel text-left transition hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" disabled={offline || Boolean(busy)} key={action.code} onClick={() => selectAction(action)} type="button">
                  <Sparkles className="h-4 w-4 text-primary" />
                  <p className="mt-3 text-base font-semibold text-foreground">{copy[0]}</p>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{copy[2]}</p>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="archival-card" aria-labelledby="today-recent-heading" data-testid="today-recent-changes">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="eyebrow-text">Recent changes</p><h2 className="mt-2 font-display text-3xl" id="today-recent-heading">What changed privately</h2></div>
          {unreadRecent ? <Button disabled={busy === "mark-read" || offline} onClick={markRecentRead} size="sm" type="button" variant="outline"><CheckCheck className="mr-2 h-4 w-4" />Mark changes read</Button> : null}
        </div>
        <div className="mt-5 space-y-3">
          {todayData.recent_changes.length ? todayData.recent_changes.map((item, index) => (
            <div className="soft-panel flex items-center gap-3" key={`${item.category}-${index}`}>
              <BellRing className="h-4 w-4 text-primary" />
              <p className={`text-sm ${item.is_read ? "text-muted-foreground" : "font-semibold text-foreground"}`}>{RECENT_CHANGE_COPY[item.category] || RECENT_CHANGE_COPY.family_update}</p>
            </div>
          )) : <div className="soft-panel"><p className="text-sm text-muted-foreground">Nothing new needs your attention. Opening Today never marks anything read.</p></div>}
        </div>
      </section>
    </div>
  );
};
