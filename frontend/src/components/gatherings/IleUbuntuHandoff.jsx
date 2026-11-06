import { useCallback, useEffect, useState } from "react";
import { GraduationCap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import { apiRequest, errorDetail } from "@/lib/api";

// X2: after an event ends, send the people marked "coming" to the matching
// Ile Ubuntu courses. Ile Ubuntu creates their accounts, enrolls them and
// emails each a sign-in link, so nobody needs a shared login.

const serverMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  return detail?.message || errorDetail(error, fallback);
};

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

export const reportLines = (result) => {
  if (!result) return [];
  const local = result.local || {};
  const lines = [plural(local.sending || 0, "person", "people") + " marked coming for a matched activity"];
  if (local.no_email) lines.push(`${plural(local.no_email, "person", "people")} left out: no email on file`);
  if (local.not_registered) lines.push(`${plural(local.not_registered, "answer", "answers")} from invitations no longer active`);
  const counts = result.report?.counts;
  if (counts) {
    const verb = result.dry_run ? "would be" : "";
    lines.push(`${plural(counts.created || 0, "new account", "new accounts")} ${verb ? `${verb} created` : "created"}`);
    lines.push(`${plural(counts.enrolled || 0, "enrollment", "enrollments")} ${verb ? `${verb} added` : "added"}`);
    if (counts.skipped) lines.push(`${plural(counts.skipped, "enrollment", "enrollments")} already in place`);
    if (counts.errors) lines.push(`${plural(counts.errors, "row", "rows")} Ile Ubuntu couldn't use`);
    if (!result.dry_run) {
      lines.push(`${plural(result.report.welcome_emails || 0, "welcome email", "welcome emails")} with a sign-in link`);
    }
  }
  return lines;
};

