import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/pricing";

// `onChoose(planId, cycle)` turns this from a price list into a storefront.
// Without it the cards stay display-only, which is what every public page used
// to render — five tiers, real prices, and nothing to click.
export const PublicPlanCards = ({ plans, detailed = false, onChoose, supportEmail }) => (
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
                {onChoose && (
                  <Button
                    className="mt-3 w-full"
                    data-testid={`public-plan-choose-${plan.id}-monthly`}
                    onClick={() => onChoose(plan.id, "monthly")}
                    size="sm"
                    variant="outline"
                  >
                    Choose monthly
                  </Button>
                )}
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
                {onChoose && (
                  <Button
                    className="mt-3 w-full"
                    data-testid={`public-plan-choose-${plan.id}-annual`}
                    onClick={() => onChoose(plan.id, "annual")}
                    size="sm"
                  >
                    Choose annual
                  </Button>
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
          {onChoose && free && (
            <Button
              className="mt-4 w-full"
              data-testid={`public-plan-choose-${plan.id}-free`}
              onClick={() => onChoose(plan.id, "free")}
              size="sm"
            >
              Start free
            </Button>
          )}
          {onChoose && isCustom && supportEmail && (
            <Button asChild className="mt-4 w-full" data-testid={`public-plan-choose-${plan.id}-contact`} size="sm" variant="outline">
              <a href={`mailto:${supportEmail}`}>Talk to us</a>
            </Button>
          )}
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
