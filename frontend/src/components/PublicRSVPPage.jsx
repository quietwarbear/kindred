import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, CheckCircle2, Clock, MapPin, Users } from "lucide-react";
import { useParams } from "react-router-dom";

import { API_URL } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { runOfShow, zonedDateTimeToEpoch } from "@/lib/itinerary";

// Public, no-account RSVP page for https://heykindred.org/rsvp/:token.
// The bearer token is intentionally used only in the API URL and never analytics.

const APP_STORE_URL = "https://apps.apple.com/app/heykindred/id6760608478";

const OVERALL_OPTIONS = [
  { value: "going", label: "Attending", sub: "I plan to join the full reunion" },
  { value: "some", label: "Attending some activities", sub: "I’ll choose from the schedule" },
  { value: "maybe", label: "Not sure", sub: "Please keep me in the loop" },
  { value: "not-going", label: "Unable to attend", sub: "I’m sorry to miss it" },
];

const ACTIVITY_OPTIONS = [
  { value: "coming", label: "Coming" },
  { value: "maybe", label: "Maybe" },
  { value: "not-coming", label: "Not coming" },
];

const formatMoment = (value, timezone, options = {}) => {
  if (!value) return "";
  const epoch = zonedDateTimeToEpoch(value, timezone);
  if (Number.isNaN(epoch)) return value;
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone || "UTC",
    ...options,
  }).format(new Date(epoch));
};

const dateRange = (gathering) => {
  const timezone = gathering.timezone || "UTC";
  const start = formatMoment(gathering.start_at, timezone, {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  });
  const end = gathering.end_at
    ? formatMoment(gathering.end_at, timezone, {
      weekday: "long", month: "long", day: "numeric", year: "numeric",
    })
    : "";
  return end && end !== start ? `${start} through ${end}` : start;
};

const dayGroups = (activities) => activities.reduce((groups, activity) => {
  const day = activity.start_at.slice(0, 10);
  if (!groups[day]) groups[day] = [];
  groups[day].push(activity);
  return groups;
}, {});

