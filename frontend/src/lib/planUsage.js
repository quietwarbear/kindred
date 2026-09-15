// Plan status for host-facing upgrade prompts, derived from GET /subscriptions/current.

// pricing.py uses 9999 as "no practical limit" (Elder Grove).
const UNLIMITED_MEMBERS = 9999;
// Nothing self-serve above these: Redwood is the top paid plan, Elder Grove is custom.
const TOP_PLAN_IDS = new Set(["redwood", "elder-grove"]);
export const NEAR_LIMIT_REMAINING = 3;

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
    canUpgrade: !isOverride && !TOP_PLAN_IDS.has(tier.id),
  };
};
