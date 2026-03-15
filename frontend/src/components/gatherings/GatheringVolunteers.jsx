import { useState } from "react";
import { HandHelping } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const GatheringVolunteers = ({ event, token, canCreate, onUpdate }) => {
  const [title, setTitle] = useState("");
  const [count, setCount] = useState(1);

  const handleAddSlot = async (e) => {
    e.preventDefault();
    try {
      const payload = await apiRequest(`/events/${event.id}/volunteer-slots`, {
        method: "POST",
        token,
        data: { title, needed_count: Number(count) },
      });
      onUpdate(payload);
      setTitle("");
      setCount(1);
      toast.success("Volunteer slot added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add volunteer slot.");
    }
  };

  const handleSignup = async (slotId) => {
    try {
      const payload = await apiRequest(`/events/${event.id}/volunteer-signup`, { method: "POST", token, data: { slot_id: slotId } });
      onUpdate(payload);
      toast.success("Volunteer role claimed.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to claim volunteer role.");
    }
  };

  return (
    <div className="soft-panel" data-testid="gatherings-volunteer-panel">
      <div className="flex items-center gap-3">
        <HandHelping className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">Volunteer sign-ups</p>
      </div>
      <div className="mt-4 space-y-3">
        {event.volunteer_slots.map((slot) => (
          <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-volunteer-slot-${slot.id}`} key={slot.id}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">{slot.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{slot.assigned_members.length}/{slot.needed_count} filled</p>
              </div>
              <Button className="rounded-full" data-testid={`gatherings-volunteer-join-${slot.id}`} onClick={() => handleSignup(slot.id)} size="sm" type="button" variant="secondary">
                Join
              </Button>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{slot.assigned_members.join(", ") || "No one assigned yet."}</p>
          </div>
        ))}
      </div>
      {canCreate && (
        <form className="mt-4 space-y-3" onSubmit={handleAddSlot}>
          <Input className="field-input" data-testid="gatherings-volunteer-title-input" onChange={(e) => setTitle(e.target.value)} placeholder="Hospitality team" required value={title} />
          <Input className="field-input" data-testid="gatherings-volunteer-count-input" min={1} onChange={(e) => setCount(e.target.value)} type="number" value={count} />
          <Button className="w-full rounded-full" data-testid="gatherings-volunteer-submit-button" type="submit" variant="secondary">
            Add volunteer slot
          </Button>
        </form>
      )}
    </div>
  );
};
