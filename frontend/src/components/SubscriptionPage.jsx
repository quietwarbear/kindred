import { useCallback, useEffect, useState } from "react";
import {
  Check,
  ChevronRight,
  Crown,
  Leaf,
  Loader2,
  Sparkles,
  TreeDeciduous,
  TreePine,
  Trees,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import {
  ensureInitialized,
  isIOS,
  makePurchase,
  syncRevenueCatUser,
  TIER_TO_PRODUCT_ID,
} from "@/lib/revenuecat";

const TIER_ICONS = {
  seedling: Leaf,
  sapling: TreePine,
  oak: TreeDeciduous,
  redwood: Trees,
  "elder-grove": Crown,
};

const TIER_COLORS = {
  seedling: "from-emerald-500/15 to-emerald-600/5 border-emerald-500/30",
  sapling: "from-teal-500/15 to-teal-600/5 border-teal-500/30",
  oak: "from-amber-500/15 to-amber-600/5 border-amber-500/30",
  redwood: "from-primary/15 to-primary/5 border-primary/30",
  "elder-grove": "from-violet-500/15 to-violet-600/5 border-violet-500/30",
};

const TIER_ACCENT = {
  seedling: "text-emerald-600 dark:text-emerald-400",
  sapling: "text-teal-600 dark:text-teal-400",
  oak: "text-amber-600 dark:text-amber-400",
  redwood: "text-primary",
  "elder-grove": "text-violet-600 dark:text-violet-400",
};

const TIER_BTN = {
  seedling: "bg-emerald-600 hover:bg-emerald-700 text-white",
  sapling: "bg-teal-600 hover:bg-teal-700 text-white",
  oak: "bg-amber-600 hover:bg-amber-700 text-white",
  redwood: "bg-primary hover:bg-primary/90 text-primary-foreground",
  "elder-grove": "bg-violet-600 hover:bg-violet-700 text-white",
};

const formatPrice = (val) =>
  val === 0
    ? "Free"
    : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val);

