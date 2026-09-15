import { describePlanUsage } from "./planUsage";

const payload = ({ id = "seedling", name = "Seedling", max = 10, members = 4, provider } = {}) => ({
  subscription: provider ? { provider } : null,
  tier: { id, name, max_members: max },
  usage: { member_count: members, subyard_count: 0 },
});

describe("describePlanUsage", () => {
  it("reports room left on a free family without prompting", () => {
    expect(describePlanUsage(payload({ members: 4 }))).toMatchObject({
      planName: "Seedling",
      memberCount: 4,
      maxMembers: 10,
      remaining: 6,
      atLimit: false,
      nearLimit: false,
      canUpgrade: true,
    });
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
    expect(admin.canUpgrade).toBe(false);
  });

  it("returns null when the plan payload is incomplete", () => {
    expect(describePlanUsage(null)).toBeNull();
    expect(describePlanUsage({ tier: { id: "seedling" }, usage: {} })).toBeNull();
  });
});
