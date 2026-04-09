import { useCallback, useEffect, useMemo, useState } from "react";
import { Coins, CreditCard, Plane, Trash2, Wallet } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { isNative } from "@/lib/native-bridge";

const initialBudgetForm = {
  title: "",
  event_id: "",
  target_amount: 0,
  current_amount: 0,
  suggested_contribution: 0,
  notes: "",
};

export const FundsTravelPage = ({ token, user }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [budgetForm, setBudgetForm] = useState(initialBudgetForm);
  const [loadingPackageId, setLoadingPackageId] = useState("");
  const [isSavingBudget, setIsSavingBudget] = useState(false);

  const sessionId = useMemo(() => searchParams.get("session_id"), [searchParams]);
  const canManage = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);

  const loadData = useCallback(async () => {
    try {
      const [summaryPayload, eventsPayload] = await Promise.all([
        apiRequest("/funds-travel/overview", { token }),
        apiRequest("/events", { token }),
      ]);
      setSummary(summaryPayload);
      setEvents(eventsPayload || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load funds and travel details.");
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!sessionId) return;

    let cancelled = false;
    const pollPayment = async () => {
      for (let attempt = 0; attempt < 5; attempt += 1) {
        try {
          const payload = await apiRequest(`/payments/checkout/status/${sessionId}`, { token });
          if (payload.payment_status === "paid") {
            toast.success("Contribution received.");
            await loadData();
            if (!cancelled) {
              const nextParams = new URLSearchParams(searchParams);
              nextParams.delete("session_id");
              setSearchParams(nextParams, { replace: true });
            }
            return;
          }
          if (["expired", "canceled"].includes(payload.status)) {
            toast.error("This payment session expired or was canceled.");
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 2000));
        } catch {
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      }
    };

    pollPayment();
    return () => {
      cancelled = true;
    };
  }, [loadData, searchParams, sessionId, setSearchParams, token]);

  const handleCheckout = async (packageId) => {
    setLoadingPackageId(packageId);
    try {
      const payload = await apiRequest("/payments/checkout/session", {
        method: "POST",
        token,
        data: { package_id: packageId, origin_url: window.location.origin },
      });
      window.location.href = payload.url;
    } catch (error) {
      setLoadingPackageId("");
      toast.error(error.response?.data?.detail || "Unable to start checkout.");
    }
  };

  const handleCreateBudget = async (event) => {
    event.preventDefault();
    setIsSavingBudget(true);
    try {
      await apiRequest("/budget-plans", {
        method: "POST",
        token,
        data: {
          ...budgetForm,
          event_id: budgetForm.event_id || null,
          target_amount: Number(budgetForm.target_amount) || 0,
          current_amount: Number(budgetForm.current_amount) || 0,
          suggested_contribution: Number(budgetForm.suggested_contribution) || 0,
        },
      });
      setBudgetForm(initialBudgetForm);
      toast.success("Budget plan created.");
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create budget plan.");
    } finally {
      setIsSavingBudget(false);
    }
  };

  const handleDeleteBudget = async (budgetId) => {
    try {
      await apiRequest(`/budget-plans/${budgetId}`, { method: "DELETE", token });
      toast.success("Budget plan deleted.");
      loadSummary();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to delete budget.");
    }
  };

  const handleDeleteTravelPlan = async (planId) => {
    try {
      await apiRequest(`/travel-plans/${planId}`, { method: "DELETE", token });
      toast.success("Travel plan deleted.");
      loadSummary();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to delete travel plan.");
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Funds & Travel</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="funds-travel-page-title">
          Shared resources for dues, budgets, contribution flows, and travel coordination.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="funds-travel-page-copy">
          Bring together pooled giving, treasurer visibility, event budgets, hotel blocks, carpools, and the travel records people usually lose in group chats.
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <article className="archival-card" data-testid="funds-travel-summary-card">
          <div className="flex items-center gap-3">
            <Wallet className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Summary</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Current position</h3>
            </div>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <div className="soft-panel" data-testid="funds-travel-total-raised">
              <p className="text-sm text-muted-foreground">Total raised</p>
              <p className="mt-2 text-3xl font-semibold text-foreground">{shortCurrency(summary?.total_paid || 0)}</p>
            </div>
            <div className="soft-panel" data-testid="funds-travel-budgets-count">
              <p className="text-sm text-muted-foreground">Budgets</p>
              <p className="mt-2 text-3xl font-semibold text-foreground">{summary?.budgets?.length || 0}</p>
            </div>
            <div className="soft-panel" data-testid="funds-travel-travel-total">
              <p className="text-sm text-muted-foreground">Travel tracked</p>
              <p className="mt-2 text-3xl font-semibold text-foreground">{shortCurrency(summary?.pending_travel_total || 0)}</p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            {summary?.packages?.map((item) => (
              <div className="soft-panel" data-testid={`funds-travel-package-${item.id}`} key={item.id}>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-lg font-semibold text-foreground">{item.label}</p>
                    <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.description}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-display text-3xl text-foreground">{shortCurrency(item.amount)}</p>
                    {isNative() ? (
                      <p className="mt-3 text-xs text-muted-foreground">Visit kindred on the web to contribute.</p>
                    ) : (
                      <Button className="mt-3 rounded-full" data-testid={`funds-travel-package-button-${item.id}`} onClick={() => handleCheckout(item.id)} type="button">
                        {loadingPackageId === item.id ? "Opening..." : "Contribute"}
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="archival-card" data-testid="funds-travel-ledger-card">
          <div className="flex items-center gap-3">
            <CreditCard className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Transaction fee model alignment</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Contribution ledger</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {summary?.transactions?.length ? (
              summary.transactions.map((transaction) => (
                <div className="soft-panel" data-testid={`funds-travel-transaction-${transaction.id}`} key={transaction.id}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-base font-semibold text-foreground">{transaction.contribution_label}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{transaction.user_email} · {formatDateTime(transaction.created_at)}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-foreground">{shortCurrency(transaction.amount)}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.16em] text-primary" data-testid={`funds-travel-transaction-status-${transaction.id}`}>
                        {transaction.payment_status}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="funds-travel-transactions-empty-state">
                <p className="text-sm text-muted-foreground">No contributions yet. Start with one of the packages on the left.</p>
              </div>
            )}
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="archival-card" data-testid="funds-travel-budget-card">
          <div className="flex items-center gap-3">
            <Coins className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Budget planning</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Event and family fund budgets</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {summary?.budgets?.map((budget) => (
              <div className="soft-panel" data-testid={`funds-travel-budget-${budget.id}`} key={budget.id}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-base font-semibold text-foreground">{budget.title}</p>
                    <p className="mt-2 text-sm text-muted-foreground">{budget.event_title || "General courtyard budget"}</p>
                  </div>
                  {canManage && (
                    <Button
                      className="h-8 w-8 rounded-full p-0"
                      data-testid={`funds-travel-budget-delete-${budget.id}`}
                      onClick={() => handleDeleteBudget(budget.id)}
                      variant="ghost"
                    >
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                    </Button>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-4 text-sm text-muted-foreground">
                  <span>Target: {shortCurrency(budget.target_amount)}</span>
                  <span>Current: {shortCurrency(budget.current_amount)}</span>
                  <span>Suggested: {shortCurrency(budget.suggested_contribution)}</span>
                </div>
                {budget.notes ? <p className="mt-3 text-sm leading-7 text-muted-foreground">{budget.notes}</p> : null}
              </div>
            ))}
          </div>
          {canManage ? (
            <form className="mt-6 grid gap-4" onSubmit={handleCreateBudget}>
              <label>
                <span className="field-label">Budget title</span>
                <Input className="field-input" data-testid="funds-travel-budget-title-input" onChange={(e) => setBudgetForm((current) => ({ ...current, title: e.target.value }))} required value={budgetForm.title} />
              </label>
              <label>
                <span className="field-label">Related gathering</span>
                <select className="field-input w-full" data-testid="funds-travel-budget-event-select" onChange={(e) => setBudgetForm((current) => ({ ...current, event_id: e.target.value }))} value={budgetForm.event_id}>
                  <option value="">General courtyard budget</option>
                  {events.map((eventItem) => (
                    <option key={eventItem.id} value={eventItem.id}>{eventItem.title}</option>
                  ))}
                </select>
              </label>
              <div className="grid gap-4 sm:grid-cols-3">
                <label>
                  <span className="field-label">Target</span>
                  <Input className="field-input" data-testid="funds-travel-budget-target-input" min={0} onChange={(e) => setBudgetForm((current) => ({ ...current, target_amount: e.target.value }))} type="number" value={budgetForm.target_amount} />
                </label>
                <label>
                  <span className="field-label">Current</span>
                  <Input className="field-input" data-testid="funds-travel-budget-current-input" min={0} onChange={(e) => setBudgetForm((current) => ({ ...current, current_amount: e.target.value }))} type="number" value={budgetForm.current_amount} />
                </label>
                <label>
                  <span className="field-label">Suggested per attendee</span>
                  <Input className="field-input" data-testid="funds-travel-budget-suggested-input" min={0} onChange={(e) => setBudgetForm((current) => ({ ...current, suggested_contribution: e.target.value }))} type="number" value={budgetForm.suggested_contribution} />
                </label>
              </div>
              <label>
                <span className="field-label">Notes</span>
                <Textarea className="field-textarea" data-testid="funds-travel-budget-notes-input" onChange={(e) => setBudgetForm((current) => ({ ...current, notes: e.target.value }))} value={budgetForm.notes} />
              </label>
              <Button className="rounded-full" data-testid="funds-travel-budget-submit-button" disabled={isSavingBudget} type="submit">
                {isSavingBudget ? "Saving..." : "Create budget plan"}
              </Button>
            </form>
          ) : null}
        </article>

        <article className="archival-card" data-testid="funds-travel-travel-card">
          <div className="flex items-center gap-3">
            <Plane className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Travel coordination module</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Hotels, flights, carpools, and shuttles</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {summary?.travel_plans?.length ? (
              summary.travel_plans.map((plan) => (
                <div className="soft-panel" data-testid={`funds-travel-plan-${plan.id}`} key={plan.id}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-base font-semibold text-foreground">{plan.title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{plan.event_title} · {plan.travel_type}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right text-sm text-muted-foreground">
                        <p>{shortCurrency(plan.amount_estimate)}</p>
                        <p>{plan.payment_status}</p>
                      </div>
                      {canManage && (
                        <Button
                          className="h-8 w-8 rounded-full p-0"
                          data-testid={`funds-travel-plan-delete-${plan.id}`}
                          onClick={() => handleDeleteTravelPlan(plan.id)}
                          variant="ghost"
                        >
                          <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                        </Button>
                      )}
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{plan.details}</p>
                  <p className="mt-3 text-sm text-muted-foreground" data-testid={`funds-travel-plan-assigned-${plan.id}`}>
                    Assigned: {plan.assigned_members.join(", ") || "No one yet"}
                  </p>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="funds-travel-plans-empty-state">
                <p className="text-sm text-muted-foreground">Travel coordination items will appear here once they’re created from the Gatherings page.</p>
              </div>
            )}
          </div>
        </article>
      </section>
    </div>
  );
};