const PlanCard = ({ plan, isCurrentTier, billingCycle, onSelect, isLoading, currentTierId }) => {
  const Icon = TIER_ICONS[plan.id] || Leaf;
  const isElderGrove = plan.id === "elder-grove";
  const price = billingCycle === "annual" ? plan.annual_price : plan.monthly_price;
  const monthlyEquivalent = billingCycle === "annual" && plan.annual_price > 0 ? (plan.annual_price / 12).toFixed(2) : null;
  const isPopular = plan.id === "oak";

  const tierOrder = ["seedling", "sapling", "oak", "redwood", "elder-grove"];
  const currentIdx = tierOrder.indexOf(currentTierId || "seedling");
  const thisIdx = tierOrder.indexOf(plan.id);
  const isDowngrade = thisIdx < currentIdx;
  const isUpgrade = thisIdx > currentIdx;

  return (
    <div
      className={`relative flex flex-col rounded-2xl border bg-gradient-to-b p-6 transition-all duration-300 hover:shadow-lg ${TIER_COLORS[plan.id]} ${isCurrentTier ? "ring-2 ring-primary shadow-lg" : ""} ${isPopular ? "md:-translate-y-2" : ""}`}
      data-testid={`plan-card-${plan.id}`}
    >
      {isPopular && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="rounded-full bg-amber-600 px-4 py-1 text-xs font-semibold text-white shadow-md" data-testid="popular-badge">
            Most Popular
          </span>
        </div>
      )}

      {isCurrentTier && (
        <div className="absolute -top-3 right-4">
          <span className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground shadow-md" data-testid="current-plan-badge">
            Current Plan
          </span>
        </div>
      )}

      <div className="mb-4 flex items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-background/80 shadow-sm ${TIER_ACCENT[plan.id]}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <h3 className="font-display text-lg font-semibold text-foreground" data-testid={`plan-name-${plan.id}`}>
            {plan.name}
          </h3>
          <p className="text-xs text-muted-foreground">Up to {plan.max_members} members</p>
        </div>
      </div>

      <p className="mb-4 text-sm text-muted-foreground">{plan.tagline}</p>

      <div className="mb-5">
        {isElderGrove ? (
          <p className={`font-display text-3xl font-bold ${TIER_ACCENT[plan.id]}`}>Custom</p>
        ) : (
          <>
            <p className={`font-display text-3xl font-bold ${TIER_ACCENT[plan.id]}`} data-testid={`plan-price-${plan.id}`}>
              {formatPrice(price)}
              <span className="text-base font-normal text-muted-foreground">
                /{billingCycle === "annual" ? "yr" : "mo"}
              </span>
            </p>
            {monthlyEquivalent && (
              <p className="mt-1 text-xs text-muted-foreground">
                ~${monthlyEquivalent}/mo · Save {billingCycle === "annual" ? "~25%" : ""}
              </p>
            )}
          </>
        )}
      </div>

      <ul className="mb-6 flex-1 space-y-2.5">
        {plan.features.map((feat, i) => (
          <li className="flex items-start gap-2 text-sm text-foreground" key={i}>
            <Check className={`mt-0.5 h-4 w-4 flex-shrink-0 ${TIER_ACCENT[plan.id]}`} />
            <span>{feat}</span>
          </li>
        ))}
      </ul>

      {isCurrentTier ? (
        <Button className="w-full rounded-full" disabled variant="outline" data-testid={`plan-select-${plan.id}`}>
          Current Plan
        </Button>
      ) : isElderGrove ? (
        <Button
          className={`w-full rounded-full ${TIER_BTN[plan.id]}`}
          onClick={() => toast.info("Contact us at hello@kindred.community for Elder Grove pricing.")}
          data-testid={`plan-select-${plan.id}`}
        >
          Contact Sales
        </Button>
      ) : (
        <Button
          className={`w-full rounded-full ${TIER_BTN[plan.id]}`}
          disabled={isLoading}
          onClick={() => onSelect(plan.id)}
          data-testid={`plan-select-${plan.id}`}
        >
          {isLoading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <ChevronRight className="mr-1 h-4 w-4" />
          )}
          {isDowngrade ? "Downgrade" : isUpgrade ? "Upgrade" : "Select Plan"}
        </Button>
      )}
    </div>
  );
};

const ADDON_ICONS = {
  storage: "HardDrive",
  templates: "LayoutTemplate",
  sms: "MessageSquareText",
};

const ADDON_COLORS = {
  storage: "text-blue-600 bg-blue-50 dark:bg-blue-950/40",
  templates: "text-purple-600 bg-purple-50 dark:bg-purple-950/40",
  sms: "text-green-600 bg-green-50 dark:bg-green-950/40",
};

