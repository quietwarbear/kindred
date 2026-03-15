import { useState } from "react";
import { UsersRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const GatheringRsvp = ({ event, token, onUpdate }) => {
  const [status, setStatus] = useState("going");
  const [guests, setGuests] = useState(0);

  const handleRsvp = async () => {
    try {
      const payload = await apiRequest(`/events/${event.id}/rsvp`, { method: "POST", token, data: { status, guests: Number(guests) } });
      onUpdate(payload);
      toast.success("RSVP updated.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update RSVP.");
    }
  };

  return (
    <div className="soft-panel" data-testid="gatherings-rsvp-panel">
      <div className="flex items-center gap-3">
        <UsersRound className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">RSVP + attendee tracking</p>
      </div>
      <div className="mt-4 space-y-3">
        <select className="field-input w-full" data-testid="gatherings-rsvp-status-select" onChange={(e) => setStatus(e.target.value)} value={status}>
          <option value="going">Going</option>
          <option value="maybe">Maybe</option>
          <option value="not-going">Not going</option>
        </select>
        <Input className="field-input" data-testid="gatherings-rsvp-guests-input" min={0} onChange={(e) => setGuests(e.target.value)} type="number" value={guests} />
        <Button className="w-full rounded-full" data-testid="gatherings-rsvp-submit-button" onClick={handleRsvp} type="button">
          Save RSVP
        </Button>
        <div className="space-y-2">
          {event.rsvp_records.map((record) => (
            <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground" data-testid={`gatherings-rsvp-record-${record.user_id}`} key={record.user_id}>
              {record.user_name}: {record.status} {record.guests ? `(+${record.guests})` : ""}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
