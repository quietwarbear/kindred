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
