import { describePlanUsage, isContestOpen, KEEP_THE_RECORD } from "./planUsage";

const payload = ({ id = "seedling", name = "Seedling", max = 10, members = 4, provider } = {}) => ({
  subscription: provider ? { provider } : null,
  tier: { id, name, max_members: max },
  usage: { member_count: members, subyard_count: 0 },
});

describe("describePlanUsage", () => {
  it("reports room left on a free family", () => {
    expect(describePlanUsage(payload({ members: 4 }))).toMatchObject({
      planName: "Seedling",
      memberCount: 4,
      maxMembers: 10,
      remaining: 6,
      atLimit: false,
      nearLimit: false,
      isPaid: false,
      canUpgrade: true,
    });
  });

  it("treats every non-Seedling plan as paid", () => {
    expect(describePlanUsage(payload({ id: "sapling", name: "Sapling", max: 25 })).isPaid).toBe(true);
    expect(describePlanUsage(payload({ id: "oak", name: "Oak", max: 50 })).isPaid).toBe(true);
  });

  it("flags a family within three spots of its limit", () => {
    expect(describePlanUsage(payload({ members: 7 }))).toMatchObject({ remaining: 3, nearLimit: true, atLimit: false });
  });

  it("flags a full family, including one already over its limit", () => {
    expect(describePlanUsage(payload({ members: 10 }))).toMatchObject({ remaining: 0, atLimit: true, nearLimit: false });
    expect(describePlanUsage(payload({ members: 12 }))).toMatchObject({ remaining: 0, atLimit: true });
  });

  it("offers no self-serve upgrade above Redwood or on custom Elder Grove", () => {
    expect(describePlanUsage(payload({ id: "redwood", name: "Redwood", max: 100, members: 99 })).canUpgrade).toBe(false);
    const elder = describePlanUsage(payload({ id: "elder-grove", name: "Elder Grove", max: 9999, members: 400 }));
    expect(elder).toMatchObject({ canUpgrade: false, maxMembers: null, remaining: null, atLimit: false, nearLimit: false });
  });

  it("never prompts the admin override to upgrade", () => {
    const admin = describePlanUsage(payload({ id: "redwood", name: "Redwood", max: 100, members: 3, provider: "admin_override" }));
    expect(admin).toMatchObject({ canUpgrade: false, isPaid: true });
  });

  it("returns null when the plan payload is incomplete", () => {
    expect(describePlanUsage(null)).toBeNull();
    expect(describePlanUsage({ tier: { id: "seedling" }, usage: {} })).toBeNull();
  });
});

describe("isContestOpen", () => {
  it("opens at midnight Pacific on Sep 7", () => {
    expect(isContestOpen(Date.parse("2026-09-06T23:59:59-07:00"))).toBe(false);
    expect(isContestOpen(KEEP_THE_RECORD.startsAt)).toBe(true);
  });

  // The amended rules close entries on Dec 6 at 11:59 PM PT, so the last full
  // day of entry is Dec 6 and the window ends at midnight starting Dec 7.
  // This test still asserted the older Dec 5 close after d36710e corrected
  // planUsage.js, which is why it has been failing on main since Sep 20.
  it("stays open through the whole of Dec 6 Pacific and closes after", () => {
    expect(isContestOpen(Date.parse("2026-12-06T23:59:59-08:00"))).toBe(true);
    expect(isContestOpen(Date.parse("2026-12-07T00:00:00-08:00"))).toBe(false);
  });

  it("is still open on Dec 5, a day the older window wrongly excluded", () => {
    expect(isContestOpen(Date.parse("2026-12-05T12:00:00-08:00"))).toBe(true);
  });
});
