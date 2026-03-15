import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialRoleForm = { role_name: "", assignees: "" };

export const GatheringRoles = ({ event, token, onUpdate }) => {
  const [form, setForm] = useState(initialRoleForm);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = await apiRequest(`/events/${event.id}/role-assignments`, {
        method: "POST",
        token,
        data: {
          role_name: form.role_name,
          assignees: form.assignees.split(",").map((s) => s.trim()).filter(Boolean),
        },
      });
      onUpdate(payload);
      setForm(initialRoleForm);
      toast.success("Event role assignments updated.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to assign event roles.");
    }
  };

  return (
    <div className="soft-panel" data-testid="gatherings-role-assignments-panel">
      <p className="text-lg font-semibold text-foreground">Assign event roles</p>
      <div className="mt-4 space-y-3">
        {event.event_role_assignments?.map((assignment) => (
          <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-role-assignment-${assignment.id}`} key={assignment.id}>
            <p className="text-sm font-semibold text-foreground">{assignment.role_name}</p>
            <p className="mt-1 text-sm text-muted-foreground">{assignment.assignees?.join(", ") || "No one assigned yet."}</p>
          </div>
        ))}
      </div>
      <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
        <Input className="field-input" data-testid="gatherings-role-name-input" onChange={(e) => setForm((c) => ({ ...c, role_name: e.target.value }))} placeholder="Zoom host, greeter, prayer lead" required value={form.role_name} />
        <Input className="field-input" data-testid="gatherings-role-assignees-input" onChange={(e) => setForm((c) => ({ ...c, assignees: e.target.value }))} placeholder="Name or email, multiple separated by commas" required value={form.assignees} />
        <Button className="w-full rounded-full" data-testid="gatherings-role-submit-button" type="submit" variant="secondary">
          Save role assignment
        </Button>
      </form>
    </div>
  );
};
