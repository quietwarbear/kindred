import { useCallback, useEffect, useState } from "react";
import { Check, HandHeart, Plus, Utensils } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const KINDS = [
  { value: "meal-train", label: "Meal train" },
  { value: "check-in", label: "Check-in" },
  { value: "milestone", label: "Milestone" },
  { value: "support", label: "General support" },
];

const KIND_BADGE = {
  "meal-train": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  "check-in": "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  milestone: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
  support: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
};

const initialForm = { kind: "meal-train", title: "", note: "", for_member_id: "", milestone_type: "", slotsText: "" };

export const CarePage = ({ token, user }) => {
  const [circles, setCircles] = useState([]);
  const [members, setMembers] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [careData, memberData] = await Promise.all([
        apiRequest("/care", { token }),
        apiRequest("/community/members", { token }),
      ]);
      setCircles(careData.circles || []);
      setMembers(memberData.members || []);
    } catch {
      toast.error("Unable to load the circle of care.");
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const createCircle = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) { toast.error("Give it a short title."); return; }
    setSubmitting(true);
    try {
      const slots = form.kind === "meal-train"
        ? form.slotsText.split("\n").map((l) => l.trim()).filter(Boolean).map((label) => ({ label, item: "" }))
        : [];
      await apiRequest("/care", {
        method: "POST",
        token,
        data: {
          kind: form.kind,
          title: form.title.trim(),
          note: form.note.trim(),
          for_member_id: form.for_member_id,
          milestone_type: form.kind === "milestone" ? form.milestone_type.trim() : "",
          slots,
        },
      });
      setForm(initialForm);
      setShowForm(false);
      toast.success("Circle of care opened — your community has been let know.");
      load();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't open the circle.");
    } finally {
      setSubmitting(false);
    }
  };

  const claimSlot = async (circleId, slotId) => {
    try {
      const updated = await apiRequest(`/care/${circleId}/claim`, { method: "POST", token, data: { slot_id: slotId } });
      setCircles((c) => c.map((x) => (x.id === updated.id ? updated : x)));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't update that.");
    }
  };

  const closeCircle = async (circleId) => {
    try {
      const updated = await apiRequest(`/care/${circleId}/close`, { method: "POST", token });
      setCircles((c) => c.map((x) => (x.id === updated.id ? updated : x)));
      toast.success("Circle closed with gratitude.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't close it.");
    }
  };

  const open = circles.filter((c) => c.status !== "closed");

  return (
    <div className="space-y-6" data-testid="care-page">
      <div className="archival-card">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <HandHeart className="h-5 w-5 text-primary" />
            <div>
              <h2 className="font-display text-2xl text-foreground" data-testid="care-title">Circle of Care</h2>
              <p className="text-sm text-muted-foreground">When someone needs us, this is how we show up. {open.length} open.</p>
            </div>
          </div>
          <Button className="rounded-full" data-testid="care-add-btn" onClick={() => setShowForm(!showForm)} size="sm">
            <Plus className="mr-1 h-4 w-4" /> Start a circle
          </Button>
        </div>
      </div>

      {showForm && (
        <div className="archival-card" data-testid="care-form">
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={createCircle}>
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">Kind</span>
              <select className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" data-testid="care-kind" onChange={(e) => setForm((c) => ({ ...c, kind: e.target.value }))} value={form.kind}>
                {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">For (optional)</span>
              <select className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" data-testid="care-for" onChange={(e) => setForm((c) => ({ ...c, for_member_id: e.target.value }))} value={form.for_member_id}>
                <option value="">The whole community</option>
                {members.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
              </select>
            </label>
            <label className="block sm:col-span-2">
              <span className="text-xs font-semibold text-muted-foreground">Title</span>
              <Input className="field-input mt-1" data-testid="care-title-input" onChange={(e) => setForm((c) => ({ ...c, title: e.target.value }))} placeholder="e.g. Meals for the Johnsons' new baby" required value={form.title} />
            </label>
            {form.kind === "milestone" && (
              <label className="block sm:col-span-2">
                <span className="text-xs font-semibold text-muted-foreground">Milestone</span>
                <Input className="field-input mt-1" data-testid="care-milestone" onChange={(e) => setForm((c) => ({ ...c, milestone_type: e.target.value }))} placeholder="new baby · loss · recovery · graduation" value={form.milestone_type} />
              </label>
            )}
            <label className="block sm:col-span-2">
              <span className="text-xs font-semibold text-muted-foreground">Note</span>
              <Textarea className="field-textarea mt-1" data-testid="care-note" onChange={(e) => setForm((c) => ({ ...c, note: e.target.value }))} rows={2} value={form.note} />
            </label>
            {form.kind === "meal-train" && (
              <label className="block sm:col-span-2">
                <span className="text-xs font-semibold text-muted-foreground">Days / slots — one per line</span>
                <Textarea className="field-textarea mt-1" data-testid="care-slots" onChange={(e) => setForm((c) => ({ ...c, slotsText: e.target.value }))} placeholder={"Mon dinner\nWed dinner\nFri dinner"} rows={3} value={form.slotsText} />
              </label>
            )}
            <div className="flex gap-2 sm:col-span-2">
              <Button className="rounded-full" data-testid="care-submit" disabled={submitting} size="sm" type="submit">{submitting ? "Opening…" : "Open circle"}</Button>
              <Button className="rounded-full" onClick={() => setShowForm(false)} size="sm" type="button" variant="outline">Cancel</Button>
            </div>
          </form>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        {circles.length ? circles.map((circle) => (
          <article className={`archival-card ${circle.status === "closed" ? "opacity-60" : ""}`} data-testid={`care-circle-${circle.id}`} key={circle.id}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${KIND_BADGE[circle.kind] || "bg-muted text-muted-foreground"}`}>
                  {KINDS.find((k) => k.value === circle.kind)?.label || circle.kind}
                  {circle.milestone_type ? ` · ${circle.milestone_type}` : ""}
                </span>
                <h3 className="mt-2 text-lg font-semibold text-foreground leading-snug">{circle.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {circle.for_name ? <>For <span className="font-medium text-foreground/80">{circle.for_name}</span> · </> : null}
                  {circle.created_by_name} · {formatDateTime(circle.created_at)}
                </p>
              </div>
              {circle.status !== "closed" && (circle.created_by === user?.id || user?.role === "host" || user?.role === "organizer") && (
                <button className="text-xs font-medium text-muted-foreground hover:text-foreground" data-testid={`care-close-${circle.id}`} onClick={() => closeCircle(circle.id)} type="button">Close</button>
              )}
            </div>
            {circle.note ? <p className="mt-3 text-sm leading-7 text-muted-foreground">{circle.note}</p> : null}

            {circle.slots?.length > 0 && (
              <div className="mt-4 space-y-2" data-testid={`care-slots-${circle.id}`}>
                {circle.slots.map((slot) => {
                  const mine = slot.claimed_by === user?.id;
                  const taken = Boolean(slot.claimed_by);
                  return (
                    <div className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-muted/30 px-3 py-2" key={slot.id}>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{slot.label || slot.item || "Slot"}</p>
                        {taken ? <p className="text-xs text-muted-foreground">{mine ? "You've got this" : `${slot.claimed_by_name} has this`}</p> : <p className="text-xs text-muted-foreground">Open</p>}
                      </div>
                      {circle.status !== "closed" && (!taken || mine) && (
                        <button
                          className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition ${mine ? "bg-primary text-primary-foreground" : "border border-border text-primary hover:bg-muted/60"}`}
                          data-testid={`care-claim-${slot.id}`}
                          onClick={() => claimSlot(circle.id, slot.id)}
                          type="button"
                        >
                          {mine ? (<><Check className="h-3.5 w-3.5" /> I've got it</>) : "I'll bring it"}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </article>
        )) : (
          <div className="archival-card lg:col-span-2 py-12 text-center" data-testid="care-empty">
            <HandHeart className="mx-auto mb-4 h-10 w-10 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">No open circles. When someone needs a hand — a meal, a check-in, a milestone — start one here.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default CarePage;