const AddOnsSection = ({ token }) => {
  const [addons, setAddons] = useState([]);
  const [purchasing, setPurchasing] = useState("");

  const loadAddons = useCallback(async () => {
    try {
      const payload = await apiRequest("/addons/catalog", { token });
      setAddons(payload.addons || []);
    } catch { /* ignore */ }
  }, [token]);

  useEffect(() => { loadAddons(); }, [loadAddons]);

  const handlePurchase = async (addonId) => {
    setPurchasing(addonId);
    try {
      const payload = await apiRequest("/addons/checkout", {
        method: "POST",
        token,
        data: { addon_id: addonId, origin_url: window.location.href.split("?")[0] },
      });
      if (payload.checkout_url) {
        window.location.href = payload.checkout_url;
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to start checkout.");
    } finally {
      setPurchasing("");
    }
  };

  if (!addons.length) return null;

  return (
    <div className="archival-card" data-testid="addons-section">
      <div className="flex items-center gap-3 mb-1">
        <Sparkles className="h-5 w-5 text-primary" />
        <h2 className="font-display text-xl text-foreground">Add-Ons</h2>
      </div>
      <p className="text-sm text-muted-foreground">Enhance your community with extras.</p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {addons.map((addon) => (
          <div
            className="rounded-2xl border border-border/60 bg-background p-5 space-y-3 hover:shadow-md transition-shadow"
            data-testid={`addon-card-${addon.id}`}
            key={addon.id}
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-semibold text-foreground">{addon.name}</p>
                <p className="mt-1 text-xs text-muted-foreground">{addon.description}</p>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${ADDON_COLORS[addon.category] || "text-muted-foreground bg-muted"}`}>
                {addon.category}
              </span>
            </div>
            <div className="flex items-center justify-between pt-1">
              <p className="font-display text-lg font-bold text-foreground">{addon.price_display}</p>
              <Button
                className="rounded-full"
                data-testid={`addon-buy-${addon.id}`}
                disabled={purchasing === addon.id}
                onClick={() => handlePurchase(addon.id)}
                size="sm"
              >
                {purchasing === addon.id ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ChevronRight className="mr-1 h-3.5 w-3.5" />
                )}
                Purchase
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export const SubscriptionPage = ({ token, user }) => {
  const [plans, setPlans] = useState([]);
  const [currentSub, setCurrentSub] = useState(null);
  const [currentTier, setCurrentTier] = useState(null);
  const [usage, setUsage] = useState({});
  const [billingCycle, setBillingCycle] = useState("monthly");
  const [checkoutLoading, setCheckoutLoading] = useState(null);
  const [pollingSessionId, setPollingSessionId] = useState(null);
  const [cancelLoading, setCancelLoading] = useState(false);
  const [rcReady, setRcReady] = useState(!isIOS()); // web is always "ready"

  const isHost = user?.role === "host";

  const loadPlans = useCallback(async () => {
    try {
      const payload = await apiRequest("/subscriptions/plans", { token });
      setPlans(payload.plans || []);
    } catch {
      toast.error("Unable to load subscription plans.");
    }
  }, [token]);

  const loadCurrentSub = useCallback(async () => {
    try {
      const payload = await apiRequest("/subscriptions/current", { token });
      setCurrentSub(payload.subscription);
      setCurrentTier(payload.tier);
      setUsage(payload.usage || {});
    } catch {
      // no subscription
    }
  }, [token]);

  useEffect(() => {
    loadPlans();
    loadCurrentSub();

    // Initialize and sync user with RevenueCat on iOS
    if (isIOS() && user?.id) {
      const initRC = async () => {
        // Try up to 3 times with increasing delays
        for (let attempt = 1; attempt <= 3; attempt++) {
          const ready = await ensureInitialized();
          if (ready) {
            await syncRevenueCatUser(user.id).catch(() => {});
            setRcReady(true);
            return;
          }
          // Wait before retrying (2s, 4s)
          if (attempt < 3) {
            await new Promise((r) => setTimeout(r, attempt * 2000));
          }
        }
        // All retries exhausted — still mark as ready so user can attempt purchase
        // (makePurchase will show a specific error if init truly failed)
        setRcReady(true);
        console.warn("[Kindred] RevenueCat init failed after 3 attempts");
      };
      initRC();
    }
  }, [loadPlans, loadCurrentSub, user?.id]);

  // Handle redirect back from Stripe with session_id
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id");
    if (sessionId) {
      setPollingSessionId(sessionId);
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  // Poll checkout status
  useEffect(() => {
    if (!pollingSessionId) return;
    let attempts = 0;
    const maxAttempts = 8;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await apiRequest(`/subscriptions/checkout/status/${pollingSessionId}`, { token });
        if (res.payment_status === "paid") {
          clearInterval(interval);
          setPollingSessionId(null);
          toast.success("Subscription activated! Welcome to your new plan.");
          loadCurrentSub();
        } else if (res.status === "expired" || attempts >= maxAttempts) {
          clearInterval(interval);
          setPollingSessionId(null);
          if (res.status === "expired") {
            toast.error("Checkout session expired. Please try again.");
          } else {
            toast.info("Payment is still processing. Check back shortly.");
          }
        }
      } catch {
        if (attempts >= maxAttempts) {
          clearInterval(interval);
          setPollingSessionId(null);
          toast.error("Unable to verify payment status.");
        }
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [pollingSessionId, token, loadCurrentSub]);

  const handleSelectPlan = async (planId) => {
    if (!isHost) {
      toast.error("Only the community host can manage subscriptions.");
      return;
    }
    setCheckoutLoading(planId);
    try {
      // Determine if we're on iOS and should use RevenueCat
      const useRevenueCat = isIOS();

      if (useRevenueCat) {
        // iOS: Use RevenueCat for native IAP
        const productIdMap = TIER_TO_PRODUCT_ID[planId];
        if (!productIdMap) {
          toast.error("Plan not available on this platform.");
          setCheckoutLoading(null);
          return;
        }

        const productId = billingCycle === "annual" ? productIdMap.annual : productIdMap.monthly;

        try {
          // Ensure RevenueCat is initialized before attempting purchase
          const ready = await ensureInitialized();
          if (!ready) {
            toast.error("Unable to connect to the App Store. Please check your connection and try again.");
            setCheckoutLoading(null);
            return;
          }

          const result = await makePurchase(productId);

          if (result.success) {
            toast.success("Purchase completed! Activating your plan...");
            // Sync user to RevenueCat and refresh subscription
            await syncRevenueCatUser(user?.id);
            // Give a moment for the backend to receive webhook notification
            setTimeout(() => {
              loadCurrentSub();
            }, 2000);
          } else {
            toast.error(result.message || "Purchase was not completed.");
          }
        } catch (error) {
          console.error("[Kindred] RevenueCat purchase error:", error);
          // Check if user cancelled (common for iOS purchases)
          const msg = error?.message || "";
          if (
            msg.includes("cancelled") ||
            msg.includes("user cancelled") ||
            msg.includes("PURCHASE_CANCELLED") ||
            error?.code === 1 // RevenueCat: purchaseCancelledError
          ) {
            toast.info("Purchase was cancelled.");
          } else if (msg.includes("not yet available") || msg.includes("not found in offerings")) {
            toast.error("This plan is not yet available for purchase. Please contact support.");
          } else if (msg.includes("not ready")) {
            toast.error("Unable to connect to the App Store. Please check your connection and try again.");
          } else {
            toast.error(msg || "Unable to complete purchase. Please try again.");
          }
        }
      } else {
        // Web: Use existing Stripe backend flow
        const res = await apiRequest("/subscriptions/checkout", {
          method: "POST",
          token,
          data: { plan_id: planId, billing_cycle: billingCycle, origin_url: window.location.origin },
        });
        if (res.url) {
          window.location.href = res.url;
        }
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Unable to start checkout.");
    } finally {
      setCheckoutLoading(null);
    }
  };

  const handleCancel = async () => {
    if (!window.confirm("Are you sure you want to cancel your subscription? You'll retain access until the end of your billing period.")) return;
    setCancelLoading(true);
    try {
      const res = await apiRequest("/subscriptions/cancel", { method: "POST", token });
      toast.success(res.message || "Subscription cancelled.");
      loadCurrentSub();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Unable to cancel subscription.");
    } finally {
      setCancelLoading(false);
    }
  };

  const currentTierId = currentTier?.id || "seedling";

  return (
    <div className="space-y-8" data-testid="subscription-page">
      {/* Header */}
      <div className="archival-card text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Sparkles className="h-7 w-7" />
        </div>
        <h1 className="mt-4 font-display text-3xl text-foreground sm:text-4xl" data-testid="subscription-page-title">
          Choose Your Plan
        </h1>
        <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground sm:text-base">
          Scale your community with the tools you need. Every plan includes core gathering features.
        </p>

        {/* Billing Toggle */}
        <div className="mt-6 flex items-center justify-center gap-3" data-testid="billing-toggle">
          <button
            className={`rounded-full px-5 py-2 text-sm font-semibold transition-all ${billingCycle === "monthly" ? "bg-primary text-primary-foreground shadow-md" : "bg-secondary text-secondary-foreground hover:bg-secondary/80"}`}
            onClick={() => setBillingCycle("monthly")}
            data-testid="billing-toggle-monthly"
          >
            Monthly
          </button>
          <button
            className={`rounded-full px-5 py-2 text-sm font-semibold transition-all ${billingCycle === "annual" ? "bg-primary text-primary-foreground shadow-md" : "bg-secondary text-secondary-foreground hover:bg-secondary/80"}`}
            onClick={() => setBillingCycle("annual")}
            data-testid="billing-toggle-annual"
          >
            Annual
            <span className="ml-1.5 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
              Save ~25%
            </span>
          </button>
        </div>
      </div>

      {/* Polling overlay */}
      {pollingSessionId && (
        <div className="archival-card flex items-center gap-3 border-primary/30 bg-primary/5" data-testid="payment-processing-banner">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <p className="text-sm font-medium text-foreground">Verifying your payment... This may take a moment.</p>
        </div>
      )}

      {/* Current Plan Summary */}
      {currentSub && (
        <div className="archival-card" data-testid="current-subscription-card">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="eyebrow-text">Active Subscription</p>
              <h2 className="font-display text-2xl text-foreground">
                {currentTier?.name || "Seedling"} Plan
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {currentSub.billing_cycle === "annual" ? "Annual" : "Monthly"} billing
                {currentSub.expires_at && ` · Renews ${new Date(currentSub.expires_at).toLocaleDateString()}`}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {usage.member_count || 0} of {currentTier?.max_members || 10} members · {usage.subyard_count || 0} subyard(s)
              </p>
            </div>
            {isHost && currentSub.status === "active" && (
              <Button
                className="rounded-full"
                disabled={cancelLoading}
                onClick={handleCancel}
                variant="destructive"
                data-testid="cancel-subscription-button"
              >
                {cancelLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <X className="mr-1 h-4 w-4" />}
                Cancel Plan
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Plan Cards */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" data-testid="plans-grid">
        {plans.map((plan) => (
          <PlanCard
            billingCycle={billingCycle}
            currentTierId={currentTierId}
            isCurrentTier={currentTierId === plan.id}
            isLoading={checkoutLoading === plan.id}
            key={plan.id}
            onSelect={handleSelectPlan}
            plan={plan}
          />
        ))}
      </div>

      {/* Add-Ons Section — hidden on iOS per App Store guideline 3.1.1 */}
      {!isIOS() && <AddOnsSection token={token} />}

      {/* FAQ / Notes */}
      <div className="archival-card" data-testid="subscription-faq">
        <h2 className="font-display text-xl text-foreground">Pricing Notes</h2>
        <div className="mt-3 space-y-3 text-sm text-muted-foreground">
          <p>All plans include a 14-day free trial. Cancel anytime before the trial ends and you won't be charged.</p>
          <p>Annual billing offers approximately 25% savings compared to monthly billing.</p>
          <p>Downgrading takes effect at the end of your current billing period. Your community data is always preserved.</p>
          <p>For communities of 100+ members, Elder Grove offers dedicated support and custom integrations — reach out to discuss your needs.</p>
        </div>
      </div>

      {/* Auto-Renewal Disclosure (Apple 3.1.2(c) / Google Play compliance) */}
      <div className="archival-card space-y-3" data-testid="subscription-legal">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Paid plans are auto-renewable subscriptions. Payment is charged to your Apple ID account (iOS),
          Google Play account (Android), or payment method on file (web) at confirmation of purchase.
          Subscriptions automatically renew unless auto-renew is turned off at least 24 hours before the
          end of the current billing period. Your account will be charged for renewal within 24 hours prior
          to the end of the current period. You can manage and cancel subscriptions at any time: on iOS, go
          to Settings &gt; [Your Name] &gt; Subscriptions; on Android, go to Google Play Store &gt; Menu &gt;
          Subscriptions; on web, use the Cancel Plan button above.
        </p>
        <div className="flex items-center justify-center gap-4 text-xs">
          <a href="/terms" className="text-primary hover:underline">Terms of Service</a>
          <a href="/privacy" className="text-primary hover:underline">Privacy Policy</a>
        </div>
      </div>
    </div>
  );
};
