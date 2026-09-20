const PENDING_PLAN_KEY = "kindredPendingPlan";

// A visitor picks a plan on a public page, then has to make an account before
// RevenueCat can bill them (web billing needs an app user id). Remember the
// choice so /subscription opens on it instead of asking twice. Wrapped because
// private mode and blocked site data make localStorage throw.
export const rememberPendingPlan = (planId, cycle) => {
  try {
    localStorage.setItem(PENDING_PLAN_KEY, JSON.stringify({ planId, cycle }));
  } catch (error) {
    /* the plan just won't be preselected */
  }
};

export const takePendingPlan = () => {
  try {
    const raw = localStorage.getItem(PENDING_PLAN_KEY);
    if (!raw) return null;
    localStorage.removeItem(PENDING_PLAN_KEY);
    const parsed = JSON.parse(raw);
    if (!parsed?.planId) return null;
    return { planId: parsed.planId, cycle: parsed.cycle === "annual" ? "annual" : "monthly" };
  } catch (error) {
    return null;
  }
};

export const formatPrice = (amount, minimumFractionDigits = 2) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits,
    maximumFractionDigits: 2,
  }).format(amount);

export const formatLocalizedPrice = (amount, currencyCode) => {
  if (!Number.isFinite(amount) || !currencyCode) return "";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currencyCode,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return "";
  }
};

export const calculateSavings = (monthlyAmount, annualAmount) => {
  if (!Number.isFinite(monthlyAmount) || !Number.isFinite(annualAmount) || monthlyAmount <= 0) {
    return null;
  }
  const monthlyTotal = Math.round(monthlyAmount * 12 * 100) / 100;
  const amount = Math.round((monthlyTotal - annualAmount) * 100) / 100;
  if (amount <= 0) return null;
  const percent = Math.round((amount / monthlyTotal) * 1000) / 10;
  return { amount, percent, comparison: "12_monthly_payments" };
};

export const normalizePlanPricing = (plan) => {
  if (plan?.billing_options) return plan;

  // Supports a staged backend/frontend rollout while preserving API-sourced
  // amounts. The canonical API schema is billing_options.
  if (plan?.id === "seedling") {
    return {
      ...plan,
      billing_options: {
        free: { amount: 0, currency: "usd", recurring: false, label: "Free" },
      },
      custom_pricing: false,
    };
  }
  if (plan?.id === "elder-grove") {
    return { ...plan, billing_options: {}, custom_pricing: true };
  }
  if (Number.isFinite(plan?.monthly_price) && Number.isFinite(plan?.annual_price)) {
    return {
      ...plan,
      billing_options: {
        monthly: {
          amount: plan.monthly_price,
          currency: "usd",
          recurring: true,
          period: "month",
        },
        annual: {
          amount: plan.annual_price,
          currency: "usd",
          recurring: true,
          period: "year",
          savings: calculateSavings(plan.monthly_price, plan.annual_price),
        },
      },
      custom_pricing: false,
    };
  }
  return { ...plan, billing_options: {}, custom_pricing: Boolean(plan?.custom_pricing) };
};

export const normalizePlans = (plans = []) => plans.map(normalizePlanPricing);
