import { useCallback, useEffect, useState } from "react";
import { BellRing, Megaphone, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import { apiRequest, errorDetail } from "@/lib/api";
import {
  DEFAULT_OFFSETS,
  OFFSET_PRESETS,
  audienceSummary,
  buildOverrides,
  choicesFromSettings,
  dayLabel,
  deliveryLine,
  describeOffsets,
  readinessNotes,
  sendTimeLabel,
  toggleOffset,
} from "@/lib/eventMessaging";

const fieldClass =
  "w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary";

const OffsetPicker = ({ offsets, onChange, testId }) => (
  <div className="flex flex-wrap gap-2" data-testid={testId}>
    {OFFSET_PRESETS.map((preset) => {
      const active = offsets.includes(preset.minutes);
      return (
        <button
          aria-pressed={active}
          className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
            active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted/60"
          }`}
          data-testid={`${testId}-${preset.minutes}`}
          key={preset.minutes}
          onClick={() => onChange(toggleOffset(offsets, preset.minutes))}
          type="button"
        >
          {preset.label}
        </button>
      );
    })}
  </div>
);

export const AnnouncementComposer = ({ event, messaging, token, onSent }) => {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState("everyone");
  const [day, setDay] = useState("");
  const [activityId, setActivityId] = useState("");
  const [email, setEmail] = useState(true);
  const [push, setPush] = useState(true);
  const [preview, setPreview] = useState(null);
  const [sending, setSending] = useState(false);

  const days = messaging?.days || [];
  const activities = messaging?.activities || [];
  const targetMissing = (audience === "day" && !day) || (audience === "activity" && !activityId);

  useEffect(() => {
    if (targetMissing) {
      setPreview(null);
      return undefined;
    }
    let cancelled = false;
    apiRequest(`/events/${event.id}/announcements/audience`, {
      method: "POST",
      token,
      data: { audience, day, activity_id: activityId },
    })
      .then((result) => !cancelled && setPreview(result))
      .catch(() => !cancelled && setPreview(null));
    return () => {
      cancelled = true;
    };
  }, [activityId, audience, day, event.id, targetMissing, token]);

  const handleSend = async () => {
    setSending(true);
    try {
      const channels = [email ? "email" : null, push ? "push" : null].filter(Boolean);
      await apiRequest("/announcements", {
        method: "POST",
        token,
        timeout: 60000,
        data: { title, body, scope: "courtyard", event_id: event.id, audience, day, activity_id: activityId, channels },
      });
      toast.success("Announcement sent.");
      setTitle("");
      setBody("");
      onSent?.();
    } catch (error) {
      toast.error(errorDetail(error, "Unable to send that announcement."));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="announcement-composer">
      <input
        aria-label="Announcement title"
        className={fieldClass}
        data-testid="announcement-title"
        maxLength={160}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title, e.g. Parking for day two"
        value={title}
      />
      <textarea
        aria-label="Announcement message"
        className={`${fieldClass} min-h-[110px]`}
        data-testid="announcement-body"
        maxLength={5000}
        onChange={(e) => setBody(e.target.value)}
        placeholder="What should people know?"
        value={body}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm font-medium text-foreground">
          Send to
          <select
            className={`${fieldClass} mt-1`}
            data-testid="announcement-audience"
            onChange={(e) => setAudience(e.target.value)}
            value={audience}
          >
            <option value="everyone">Everyone invited</option>
            <option disabled={!days.length} value="day">People coming on one day</option>
            <option disabled={!activities.length} value="activity">People coming to one activity</option>
          </select>
        </label>
        {audience === "day" ? (
          <label className="block text-sm font-medium text-foreground">
            Day
            <select className={`${fieldClass} mt-1`} data-testid="announcement-day" onChange={(e) => setDay(e.target.value)} value={day}>
              <option value="">Choose a day</option>
              {days.map((d) => (
                <option key={d.day} value={d.day}>
                  {dayLabel(d.day)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {audience === "activity" ? (
          <label className="block text-sm font-medium text-foreground">
            Activity
            <select
              className={`${fieldClass} mt-1`}
              data-testid="announcement-activity"
              onChange={(e) => setActivityId(e.target.value)}
              value={activityId}
            >
              <option value="">Choose an activity</option>
              {activities.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.title}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-foreground">
        <span className="text-muted-foreground">In the app, plus:</span>
        <label className="flex items-center gap-2">
          <input checked={email} data-testid="announcement-email" onChange={(e) => setEmail(e.target.checked)} type="checkbox" />
          Email
        </label>
        <label className="flex items-center gap-2">
          <input checked={push} data-testid="announcement-push" onChange={(e) => setPush(e.target.checked)} type="checkbox" />
          Push notification
        </label>
      </div>
      <p className="text-xs leading-5 text-muted-foreground" data-testid="announcement-audience-summary">
        {targetMissing ? "Choose who this goes to." : audienceSummary(preview)}
      </p>
      <Button
        className="w-full rounded-full"
        data-testid="announcement-send"
        disabled={sending || !title.trim() || targetMissing || (preview && !preview.recipients)}
        onClick={handleSend}
        type="button"
      >
        <Send className="mr-2 h-4 w-4" />
        {sending ? "Sending…" : "Send announcement"}
      </Button>
    </div>
  );
};

export const ReminderSettings = ({ event, messaging, token, onSaved }) => {
  const settings = messaging.settings;
  const [senderName, setSenderName] = useState(settings.sender_name || "");
  const [replyTo, setReplyTo] = useState(settings.reply_to_user_id || "");
  const [enabled, setEnabled] = useState(settings.reminders_enabled !== false);
  const [defaults, setDefaults] = useState(settings.default_reminder_offsets_minutes || DEFAULT_OFFSETS);
  const [choices, setChoices] = useState(() =>
    choicesFromSettings(messaging.activities, settings.activity_reminder_offsets_minutes || {})
  );
  const [saving, setSaving] = useState(false);

  const setChoice = (activityId, next) => setChoices((current) => ({ ...current, [activityId]: { ...current[activityId], ...next } }));

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await apiRequest(`/events/${event.id}/messaging`, {
        method: "PUT",
        token,
        data: {
          sender_name: senderName,
          reply_to_user_id: replyTo,
          reminders_enabled: enabled,
          default_reminder_offsets_minutes: defaults,
          activity_reminder_offsets_minutes: buildOverrides(choices),
        },
      });
      toast.success("Message settings saved.");
      onSaved?.(result);
    } catch (error) {
      toast.error(errorDetail(error, "Unable to save those settings."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="reminder-settings">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm font-medium text-foreground">
          Sender name
          <input
            className={`${fieldClass} mt-1`}
            data-testid="messaging-sender-name"
            maxLength={64}
            onChange={(e) => setSenderName(e.target.value)}
            placeholder={messaging.default_sender_name || "Your name"}
            value={senderName}
          />
        </label>
        <label className="block text-sm font-medium text-foreground">
          Replies go to
          <select
            className={`${fieldClass} mt-1`}
            data-testid="messaging-reply-to"
            onChange={(e) => setReplyTo(e.target.value)}
            value={replyTo}
          >
            {(messaging.reply_to_options || []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.name ? `${o.name} (${o.email})` : o.email}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        Emails show this name and come from Kindred's address, so they reach inboxes reliably. Replies go to the
        organizer you choose.
      </p>

      <label className="flex items-center gap-2 text-sm font-medium text-foreground">
        <input checked={enabled} data-testid="messaging-reminders-enabled" onChange={(e) => setEnabled(e.target.checked)} type="checkbox" />
        Remind people before each activity they're coming to
      </label>
      {enabled ? (
        <>
          <div>
            <p className="mb-2 text-sm text-foreground">Default reminder times</p>
            <OffsetPicker offsets={defaults} onChange={setDefaults} testId="messaging-default-offsets" />
          </div>
          {messaging.activities.length ? (
            <ul className="space-y-2" data-testid="messaging-activity-list">
              {messaging.activities.map((activity) => {
                const choice = choices[activity.id] || { mode: "default", offsets: [] };
                return (
                  <li className="rounded-xl border border-border/60 px-3 py-2" key={activity.id}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium text-foreground">{activity.title}</span>
                      <select
                        aria-label={`Reminders for ${activity.title}`}
                        className="rounded-lg border border-border bg-background px-2 py-1 text-xs"
                        data-testid={`messaging-activity-mode-${activity.id}`}
                        onChange={(e) =>
                          setChoice(activity.id, {
                            mode: e.target.value,
                            offsets: e.target.value === "custom" && !choice.offsets.length ? defaults : choice.offsets,
                          })
                        }
                        value={choice.mode}
                      >
                        <option value="default">Default ({describeOffsets(defaults)})</option>
                        <option value="custom">Custom</option>
                        <option value="off">No reminders</option>
                      </select>
                    </div>
                    {choice.mode === "custom" ? (
                      <div className="mt-2">
                        <OffsetPicker
                          offsets={choice.offsets}
                          onChange={(offsets) => setChoice(activity.id, { offsets })}
                          testId={`messaging-activity-offsets-${activity.id}`}
                        />
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">Publish activities with a start time to schedule reminders.</p>
          )}
        </>
      ) : null}
      <Button className="w-full rounded-full" data-testid="messaging-save" disabled={saving} onClick={handleSave} type="button" variant="secondary">
        {saving ? "Saving…" : "Save message settings"}
      </Button>
    </div>
  );
};

export const EventMessaging = ({ event, token }) => {
  const isDraft = event.publication_state === "organizer_draft";
  const [messaging, setMessaging] = useState(null);
  const [sent, setSent] = useState([]);

  const load = useCallback(async () => {
    try {
      const [settings, history] = await Promise.all([
        apiRequest(`/events/${event.id}/messaging`, { token }),
        apiRequest(`/events/${event.id}/announcements`, { token }),
      ]);
      setMessaging(settings);
      setSent(history.announcements || []);
    } catch {
      setMessaging(null);
    }
  }, [event.id, token]);

  useEffect(() => {
    if (!isDraft) load();
  }, [isDraft, load]);

  const notes = readinessNotes(messaging?.delivery);

  return (
    <div className="soft-panel" data-testid="event-messaging-panel">
      <div className="flex items-center gap-3">
        <Megaphone className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">Announcements & reminders</p>
      </div>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        Send an update to everyone, one day, or one activity's attendees. Reminders go automatically to people coming to
        each activity.
      </p>

      {isDraft ? (
        <p className="mt-3 text-xs leading-5 text-muted-foreground" data-testid="event-messaging-draft-guard">
          Finish the private organizer checklist before messaging attendees.
        </p>
      ) : !messaging ? (
        <p className="mt-3 text-xs text-muted-foreground">Loading…</p>
      ) : (
        <>
          {notes.length ? (
            <ul className="mt-3 space-y-1 text-xs leading-5 text-amber-700" data-testid="event-messaging-readiness">
              {notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
          <div className="mt-4">
            <AnnouncementComposer event={event} messaging={messaging} onSent={load} token={token} />
          </div>

          {sent.length ? (
            <div className="mt-6 border-t border-border/60 pt-4">
              <p className="text-sm font-semibold text-foreground">Sent</p>
              <ul className="mt-2 space-y-2" data-testid="event-messaging-sent">
                {sent.map((item) => (
                  <li className="rounded-xl border border-border/60 px-3 py-2 text-sm" key={item.id}>
                    <p className="font-medium text-foreground">{item.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {item.audience_label} · {deliveryLine(item.delivery_summary)}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mt-6 border-t border-border/60 pt-4">
            <div className="mb-3 flex items-center gap-3">
              <BellRing className="h-4 w-4 text-primary" />
              <p className="text-sm font-semibold text-foreground">Sender & reminders</p>
            </div>
            <ReminderSettings event={event} key={JSON.stringify(messaging.settings)} messaging={messaging} onSaved={setMessaging} token={token} />
            {messaging.upcoming_reminders?.length ? (
              <div className="mt-4" data-testid="event-messaging-upcoming">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Next reminders</p>
                <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                  {messaging.upcoming_reminders.slice(0, 6).map((r) => (
                    <li key={`${r.activity_id}-${r.offset_minutes}`}>
                      {sendTimeLabel(r.send_at)} · {r.activity_title}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
};

export default EventMessaging;
