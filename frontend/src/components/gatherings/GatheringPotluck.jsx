import { useState } from "react";
import { Soup } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const GatheringPotluck = ({ event, token, canCreate, onUpdate }) => {
  const [item, setItem] = useState("");

  const handleAdd = async (e) => {
    e.preventDefault();
    try {
      const payload = await apiRequest(`/events/${event.id}/potluck-items`, { method: "POST", token, data: { item_name: item } });
      onUpdate(payload);
      setItem("");
      toast.success("Potluck item added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add potluck item.");
    }
  };

  const handleClaim = async (itemId) => {
    try {
      const payload = await apiRequest(`/events/${event.id}/potluck-claim`, { method: "POST", token, data: { item_id: itemId } });
      onUpdate(payload);
      toast.success("Potluck item claimed.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to claim potluck item.");
    }
  };

  return (
    <div className="soft-panel" data-testid="gatherings-potluck-panel">
      <div className="flex items-center gap-3">
        <Soup className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">Shared table planning</p>
      </div>
      <div className="mt-4 space-y-3">
        {event.potluck_items.map((potluck) => (
          <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-potluck-item-${potluck.id}`} key={potluck.id}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">{potluck.item_name}</p>
                <p className="mt-1 text-xs text-muted-foreground">{potluck.assigned_to || "Unclaimed"}</p>
              </div>
              {!potluck.assigned_to && (
                <Button className="rounded-full" data-testid={`gatherings-potluck-claim-${potluck.id}`} onClick={() => handleClaim(potluck.id)} size="sm" type="button" variant="secondary">
                  Claim
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
      {canCreate && (
        <form className="mt-4 space-y-3" onSubmit={handleAdd}>
          <Input className="field-input" data-testid="gatherings-potluck-item-input" onChange={(e) => setItem(e.target.value)} placeholder="Mac and cheese tray" required value={item} />
          <Button className="w-full rounded-full" data-testid="gatherings-potluck-submit-button" type="submit" variant="secondary">
            Add potluck item
          </Button>
        </form>
      )}
    </div>
  );
};
