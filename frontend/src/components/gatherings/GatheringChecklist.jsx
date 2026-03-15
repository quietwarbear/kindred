import { useState } from "react";
import { ClipboardList } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialChecklistForm = { category: "experience", title: "" };

export const GatheringChecklist = ({ event, token, canCreate, onUpdate }) => {
  const [form, setForm] = useState(initialChecklistForm);

  const handleAdd = async (e) => {
    e.preventDefault();
    try {
      const payload = await apiRequest(`/events/${event.id}/checklist-items`, { method: "POST", token, data: form });
      onUpdate(payload);
      setForm(initialChecklistForm);
      toast.success("Checklist item added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add checklist item.");
    }
  };

  const handleToggle = async (itemId) => {
    try {
      const payload = await apiRequest(`/events/${event.id}/checklist-toggle`, { method: "POST", token, data: { item_id: itemId } });
      onUpdate(payload);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update checklist item.");
    }
  };

  return (
    <div className="soft-panel" data-testid="gatherings-checklist-panel">
      <div className="flex items-center gap-3">
        <ClipboardList className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">Auto-generated planning checklist</p>
      </div>
      <div className="mt-4 space-y-3">
        {event.planning_checklist.map((item) => (
          <button
            className={`w-full rounded-2xl border px-4 py-3 text-left ${item.completed ? "border-primary bg-primary/5" : "border-border bg-background/70"}`}
            data-testid={`gatherings-checklist-item-${item.id}`}
            key={item.id}
            onClick={() => handleToggle(item.id)}
            type="button"
          >
            <p className="text-sm font-semibold text-foreground">{item.title}</p>
            <p className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">{item.category} · {item.completed ? "done" : "open"}</p>
          </button>
        ))}
      </div>
      {canCreate && (
        <form className="mt-4 space-y-3" onSubmit={handleAdd}>
          <select className="field-input w-full" data-testid="gatherings-checklist-category-select" onChange={(e) => setForm((c) => ({ ...c, category: e.target.value }))} value={form.category}>
            <option value="administrative">Administrative</option>
            <option value="experience">Experience</option>
            <option value="technology">Technology</option>
            <option value="promotion">Promotion</option>
            <option value="post-event">Post-event</option>
          </select>
          <Input className="field-input" data-testid="gatherings-checklist-title-input" onChange={(e) => setForm((c) => ({ ...c, title: e.target.value }))} placeholder="Add custom checklist item" required value={form.title} />
          <Button className="w-full rounded-full" data-testid="gatherings-checklist-submit-button" type="submit" variant="secondary">
            Add checklist item
          </Button>
        </form>
      )}
    </div>
  );
};
