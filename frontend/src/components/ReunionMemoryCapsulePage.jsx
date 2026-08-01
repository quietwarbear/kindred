import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookHeart,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  Clock,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/sonner";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { zonedDateTimeToEpoch } from "@/lib/itinerary";

const ACTION_COPY = {
  share_first_memory: [
    "Share the first reunion memory",
    "Begin the private capsule with one story your community can revisit.",
  ],
  finish_memory_draft: [
    "Finish your saved draft",
    "Your draft is visible only to you until you publish it.",
  ],
  review_reunion_memories: [
    "Revisit the family stories",
    "Read what the community has preserved, then mark the capsule reviewed.",
  ],
  reunion_capsule_complete: [
    "The reunion capsule is ready",
    "Return whenever you want to revisit the published stories and itinerary.",
  ],
};

const formatMoment = (value, timezone, options = {}) => {
  if (!value) return "";
  const epoch = zonedDateTimeToEpoch(value, timezone || "UTC");
  if (Number.isNaN(epoch)) return value;
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone || "UTC",
    ...options,
  }).format(new Date(epoch));
};

const operationKey = (kind, eventId) => {
  const storageKey = `kindred:capsule:${kind}:${eventId}`;
  const existing = window.sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `${kind}:${random}`;
  window.sessionStorage.setItem(storageKey, value);
  return value;
};

const clearOperationKey = (kind, eventId) => {
  window.sessionStorage.removeItem(`kindred:capsule:${kind}:${eventId}`);
};

