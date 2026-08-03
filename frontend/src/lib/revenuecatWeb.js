import { calculateSavings } from "./pricing";

const WEB_API_KEY = process.env.REACT_APP_REVENUECAT_WEB_KEY;

let purchasesInstance = null;
let configuredUserId = null;
let revenueCatWebSdkPromise = null;

const getRevenueCatWebSdk = () => {
  if (!revenueCatWebSdkPromise) {
    revenueCatWebSdkPromise = import("@revenuecat/purchases-js");
  }
  return revenueCatWebSdkPromise;
};

const requireMapping = (mapping, planId, billingInterval) => {
  const expected = mapping?.[planId]?.[billingInterval];
  if (
    !expected?.product_id
    || !expected?.offering_id
    || !expected?.package_id
    || !expected?.entitlement_id
    || !Number.isInteger(expected?.amount_micros)
    || !expected?.currency
    || !expected?.period
  ) {
    throw new Error(`RevenueCat Billing is not configured for ${planId}/${billingInterval}.`);
  }
  return expected;
};

export const initializeRevenueCatWeb = async (appUserId) => {
  if (!WEB_API_KEY) {
    throw new Error("RevenueCat Billing is not configured for web purchases.");
  }
  if (!appUserId) {
    throw new Error("Sign in before starting a web subscription.");
  }
  if (purchasesInstance) {
    if (configuredUserId !== appUserId) {
      throw new Error("RevenueCat Billing customer identity changed. Reload before purchasing.");
    }
    return purchasesInstance;
  }

  const { Purchases } = await getRevenueCatWebSdk();
  purchasesInstance = Purchases.configure({
    apiKey: WEB_API_KEY,
    appUserId,
  });
  configuredUserId = appUserId;
  return purchasesInstance;
};

export const validateRevenueCatWebProduct = (
  offering,
  rcPackage,
  expected,
  planId,
  billingInterval,
) => {
  const product = rcPackage?.webBillingProduct;
  const contradictions = [];
  if (!offering || offering.identifier !== expected.offering_id) contradictions.push("offering");
  if (!rcPackage || rcPackage.identifier !== expected.package_id) contradictions.push("package");
  if (!product || product.identifier !== expected.product_id) contradictions.push("product");
  if (product?.productType !== "subscription") contradictions.push("product type");
  if (product?.normalPeriodDuration !== expected.period) contradictions.push("billing interval");
  if (product?.price?.currency?.toUpperCase() !== expected.currency) contradictions.push("currency");
  if (product?.price?.amountMicros !== expected.amount_micros) contradictions.push("amount");
  if (product?.freeTrialPhase) contradictions.push("free trial");
  if (product?.introPricePhase) contradictions.push("introductory price");

  if (contradictions.length) {
    throw new Error(
      `RevenueCat Billing catalog mismatch for ${planId}/${billingInterval}: ${contradictions.join(", ")}.`,
    );
  }
  return product;
};

const resolveVerifiedPackage = async (
  purchases,
  mapping,
  planId,
  billingInterval,
) => {
  const expected = requireMapping(mapping, planId, billingInterval);
  const offerings = await purchases.getOfferings({ currency: expected.currency });
  const offering = offerings?.all?.[expected.offering_id];
  const rcPackage = offering?.packagesById?.[expected.package_id]
    || offering?.availablePackages?.find((candidate) => candidate?.identifier === expected.package_id);
  const product = validateRevenueCatWebProduct(
    offering,
    rcPackage,
    expected,
    planId,
    billingInterval,
  );
  return { expected, rcPackage, product };
};

export const getVerifiedRevenueCatWebPricing = async (appUserId, mapping) => {
  const purchases = await initializeRevenueCatWeb(appUserId);
  const localized = {};
  for (const planId of Object.keys(mapping || {})) {
    localized[planId] = {};
    for (const billingInterval of ["monthly", "annual"]) {
      const { expected, product } = await resolveVerifiedPackage(
        purchases,
        mapping,
        planId,
        billingInterval,
      );
      localized[planId][billingInterval] = {
        amount: product.price.amountMicros / 1_000_000,
        currencyCode: product.price.currency,
        formattedPrice: product.price.formattedPrice,
        packageIdentifier: expected.package_id,
        productId: expected.product_id,
      };
    }
    const monthly = localized[planId].monthly;
    const annual = localized[planId].annual;
    if (monthly?.currencyCode && monthly.currencyCode === annual?.currencyCode) {
      const savings = calculateSavings(monthly.amount, annual.amount);
      if (savings) {
        annual.savings = {
          ...savings,
          currencyCode: annual.currencyCode,
        };
      }
    }
  }
  return localized;
};

export const makeRevenueCatWebPurchase = async ({
  appUserId,
  email,
  mapping,
  planId,
  billingInterval,
}) => {
  const purchases = await initializeRevenueCatWeb(appUserId);
  const { expected, rcPackage } = await resolveVerifiedPackage(
    purchases,
    mapping,
    planId,
    billingInterval,
  );
  const purchaseResult = await purchases.purchase({
    rcPackage,
    customerEmail: email || undefined,
    metadata: {
      kindred_plan_id: planId,
      kindred_billing_interval: billingInterval,
    },
    skipSuccessPage: true,
    showDiscountCodeField: false,
    termsAndConditionsUrl: "https://www.heykindred.org/terms",
  });
  const active = purchaseResult?.customerInfo?.entitlements?.active || {};
  if (!active[expected.entitlement_id]) {
    throw new Error("The RevenueCat purchase did not grant the expected Kindred entitlement.");
  }
  return purchaseResult;
};

export const openRevenueCatWebSubscriptionManagement = async (appUserId) => {
  const purchases = await initializeRevenueCatWeb(appUserId);
  const customerInfo = await purchases.getCustomerInfo();
  if (!customerInfo?.managementURL) {
    throw new Error("RevenueCat subscription management is unavailable.");
  }
  window.location.assign(customerInfo.managementURL);
};

export const isRevenueCatWebCancellation = (error) => error?.errorCode === 1;
