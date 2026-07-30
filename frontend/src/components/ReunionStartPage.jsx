import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Eye,
  HandHelping,
  LockKeyhole,
  MapPin,
  MessageCircleHeart,
  Soup,
  Users,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest, formatDateTime } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import {
  clearReunionDraft,
  loadReunionDraft,
  provisionalCommunityName,
  reunionDayCount,
  reunionDraftIsComplete,
  reunionDraftToEventPayload,
  saveReunionDraft,
} from "@/lib/reunionDraft";
import { toast } from "@/components/ui/sonner";

const draftChecklist = [
  "Confirm the date and location",
  "Invite the first family members",
  "Open potluck and volunteer sign-ups",
  "Choose a family story to collect",
];

export const ReunionInvitePreview = ({ draft, activities = [], compact = false }) => {
  const when = draft?.approximate_date
    ? formatDateTime(new Date(`${draft.approximate_date}T12:00:00`).toISOString())
    : "Date to be confirmed";
  const through = draft?.end_date && draft.end_date !== draft.approximate_date
    ? formatDateTime(new Date(`${draft.end_date}T12:00:00`).toISOString())
    : "";
  const dayCount = reunionDayCount(draft);
  const publishedActivities = activities.filter((activity) => activity.visibility === "published");
  const featuredActivity = publishedActivities.find((activity) => activity.featured) || publishedActivities[0];

  return (
    <section
      aria-label="Invitation preview"
      className={`rounded-[28px] border border-amber-200 bg-gradient-to-b from-amber-50 to-rose-50 text-slate-900 shadow-sm ${compact ? "p-5" : "p-6 sm:p-8"}`}
      data-testid="reunion-invitation-preview"
    >
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-700">Private family invitation</p>
      <p className="mt-3 text-sm text-slate-600">You’re invited by {draft.organizer_name || "your family organizer"}</p>
      <h2 className="mt-2 font-display text-3xl leading-tight text-slate-950">{draft.gathering_name || "Your family reunion"}</h2>
      <div className="mt-5 space-y-2 text-sm text-slate-700">
        <p className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-rose-700" />
          {through ? `${when} through ${through}` : when}
        </p>
        <p className="flex items-center gap-2"><MapPin className="h-4 w-4 text-rose-700" /> {draft.location || "Location to be confirmed"}</p>
        {dayCount > 1 ? <p>{dayCount} days · Full activity schedule available from this invitation</p> : null}
        {publishedActivities.length ? (
          <p>{publishedActivities.length} planned activit{publishedActivities.length === 1 ? "y" : "ies"}</p>
        ) : null}
        {featuredActivity ? <p><strong>Featured:</strong> {featuredActivity.title}</p> : null}
      </div>
      <div className="mt-6 rounded-2xl bg-white/80 p-4 text-left">
        <p className="font-semibold">Will you be there?</p>
        <div className="mt-3 grid grid-cols-3 gap-2" aria-hidden="true">
          {["I’m coming", "Maybe", "Can’t make it"].map((label) => (
            <span className="rounded-full border border-slate-200 bg-white px-2 py-2 text-center text-xs font-semibold" key={label}>{label}</span>
          ))}
        </div>
      </div>
      <p className="mt-5 text-xs leading-5 text-slate-600">
        This invitation-only link shows the gathering schedule, aggregate activity counts, and only the recipient’s responses. It does not expose contact details, the full guest list, or create an account.
      </p>
    </section>
  );
};

