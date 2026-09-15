// Plan status for upgrade prompts, derived from GET /subscriptions/current.

// pricing.py uses 9999 as "no practical limit" (Elder Grove).
const UNLIMITED_MEMBERS = 9999;
// Nothing self-serve above these: Redwood is the top paid plan, Elder Grove is custom.
const TOP_PLAN_IDS = new Set(["redwood", "elder-grove"]);
const FREE_PLAN_ID = "seedling";
export const NEAR_LIMIT_REMAINING = 3;

// Keep The Record is open to subscriber families from Sep 7 through Dec 5 2026,
// Pacific time. The end is exclusive: midnight starting Dec 6.
export const KEEP_THE_RECORD = {
  name: "Keep The Record",
  startsAt: Date.parse("2026-09-07T00:00:00-07:00"),
  endsAt: Date.parse("2026-12-06T00:00:00-08:00"),
};

export const isContestOpen = (now = Date.now()) =>
  now >= KEEP_THE_RECORD.startsAt && now < KEEP_THE_RECORD.endsAt;

/**
 * Returns null when the payload lacks the fields a prompt needs, so callers
 * render nothing rather than a guessed plan.
 */
export const describePlanUsage = (payload) => {
  const tier = payload?.tier;
  const maxMembers = Number(tier?.max_members);
  const memberCount = Number(payload?.usage?.member_count);
  if (!tier?.id || !Number.isFinite(maxMembers) || !Number.isFinite(memberCount)) return null;

  const limited = maxMembers < UNLIMITED_MEMBERS;
  const remaining = limited ? Math.max(maxMembers - memberCount, 0) : null;
  // Owner/admin accounts are shown Redwood regardless of what the family pays for.
  const isOverride = payload?.subscription?.provider === "admin_override";

  return {
    planId: tier.id,
    planName: tier.name || "Current",
    memberCount,
    maxMembers: limited ? maxMembers : null,
    remaining,
    atLimit: limited && remaining === 0,
    nearLimit: limited && remaining > 0 && remaining <= NEAR_LIMIT_REMAINING,
    // The backend only reports a paid tier for active, past-due or canceling subscriptions.
    isPaid: tier.id !== FREE_PLAN_ID,
    canUpgrade: !isOverride && !TOP_PLAN_IDS.has(tier.id),
  };
};