export const PublicRSVPPage = () => {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [step, setStep] = useState(1);
  const [overall, setOverall] = useState("");
  const [activityResponses, setActivityResponses] = useState({});
  const [guests, setGuests] = useState(0);
  const openedTracked = useRef(false);
  const itineraryTracked = useRef(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/public/rsvp/${token}`);
      if (!response.ok) throw new Error("not found");
      const payload = await response.json();
      setData(payload);
      setOverall(payload.rsvp_status === "pending" ? "" : payload.rsvp_status);
      setActivityResponses(Object.fromEntries(
        (payload.gathering?.activities || [])
          .filter((activity) => activity.my_response && activity.my_response !== "no-response")
          .map((activity) => [activity.id, activity.my_response])
      ));
    } catch {
      setError("We couldn't find this invitation. Ask whoever invited you for a fresh link.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (data?.gathering?.event_template === "reunion" && !openedTracked.current) {
      openedTracked.current = true;
      trackReunionEvent("invite_opened", { source: "public_rsvp" });
    }
    if (data?.gathering?.activities?.length && !itineraryTracked.current) {
      itineraryTracked.current = true;
      trackReunionEvent("itinerary_viewed", {
        activity_count: data.gathering.activities.length,
        actor_type: "invitee",
      });
    }
  }, [data]);

  const gathering = data?.gathering || {};
  const activities = useMemo(() => {
    if (!gathering.activities?.length) return [];
    return runOfShow({
      agenda: gathering.activities.map((activity) => ({ ...activity, visibility: "published" })),
      timezone: gathering.timezone,
    });
  }, [gathering.activities, gathering.timezone]);
  const groupedActivities = useMemo(() => dayGroups(activities), [activities]);
  const everyActivityDeclined = activities.length > 0
    && activities.every((activity) => activityResponses[activity.id] === "not-coming");
  const comingCount = Object.values(activityResponses).filter((value) => value === "coming").length;

  const submit = async () => {
    if (!overall) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/public/rsvp/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: overall,
          guests: Math.max(0, Number(guests) || 0),
          activity_responses: activityResponses,
        }),
      });
      if (!response.ok) throw new Error("save failed");
      const payload = await response.json();
      setData(payload);
      setSaved(true);
      if (payload?.gathering?.event_template === "reunion") {
        trackReunionEvent("rsvp_completed", {
          source: "public_rsvp",
          status: overall,
        });
        Object.values(activityResponses).forEach((responseCategory) => {
          trackReunionEvent("activity_rsvp_updated", {
            response_category: responseCategory,
            actor_type: "invitee",
          });
        });
      }
    } catch {
      setError("Something went wrong saving your reply. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const shell = (children) => (
    <div className="min-h-screen bg-gradient-to-b from-amber-50 to-rose-50 px-4 py-8 sm:px-6 sm:py-16" data-ph-no-capture="true">
      <main className="mx-auto w-full max-w-3xl rounded-3xl bg-white p-6 text-center shadow-xl sm:p-10">
        <p className="mb-4 text-sm uppercase tracking-[0.2em] text-rose-600">heyKindred</p>
        {children}
      </main>
    </div>
  );

  if (loading) return shell(<p className="text-xl text-slate-600">Loading your invitation…</p>);

  if (error && !data) {
    return shell(
      <>
        <h1 className="mb-3 text-2xl font-semibold text-slate-900">Invitation not found</h1>
        <p className="text-lg text-slate-600">{error}</p>
      </>
    );
  }

  const featured = activities.find((activity) => activity.featured) || activities[0];

  return shell(
    <>
      {data?.invitee_name ? <p className="mb-1 text-lg text-slate-500">Hello {data.invitee_name},</p> : null}
      <h1 className="mb-2 text-3xl font-semibold text-slate-900">You’re invited</h1>
      {data?.invited_by_name ? (
        <p className="mb-5 text-base text-rose-700">
          {data.invited_by_name} invited you{data?.community_name ? ` from ${data.community_name}` : ""}
        </p>
      ) : null}

      <section className="mb-7 rounded-2xl bg-slate-50 px-5 py-5 text-left" aria-labelledby="invitation-title">
        <h2 className="text-2xl font-semibold leading-snug text-slate-900" id="invitation-title">{gathering.title}</h2>
        <p className="mt-3 flex items-start gap-2 text-base text-slate-700">
          <CalendarDays className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" /> {dateRange(gathering)}
        </p>
        <p className="mt-2 flex items-start gap-2 text-base text-slate-600">
          <MapPin className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" /> {gathering.location || "Host city to be announced"}
        </p>
        {activities.length ? (
          <p className="mt-2 flex items-center gap-2 text-base text-slate-600">
            <Clock className="h-5 w-5 text-rose-600" /> {activities.length} planned activit{activities.length === 1 ? "y" : "ies"}
          </p>
        ) : null}
        {featured ? <p className="mt-3 text-sm text-slate-600"><strong>Featured:</strong> {featured.title}</p> : null}
      </section>

      {!saved ? (
        <div className="mb-6 flex justify-center gap-2" aria-label={`Step ${step} of 3`}>
          {[1, 2, 3].map((number) => (
            <span className={`h-2 w-12 rounded-full ${step >= number ? "bg-rose-600" : "bg-slate-200"}`} key={number} />
          ))}
        </div>
      ) : null}

      {saved ? (
        <section className="rounded-2xl bg-emerald-50 px-5 py-6">
          <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-700" />
          <h2 className="mt-3 text-xl font-semibold text-emerald-900">Your reunion response is saved.</h2>
          <p className="mt-2 text-base text-emerald-800">Return to this private invitation link anytime to update the whole response in one place.</p>
          <button className="mt-4 font-semibold text-emerald-900 underline" onClick={() => { setSaved(false); setStep(1); }} type="button">Edit my response</button>
        </section>
      ) : null}

      {!saved && step === 1 ? (
        <fieldset>
          <legend className="text-xl font-semibold text-slate-900">Will you join the reunion?</legend>
          <p className="mt-2 text-sm text-slate-600">You can still choose individual activities next.</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {OVERALL_OPTIONS.map((option) => (
              <button
                aria-pressed={overall === option.value}
                className={`rounded-2xl border-2 p-4 text-left ${overall === option.value ? "border-rose-600 bg-rose-50" : "border-slate-200"}`}
                data-testid={`public-rsvp-${option.value}`}
                key={option.value}
                onClick={() => setOverall(option.value)}
                type="button"
              >
                <span className="block font-semibold text-slate-900">{option.label}</span>
                <span className="mt-1 block text-sm text-slate-600">{option.sub}</span>
              </button>
            ))}
          </div>
          <button className="mt-6 rounded-full bg-rose-600 px-6 py-3 font-semibold text-white disabled:opacity-50" data-testid="public-rsvp-continue" disabled={!overall} onClick={() => setStep(activities.length ? 2 : 3)} type="button">
            {activities.length ? "Choose activities" : "Review response"}
          </button>
        </fieldset>
      ) : null}

      {!saved && step === 2 ? (
        <section className="text-left" data-testid="public-rsvp-itinerary">
          <h2 className="text-center text-2xl font-semibold text-slate-900">Tell us which activities you’re joining</h2>
          <p className="mt-2 text-center text-sm text-slate-600">One schedule, one final submission. You can change it later.</p>
          <div className="mt-6 space-y-8">
            {Object.entries(groupedActivities).map(([day, dayActivities]) => (
              <section key={day}>
                <h3 className="border-b border-slate-200 pb-2 font-semibold text-slate-900">
                  {formatMoment(`${day}T12:00:00`, gathering.timezone, {
                    weekday: "long", month: "long", day: "numeric",
                  })}
                </h3>
                <div className="mt-3 space-y-4">
                  {dayActivities.map((activity) => (
                    <article className={`rounded-2xl border p-4 ${activity.run_state === "happening" ? "border-emerald-500 bg-emerald-50" : activity.run_state === "up-next" ? "border-rose-400 bg-rose-50" : "border-slate-200"}`} key={activity.id}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <span className="text-xs font-semibold uppercase tracking-wide text-rose-700">{activity.run_state.replaceAll("-", " ")}</span>
                          <h4 className="mt-1 text-lg font-semibold text-slate-900">{activity.title}</h4>
                          <p className="mt-1 text-sm text-slate-600">
                            {formatMoment(activity.start_at, activity.timezone, { hour: "numeric", minute: "2-digit" })}
                            {"–"}
                            {formatMoment(activity.end_at, activity.timezone, { hour: "numeric", minute: "2-digit" })}
                          </p>
                          <p className="mt-1 text-sm text-slate-600">
                            {activity.location_tba ? "Location to be announced" : [activity.venue_name, activity.venue_detail, activity.venue_address].filter(Boolean).join(" · ") || "Venue to be announced"}
                          </p>
                        </div>
                        <div className="text-sm text-slate-600">
                          <p><Users className="mr-1 inline h-4 w-4" />{activity.attendance?.coming || 0} coming</p>
                          <p>{activity.attendance?.maybe || 0} maybe</p>
                        </div>
                      </div>
                      {activity.description ? <p className="mt-3 text-sm leading-6 text-slate-600">{activity.description}</p> : null}
                      {activity.notes ? <p className="mt-2 text-sm text-slate-700"><strong>Know before you go:</strong> {activity.notes}</p> : null}
                      {activity.rsvp_deadline ? (
                        <p className="mt-2 text-xs text-slate-500">
                          Activity response deadline: {formatMoment(activity.rsvp_deadline, activity.timezone, {
                            month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
                          })}
                        </p>
                      ) : null}
                      {activity.attendance_requested ? (
                        <fieldset className="mt-4">
                          <legend className="sr-only">Response for {activity.title}</legend>
                          <div className="flex flex-wrap gap-2">
                            {ACTIVITY_OPTIONS.map((option) => (
                              <button
                                aria-pressed={activityResponses[activity.id] === option.value}
                                className={`rounded-full border px-4 py-2 text-sm font-semibold ${activityResponses[activity.id] === option.value ? "border-rose-600 bg-rose-600 text-white" : "border-slate-300 text-slate-800"}`}
                                disabled={!activity.response_open}
                                key={option.value}
                                onClick={() => setActivityResponses((current) => ({ ...current, [activity.id]: option.value }))}
                                type="button"
                              >
                                {option.label}
                              </button>
                            ))}
                          </div>
                          {!activity.response_open ? <p className="mt-2 text-sm text-amber-800">This activity’s response deadline has passed. Your saved choice remains visible.</p> : null}
                        </fieldset>
                      ) : <p className="mt-4 text-sm text-slate-500">No separate attendance response requested.</p>}
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="mt-6 flex justify-center gap-3">
            <button className="rounded-full border border-slate-300 px-5 py-3 font-semibold text-slate-800" onClick={() => setStep(1)} type="button">Back</button>
            <button className="rounded-full bg-rose-600 px-5 py-3 font-semibold text-white" onClick={() => setStep(3)} type="button">Review response</button>
          </div>
        </section>
      ) : null}

      {!saved && step === 3 ? (
        <section data-testid="public-rsvp-summary">
          <h2 className="text-2xl font-semibold text-slate-900">Review your response</h2>
          <div className="mx-auto mt-5 max-w-xl rounded-2xl bg-slate-50 p-5 text-left">
            <p><strong>Overall:</strong> {OVERALL_OPTIONS.find((option) => option.value === overall)?.label}</p>
            {activities.length ? <p className="mt-2"><strong>Activities:</strong> {comingCount} coming · {Object.values(activityResponses).filter((value) => value === "maybe").length} maybe · {Object.values(activityResponses).filter((value) => value === "not-coming").length} not coming</p> : null}
            <label className="mt-4 block">
              <span className="font-semibold">Additional people in your party</span>
              <input className="mt-2 block w-full rounded-xl border border-slate-300 px-3 py-2" min={0} onChange={(event) => setGuests(event.target.value)} type="number" value={guests} />
            </label>
          </div>
          {comingCount > 0 && overall !== "going" && overall !== "some" ? (
            <p className="mx-auto mt-4 max-w-xl rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              You selected at least one activity. Consider “Attending some activities,” but your explicit overall choice will not be changed automatically.
            </p>
          ) : null}
          {everyActivityDeclined && overall !== "not-going" ? (
            <div className="mx-auto mt-4 max-w-xl rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              <p>You declined every activity. Should your overall response be “Unable to attend”?</p>
              <button className="mt-2 font-semibold underline" onClick={() => setOverall("not-going")} type="button">Yes, update overall response</button>
            </div>
          ) : null}
          {error ? <p className="mt-4 text-base text-rose-600">{error}</p> : null}
          <div className="mt-6 flex justify-center gap-3">
            <button className="rounded-full border border-slate-300 px-5 py-3 font-semibold text-slate-800" onClick={() => setStep(activities.length ? 2 : 1)} type="button">Back</button>
            <button className="rounded-full bg-rose-600 px-6 py-3 font-semibold text-white disabled:opacity-50" data-testid="public-rsvp-submit" disabled={saving || !overall} onClick={submit} type="button">
              {saving ? "Saving…" : "Save my response"}
            </button>
          </div>
        </section>
      ) : null}

      <section className="mt-8 rounded-2xl border border-slate-200 bg-white px-5 py-5 text-left">
        <p className="text-sm font-semibold text-slate-900">Private by design</p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          This invitation link shows only this reunion, aggregate activity counts, and your response. It does not expose email addresses, phone numbers, minors’ details, private notes, the full guest list, or a public profile.
        </p>
      </section>

      <div className="mt-5 text-sm text-slate-500">
        <p>No account or app is required to respond. Want family chat, photos, stories, and ongoing access?</p>
        <a
          className="mt-2 inline-flex font-semibold text-rose-700 underline"
          data-testid="public-rsvp-account-link"
          href="/login?intent=guest"
          onClick={() => trackReunionEvent("guest_account_started", { source: "public_rsvp" })}
        >
          Sign in or start an account
        </a>
        <span className="mx-2">·</span>
        <a className="font-medium text-rose-600 underline" href={APP_STORE_URL} rel="noopener noreferrer" target="_blank">Mobile app</a>
        <p className="mt-2 text-xs leading-5">New guests still need a private community invitation from the organizer.</p>
      </div>
    </>
  );
};

export default PublicRSVPPage;
