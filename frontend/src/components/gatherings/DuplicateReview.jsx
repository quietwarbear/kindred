import { useCallback, useEffect, useState } from "react";
import { GitMerge, UserRoundX, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import { apiRequest, errorDetail } from "@/lib/api";

const REASON_LABEL = {
  same_email: "Same email or account",
  same_name: "Same name, different email",
};

const STATUS_LABEL = {
  pending: "No response yet",
  going: "Coming",
  maybe: "Maybe",
  not_going: "Not coming",
  declined: "Not coming",
};

export const mergeSummary = (merge) => {
  if (!merge) return "Merged.";
  const moved = (merge.moved_event_answers || 0) + (merge.moved_activity_answers || 0);
  const parts = [moved === 1 ? "1 answer moved" : `${moved} answers moved`];
  if (merge.overlapping_answers_resolved) parts.push("newest answer kept where both replied");
  if (merge.account_linked) parts.push("account link moved");
  return `Merged: ${parts.join(", ")}.`;
};

const PersonChoice = ({ person, checked, name, onChoose }) => (
  <label
    className={`flex cursor-pointer flex-col gap-1 rounded-xl border p-3 text-sm ${
      checked ? "border-primary bg-primary/5" : "border-border"
    }`}
  >
    <span className="flex items-center gap-2 font-medium">
      <input
        checked={checked}
        name={name}
        onChange={() => onChoose(person.invite_id)}
        type="radio"
        value={person.invite_id}
      />
      {person.name || "Unnamed guest"}
    </span>
    <span className="text-muted-foreground">{person.email || "No email"}</span>
    <span className="text-muted-foreground">
      {STATUS_LABEL[person.rsvp_status] || person.rsvp_status}
      {" · "}
      {person.activity_answers === 1 ? "1 activity answer" : `${person.activity_answers} activity answers`}
      {person.has_account ? " · Has an account" : ""}
    </span>
  </label>
);

const DuplicatePair = ({ pair, busy, onMerge, onDismiss }) => {
  const [keepId, setKeepId] = useState(pair.suggested_keep_invite_id);
  const other = pair.people.find((person) => person.invite_id !== keepId);
  const bothAccounts = pair.people.every((person) => person.has_account);
  const groupName = `keep-${pair.pair_key}`;
  return (
    <li className="rounded-2xl border border-border p-4" data-testid="duplicate-pair">
      <fieldset>
        <legend className="text-sm font-medium">
          {REASON_LABEL[pair.reason] || "Possible duplicate"} — choose the record to keep
        </legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {pair.people.map((person) => (
            <PersonChoice
              checked={keepId === person.invite_id}
              key={person.invite_id}
              name={groupName}
              onChoose={setKeepId}
              person={person}
            />
          ))}
        </div>
      </fieldset>
      {bothAccounts ? (
        <p className="mt-3 text-sm text-muted-foreground" role="note">
          Both people have their own account, so these records can't be merged here.
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          disabled={busy || bothAccounts || !other}
          onClick={() => onMerge(pair, keepId, other.invite_id)}
          size="sm"
        >
          <GitMerge aria-hidden="true" className="mr-2 h-4 w-4" />
          Merge into {pair.people.find((person) => person.invite_id === keepId)?.name || "kept record"}
        </Button>
        <Button disabled={busy} onClick={() => onDismiss(pair)} size="sm" variant="outline">
          <UserRoundX aria-hidden="true" className="mr-2 h-4 w-4" />
          Not the same person
        </Button>
      </div>
    </li>
  );
};

export const DuplicateReview = ({ event, onUpdate, token }) => {
  const [pairs, setPairs] = useState(null);
  const [busy, setBusy] = useState(false);
  const eventId = event?.id;

  const load = useCallback(async () => {
    if (!eventId || !token) return;
    try {
      const payload = await apiRequest(`/events/${eventId}/duplicates`, { token });
      setPairs(payload.pairs || []);
    } catch {
      setPairs([]);
    }
  }, [eventId, token]);

  useEffect(() => {
    load();
  }, [load]);

  const merge = async (pair, keepInviteId, mergeInviteId) => {
    const kept = pair.people.find((person) => person.invite_id === keepInviteId);
    const dropped = pair.people.find((person) => person.invite_id === mergeInviteId);
    const ok = window.confirm(
      `Merge ${dropped?.name || "this record"} into ${kept?.name || "the kept record"}? `
        + "Their answers and contributions move to the kept record, and their old link opens it. This can't be undone."
    );
    if (!ok) return;
    setBusy(true);
    try {
      const payload = await apiRequest(`/events/${eventId}/duplicates/merge`, {
        method: "POST",
        token,
        data: { keep_invite_id: keepInviteId, merge_invite_id: mergeInviteId },
      });
      setPairs(payload.pairs || []);
      toast.success(mergeSummary(payload.merge));
      onUpdate?.(await apiRequest(`/events/${eventId}`, { token }));
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(detail?.message || errorDetail(error, "Unable to merge these records."));
    } finally {
      setBusy(false);
    }
  };

  const dismiss = async (pair) => {
    setBusy(true);
    try {
      const payload = await apiRequest(`/events/${eventId}/duplicates/${pair.pair_key}/dismiss`, {
        method: "POST",
        token,
      });
      setPairs(payload.pairs || []);
      toast.success("Kept as two different people.");
    } catch (error) {
      toast.error(errorDetail(error, "Unable to update that pair."));
    } finally {
      setBusy(false);
    }
  };

  if (!pairs || pairs.length === 0) return null;

  return (
    <section aria-labelledby="duplicate-review-heading" className="archival-card" data-testid="duplicate-review">
      <div className="flex items-start gap-3">
        <Users aria-hidden="true" className="mt-1 h-5 w-5 text-primary" />
        <div className="flex-1">
          <p className="eyebrow-text">Guest list</p>
          <h2 className="mt-2 font-display text-2xl" id="duplicate-review-heading">
            Possible duplicates ({pairs.length})
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            These look like the same person invited twice. Merging keeps one record and moves the other
            one's answers, contributions and invitation link to it.
          </p>
        </div>
      </div>
      <ul className="mt-4 space-y-3">
        {pairs.map((pair) => (
          <DuplicatePair busy={busy} key={pair.pair_key} onDismiss={dismiss} onMerge={merge} pair={pair} />
        ))}
      </ul>
    </section>
  );
};

export default DuplicateReview;
