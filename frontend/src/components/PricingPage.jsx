import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { PublicPlanCards } from "@/components/PublicPlanCards";
import { PUBLIC_IDENTITY } from "@/config/publicIdentity";
import { usePublicPlans } from "@/hooks/usePublicPlans";

// Mirrors SubscriptionPage: web purchases are live only once the deployment
// sets the RevenueCat Billing web key.
const WEB_PURCHASES_ENABLED = Boolean(process.env.REACT_APP_REVENUECAT_WEB_KEY);

export const PricingPage = () => {
  const { plans, loading, error } = usePublicPlans();

  return (
    <div className="app-canvas min-h-screen py-8">
      <main className="page-section">
        <Link className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline" to="/">
          <ArrowLeft className="h-4 w-4" /> Back to Kindred
        </Link>
        <section className="archival-card mt-6" data-testid="public-pricing-page">
          <p className="eyebrow-text">Pricing</p>
          <h1 className="mt-3 font-display text-4xl text-foreground sm:text-5xl">Plans for communities of every size.</h1>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base">
            Plan names, member limits, and billing amounts below come directly from Kindred's subscription service.
            Subscription management remains available inside the signed-in application.
          </p>
          {!WEB_PURCHASES_ENABLED && (
            <div
              className="mt-6 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4"
              data-testid="web-subscription-unavailable"
              role="status"
            >
              <p className="text-sm font-semibold text-foreground">
                Web subscriptions are temporarily unavailable while billing is being updated.
              </p>
            </div>
          )}
          <div className="mt-8" aria-live="polite">
            {loading && <p className="text-sm text-muted-foreground">Loading current plans…</p>}
            {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
            {!loading && !error && <PublicPlanCards detailed plans={plans} />}
          </div>
          <p className="mt-8 text-sm text-muted-foreground">
            Questions about plans? Email{" "}
            <a className="font-semibold text-primary hover:underline" href={`mailto:${PUBLIC_IDENTITY.supportEmail}`}>
              {PUBLIC_IDENTITY.supportEmail}
            </a>.
          </p>
        </section>
      </main>
    </div>
  );
};
