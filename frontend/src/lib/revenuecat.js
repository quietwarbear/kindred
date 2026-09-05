/**
 * RevenueCat integration for iOS in-app purchases via Capacitor
 * Falls back gracefully on web platforms
 */
import { Capacitor } from "@capacitor/core";
import { Browser } from "@capacitor/browser";
import { Purchases } from "@revenuecat/purchases-capacitor";
import { apiRequest } from "@/lib/api";
import { calculateSavings } from "@/lib/pricing";

// One RevenueCat app per store, so one public key per platform. Android was
// previously unreachable: the iOS key was the only one wired, so an Android
// build had no native purchase path and fell through to the web branch, which
// is both disabled in a native build and disallowed by Play billing policy.
const REVENUECAT_KEYS = {
    ios: process.env.REACT_APP_REVENUECAT_IOS_KEY,
    android: process.env.REACT_APP_REVENUECAT_ANDROID_KEY,
};

const nativePlatform = () =>
    (Capacitor.isNativePlatform() ? Capacitor.getPlatform() : null);

/** The RevenueCat public key for the platform we are running on, if any. */
const platformApiKey = () => {
    const platform = nativePlatform();
    return platform ? REVENUECAT_KEYS[platform] : undefined;
};

let productMappingPromise = null;

export const getRevenueCatProductMapping = async () => {
    if (!productMappingPromise) {
          // Platform matters: an Android build handed App Store identifiers
          // finds nothing in its offering and every purchase fails.
          const platform = nativePlatform() || "web";
          productMappingPromise = apiRequest(`/revenuecat/config?platform=${platform}`)
            .then((config) => config?.product_mapping || {})
            .catch((error) => {
              productMappingPromise = null;
              throw error;
            });
    }
    return productMappingPromise;
};

let revenueCatInitialized = false;
let initPromise = null;

// How long (ms) to wait for RevenueCat to initialize before giving up
// RevenueCat SDK now runs a health report during configure(), which can
// take 20s+ in sandbox. 30s gives it room without hanging forever.
const RC_INIT_TIMEOUT_MS = 30000;

/**
 * Initialize RevenueCat SDK (iOS only)
 * Safe to call on web - will no-op.
 * Re-entrant: returns the same promise if already in progress.
 * Has a timeout so it never hangs forever.
 */
export const initializeRevenueCat = async () => {
    if (revenueCatInitialized) return true;
    if (initPromise) return initPromise;

    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    // Native store purchases: iOS and Android both go through RevenueCat.
    if (!isNative || (platform !== "ios" && platform !== "android")) {
          console.log("[Kindred] RevenueCat: skipping init (not a native store platform)");
          return false;
    }

    const apiKey = platformApiKey();
    if (!apiKey) {
          console.warn(
            `[Kindred] RevenueCat: no public key configured for ${platform} ` +
            "(REACT_APP_REVENUECAT_IOS_KEY / REACT_APP_REVENUECAT_ANDROID_KEY)"
          );
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
 * Fetch offerings from RevenueCat (iOS only)
 * Returns structured offerings or null on web/error
 */
export const fetchOfferings = async () => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || platform !== "ios") return null;

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

const allOfferingPackages = (offerings) => {
    const packages = [];
    const seen = new Set();
    const availableOfferings = [
          ...Object.values(offerings?.all || {}),
          offerings?.current,
    ].filter(Boolean);
    for (const offering of availableOfferings) {
          for (const pkg of offering.availablePackages || []) {
                  const productId = pkg?.product?.identifier;
                  if (productId && !seen.has(productId)) {
                          seen.add(productId);
                          packages.push(pkg);
                  }
          }
    }
    return packages;
};

/**
 * Return StoreKit-localized display prices for every mapped package.
 * Savings are calculated only when both package amounts use the same currency.
 */
export const getLocalizedRevenueCatPricing = async (productMapping) => {
    const offerings = await fetchOfferings();
    if (!offerings) return {};

    const packages = allOfferingPackages(offerings);
    const localized = {};
    for (const [planId, intervals] of Object.entries(productMapping || {})) {
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
 * iOS only
 */
export const getPackageByProductId = async (productId) => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || platform !== "ios") return null;

    const ready = await ensureInitialized();
    if (!ready) return null;

    try {
          const offerings = await Purchases.getOfferings();

      if (offerings?.current?.availablePackages) {
              const found = offerings.current.availablePackages.find(
                        (pkg) => pkg.product.identifier === productId
                      );
              if (found) return found;
      }

      if (offerings?.all) {
              for (const offering of Object.values(offerings.all)) {
                        const found = (offering.availablePackages || []).find(
                                    (pkg) => pkg.product.identifier === productId
                                  );
                        if (found) return found;
              }
      }

      return null;
    } catch {
          console.error("[Kindred] Error fetching package");
          return null;
    }
};

/**
 * Make purchase on iOS
 * Handles transaction and receipt validation.
 */
export const makePurchase = async (productId, billingInterval, expectedEntitlementId) => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || platform !== "ios") {
          throw new Error("In-app purchases are only available on iOS.");
    }

    const ready = await ensureInitialized();
    if (!ready) {
          throw new Error(
                  "Subscription service is not ready. Please restart the app and try again."
                );
    }

    try {
      const pkg = await getPackageByProductId(productId);
          if (!pkg) {
                  throw new Error(
                            "This subscription product is not yet available. Please try again later."
                          );
          }
      const expectedPackageIdentifier =
        billingInterval === "monthly" ? "$rc_monthly" : billingInterval === "annual" ? "$rc_annual" : "";
      if (!expectedPackageIdentifier || pkg.identifier !== expectedPackageIdentifier) {
        throw new Error("The App Store product does not match the selected billing interval.");
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
 * iOS only
 */
export const syncRevenueCatUser = async (userId) => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || platform !== "ios") return;

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
          throw new Error("The App Store subscription management link is unavailable.");
    }
    await Browser.open({ url: managementURL, presentationStyle: "popover" });
};

/**
 * Restore previously purchased subscriptions (iOS only)
 * Apple requires a visible "Restore Purchases" button per guideline 3.1.1
 */
export const restorePurchases = async () => {
    const isNative = Capacitor.isNativePlatform();
    const platform = Capacitor.getPlatform();

    if (!isNative || platform !== "ios") {
          throw new Error("Restore purchases is only available on iOS.");
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
 * Check if running on iOS
 */
export const isIOS = () => {
    return Capacitor.isNativePlatform() && Capacitor.getPlatform() === "ios";
};

/**
 * True when this build can take a native store purchase — iOS or Android, with
 * a key configured for it. This, not isIOS(), is what purchase UI should gate
 * on: selling digital goods through anything other than the platform's own
 * billing is against both stores' rules.
 */
export const isNativeBilling = () => Boolean(platformApiKey());
