/**
 * RevenueCat integration for App Store and Google Play purchases via Capacitor
 * Falls back gracefully on web platforms
 */
import { Capacitor } from "@capacitor/core";
import { Browser } from "@capacitor/browser";
import { Purchases } from "@revenuecat/purchases-capacitor";
import { apiRequest } from "@/lib/api";
import { calculateSavings } from "@/lib/pricing";

const REVENUECAT_API_KEYS = {
    ios: process.env.REACT_APP_REVENUECAT_IOS_KEY,
    android: process.env.REACT_APP_REVENUECAT_ANDROID_KEY,
};

let revenueCatConfigPromise = null;

export const getRevenueCatConfig = async () => {
    if (!revenueCatConfigPromise) {
          revenueCatConfigPromise = apiRequest("/revenuecat/config")
            .catch((error) => {
              revenueCatConfigPromise = null;
              throw error;
            });
    }
    return revenueCatConfigPromise;
};

export const getRevenueCatProductMapping = async () => {
    const config = await getRevenueCatConfig();
    const platform = Capacitor.getPlatform();
    const providerPlatform = platform === "android" ? "play_store" : "app_store";
    return config?.product_mapping_by_platform?.[providerPlatform]
      || config?.product_mapping
      || {};
};

let revenueCatInitialized = false;
let initPromise = null;

// How long (ms) to wait for RevenueCat to initialize before giving up
// RevenueCat SDK now runs a health report during configure(), which can
// take 20s+ in sandbox. 30s gives it room without hanging forever.
const RC_INIT_TIMEOUT_MS = 30000;

/**
 * Initialize RevenueCat SDK on supported native stores
 * Safe to call on web - will no-op.
 * Re-entrant: returns the same promise if already in progress.
 * Has a timeout so it never hangs forever.
 */
export const initializeRevenueCat = async () => {
    if (revenueCatInitialized) return true;
    if (initPromise) return initPromise;

    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || !["ios", "android"].includes(platform)) {
          console.log("[Kindred] RevenueCat: skipping init (not a supported native store)");
          return false;
    }

    const apiKey = REVENUECAT_API_KEYS[platform];
    if (!apiKey) {
          console.warn(`[Kindred] RevenueCat: ${platform} API key is not configured`);
          return false;
    }

    const initCore = (async () => {
          try {
                  console.log(`[Kindred] RevenueCat: configuring ${platform} purchases`);
                  await Purchases.configure({
                            apiKey,
                            appUserID: null,
                  });
                  revenueCatInitialized = true;
                  console.log("[Kindred] RevenueCat initialized successfully");

                  // Pre-fetch offerings in background (don't block init on this)
                  // The SDK caches them so subsequent getOfferings() calls are instant
                  Purchases.getOfferings().then((offerings) => {
                    let totalPackages = 0;
                    if (offerings?.all) {
                      for (const offering of Object.values(offerings.all)) {
                        totalPackages += (offering.availablePackages || []).length;
                      }
                    }
                    console.log("[Kindred] RevenueCat offerings pre-fetched:", totalPackages, "packages available across all offerings");
                    if (totalPackages === 0) {
                      console.warn("[Kindred] No packages found in any offering — check RevenueCat dashboard");
                    }
                  }).catch(() => {
                    console.warn("[Kindred] RevenueCat offerings pre-fetch failed");
                  });

                  return true;
          } catch {
                  console.error("[Kindred] Failed to initialize RevenueCat");
                  initPromise = null; // Allow retry
            return false;
          }
    })();

    const timeout = new Promise((resolve) =>
          setTimeout(() => {
                  console.warn("[Kindred] RevenueCat init timed out after " + RC_INIT_TIMEOUT_MS + "ms");
                  initPromise = null; // Allow retry
                           resolve(false);
          }, RC_INIT_TIMEOUT_MS)
                                  );

    initPromise = Promise.race([initCore, timeout]);
    return initPromise;
};

/**
 * Ensure RevenueCat is initialized before performing an action.
 * Useful when the user reaches the subscription page before init completes.
 */
export const ensureInitialized = async () => {
    if (revenueCatInitialized) return true;
    return initializeRevenueCat();
};

/**
 * Fetch offerings from RevenueCat on supported native stores
 * Returns structured offerings or null on web/error
 */
export const fetchOfferings = async () => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || !["ios", "android"].includes(platform)) return null;

    const ready = await ensureInitialized();
    if (!ready) return null;

    try {
          const offerings = await Purchases.getOfferings();
          return offerings;
    } catch {
          console.error("[Kindred] Error fetching RevenueCat offerings");
          return null;
    }
};

/**
 * Return StoreKit-localized display prices for every mapped package.
 * Savings are calculated only when both package amounts use the same currency.
 */