export const IleUbuntuHandoff = ({ event, token }) => {
  const eventId = event?.id;
  const [state, setState] = useState(null);
  const [key, setKey] = useState("");
  const [courseMap, setCourseMap] = useState({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const apply = (payload) => {
    setState(payload);
    setCourseMap(payload.course_map || {});
  };

  const load = useCallback(async () => {
    if (!eventId || !token) return;
    try {
      apply(await apiRequest(`/events/${eventId}/ile-ubuntu-handoff`, { token }));
    } catch {
      setState(null);
    }
  }, [eventId, token]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const data = { course_map: courseMap };
      if (key.trim()) data.connection_key = key.trim();
      apply(await apiRequest(`/events/${eventId}/ile-ubuntu-handoff`, { method: "PUT", token, data }));
      setKey("");
      toast.success("Saved.");
    } catch (err) {
      setError(serverMessage(err, "Unable to save."));
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm("Remove the Ile Ubuntu connection key from this event?")) return;
    setBusy(true);
    setError("");
    try {
      apply(await apiRequest(`/events/${eventId}/ile-ubuntu-handoff/connection`, { method: "DELETE", token }));
      setResult(null);
    } catch (err) {
      setError(serverMessage(err, "Unable to remove the connection."));
    } finally {
      setBusy(false);
    }
  };

  const send = async (dryRun) => {
    if (!dryRun && !window.confirm(
      "Send everyone marked coming to the matched Ile Ubuntu courses? Each new person gets a welcome email with a sign-in link. Sending again later only adds people who are new."
    )) return;
    setBusy(true);
    setError("");
    try {
      const payload = await apiRequest(`/events/${eventId}/ile-ubuntu-handoff/send`, {
        method: "POST",
        token,
        data: { dry_run: dryRun },
        timeout: 90000,
      });
      setResult(payload);
      if (!dryRun) {
        toast.success("Sent to Ile Ubuntu.");
        load();
      }
    } catch (err) {
      setError(serverMessage(err, "Unable to reach Ile Ubuntu."));
    } finally {
      setBusy(false);
    }
  };

  if (!state || !state.configured) return null;

  const mapped = Object.values(courseMap).some(Boolean);
  const savedMapped = Object.values(state.course_map || {}).some(Boolean);
  const dirty = JSON.stringify(courseMap) !== JSON.stringify(state.course_map || {});
  const last = state.last_send;

  return (
    <section aria-labelledby="ile-ubuntu-handoff-heading" className="archival-card" data-testid="ile-ubuntu-handoff">
      <div className="flex items-start gap-3">
        <GraduationCap aria-hidden="true" className="mt-1 h-5 w-5 text-primary" />
        <div className="flex-1">
          <p className="eyebrow-text">After the event</p>
          <h2 className="mt-2 font-display text-2xl" id="ile-ubuntu-handoff-heading">
            Send attendees to Ile Ubuntu
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Match each activity to an Ile Ubuntu course. Everyone marked coming is enrolled in the matching
            courses and gets an email with a sign-in link. Only names and emails are sent.
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {state.connected ? (
          <p className="text-sm">
            Connected{state.teacher_name ? ` to ${state.teacher_name}'s courses` : ""} (key ending {state.key_last4}).{" "}
            <button className="underline" disabled={busy} onClick={disconnect} type="button">
              Remove
            </button>
          </p>
        ) : null}
        <label className="block text-sm font-medium" htmlFor="ile-ubuntu-key">
          {state.connected ? "Replace connection key" : "Connection key from the course's teacher"}
        </label>
        <input
          autoComplete="off"
          className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
          id="ile-ubuntu-key"
          onChange={(e) => setKey(e.target.value)}
          placeholder="kh_…"
          type="password"
          value={key}
        />
        <p className="text-xs text-muted-foreground">
          The teacher creates it on their Ile Ubuntu teaching dashboard under "Receive attendees from Kindred".
        </p>
      </div>

      {state.courses_error ? (
        <p className="mt-3 text-sm text-destructive" role="alert">{state.courses_error}</p>
      ) : null}

      {state.connected && state.courses.length > 0 ? (
        <fieldset className="mt-4">
          <legend className="text-sm font-medium">Match activities to courses</legend>
          <div className="mt-2 space-y-2">
            {state.activities.map((activity) => (
              <div className="grid gap-1 sm:grid-cols-2 sm:items-center" key={activity.id}>
                <label className="text-sm" htmlFor={`ile-course-${activity.id}`}>
                  {activity.title || "Untitled activity"}
                </label>
                <select
                  className="rounded-xl border border-border bg-background px-3 py-2 text-sm"
                  id={`ile-course-${activity.id}`}
                  onChange={(e) => setCourseMap((current) => {
                    const next = { ...current };
                    if (e.target.value) next[activity.id] = e.target.value;
                    else delete next[activity.id];
                    return next;
                  })}
                  value={courseMap[activity.id] || ""}
                >
                  <option value="">Don't send</option>
                  {state.courses.map((course) => (
                    <option key={course.id} value={course.id}>{course.title || course.id}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </fieldset>
      ) : null}

      {error ? <p className="mt-3 text-sm text-destructive" role="alert">{error}</p> : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <Button disabled={busy || (!key.trim() && !dirty)} onClick={save} size="sm" variant="outline">
          Save
        </Button>
        <Button
          disabled={busy || !state.connected || !savedMapped || dirty}
          onClick={() => send(true)}
          size="sm"
          variant="outline"
        >
          Preview
        </Button>
        <Button
          disabled={busy || !state.connected || !savedMapped || dirty || !state.event_ended}
          onClick={() => send(false)}
          size="sm"
        >
          Send attendees to Ile Ubuntu
        </Button>
      </div>
      {state.connected && !state.event_ended ? (
        <p className="mt-2 text-xs text-muted-foreground">You can send once the event has ended. Preview works now.</p>
      ) : null}
      {dirty && mapped ? <p className="mt-2 text-xs text-muted-foreground">Save your matches before sending.</p> : null}

      {result ? (
        <div className="mt-4 rounded-2xl border border-border p-4" data-testid="ile-ubuntu-report" role="status">
          <p className="text-sm font-medium">{result.dry_run ? "Preview — nothing sent yet" : "Sent"}</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {reportLines(result).map((line) => <li key={line}>{line}</li>)}
          </ul>
          {result.report?.errors?.length ? (
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {result.report.errors.slice(0, 20).map((item, i) => (
                <li key={`${item.row}-${i}`}>{item.email ? `${item.email}: ` : ""}{item.error || item.message}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : last ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Last sent {new Date(last.sent_at).toLocaleString()}: {plural(last.counts?.enrolled || 0, "enrollment", "enrollments")} added,
          {" "}{plural(last.welcome_emails || 0, "welcome email", "welcome emails")}.
        </p>
      ) : null}
    </section>
  );
};

export default IleUbuntuHandoff;
