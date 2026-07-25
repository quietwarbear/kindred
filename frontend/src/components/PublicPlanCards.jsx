import { formatPrice } from "@/lib/pricing";

export const PublicPlanCards = ({ plans, detailed = false }) => (
  <div className={`grid gap-4 ${detailed ? "md:grid-cols-2 xl:grid-cols-3" : "sm:grid-cols-2 xl:grid-cols-4"}`}>
    {plans.map((plan) => {
      const isCustom = plan.id === "elder-grove";
      const free = plan.billing_options?.free;
      const monthly = plan.billing_options?.monthly;
      const annual = plan.billing_options?.annual;
      return (
        <article className="soft-panel" data-testid={`public-plan-${plan.id}`} key={plan.id}>
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">{plan.name}</p>
          {isCustom ? (
            <p className="mt-3 font-display text-3xl font-bold text-foreground">Contact us</p>
          ) : free ? (
            <div className="mt-3" data-testid={`public-plan-price-${plan.id}-free`}>
              <p className="font-display text-3xl font-bold text-foreground">Free</p>
              <p className="mt-1 text-xs text-muted-foreground">No billing interval or recurring charge</p>
            </div>
          ) : monthly && annual ? (
            <div className="mt-3 grid gap-2">
              <div className="rounded-xl border border-border/70 p-3" data-testid={`public-plan-price-${plan.id}-monthly`}>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Monthly</p>
                <p className="font-display text-2xl font-bold text-foreground">{formatPrice(monthly.amount)}</p>
                <p className="text-xs text-muted-foreground">Billed every month</p>
              </div>
              <div className="rounded-xl border border-primary/25 bg-primary/5 p-3" data-testid={`public-plan-price-${plan.id}-annual`}>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Annual</p>
                <p className="font-display text-2xl font-bold text-foreground">{formatPrice(annual.amount)}</p>
                <p className="text-xs text-muted-foreground">Billed once per year</p>
                {annual.savings && (
                  <p className="mt-1 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                    Save {formatPrice(annual.savings.amount)} per year ({annual.savings.percent}%) versus 12 monthly payments
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className="mt-3 text-sm font-medium text-destructive">Pricing temporarily unavailable</p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {isCustom ? "For communities above 100 members" : `Up to ${plan.max_members} members`}
          </p>
          <p className="mt-3 text-sm text-muted-foreground">{plan.tagline}</p>
          {detailed && (
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              {plan.features.map((feature) => <li key={feature}>• {feature}</li>)}
            </ul>
          )}
        </article>
      );
    })}
  </div>
);
