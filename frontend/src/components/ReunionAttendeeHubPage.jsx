import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  Clock,
  HandHelping,
  MapPin,
  RefreshCw,
  Soup,
  Users,
} from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { dayKeyAtTimezone, runOfShow, zonedDateTimeToEpoch } from "@/lib/itinerary";
import { toast } from "@/components/ui/sonner";

const OVERALL_OPTIONS = [
  ["going", "I’m coming"],
  ["some", "Some activities"],
  ["maybe", "Maybe"],
  ["not-going", "I can’t make it"],
];

const ACTIVITY_OPTIONS = [
  ["coming", "Coming"],
  ["maybe", "Maybe"],
  ["not-coming", "Not coming"],
];

const ACTION_COPY = {
  respond_to_reunion: ["Tell the family if you’re coming", "Save your overall reunion response."],
  complete_activity_responses: ["Choose your activities", "Finish the open activity responses on your itinerary."],
  choose_contribution: ["Choose one way to help", "Claim an open dish or volunteer role if it works for you."],
  review_itinerary: ["Review the reunion plan", "Look through the published schedule and mark it reviewed."],
  share_a_memory: ["Keep one family story", "Add an optional story to your private Kindred community."],
  reunion_plan_complete: ["You’re ready for the reunion", "Your response, plans, and optional story are in one place."],
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

const stableOperationKey = (kind, eventId, itemId) => {
  const key = `kindred:attendee:${kind}:${eventId}:${itemId}`;
  const existing = window.sessionStorage.getItem(key);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `${kind}:${random}`;
  window.sessionStorage.setItem(key, value);
  return value;
};

export const ReunionAttendeeHubPage = ({ session }) => {
  const { eventId } = useParams();
  const [hub, setHub] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [loadError, setLoadError] = useState("");
  const [overall, setOverall] = useState("");
  const [guests, setGuests] = useState(0);
  const [story, setStory] = useState("");
  const [online, setOnline] = useState(() => navigator.onLine);
  const viewedRef = useRef(false);
  const actionRef = useRef("");

  const load = useCallback(async () => {
    if (!session?.token || !eventId) return;
    setLoadError("");
    try {
      const payload = await apiRequest(`/events/${eventId}/attendee-hub`, {
        token: session.token,
      });
      setHub(payload);
      setOverall(payload.rsvp?.my_status || "");
      setGuests(payload.rsvp?.my_guests || 0);
    } catch (error) {
      setLoadError(
        error.response?.status === 404
          ? "This reunion is not available in your current community."
          : "The reunion hub could not be opened. Please try again."
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
    if (!hub) return;
    if (!viewedRef.current) {
      viewedRef.current = true;
      trackReunionEvent("reunion_hub_viewed", { source: "attendee_hub" });
    }
    if (actionRef.current !== hub.next_action?.code) {
      actionRef.current = hub.next_action?.code || "";
      trackReunionEvent("attendee_next_action_viewed", {
        source: "attendee_hub",
        action_code: hub.next_action?.code || "reunion_plan_complete",
      });
    }
  }, [hub]);

  const activities = useMemo(
    () => runOfShow({
      agenda: (hub?.itinerary?.activities || []).map((activity) => ({
        ...activity,
        visibility: "published",
      })),
      timezone: hub?.gathering?.timezone || "UTC",
    }),
    [hub?.gathering?.timezone, hub?.itinerary?.activities]
  );
  const activityDays = useMemo(
    () => activities.reduce((groups, activity) => {
      const day = dayKeyAtTimezone(
        activity.start_at,
        activity.timezone || hub?.gathering?.timezone || "UTC"
      );
      if (!day) return groups;
      if (!groups[day]) groups[day] = [];
      groups[day].push(activity);
      return groups;
    }, {}),
    [activities, hub?.gathering?.timezone]
  );

  if (!session?.token) return <Navigate replace to="/login?intent=reunion" />;

  const refreshAfter = async (operation, successMessage) => {
    try {
      await operation();
      await load();
      if (successMessage) toast.success(successMessage);
      return true;
    } catch (error) {
      const code = error.response?.data?.detail?.code;
      if (["contribution_full", "contribution_claimed", "contribution_not_owned"].includes(code)) {
        await load();
        toast.info(error.response.data.detail.message);
      } else {
        toast.error(error.response?.data?.detail?.message || error.response?.data?.detail || "That change could not be saved.");
      }
      return false;
    } finally {
      setBusy("");
    }
  };

  const saveOverall = () => {
    if (!overall) return;
    setBusy("overall");
    refreshAfter(
      () => apiRequest(`/events/${eventId}/rsvp`, {
        method: "POST",
        token: session.token,
        data: { status: overall, guests: Math.max(0, Number(guests) || 0) },
      }),
      "Your reunion response is saved."
    );
  };

  const saveActivity = (activityId, status) => {
    setBusy(`activity:${activityId}`);
    refreshAfter(
      () => apiRequest(`/events/${eventId}/activity-rsvp`, {
        method: "POST",
        token: session.token,
        data: { activity_id: activityId, status, party_size: 1 },
      }),
      "Activity response saved."
    );
  };

  const changeContribution = (kind, item, release = false) => {
    const endpoint = kind === "potluck"
      ? `potluck-${release ? "release" : "claim"}`
      : `volunteer-${release ? "release" : "signup"}`;
    const idKey = kind === "potluck" ? "item_id" : "slot_id";
    setBusy(`${kind}:${item.id}`);
    refreshAfter(
      () => apiRequest(`/events/${eventId}/${endpoint}`, {
        method: "POST",
        token: session.token,
        data: {
          [idKey]: item.id,
          idempotency_key: stableOperationKey(endpoint, eventId, item.id),
        },
      }),
      release ? "Commitment released." : "Commitment saved."
    ).then((saved) => {
      if (saved) {
        trackReunionEvent(
          release ? "contribution_released" : "contribution_claimed",
          { source: "attendee_hub", status: kind }
        );
      }
    });
  };

  const reviewItinerary = () => {
    setBusy("review");
    refreshAfter(
      () => apiRequest(`/events/${eventId}/attendee-hub/itinerary-reviewed`, {
        method: "POST",
        token: session.token,
      }),
      "Itinerary marked reviewed."
    );
  };

  const saveStory = () => {
    if (!story.trim()) return;
    setBusy("memory");
    trackReunionEvent("memory_prompt_started", { source: "attendee_hub" });
    refreshAfter(
      () => apiRequest(`/events/${eventId}/attendee-hub/memory`, {
        method: "POST",
        token: session.token,
        data: { story: story.trim() },
      }),
      "Your story is saved to the private community."
    ).then((saved) => {
      if (saved) {
        setStory("");
        trackReunionEvent("memory_prompt_completed", { source: "attendee_hub" });
      }
    });
  };

  if (loading) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center" aria-busy="true">
        <p className="text-sm text-muted-foreground">Gathering your reunion details…</p>
      </div>
    );
  }

  if (loadError || !hub) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-5">
        <section className="archival-card max-w-lg text-center" role="alert">
          <h1 className="font-display text-3xl">Reunion unavailable</h1>
          <p className="mt-3 text-sm text-muted-foreground">{loadError}</p>
          <Button className="mt-5" onClick={load} type="button" variant="outline">
            <RefreshCw className="mr-2 h-4 w-4" /> Try again
          </Button>
        </section>
      </div>
    );
  }

  const gathering = hub.gathering;
  const [actionTitle, actionCopy] = ACTION_COPY[hub.next_action.code] || ACTION_COPY.reunion_plan_complete;

  return (
    <div
      className="app-canvas min-h-screen"
      data-ph-no-capture="true"
      data-testid="reunion-attendee-hub"
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
            <Link to="/gatherings"><ChevronLeft className="mr-2 h-4 w-4" /> Gatherings</Link>
          </Button>
          {!online ? (
            <p className="mt-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
              You’re offline. Your saved reunion details remain on screen; reconnect before making changes.
            </p>
          ) : null}
        </header>

        <section className="archival-card overflow-hidden p-0">
          <div className="grid lg:grid-cols-[1.25fr_0.75fr]">
            <div className="p-6 sm:p-8">
              <p className="eyebrow-text">Your reunion hub</p>
              <h1 className="mt-3 font-display text-4xl sm:text-5xl">{gathering.title}</h1>
              {gathering.description ? <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground">{gathering.description}</p> : null}
              <div className="mt-5 grid gap-3 text-sm text-muted-foreground sm:grid-cols-2">
                <p className="flex gap-2"><CalendarDays className="h-4 w-4 text-primary" /> {formatMoment(gathering.start_at, gathering.timezone, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</p>
                <p className="flex gap-2"><Clock className="h-4 w-4 text-primary" /> {formatMoment(gathering.start_at, gathering.timezone, { hour: "numeric", minute: "2-digit", timeZoneName: "short" })}</p>
                <p className="flex gap-2"><MapPin className="h-4 w-4 text-primary" /> {gathering.location || "Location to be announced"}</p>
                <p className="flex gap-2"><Users className="h-4 w-4 text-primary" /> {(hub.rsvp.summary.going || 0) + (hub.rsvp.summary.some || 0)} attending · {hub.rsvp.summary.maybe || 0} maybe</p>
              </div>
            </div>
            <aside className="bg-stone-950 p-6 text-white sm:p-8">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-200">One next step</p>
              <h2 className="mt-3 text-2xl font-semibold">{actionTitle}</h2>
              <p className="mt-3 text-sm leading-6 text-stone-300">{actionCopy}</p>
              <Button
                className="mt-5"
                onClick={() => document.getElementById(hub.next_action.code)?.scrollIntoView({ behavior: "smooth" })}
                type="button"
                variant="secondary"
              >
                Open this step <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </aside>
          </div>
        </section>

        <section className="archival-card" id="respond_to_reunion">
          <p className="eyebrow-text">Your response</p>
          <h2 className="mt-2 font-display text-3xl">Will you be there?</h2>
          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {OVERALL_OPTIONS.map(([value, label]) => (
              <button
                aria-pressed={overall === value}
                className={`rounded-2xl border-2 p-4 text-left text-sm font-semibold ${overall === value ? "border-primary bg-primary/10" : "border-border"}`}
                key={value}
                onClick={() => setOverall(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <label className="mt-4 block max-w-xs text-sm font-semibold">
            Additional people in your party
            <Input className="mt-2" min={0} onChange={(event) => setGuests(event.target.value)} type="number" value={guests} />
          </label>
          <Button className="mt-4" disabled={!online || !overall || busy === "overall"} onClick={saveOverall} type="button">
            {busy === "overall" ? "Saving…" : "Save my response"}
          </Button>
        </section>

        <section className="archival-card" id="complete_activity_responses">
          <p className="eyebrow-text">Published itinerary</p>
          <h2 className="mt-2 font-display text-3xl">Plan your reunion days</h2>
          {activities.length ? (
            <div className="mt-6 space-y-8">
              {Object.entries(activityDays).map(([day, dayActivities]) => (
                <section key={day}>
                  <h3 className="border-b border-border pb-2 text-lg font-semibold">
                    {formatMoment(`${day}T12:00:00`, gathering.timezone, { weekday: "long", month: "long", day: "numeric" })}
                  </h3>
                  <div className="mt-3 grid gap-3">
                    {dayActivities.map((activity) => (
                      <article className="soft-panel" key={activity.id}>
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <h4 className="text-lg font-semibold">{activity.title}</h4>
                            <p className="mt-1 text-sm text-muted-foreground">
                              {formatMoment(activity.start_at, activity.timezone, { hour: "numeric", minute: "2-digit" })}
                              {activity.end_at ? `–${formatMoment(activity.end_at, activity.timezone, { hour: "numeric", minute: "2-digit" })}` : ""}
                            </p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              {activity.location_tba ? "Location to be announced" : [activity.venue_name, activity.venue_detail, activity.venue_address].filter(Boolean).join(" · ") || "Venue to be announced"}
                            </p>
                          </div>
                          <p className="text-xs text-muted-foreground">{activity.attendance?.coming || 0} coming · {activity.attendance?.maybe || 0} maybe</p>
                        </div>
                        {activity.description ? <p className="mt-3 text-sm leading-6 text-muted-foreground">{activity.description}</p> : null}
                        {activity.notes ? <p className="mt-2 text-sm"><strong>Know before you go:</strong> {activity.notes}</p> : null}
                        {activity.attendance_requested ? (
                          <div className="mt-4 flex flex-wrap gap-2">
                            {ACTIVITY_OPTIONS.map(([value, label]) => (
                              <Button
                                aria-pressed={activity.my_response === value}
                                disabled={!online || !activity.response_open || busy === `activity:${activity.id}`}
                                key={value}
                                onClick={() => saveActivity(activity.id, value)}
                                size="sm"
                                type="button"
                                variant={activity.my_response === value ? "default" : "outline"}
                              >
                                {label}
                              </Button>
                            ))}
                          </div>
                        ) : <p className="mt-3 text-xs text-muted-foreground">No separate response requested.</p>}
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : <p className="mt-4 text-sm text-muted-foreground">The organizer has not published the itinerary yet.</p>}
          {activities.length ? (
            <Button className="mt-5" disabled={!online || busy === "review"} id="review_itinerary" onClick={reviewItinerary} type="button" variant="outline">
              {hub.itinerary.reviewed ? <CheckCircle2 className="mr-2 h-4 w-4" /> : null}
              {hub.itinerary.reviewed ? "Itinerary reviewed" : "Mark itinerary reviewed"}
            </Button>
          ) : null}
        </section>

        <section className="grid gap-6 lg:grid-cols-2" id="choose_contribution">
          <article className="archival-card">
            <div className="flex items-center gap-3"><Soup className="h-5 w-5 text-primary" /><h2 className="font-display text-3xl">Shared table</h2></div>
            <div className="mt-5 space-y-3">
              {hub.contributions.potluck.map((item) => (
                <div className="soft-panel flex items-center justify-between gap-3" key={item.id}>
                  <div><p className="font-semibold">{item.item_name}</p><p className="text-xs text-muted-foreground">{item.is_mine ? "Your commitment" : item.claimed ? "Claimed" : "Open"}</p></div>
                  {item.is_mine ? (
                    <Button disabled={!online || busy === `potluck:${item.id}`} onClick={() => changeContribution("potluck", item, true)} size="sm" type="button" variant="outline">Release</Button>
                  ) : !item.claimed ? (
                    <Button disabled={!online || busy === `potluck:${item.id}`} onClick={() => changeContribution("potluck", item)} size="sm" type="button">Claim</Button>
                  ) : null}
                </div>
              ))}
              {!hub.contributions.potluck.length ? <p className="text-sm text-muted-foreground">No potluck needs are posted.</p> : null}
            </div>
          </article>
          <article className="archival-card">
            <div className="flex items-center gap-3"><HandHelping className="h-5 w-5 text-primary" /><h2 className="font-display text-3xl">Ways to help</h2></div>
            <div className="mt-5 space-y-3">
              {hub.contributions.volunteer.map((item) => (
                <div className="soft-panel flex items-center justify-between gap-3" key={item.id}>
                  <div><p className="font-semibold">{item.title}</p><p className="text-xs text-muted-foreground">{item.filled_count}/{item.needed_count} filled{item.is_mine ? " · Your commitment" : ""}</p></div>
                  {item.is_mine ? (
                    <Button disabled={!online || busy === `volunteer:${item.id}`} onClick={() => changeContribution("volunteer", item, true)} size="sm" type="button" variant="outline">Release</Button>
                  ) : item.openings > 0 ? (
                    <Button disabled={!online || busy === `volunteer:${item.id}`} onClick={() => changeContribution("volunteer", item)} size="sm" type="button">Join</Button>
                  ) : null}
                </div>
              ))}
              {!hub.contributions.volunteer.length ? <p className="text-sm text-muted-foreground">No volunteer roles are posted.</p> : null}
            </div>
          </article>
        </section>

        <section className="archival-card" id="share_a_memory">
          <p className="eyebrow-text">Optional memory prompt</p>
          <h2 className="mt-2 font-display text-3xl">{hub.memory_prompt.title}</h2>
          <p className="mt-3 text-sm text-muted-foreground">{hub.memory_prompt.question}</p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{hub.memory_prompt.sharing_boundary}</p>
          {hub.memory_prompt.completed ? (
            <div className="mt-5">
              <p className="flex items-center gap-2 text-sm font-semibold text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Your reunion story is saved.</p>
              <Button asChild className="mt-4" variant="outline">
                <Link to={hub.memory_prompt.capsule_path || `/reunion/memories/${eventId}`}>
                  Open the private reunion capsule
                </Link>
              </Button>
            </div>
          ) : (
            <>
              <Textarea className="mt-5" maxLength={4000} onChange={(event) => setStory(event.target.value)} rows={5} value={story} />
              <Button className="mt-4" disabled={!online || !story.trim() || busy === "memory"} onClick={saveStory} type="button">
                {busy === "memory" ? "Saving…" : "Save this story"}
              </Button>
            </>
          )}
          {!hub.memory_prompt.completed ? (
            <p className="mt-4 text-xs leading-5 text-muted-foreground">
              After saving, you can revisit and manage your story in the private reunion capsule.
            </p>
          ) : null}
        </section>

        <section className="archival-card text-center" id="reunion_plan_complete">
          <CheckCircle2 className="mx-auto h-7 w-7 text-emerald-700" />
          <h2 className="mt-3 font-display text-3xl">Your plans stay yours</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            This hub shows your responses, safe family totals, published reunion details, and your own commitments. It does not show private travel, planning notes, budgets, draft activities, invitation links, or anyone else’s named response.
          </p>
        </section>
      </main>
    </div>
  );
};

export default ReunionAttendeeHubPage;
