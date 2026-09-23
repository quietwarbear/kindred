import { useCallback, useEffect, useState } from "react";
import { HandCoins } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { gaClientId, trackReunionEvent } from "@/lib/analytics";
import { formatPrice } from "@/lib/pricing";
import { isNative } from "@/lib/native-bridge";
import { toast } from "@/components/ui/sonner";

const WEB_PURCHASES_ENABLED = Boolean(process.env.REACT_APP_REVENUECAT_WEB_KEY);
const MIN_CHIP_IN_DOLLARS = 5;

/**
 * Anyone in the family can put money toward the host's Reunion Pass.
 *
 * A reunion has a committee and a budget, and the organizer is rarely the one
 * who should absorb the cost. The host still HOLDS the pass — this only
 * changes who can pay for it. The contribution funds THIS gathering; it does
 * not buy the contributor a plan of their own, which the copy says plainly
 * because entitlement follows the Circle, not the person.
 *
 * Web only: a one-time web purchase has no business inside the iOS or Android
 * app, and the app stays silent about the pass by decision.
 */
export const ReunionPassChipIn = ({ token, variant = "full" }) => {
  const [status, setStatus] = useState(null);
  const [amount, setAmount] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await apiRequest("/reunion-pass/status", { token }));
    } catch {
      /* Supplementary — the page works without it. */
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  if (!status || isNative() || !WEB_PURCHASES_ENABLED) return null;
  if (status.active) return null;

  const remainingDollars = status.remaining_cents / 100;
  const pledged = status.contributed_cents > 0;
  const pct = status.price_cents
    ? Math.min(Math.round((status.contributed_cents / status.price_cents) * 100), 100)
    : 0;

  const contribute = async (event) => {
    event.preventDefault();
    const dollars = Number(amount);
    if (!Number.isFinite(dollars) || dollars < MIN_CHIP_IN_DOLLARS) {
      toast.error(`Contributions start at ${formatPrice(MIN_CHIP_IN_DOLLARS)}.`);
      return;
    }
    setSending(true);
    try {
      trackReunionEvent("chip_in_started", { surface: "web" });
      const res = await apiRequest("/reunion-pass/chip-in", {
        method: "POST",
        token,
        data: {
          amount_cents: Math.round(dollars * 100),
          origin_url: window.location.origin,
          ga_client_id: gaClientId(),
        },
      });
      if (res?.url) window.location.href = res.url;
      else throw new Error("no checkout url");
    } catch (error) {
      setSending(false);
      toast.error(
        error.response?.data?.detail || "Could not start checkout. Please try again."
      );
    }
  };

  return (
    <section
      className={variant === "today" ? "archival-card" : "rounded-2xl border border-border bg-muted/30 p-6"}
      data-testid="reunion-pass-chip-in"
    >
      <div className="flex items-start gap-3">
        <HandCoins className="mt-1 h-5 w-5 shrink-0 text-primary" />
        <div className="w-full">
          <p className="eyebrow-text">Reunion Pass</p>
          <h2 className="mt-2 font-display text-2xl text-foreground">
            {pledged
              ? `${formatPrice(remainingDollars)} to go`
              : "Chip in for the family's pass"}
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            The pass covers your whole family for twelve months, with no member
            limit. Anyone can put money toward it — {status.can_buy
              ? "and as host you can also buy it outright."
              : "your host holds it once it's funded."}
          </p>

          <div className="mt-4" aria-hidden="true">
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {formatPrice(status.contributed_cents / 100)} of{" "}
              {formatPrice(status.price_cents / 100)} together so far
            </p>
          </div>

          <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={contribute}>
            <label className="grow sm:grow-0">
              <span className="field-label">Your contribution</span>
              <Input
                className="field-input sm:w-40"
                data-testid="chip-in-amount"
                inputMode="decimal"
                min={MIN_CHIP_IN_DOLLARS}
                onChange={(event) => setAmount(event.target.value)}
                placeholder={String(Math.min(25, Math.ceil(remainingDollars)))}
                type="number"
                value={amount}
              />
            </label>
            <Button data-testid="chip-in-submit" disabled={sending} type="submit">
              {sending ? "Opening checkout…" : "Chip in"}
            </Button>
          </form>

          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            You'll never be charged more than the family still needs. This funds
            this gathering — it doesn't start a plan of your own.
          </p>
        </div>
      </div>
    </section>
  );
};
