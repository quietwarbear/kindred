import {
  calculateSavings,
  normalizePlanPricing,
} from "./pricing";

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
