import { useEffect, useState } from "react";
import { ArrowRight, Crown } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { describePlanUsage } from "@/lib/planUsage";

/**
 * Host-facing plan status with a path to the subscription page.
 * Render it only for hosts — they are the only role that can change the plan.
 *
 * variant="settings" always shows the plan; variant="today" shows only when the
 * family is near or at its member limit and a self-serve upgrade exists.
 */
export const PlanUpgradeCard = ({ token, variant = "settings" }) => {
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiRequest("/subscriptions/current", { token })
      .then((payload) => {
        if (!cancelled) setUsage(describePlanUsage(payload));
      })
      .catch(() => {
        /* Plan status is supplementary; the page works without it. */
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (!usage) return null;

  const membersLine = usage.maxMembers
    ? `${usage.memberCount} of ${usage.maxMembers} members`
    : `${usage.memberCount} members`;

  if (variant === "today") {
    if (!usage.canUpgrade || !(usage.atLimit || usage.nearLimit)) return null;
    return (
      <section className="archival-card" data-testid="today-plan-upgrade-card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <Crown className="mt-1 h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">{usage.planName} plan · {membersLine}</p>
              <h2 className="mt-2 font-display text-3xl">
                {usage.atLimit ? "Your family is full" : "Your family is almost full"}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">
                {usage.atLimit
                  ? "New relatives can't join until the plan has room. Upgrade to keep bringing everyone in."
                  : `Only ${usage.remaining} ${usage.remaining === 1 ? "spot is" : "spots are"} left. Upgrade before the next invitations go out.`}
              </p>
            </div>
          </div>
          <Button asChild data-testid="today-plan-upgrade-button">
            <Link to="/subscription">
              Upgrade plan <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className="archival-card" data-testid="settings-plan-card">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Crown className="h-5 w-5 text-primary" />
          <div>
            <p className="eyebrow-text">Plan</p>
            <h3 className="mt-2 font-display text-3xl text-foreground">{usage.planName}</h3>
            <p className="mt-1 text-sm text-muted-foreground" data-testid="settings-plan-usage">
              {membersLine}
              {usage.atLimit ? " · family is full" : usage.nearLimit ? " · almost full" : ""}
            </p>
          </div>
        </div>
        <Button asChild variant={usage.canUpgrade ? "default" : "outline"} data-testid="settings-plan-button">
          <Link to="/subscription">{usage.canUpgrade ? "Upgrade plan" : "Manage plan"}</Link>
        </Button>
      </div>
    </section>
  );
};