export const ReunionStartPage = ({ onSessionRefresh, session }) => {
  const navigate = useNavigate();
  const [draft, setDraft] = useState(() => loadReunionDraft());
  const [hasDraft, setHasDraft] = useState(() => reunionDraftIsComplete(loadReunionDraft()));
  const [showPreview, setShowPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const canActivateOrganizer = Boolean(session?.token && !session?.user?.community_id);
  const canPersist = canActivateOrganizer || ["host", "organizer"].includes(session?.user?.role);

  const dateLabel = useMemo(() => {
    if (!draft.approximate_date) return "Choose an approximate date";
    return formatDateTime(new Date(`${draft.approximate_date}T12:00:00`).toISOString());
  }, [draft.approximate_date]);

  const update = (key, value) => setDraft((current) => ({ ...current, [key]: value }));

  const toggleMultiday = () => {
    setDraft((current) => {
      const enabled = !current.multiday_enabled;
      if (enabled) {
        trackReunionEvent("reunion_multiday_enabled", {
          reunion_days: current.end_date ? reunionDayCount(current) : 1,
        });
      }
      return {
        ...current,
        multiday_enabled: enabled,
        end_date: enabled ? current.end_date : "",
      };
    });
  };

  const createDraft = (event) => {
    event.preventDefault();
    if (!reunionDraftIsComplete(draft)) {
      toast.error("Check the reunion date range and enter a valid IANA timezone.");
      return;
    }
    const saved = saveReunionDraft(draft);
    setDraft(saved);
    setHasDraft(true);
    setShowPreview(false);
    trackReunionEvent("reunion_draft_created", { source: "public_reunion_start" });
  };

  const previewInvitation = () => {
    setShowPreview(true);
    trackReunionEvent("reunion_preview_viewed", { source: "public_reunion_start" });
  };

  const persistDraft = async () => {
    if (!session?.token || !canPersist) return;
    setSaving(true);
    try {
      let activeSession = session;
      if (canActivateOrganizer) {
        activeSession = await apiRequest("/auth/onboarding/complete", {
          method: "POST",
          token: session.token,
          data: {
            full_name: draft.organizer_name,
            community_name: provisionalCommunityName(draft),
            community_type: "family reunion",
            location: draft.location,
          },
        });
        onSessionRefresh?.(activeSession);
        trackReunionEvent("organizer_intent_confirmed", { source: "reunion_start" });
      }
      const event = await apiRequest("/events", {
        method: "POST",
        token: activeSession.token,
        data: reunionDraftToEventPayload(draft),
      });
      clearReunionDraft();
      trackReunionEvent("reunion_saved", { source: "authenticated_reunion_start" });
      navigate(`/reunion/activate/${event.id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to save this reunion draft.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-canvas min-h-screen py-6 sm:py-10" data-ph-no-capture="true">
      <main className="page-section">
        <Link className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline" to="/">
          <ArrowLeft className="h-4 w-4" /> Back to Kindred
        </Link>

        <div className="mt-6 grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <section className="archival-card h-fit" data-testid="reunion-draft-form-card">
            <p className="eyebrow-text">Start with the gathering</p>
            <h1 className="mt-3 font-display text-4xl leading-tight text-foreground sm:text-5xl">
              Make the reunion real in a few minutes.
            </h1>
            <p className="mt-4 text-sm leading-7 text-muted-foreground sm:text-base">
              Draft first. Preview exactly what family will see. Create an account only when you’re ready to save and share.
            </p>

            <form className="mt-7 grid gap-4" onSubmit={createDraft}>
              <label>
                <span className="field-label">Reunion or gathering name</span>
                <Input
                  autoComplete="off"
                  className="field-input"
                  data-testid="reunion-name-input"
                  maxLength={120}
                  onChange={(event) => update("gathering_name", event.target.value)}
                  placeholder="The Johnson Family Reunion"
                  required
                  value={draft.gathering_name}
                />
              </label>
              <label>
                <span className="field-label">Approximate date</span>
                <Input
                  className="field-input"
                  data-testid="reunion-date-input"
                  onChange={(event) => update("approximate_date", event.target.value)}
                  required
                  type="date"
                  value={draft.approximate_date}
                />
              </label>
              <button
                aria-expanded={draft.multiday_enabled}
                className="flex w-full items-center justify-between rounded-2xl border border-border bg-background px-4 py-3 text-left text-sm font-semibold text-foreground"
                data-testid="reunion-multiday-toggle"
                onClick={toggleMultiday}
                type="button"
              >
                <span>Add multiple days or activities</span>
                <span aria-hidden="true">{draft.multiday_enabled ? "−" : "+"}</span>
              </button>
              {draft.multiday_enabled ? (
                <label>
                  <span className="field-label">Optional end date</span>
                  <Input
                    className="field-input"
                    data-testid="reunion-end-date-input"
                    min={draft.approximate_date || undefined}
                    onChange={(event) => update("end_date", event.target.value)}
                    type="date"
                    value={draft.end_date}
                  />
                </label>
              ) : null}
              <label>
                <span className="field-label">Primary timezone</span>
                <Input
                  autoComplete="off"
                  className="field-input"
                  data-testid="reunion-timezone-input"
                  list="reunion-timezones"
                  maxLength={80}
                  onChange={(event) => update("timezone", event.target.value)}
                  placeholder="America/Los_Angeles"
                  required
                  value={draft.timezone}
                />
                <datalist id="reunion-timezones">
                  <option value="America/Los_Angeles" />
                  <option value="America/Denver" />
                  <option value="America/Chicago" />
                  <option value="America/New_York" />
                  <option value="Europe/London" />
                  <option value="Africa/Lagos" />
                  <option value="Africa/Nairobi" />
                  <option value="UTC" />
                </datalist>
              </label>
              <label>
                <span className="field-label">Organizer name</span>
                <Input
                  autoComplete="name"
                  className="field-input"
                  data-testid="reunion-organizer-input"
                  maxLength={100}
                  onChange={(event) => update("organizer_name", event.target.value)}
                  placeholder="How invitees will know who invited them"
                  required
                  value={draft.organizer_name}
                />
              </label>
              <label>
                <span className="field-label">Location <span className="font-normal text-muted-foreground">(optional)</span></span>
                <Input
                  autoComplete="off"
                  className="field-input"
                  data-testid="reunion-location-input"
                  maxLength={160}
                  onChange={(event) => update("location", event.target.value)}
                  placeholder="Oakland, California — or decide later"
                  value={draft.location}
                />
              </label>
              <Button className="rounded-full py-6 text-base" data-testid="reunion-create-draft-button" type="submit">
                Build my reunion draft <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </form>

            <div className="mt-6 flex items-start gap-3 rounded-2xl border border-border/70 bg-muted/40 p-4">
              <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <p className="text-xs leading-5 text-muted-foreground">
                Before sign-in, this draft stays only in this browser. It is not shareable and is not sent to Kindred’s servers.
              </p>
            </div>
          </section>

          <section className="space-y-6" aria-live="polite">
            {!hasDraft ? (
              <div className="archival-card" data-testid="reunion-draft-empty-state">
                <p className="eyebrow-text">What appears next</p>
                <h2 className="mt-3 font-display text-3xl text-foreground">A useful planning space—not another setup questionnaire.</h2>
                <div className="mt-6 grid gap-4 sm:grid-cols-2">
                  {[
                    [ClipboardList, "A reunion checklist"],
                    [Users, "A clear RSVP area"],
                    [Soup, "Potluck coordination"],
                    [HandHelping, "Volunteer roles"],
                    [MessageCircleHeart, "One family memory prompt"],
                  ].map(([Icon, label]) => (
                    <div className="soft-panel flex items-center gap-3" key={label}>
                      <Icon className="h-5 w-5 text-primary" />
                      <p className="text-sm font-semibold text-foreground">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <div className="archival-card" data-testid="reunion-draft-workspace">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="eyebrow-text">Draft ready</p>
                      <h2 className="mt-2 font-display text-3xl text-foreground">{draft.gathering_name}</h2>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {dateLabel}
                        {draft.end_date ? ` through ${draft.end_date}` : ""}
                        {" · "}
                        {draft.timezone}
                        {" · "}
                        {draft.location || "Location to be confirmed"}
                      </p>
                    </div>
                    <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">Private browser draft</span>
                  </div>

                  <div className="mt-6 grid gap-4 lg:grid-cols-2">
                    <div className="soft-panel">
                      <p className="flex items-center gap-2 font-semibold"><ClipboardList className="h-4 w-4 text-primary" /> Planning checklist</p>
                      <ul className="mt-3 space-y-3">
                        {draftChecklist.map((item) => (
                          <li className="flex items-start gap-2 text-sm text-muted-foreground" key={item}>
                            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="soft-panel">
                      <p className="flex items-center gap-2 font-semibold"><Users className="h-4 w-4 text-primary" /> RSVP</p>
                      <p className="mt-3 text-sm text-muted-foreground">0 invited · 0 coming · 0 waiting</p>
                      <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full w-0 bg-primary" /></div>
                    </div>
                    <div className="soft-panel">
                      <p className="flex items-center gap-2 font-semibold"><Soup className="h-4 w-4 text-primary" /> Shared table</p>
                      <p className="mt-3 text-sm text-muted-foreground">Main dish · Side dish · Dessert or drinks</p>
                    </div>
                    <div className="soft-panel">
                      <p className="flex items-center gap-2 font-semibold"><HandHelping className="h-4 w-4 text-primary" /> Volunteers</p>
                      <p className="mt-3 text-sm text-muted-foreground">Welcome team · Photo and story team</p>
                    </div>
                  </div>

                  <div className="mt-4 rounded-2xl border border-primary/20 bg-primary/5 p-4">
                    <p className="flex items-center gap-2 font-semibold"><MessageCircleHeart className="h-4 w-4 text-primary" /> First memory prompt</p>
                    <p className="mt-2 text-sm text-muted-foreground">What family story should every younger cousin know?</p>
                  </div>

                  <div className="mt-6 flex flex-wrap gap-3">
                    <Button data-testid="reunion-preview-button" onClick={previewInvitation} type="button" variant="outline">
                      <Eye className="mr-2 h-4 w-4" /> Preview invitation
                    </Button>
                    {session?.token && canPersist ? (
                      <Button data-testid="reunion-save-button" disabled={saving} onClick={persistDraft} type="button">
                        {saving ? "Saving…" : "Save and create invitation"}
                      </Button>
                    ) : (
                      <Button asChild data-testid="reunion-account-boundary-link">
                        <Link to="/login?intent=reunion">Save and create invitation <ArrowRight className="ml-2 h-4 w-4" /></Link>
                      </Button>
                    )}
                  </div>
                  {session?.token && !canPersist ? (
                    <p className="mt-3 text-sm text-muted-foreground">A host or organizer role is required to save a new gathering.</p>
                  ) : null}
                </div>

                {showPreview ? <ReunionInvitePreview draft={draft} /> : null}
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
};

export default ReunionStartPage;
