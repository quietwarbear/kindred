import { useCallback, useEffect, useMemo, useState } from "react";
import { Coins, CreditCard, Wallet } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { apiRequest, formatDateTime, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { isNative } from "@/lib/native-bridge";

export const ContributionsPage = ({ token }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [packages, setPackages] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [totalPaid, setTotalPaid] = useState(0);
  const [loadingPackageId, setLoadingPackageId] = useState("");

  const sessionId = useMemo(() => searchParams.get("session_id"), [searchParams]);

  const loadSummary = useCallback(async () => {
    try {
      const payload = await apiRequest("/payments/summary", { token });
      setPackages(payload.packages || []);
      setTransactions(payload.transactions || []);
      setTotalPaid(payload.total_paid || 0);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load contributions.");
    }
  }, [token]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    if (!sessionId) return;

    let cancelled = false;
    const pollPayment = async () => {
      for (let attempt = 0; attempt < 5; attempt += 1) {
        try {
          const payload = await apiRequest(`/payments/checkout/status/${sessionId}`, { token });
          if (payload.payment_status === "paid") {
            toast.success("Contribution received.");
            await loadSummary();
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
  }, [loadSummary, searchParams, sessionId, setSearchParams, token]);

  const handleCheckout = async (packageId) => {
    setLoadingPackageId(packageId);
    try {
      const payload = await apiRequest("/payments/checkout/session", {
        method: "POST",
        data: {
          package_id: packageId,
          origin_url: window.location.origin,
        },
        token,
      });
      window.location.href = payload.url;
    } catch (error) {
      setLoadingPackageId("");
      toast.error(error.response?.data?.detail || "Unable to start checkout.");
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Shared contributions</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="contributions-page-title">
          Transparent support for the work your community is already doing.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="contributions-page-copy">
          Launch fixed contribution packages, route people into secure Stripe checkout, and keep a clean internal ledger of what has been raised.
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <article className="archival-card" data-testid="contributions-summary-card">
          <div className="flex items-center gap-3">
            <Wallet className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Contribution overview</h3>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <div className="soft-panel" data-testid="contributions-total-paid">
              <p className="text-sm text-muted-foreground">Total raised</p>
              <p className="mt-2 font-display text-4xl text-foreground">{shortCurrency(totalPaid)}</p>
            </div>
            <div className="soft-panel" data-testid="contributions-session-status">
              <p className="text-sm text-muted-foreground">Stripe return status</p>
              <p className="mt-2 text-sm font-semibold text-foreground">{sessionId ? "Checking latest payment..." : "Ready for new contributions"}</p>
            </div>
          </div>

          <div className="mt-6 grid gap-4">
            {packages.map((item) => (
              <div className="soft-panel" data-testid={`contribution-package-${item.id}`} key={item.id}>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-xl font-semibold text-foreground">{item.label}</p>
                    <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.description}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-display text-3xl text-foreground">{shortCurrency(item.amount)}</p>
                    {isNative() ? (
                      <p className="mt-3 text-xs text-muted-foreground">Visit kindred on the web to contribute.</p>
                    ) : (
                      <Button className="mt-3 rounded-full" data-testid={`contribution-package-button-${item.id}`} onClick={() => handleCheckout(item.id)} type="button">
                        {loadingPackageId === item.id ? "Opening..." : "Contribute"}
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="archival-card" data-testid="contributions-ledger-card">
          <div className="flex items-center gap-3">
            <Coins className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Transaction ledger</h3>
          </div>
          <div className="mt-6 space-y-4">
            {transactions.length ? (
              transactions.map((transaction) => (
                <div className="soft-panel" data-testid={`contribution-transaction-${transaction.id}`} key={transaction.id}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-lg font-semibold text-foreground">{transaction.contribution_label}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{transaction.user_email} · {formatDateTime(transaction.created_at)}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-foreground">{shortCurrency(transaction.amount)}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-primary" data-testid={`contribution-status-${transaction.id}`}>
                        {transaction.payment_status}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="contributions-empty-state">
                <div className="mb-3 flex items-center gap-2 text-primary">
                  <CreditCard className="h-4 w-4" />
                  <p className="text-sm font-semibold">No contributions yet</p>
                </div>
                <p className="text-sm text-muted-foreground">When members contribute, the transaction ledger will appear here with clear payment status.</p>
              </div>
            )}
          </div>
        </article>
      </section>
    </div>
  );
};