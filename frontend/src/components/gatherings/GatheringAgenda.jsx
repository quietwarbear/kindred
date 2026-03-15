import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialAgendaForm = { time_label: "", title: "", notes: "" };

export const GatheringAgenda = ({ event, token, canCreate, onUpdate }) => {
  const [form, setForm] = useState(initialAgendaForm);

  const handleAdd = async (e) => {
    e.preventDefault();
    try {
      const payload = await apiRequest(`/events/${event.id}/agenda`, { method: "POST", token, data: form });
      onUpdate(payload);
      setForm(initialAgendaForm);
      toast.success("Agenda item added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add agenda item.");
    }
  };

  return (
    <div className="soft-panel" data-testid="gatherings-agenda-panel">
      <p className="text-lg font-semibold text-foreground">Agenda builder</p>
      <div className="mt-4 space-y-3">
        {event.agenda.map((item) => (
          <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-agenda-item-${item.id}`} key={item.id}>
            <p className="text-sm font-semibold text-foreground">{item.time_label} · {item.title}</p>
            {item.notes ? <p className="mt-2 text-sm text-muted-foreground">{item.notes}</p> : null}
          </div>
        ))}
      </div>
      {canCreate && (
        <form className="mt-4 space-y-3" onSubmit={handleAdd}>
          <Input className="field-input" data-testid="gatherings-agenda-time-input" onChange={(e) => setForm((c) => ({ ...c, time_label: e.target.value }))} placeholder="2:00 PM" required value={form.time_label} />
          <Input className="field-input" data-testid="gatherings-agenda-title-input" onChange={(e) => setForm((c) => ({ ...c, title: e.target.value }))} placeholder="Opening circle" required value={form.title} />
          <Textarea className="field-textarea" data-testid="gatherings-agenda-notes-input" onChange={(e) => setForm((c) => ({ ...c, notes: e.target.value }))} placeholder="Optional notes" value={form.notes} />
          <Button className="w-full rounded-full" data-testid="gatherings-agenda-submit-button" type="submit" variant="secondary">
            Add agenda item
          </Button>
        </form>
      )}
    </div>
  );
};
