import {calculateSavings,
  normalizePlanPricing, rememberPendingPlan, takePendingPlan } from "./pricing";

test("keeps Seedling explicitly free without recurring intervals", () => {
  const plan = normalizePlanPricing({
    id: "seedling",
    monthly_price: 0,
    annual_price: 0,
  });
  expect(Object.keys(plan.billing_options)).toEqual(["free"]);
  expect(plan.billing_options.free.recurring).toBe(false);
});

test("normalizes both paid intervals during a staged API rollout", () => {
  const plan = normalizePlanPricing({
    id: "sapling",
    monthly_price: 9.99,
    annual_price: 89.99,
  });
  expect(plan.billing_options.monthly.amount).toBe(9.99);
  expect(plan.billing_options.annual.amount).toBe(89.99);
  expect(plan.billing_options.annual.savings).toEqual({
    amount: 29.89,
    percent: 24.9,
    comparison: "12_monthly_payments",
  });
});

test("calculates savings from provider-localized numeric package prices", () => {
  expect(calculateSavings(12.5, 120)).toEqual({
    amount: 30,
    percent: 20,
    comparison: "12_monthly_payments",
  });
  expect(calculateSavings(10, 130)).toBeNull();
  expect(calculateSavings(undefined, 100)).toBeNull();
});

describe("the plan a visitor picks on a public page", () => {
  beforeEach(() => {
    try { localStorage.clear(); } catch (e) { /* not available */ }
  });

  it("survives the trip through sign-up", () => {
    rememberPendingPlan("oak", "annual");
    expect(takePendingPlan()).toEqual({ planId: "oak", cycle: "annual" });
  });

  it("is consumed once, so a later visit to /subscription is not hijacked", () => {
    rememberPendingPlan("sapling", "monthly");
    expect(takePendingPlan()).not.toBeNull();
    expect(takePendingPlan()).toBeNull();
  });

  it("returns null when nothing was picked", () => {
    expect(takePendingPlan()).toBeNull();
  });

  it("defaults an unrecognised cycle to monthly rather than billing a year", () => {
    rememberPendingPlan("redwood", "lifetime");
    expect(takePendingPlan()).toEqual({ planId: "redwood", cycle: "monthly" });
  });

  it("ignores a stored value that is not a plan", () => {
    localStorage.setItem("kindredPendingPlan", JSON.stringify({ cycle: "annual" }));
    expect(takePendingPlan()).toBeNull();
  });

  it("survives corrupted storage without throwing", () => {
    localStorage.setItem("kindredPendingPlan", "{not json");
    expect(takePendingPlan()).toBeNull();
  });
});
