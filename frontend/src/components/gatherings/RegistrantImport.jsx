import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Eye, EyeOff, FileUp, RefreshCw, UserRoundSearch, Webhook } from "lucide-react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import { BACKEND_URL, apiRequest, errorDetail } from "@/lib/api";
import {
  MAX_CSV_BYTES,
  ROW_STATUS_LABELS,
  csvTemplateFor,
  deliverySummary,
  reportSummary,
  sortReportRows,
  webhookUrl,
} from "@/lib/registrantImport";

const copyText = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

const CopyButton = ({ text, label, testId }) => {
  const [copied, setCopied] = useState(false);
  return (
    <button
      aria-label={label}
      className="shrink-0 rounded-full border border-border p-1.5 text-muted-foreground transition hover:bg-muted/60 hover:text-primary"
      data-testid={testId}
      onClick={async () => {
        if (await copyText(text)) {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }
      }}
      title={label}
      type="button"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
};

const statusTone = {
  error: "text-destructive",
  flagged: "text-amber-700",
  created: "text-primary",
  updated: "text-primary",
  skipped: "text-muted-foreground",
};

export const ImportReport = ({ report }) => {
  if (!report) return null;
  const rows = sortReportRows(report.rows);
  const delivery = deliverySummary(report.delivery);
  return (
    <div className="mt-4 rounded-2xl border border-border/70 bg-background/70 p-4" data-testid="registrant-import-report">
      <p className="text-sm font-semibold text-foreground" data-testid="registrant-import-summary">
        {reportSummary(report.counts)}
      </p>
      {delivery ? <p className="mt-1 text-xs text-muted-foreground">{delivery}</p> : null}
      {rows.length ? (
        <ul className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1">
          {rows.map((row) => (
            <li
              className="rounded-xl border border-border/60 px-3 py-2 text-sm"
              data-testid={`registrant-import-row-${row.row}`}
              key={`${row.row}-${row.email}`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium text-foreground">
                  Row {row.row}: {row.name || row.email || "(blank)"}
                  {row.name && row.email ? <span className="font-normal text-muted-foreground"> · {row.email}</span> : null}
                </span>
                <span className={`text-xs font-semibold uppercase tracking-[0.12em] ${statusTone[row.status] || ""}`}>
                  {ROW_STATUS_LABELS[row.status] || row.status}
                </span>
              </div>
              {row.sessions?.length ? (
                <p className="mt-1 text-xs text-muted-foreground">Coming to: {row.sessions.join(", ")}</p>
              ) : null}
              {row.kept_own_answer?.length ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Kept their own answer for: {row.kept_own_answer.join(", ")}
                </p>
              ) : null}
              {row.status === "flagged" ? (
                <p className="mt-1 text-xs text-amber-700">
                  Same name as {row.matched_name} ({row.matched_email}). Review it under Possible duplicates.
                </p>
              ) : row.detail ? (
                <p className="mt-1 text-xs text-muted-foreground">{row.detail}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

export const DuplicateFlags = ({ flags, busyId, onResolve }) => {
  const pending = (flags || []).filter((flag) => flag.status === "pending");
  if (!pending.length) {
    return <p className="mt-2 text-xs text-muted-foreground" data-testid="registrant-flags-empty">No possible duplicates to review.</p>;
  }
  return (
    <ul className="mt-3 space-y-3" data-testid="registrant-flags-list">
      {pending.map((flag) => (
        <li className="rounded-2xl border border-amber-300/70 bg-amber-50/40 p-3 text-sm" data-testid={`registrant-flag-${flag.id}`} key={flag.id}>
          <p className="text-foreground">
            <span className="font-semibold">{flag.name || flag.email}</span> ({flag.email}) has the same name as{" "}
            <span className="font-semibold">{flag.matched_name}</span> ({flag.matched_email}), who is already invited.
          </p>
          {flag.sessions?.length ? (
            <p className="mt-1 text-xs text-muted-foreground">Sessions on this registration: {flag.sessions.join(", ")}</p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              className="h-auto whitespace-normal rounded-full py-1.5 text-left"
              data-testid={`registrant-flag-same-${flag.id}`}
              disabled={busyId === flag.id}
              onClick={() => onResolve(flag, "apply_to_existing")}
              size="sm"
              type="button"
              variant="secondary"
            >
              Same person: add sessions to {flag.matched_name}
            </Button>
            <Button
              className="h-auto whitespace-normal rounded-full py-1.5 text-left"
              data-testid={`registrant-flag-separate-${flag.id}`}
              disabled={busyId === flag.id}
              onClick={() => onResolve(flag, "create_separate")}
              size="sm"
              type="button"
              variant="outline"
            >
              Different people: invite separately
            </Button>
            <Button
              className="h-auto whitespace-normal rounded-full py-1.5 text-left"
              data-testid={`registrant-flag-dismiss-${flag.id}`}
              disabled={busyId === flag.id}
              onClick={() => onResolve(flag, "dismissed")}
              size="sm"
              type="button"
              variant="ghost"
            >
              Ignore this registration
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
};

export const WebhookSettings = ({ hook, busy, onCreateOrRotate }) => {
  const [revealed, setRevealed] = useState(false);
  if (!hook) return null;
  if (!hook.configured) {
    return (
      <div className="mt-3">
        <p className="text-xs leading-5 text-muted-foreground">
          Let your ticketing platform or an automation tool add each new registrant here as they buy. Kindred gives
          this event its own address and secret.
        </p>
        <Button className="mt-3 rounded-full" data-testid="registrant-webhook-create" disabled={busy} onClick={onCreateOrRotate} size="sm" type="button" variant="secondary">
          Create webhook
        </Button>
      </div>
    );
  }
  const url = webhookUrl(BACKEND_URL, hook.path);
  const shownSecret = revealed ? hook.secret : `${hook.secret.slice(0, 10)}${"•".repeat(16)}`;
  return (
    <div className="mt-3 space-y-3" data-testid="registrant-webhook-settings">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Webhook URL</p>
        <div className="mt-1 flex items-center gap-2">
          <code className="flex-1 break-all rounded-lg bg-muted/50 px-2 py-1 text-xs" data-testid="registrant-webhook-url">{url}</code>
          <CopyButton label="Copy webhook URL" testId="registrant-webhook-copy-url" text={url} />
        </div>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Signing secret</p>
        <div className="mt-1 flex items-center gap-2">
          <code className="flex-1 break-all rounded-lg bg-muted/50 px-2 py-1 text-xs" data-testid="registrant-webhook-secret">{shownSecret}</code>
          <button
            aria-label={revealed ? "Hide secret" : "Show secret"}
            className="shrink-0 rounded-full border border-border p-1.5 text-muted-foreground transition hover:bg-muted/60 hover:text-primary"
            data-testid="registrant-webhook-reveal"
            onClick={() => setRevealed((v) => !v)}
            type="button"
          >
            {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
          <CopyButton label="Copy signing secret" testId="registrant-webhook-copy-secret" text={hook.secret} />
        </div>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        Send a JSON POST with <code>name</code>, <code>email</code> and <code>sessions</code> (titles or ids). Sign it
        with the headers <code>X-Kindred-Timestamp</code> (Unix seconds) and <code>X-Kindred-Signature: sha256=</code>
        followed by the hex HMAC-SHA256 of <code>timestamp.body</code> using this secret. Each person receives their
        Kindred invitation.
      </p>
      {hook.last_received_at ? (
        <p className="text-xs text-muted-foreground">Last registrant received {new Date(hook.last_received_at).toLocaleString()}.</p>
      ) : null}
      <Button
        className="rounded-full"
        data-testid="registrant-webhook-rotate"
        disabled={busy}
        onClick={() => {
          if (window.confirm("Replace the secret? Anything still using the old one will stop working.")) onCreateOrRotate();
        }}
        size="sm"
        type="button"
        variant="outline"
      >
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Rotate secret
      </Button>
    </div>
  );
};

export const RegistrantImport = ({ event, token, onUpdate }) => {
  const isDraft = event.publication_state === "organizer_draft";
  const [csvText, setCsvText] = useState("");
  const [fileName, setFileName] = useState("");
  const [sendInvitations, setSendInvitations] = useState(true);
  const [importing, setImporting] = useState(false);
  const [report, setReport] = useState(null);
  const [flags, setFlags] = useState([]);
  const [busyFlagId, setBusyFlagId] = useState("");
  const [hook, setHook] = useState(null);
  const [hookBusy, setHookBusy] = useState(false);

  const loadFlags = useCallback(async () => {
    try {
      const payload = await apiRequest(`/events/${event.id}/registrants/flags`, { token });
      setFlags(payload.flags || []);
    } catch { /* the panel still works without the list */ }
  }, [event.id, token]);

  useEffect(() => {
    if (isDraft) return;
    loadFlags();
    apiRequest(`/events/${event.id}/registrants/webhook`, { token })
      .then(setHook)
      .catch(() => setHook(null));
  }, [event.id, isDraft, loadFlags, token]);

  const refreshEvent = async () => {
    try {
      onUpdate?.(await apiRequest(`/events/${event.id}`, { token }));
    } catch { /* best-effort */ }
  };

  const handleFile = (file) => {
    setReport(null);
    if (!file) return;
    if (file.size > MAX_CSV_BYTES) {
      toast.error("That file is larger than 1 MB. Split it and import each part.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setCsvText(String(reader.result || ""));
      setFileName(file.name);
    };
    reader.readAsText(file);
  };

  const handleImport = async () => {
    setImporting(true);
    try {
      const payload = await apiRequest(`/events/${event.id}/registrants/import`, {
        method: "POST",
        token,
        timeout: 60000,
        data: { csv_text: csvText, send_invitations: sendInvitations },
      });
      setReport(payload);
      toast.success(reportSummary(payload.counts));
      await Promise.all([refreshEvent(), loadFlags()]);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(detail?.message || errorDetail(error, "Unable to import that file."));
    } finally {
      setImporting(false);
    }
  };

  const handleResolve = async (flag, action) => {
    setBusyFlagId(flag.id);
    try {
      const result = await apiRequest(`/events/${event.id}/registrants/flags/${flag.id}/resolve`, {
        method: "POST",
        token,
        data: { action, send_invitation: sendInvitations },
      });
      if (result.row?.status === "error") toast.error(result.row.detail);
      else toast.success(action === "dismissed" ? "Ignored." : "Done.");
      await Promise.all([refreshEvent(), loadFlags()]);
    } catch (error) {
      toast.error(errorDetail(error, "Unable to update that registration."));
      await loadFlags();
    } finally {
      setBusyFlagId("");
    }
  };

  const handleHook = async () => {
    setHookBusy(true);
    try {
      setHook(await apiRequest(`/events/${event.id}/registrants/webhook/rotate`, { method: "POST", token }));
      toast.success("Webhook ready. Copy the URL and secret into your ticketing tool.");
    } catch (error) {
      toast.error(errorDetail(error, "Unable to set up the webhook."));
    } finally {
      setHookBusy(false);
    }
  };

  const templateHref = `data:text/csv;charset=utf-8,${encodeURIComponent(csvTemplateFor(event))}`;
  const pendingFlags = flags.filter((flag) => flag.status === "pending").length;

  return (
    <div className="soft-panel" data-testid="registrant-import-panel">
      <div className="flex items-center gap-3">
        <FileUp className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">Import registrants</p>
      </div>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        Sold tickets somewhere else? Upload the registrant list. Each person gets one invitation and is marked
        coming for the sessions they bought, which also unlocks those sessions' links for them. Uploading the same
        list again changes nothing.
      </p>

      {isDraft ? (
        <p className="mt-3 text-xs leading-5 text-muted-foreground" data-testid="registrant-import-draft-guard">
          Finish the private organizer checklist before importing registrants.
        </p>
      ) : (
        <>
          <div className="mt-4 space-y-3">
            <label className="block text-sm font-medium text-foreground" htmlFor={`registrant-csv-${event.id}`}>
              CSV file with name, email and sessions purchased
            </label>
            <input
              accept=".csv,text/csv,text/plain"
              className="block w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-primary/10 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-primary"
              data-testid="registrant-import-file"
              id={`registrant-csv-${event.id}`}
              onChange={(e) => handleFile(e.target.files?.[0])}
              type="file"
            />
            <p className="text-xs leading-5 text-muted-foreground">
              List several sessions in one cell separated by semicolons, or use one row per ticket. Session names must
              match this event's itinerary.{" "}
              <a className="font-semibold text-primary underline" data-testid="registrant-import-template" download="registrants-template.csv" href={templateHref}>
                Download a template
              </a>
            </p>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                checked={sendInvitations}
                data-testid="registrant-import-send"
                onChange={(e) => setSendInvitations(e.target.checked)}
                type="checkbox"
              />
              Email each person their invitation
            </label>
            <Button
              className="w-full rounded-full"
              data-testid="registrant-import-submit"
              disabled={importing || !csvText}
              onClick={handleImport}
              type="button"
              variant="secondary"
            >
              {importing ? "Importing…" : fileName ? `Import ${fileName}` : "Choose a file to import"}
            </Button>
          </div>
          <ImportReport report={report} />

          <div className="mt-6 border-t border-border/60 pt-4">
            <div className="flex items-center gap-3">
              <UserRoundSearch className="h-4 w-4 text-primary" />
              <p className="text-sm font-semibold text-foreground">
                Possible duplicates{pendingFlags ? ` (${pendingFlags})` : ""}
              </p>
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              When a registrant's name matches someone already invited under another email, Kindred waits for you
              instead of inviting them twice.
            </p>
            <DuplicateFlags busyId={busyFlagId} flags={flags} onResolve={handleResolve} />
          </div>

          <div className="mt-6 border-t border-border/60 pt-4">
            <div className="flex items-center gap-3">
              <Webhook className="h-4 w-4 text-primary" />
              <p className="text-sm font-semibold text-foreground">Webhook</p>
            </div>
            <WebhookSettings busy={hookBusy} hook={hook} onCreateOrRotate={handleHook} />
          </div>
        </>
      )}
    </div>
  );
};
