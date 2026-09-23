import { useEffect, useState } from "react";
import { ArrowRight, Crown, Trophy } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { describePlanUsage, isContestOpen, KEEP_THE_RECORD } from "@/lib/planUsage";
import { ReunionPassChipIn } from "@/components/ReunionPassChipIn";

/**
 * Plan status with a path to the subscription page.
 *
 * variant="settings" (render for hosts only) always shows the plan.
 * variant="today" is rendered for every role:
 *   - hosts on the free plan see a Keep The Record upgrade prompt while the
 *     contest is open, otherwise a prompt only when the family is near or at
 *     its member limit;
 *   - everyone else on a free-plan family is told to ask the host, since only
 *     the host can change the plan.
 */
export const PlanUpgradeCard = ({ token, variant = "settings", isHost = false }) => {
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
    const contestOpen = isContestOpen();

    if (!isHost) {
      if (!contestOpen || usage.isPaid) return null;
      return (
        <section className="archival-card" data-testid="today-contest-ask-host-card">
          <div className="flex items-start gap-3">
            <Trophy className="mt-1 h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">{KEEP_THE_RECORD.name}</p>
              <h2 className="mt-2 font-display text-3xl">Your family isn’t entered yet</h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">
                {KEEP_THE_RECORD.name} is for subscriber families, and yours is on the free {usage.planName} plan.
                Only your host can change the plan — but you can help pay for it.
              </p>
            </div>
          </div>
          {/* Was an errand: "ask your host". Now an action — a cousin can put
              money toward the pass without waiting for anyone. */}
          <div className="mt-5">
            <ReunionPassChipIn token={token} variant="today" />
          </div>
        </section>
      );
    }

    const contestPrompt = contestOpen && !usage.isPaid && usage.canUpgrade;
    const limitPrompt = usage.canUpgrade && (usage.atLimit || usage.nearLimit);
    if (!contestPrompt && !limitPrompt) return null;

    const limitSentence = usage.atLimit
      ? "New relatives can't join until the plan has room."
      : usage.nearLimit
        ? `Only ${usage.remaining} ${usage.remaining === 1 ? "spot is" : "spots are"} left.`
        : "";

    let heading;
    let body;
    if (contestPrompt) {
      heading = `Upgrade to enter ${KEEP_THE_RECORD.name}`;
      body = `${KEEP_THE_RECORD.name} is for subscriber families. Upgrade from ${usage.planName} by December 6 so your family can enter.${limitSentence ? ` ${limitSentence}` : ""}`;
    } else if (usage.atLimit) {
      heading = "Your family is full";
      body = `${limitSentence} Upgrade to keep bringing everyone in.`;
    } else {
      heading = "Your family is almost full";
      body = `${limitSentence} Upgrade before the next invitations go out.`;
    }

    return (
      <section className="archival-card" data-testid={contestPrompt ? "today-contest-upgrade-card" : "today-plan-upgrade-card"}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            {contestPrompt ? <Trophy className="mt-1 h-5 w-5 text-primary" /> : <Crown className="mt-1 h-5 w-5 text-primary" />}
            <div>
              <p className="eyebrow-text">{usage.planName} plan · {membersLine}</p>
              <h2 className="mt-2 font-display text-3xl">{heading}</h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">{body}</p>
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
