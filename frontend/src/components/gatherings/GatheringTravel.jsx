import { useState } from "react";
import { Plane } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialTravelForm = {
  title: "",
  travel_type: "hotel",
  details: "",
  coordinator_name: "",
  amount_estimate: 0,
  payment_status: "pending",
  seats_available: 0,
};

export const GatheringTravel = ({ event, token, canCreate, travelPlans, onReload }) => {
  const [form, setForm] = useState(initialTravelForm);

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await apiRequest("/travel-plans", {
        method: "POST",
        token,
        data: {
          ...form,
          event_id: event.id,
          amount_estimate: Number(form.amount_estimate) || 0,
          seats_available: Number(form.seats_available) || 0,
        },
      });
      setForm(initialTravelForm);
      toast.success("Travel coordination item added.");
      onReload();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add travel coordination.");
    }
  };

  const handleJoin = async (planId) => {
    try {
      await apiRequest(`/travel-plans/${planId}/assign-self`, { method: "POST", token });
      toast.success("Travel assignment updated.");
      onReload();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to join that travel plan.");
    }
  };

  return (
    <div className="soft-panel xl:col-span-2" data-testid="gatherings-travel-panel">
      <div className="flex items-center gap-3">
        <Plane className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">Travel coordination module</p>
      </div>
      <p className="mt-3 text-sm leading-7 text-muted-foreground">{event.travel_coordination_notes || "Use this section for hotel blocks, flights, carpools, shuttles, and shared travel payment coordination."}</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {travelPlans.map((plan) => (
          <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-4" data-testid={`gatherings-travel-plan-${plan.id}`} key={plan.id}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">{plan.title}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.16em] text-muted-foreground">{plan.travel_type}</p>
              </div>
              <Button className="rounded-full" data-testid={`gatherings-travel-join-${plan.id}`} onClick={() => handleJoin(plan.id)} size="sm" type="button" variant="secondary">
                Join
              </Button>
            </div>
            <p className="mt-3 text-sm leading-7 text-muted-foreground">{plan.details}</p>
            <div className="mt-3 flex flex-wrap gap-3 text-sm text-muted-foreground">
              <span>{shortCurrency(plan.amount_estimate)}</span>
              <span>{plan.payment_status}</span>
              <span>{plan.assigned_members.length} assigned</span>
            </div>
          </div>
        ))}
      </div>
      {canCreate && (
        <form className="mt-4 grid gap-4 xl:grid-cols-2" onSubmit={handleCreate}>
          <label>
            <span className="field-label">Travel item title</span>
            <Input className="field-input" data-testid="gatherings-travel-title-input" onChange={(e) => setForm((c) => ({ ...c, title: e.target.value }))} required value={form.title} />
          </label>
          <label>
            <span className="field-label">Type</span>
            <select className="field-input w-full" data-testid="gatherings-travel-type-select" onChange={(e) => setForm((c) => ({ ...c, travel_type: e.target.value }))} value={form.travel_type}>
              <option value="hotel">Hotel</option>
              <option value="flight">Flight</option>
              <option value="carpool">Carpool</option>
              <option value="shuttle">Shuttle</option>
            </select>
          </label>
          <label>
            <span className="field-label">Coordinator</span>
            <Input className="field-input" data-testid="gatherings-travel-coordinator-input" onChange={(e) => setForm((c) => ({ ...c, coordinator_name: e.target.value }))} value={form.coordinator_name} />
          </label>
          <label>
            <span className="field-label">Estimated amount</span>
            <Input className="field-input" data-testid="gatherings-travel-amount-input" min={0} onChange={(e) => setForm((c) => ({ ...c, amount_estimate: e.target.value }))} type="number" value={form.amount_estimate} />
          </label>
          <label>
            <span className="field-label">Seats available</span>
            <Input className="field-input" data-testid="gatherings-travel-seats-input" min={0} onChange={(e) => setForm((c) => ({ ...c, seats_available: e.target.value }))} type="number" value={form.seats_available} />
          </label>
          <label>
            <span className="field-label">Payment status</span>
            <select className="field-input w-full" data-testid="gatherings-travel-payment-status-select" onChange={(e) => setForm((c) => ({ ...c, payment_status: e.target.value }))} value={form.payment_status}>
              <option value="pending">Pending</option>
              <option value="partially-funded">Partially funded</option>
              <option value="funded">Funded</option>
            </select>
          </label>
          <label className="xl:col-span-2">
            <span className="field-label">Details</span>
            <Textarea className="field-textarea" data-testid="gatherings-travel-details-input" onChange={(e) => setForm((c) => ({ ...c, details: e.target.value }))} required value={form.details} />
          </label>
          <div className="xl:col-span-2">
            <Button className="w-full rounded-full" data-testid="gatherings-travel-submit-button" type="submit" variant="secondary">
              Add travel coordination item
            </Button>
          </div>
        </form>
      )}
    </div>
  );
};