export const getLocalizedRevenueCatPricing = async (productMapping) => {
    const offerings = await fetchOfferings();
    if (!offerings) return {};

    const localized = {};
    for (const [planId, intervals] of Object.entries(productMapping || {})) {
          const offering = offerings?.all?.[`${planId}_access`];
          const packages = offering?.availablePackages || [];
          const planPricing = {};
          for (const billingInterval of ["monthly", "annual"]) {
                  const productId = intervals?.[billingInterval];
                  const expectedPackage = billingInterval === "monthly" ? "$rc_monthly" : "$rc_annual";
                  const pkg = packages.find((candidate) => candidate?.product?.identifier === productId);
                  const product = pkg?.product;
                  if (!pkg || pkg.identifier !== expectedPackage || !product?.priceString) continue;
                  planPricing[billingInterval] = {
                          amount: Number(product.price),
                          currencyCode: product.currencyCode || "",
                          formattedPrice: product.priceString,
                          packageIdentifier: pkg.identifier,
                          productId,
                  };
          }

          const monthly = planPricing.monthly;
          const annual = planPricing.annual;
          if (
                  Number.isFinite(monthly?.amount)
                  && Number.isFinite(annual?.amount)
                  && monthly.currencyCode
                  && monthly.currencyCode === annual.currencyCode
          ) {
                  const savings = calculateSavings(monthly.amount, annual.amount);
                  if (savings) {
                          annual.savings = {
                                  amount: savings.amount,
                                  currencyCode: annual.currencyCode,
                                  percent: savings.percent,
                          };
                  }
          }
          localized[planId] = planPricing;
    }
    return localized;
};

/**
 * Get package (product) from offerings by product ID
 * Supported native stores only
 */
export const getPackageByProductId = async (productId, expectedOfferingId) => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || !["ios", "android"].includes(platform)) return null;

    const ready = await ensureInitialized();
    if (!ready) return null;

    try {
          const offerings = await Purchases.getOfferings();

      const offering = offerings?.all?.[expectedOfferingId];
      return (offering?.availablePackages || []).find(
        (pkg) => pkg.product.identifier === productId,
      ) || null;
    } catch {
          console.error("[Kindred] Error fetching package");
          return null;
    }
};

/**
 * Make a purchase through the active native store
 * Handles transaction and receipt validation.
 */
export const makePurchase = async (
  productId,
  billingInterval,
  expectedOfferingId,
  expectedEntitlementId,
) => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || !["ios", "android"].includes(platform)) {
          throw new Error("In-app purchases are only available in a supported native app.");
    }

    const ready = await ensureInitialized();
    if (!ready) {
          throw new Error(
                  "Subscription service is not ready. Please restart the app and try again."
                );
    }

    try {
      const pkg = await getPackageByProductId(productId, expectedOfferingId);
          if (!pkg) {
                  throw new Error(
                            "This subscription product is not yet available. Please try again later."
                          );
          }
      const expectedPackageIdentifier =
        billingInterval === "monthly" ? "$rc_monthly" : billingInterval === "annual" ? "$rc_annual" : "";
      if (!expectedPackageIdentifier || pkg.identifier !== expectedPackageIdentifier) {
        throw new Error("The store product does not match the selected billing interval.");
      }

      const purchaseResult = await Purchases.purchasePackage({ aPackage: pkg });

      const activeEntitlements = purchaseResult?.customerInfo?.entitlements?.active || {};
      if (expectedEntitlementId && !activeEntitlements[expectedEntitlementId]) {
        throw new Error("The purchased product did not grant the expected plan entitlement.");
      }
      if (Object.keys(activeEntitlements).length > 0) {
              return {
                        success: true,
                        message: "Purchase successful",
              };
      }

      return {
              success: false,
              message: "Purchase was not completed. Please try again.",
      };
    } catch (error) {
          throw error;
    }
};

/**
 * Sync customer ID with RevenueCat (call this after user login)
 * Supported native stores only
 */
export const syncRevenueCatUser = async (userId) => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || !["ios", "android"].includes(platform)) return;

    const ready = await ensureInitialized();
    if (!ready) return;

    try {
          await Purchases.logIn({ appUserID: userId });
          console.log("[Kindred] RevenueCat user sync completed");
    } catch {
          console.error("[Kindred] Error syncing RevenueCat user");
    }
};

export const openRevenueCatSubscriptionManagement = async () => {
    const ready = await ensureInitialized();
    if (!ready) {
          throw new Error("Subscription service is not ready. Please try again.");
    }
    const result = await Purchases.getCustomerInfo();
    const managementURL = result?.customerInfo?.managementURL;
    if (!managementURL) {
          throw new Error("The store subscription management link is unavailable.");
    }
    await Browser.open({ url: managementURL, presentationStyle: "popover" });
};

/**
 * Restore previously purchased subscriptions on supported native stores
 * Apple requires a visible "Restore Purchases" button per guideline 3.1.1
 */
export const restorePurchases = async () => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || !["ios", "android"].includes(platform)) {
          throw new Error("Restore purchases is only available in a supported native app.");
    }

    const ready = await ensureInitialized();
    if (!ready) {
          throw new Error("Subscription service is not ready. Please restart the app and try again.");
    }

    try {
          const { customerInfo } = await Purchases.restorePurchases();
          const activeEntitlements = customerInfo?.entitlements?.active || {};
          const hasActive = Object.keys(activeEntitlements).length > 0;

              return {
                      success: true,
                      hasActiveSubscription: hasActive,
              };
    } catch (error) {
          throw error;
    }
};

/**
 * Check if running on a supported native store
 */
export const isNativePurchasePlatform = () => {
    return Capacitor.isNativePlatform()
      && ["ios", "android"].includes(Capacitor.getPlatform());
};