export const ReunionMemoryCapsulePage = ({ session }) => {
  const { eventId } = useParams();
  const [capsule, setCapsule] = useState(null);
  const [story, setStory] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [loadError, setLoadError] = useState("");
  const [online, setOnline] = useState(() => navigator.onLine);
  const [withdrawn, setWithdrawn] = useState(false);
  const viewedRef = useRef(false);
  const actionRef = useRef("");

  const load = useCallback(async () => {
    if (!session?.token || !eventId) return;
    setLoadError("");
    try {
      const payload = await apiRequest(`/events/${eventId}/memory-capsule`, {
        token: session.token,
      });
      setCapsule(payload);
      setStory(payload.own_contribution?.story || "");
    } catch (error) {
      setLoadError(
        error.response?.status === 404
          ? "This reunion capsule is not available in your current community."
          : "The reunion capsule could not be opened. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }, [eventId, session?.token]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  useEffect(() => {
    if (!capsule) return;
    if (!viewedRef.current) {
      viewedRef.current = true;
      trackReunionEvent("reunion_capsule_viewed", { source: "memory_capsule" });
    }
    if (actionRef.current !== capsule.next_action?.code) {
      actionRef.current = capsule.next_action?.code || "";
      trackReunionEvent("reunion_capsule_next_action_viewed", {
        source: "memory_capsule",
        action_code: capsule.next_action?.code || "reunion_capsule_complete",
      });
    }
  }, [capsule]);

  if (!session?.token) return <Navigate replace to="/login?intent=reunion" />;

  const runMutation = async (kind, operation, successMessage) => {
    setBusy(kind);
    try {
      const payload = await operation();
      clearOperationKey(kind, eventId);
      setCapsule(payload);
      setStory(payload.own_contribution?.story || "");
      toast.success(successMessage);
      return true;
    } catch (error) {
      if (error.response?.status === 409) {
        clearOperationKey(kind, eventId);
        await load();
        toast.info("The capsule changed. Your latest saved version is on screen.");
      } else if (error.response?.status === 404) {
        setLoadError("This reunion capsule is no longer available.");
      } else {
        toast.error("That change could not be saved. Please try again.");
      }
      return false;
    } finally {
      setBusy("");
    }
  };

  const saveContribution = (status) => {
    if (!story.trim()) return;
    const existing = capsule.own_contribution;
    const kind = existing ? `edit-${status}` : `create-${status}`;
    trackReunionEvent("memory_contribution_started", {
      source: "memory_capsule",
      status,
    });
    runMutation(
      kind,
      () => apiRequest(
        existing
          ? `/events/${eventId}/memory-capsule/contribution/${existing.id}`
          : `/events/${eventId}/memory-capsule/contribution`,
        {
          method: existing ? "PUT" : "POST",
          token: session.token,
          data: {
            story: story.trim(),
            status,
            idempotency_key: operationKey(kind, eventId),
          },
        }
      ),
      status === "draft"
        ? "Your private draft is saved."
        : "Your story is published to the private reunion capsule."
    ).then((saved) => {
      if (saved) {
        setWithdrawn(false);
        trackReunionEvent("memory_contribution_saved", {
          source: "memory_capsule",
          status,
        });
        if (status === "published") {
          trackReunionEvent("memory_contribution_completed", { source: "memory_capsule" });
        }
      }
    });
  };

  const withdrawContribution = () => {
    const existing = capsule.own_contribution;
    if (!existing) return;
    const kind = "withdraw";
    runMutation(
      kind,
      () => apiRequest(
        `/events/${eventId}/memory-capsule/contribution/${existing.id}`,
        {
          method: "DELETE",
          token: session.token,
          data: { idempotency_key: operationKey(kind, eventId) },
        }
      ),
      "Your contribution was withdrawn."
    ).then((saved) => {
      if (saved) {
        setWithdrawn(true);
        trackReunionEvent("memory_contribution_withdrawn", {
          source: "memory_capsule",
          status: "withdrawn",
        });
      }
    });
  };

  const reviewCapsule = () => runMutation(
    "review",
    () => apiRequest(`/events/${eventId}/memory-capsule/reviewed`, {
      method: "POST",
      token: session.token,
    }),
    "Reunion memories marked reviewed."
  );

  if (loading) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center" aria-busy="true">
        <p className="text-sm text-muted-foreground">Opening the reunion memories…</p>
      </div>
    );
  }

  if (loadError || !capsule) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-5">
        <section className="archival-card max-w-lg text-center" role="alert">
          <h1 className="font-display text-3xl">Capsule unavailable</h1>
          <p className="mt-3 text-sm text-muted-foreground">{loadError}</p>
          <Button className="mt-5" onClick={load} type="button" variant="outline">
            <RefreshCw className="mr-2 h-4 w-4" /> Try again
          </Button>
        </section>
      </div>
    );
  }

  const [actionTitle, actionCopy] = ACTION_COPY[capsule.next_action.code]
    || ACTION_COPY.reunion_capsule_complete;

  return (
    <div
      className="app-canvas min-h-screen"
      data-ph-no-capture="true"
      data-testid="reunion-memory-capsule"
      style={{
        paddingTop: "env(safe-area-inset-top, 0px)",
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
        paddingLeft: "env(safe-area-inset-left, 0px)",
        paddingRight: "env(safe-area-inset-right, 0px)",
      }}
    >
      <main className="page-section space-y-6 py-5 sm:py-10">
        <header>
          <Button asChild variant="ghost">
            <Link to={`/reunion/hub/${eventId}`}>
              <ChevronLeft className="mr-2 h-4 w-4" /> Reunion hub
            </Link>
          </Button>
          {!online ? (
            <p className="mt-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
              You’re offline. Published stories remain on screen; reconnect before saving changes.
            </p>
          ) : null}
          {withdrawn ? (
            <p className="mt-3 rounded-xl bg-stone-100 px-4 py-3 text-sm text-stone-800" role="status">
              Your contribution is withdrawn and no longer appears in this capsule.
            </p>
          ) : null}
        </header>

        <section className="archival-card overflow-hidden p-0">
          <div className="grid lg:grid-cols-[1.2fr_0.8fr]">
            <div className="p-6 sm:p-8">
              <p className="eyebrow-text">Private reunion memory capsule</p>
              <h1 className="mt-3 font-display text-4xl sm:text-5xl">{capsule.reunion.title}</h1>
              <div className="mt-5 flex flex-wrap gap-5 text-sm text-muted-foreground">
                <p className="flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-primary" />
                  {formatMoment(capsule.reunion.start_at, capsule.reunion.timezone, {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                </p>
                <p className="flex items-center gap-2">
                  <BookHeart className="h-4 w-4 text-primary" />
                  {capsule.memory_count} published {capsule.memory_count === 1 ? "story" : "stories"}
                </p>
              </div>
            </div>
            <aside className="bg-stone-950 p-6 text-white sm:p-8">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-200">One next step</p>
              <h2 className="mt-3 text-2xl font-semibold">{actionTitle}</h2>
              <p className="mt-3 text-sm leading-6 text-stone-300">{actionCopy}</p>
              <Button
                className="mt-5"
                onClick={() => document.getElementById(capsule.next_action.code)?.scrollIntoView({ behavior: "smooth" })}
                type="button"
                variant="secondary"
              >
                Open this step
              </Button>
            </aside>
          </div>
        </section>

        <section className="archival-card" id="review_reunion_memories">
          <p className="eyebrow-text">Published itinerary</p>
          <h2 className="mt-2 font-display text-3xl">The reunion you shared</h2>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {capsule.itinerary.map((activity) => (
              <article className="soft-panel" key={activity.id}>
                <h3 className="font-semibold">{activity.title}</h3>
                <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  {formatMoment(activity.start_at, activity.timezone, {
                    weekday: "short",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {activity.location_tba
                    ? "Location was to be announced"
                    : [activity.venue_name, activity.venue_detail].filter(Boolean).join(" · ") || "Reunion activity"}
                </p>
              </article>
            ))}
            {!capsule.itinerary.length ? (
              <p className="soft-panel text-sm text-muted-foreground">No published itinerary is attached.</p>
            ) : null}
          </div>
        </section>

        <section className="archival-card">
          <p className="eyebrow-text">Community stories</p>
          <h2 className="mt-2 font-display text-3xl">What the family chose to keep</h2>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {capsule.memories.map((memory) => (
              <article className="soft-panel" key={memory.id}>
                <p className="whitespace-pre-wrap text-base leading-7">{memory.story}</p>
                <p className="mt-4 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Shared by {memory.is_mine ? "you" : memory.contributor_name || "a community member"}
                </p>
              </article>
            ))}
            {!capsule.memories.length ? (
              <div className="soft-panel" id="share_first_memory">
                <p className="text-sm text-muted-foreground">No story has been published to this private capsule yet.</p>
              </div>
            ) : null}
          </div>
          {capsule.memories.length ? (
            <Button className="mt-5" disabled={!online || busy === "review"} onClick={reviewCapsule} type="button" variant="outline">
              {capsule.reviewed ? <CheckCircle2 className="mr-2 h-4 w-4" /> : null}
              {capsule.reviewed ? "Memories reviewed" : "Mark memories reviewed"}
            </Button>
          ) : null}
        </section>

        <section className="archival-card" id="finish_memory_draft">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-1 h-5 w-5 text-emerald-700" />
            <div>
              <p className="eyebrow-text">Your contribution</p>
              <h2 className="mt-2 font-display text-3xl">Keep one story from the reunion</h2>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                {capsule.visibility.explanation} A saved draft is visible only to you until you publish it.
              </p>
            </div>
          </div>
          <label className="mt-5 block text-sm font-semibold">
            Your story
            <Textarea
              className="mt-2"
              maxLength={4000}
              onChange={(event) => setStory(event.target.value)}
              rows={7}
              value={story}
            />
          </label>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button disabled={!online || !story.trim() || Boolean(busy)} onClick={() => saveContribution("draft")} type="button" variant="outline">
              Save private draft
            </Button>
            <Button disabled={!online || !story.trim() || Boolean(busy)} onClick={() => saveContribution("published")} type="button">
              {capsule.own_contribution?.status === "published" ? "Update published story" : "Publish to the capsule"}
            </Button>
            {capsule.own_contribution ? (
              <Button disabled={!online || Boolean(busy)} onClick={withdrawContribution} type="button" variant="destructive">
                Withdraw my contribution
              </Button>
            ) : null}
          </div>
        </section>

        <section className="archival-card text-center" id="reunion_capsule_complete">
          <CheckCircle2 className="mx-auto h-7 w-7 text-emerald-700" />
          <h2 className="mt-3 font-display text-3xl">Private by community membership</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            Public RSVP links cannot open, create, edit, or withdraw reunion memories. Capsule access always requires a signed-in member who can see this reunion.
          </p>
        </section>
      </main>
    </div>
  );
};

export default ReunionMemoryCapsulePage;
