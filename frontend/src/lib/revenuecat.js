/**
 * RevenueCat integration for iOS in-app purchases via Capacitor
 * Falls back gracefully on web platforms
 */
import { Capacitor } from "@capacitor/core";
import { Purchases } from "@revenuecat/purchases-capacitor";

const REVENUECAT_API_KEY = process.env.REACT_APP_REVENUECAT_IOS_KEY;

// Map tier names to RevenueCat product IDs
export const TIER_TO_PRODUCT_ID = {
    sapling: {
          monthly: "com.kindred.sapling.monthly",
          annual: "com.kindred.sapling.annual",
    },
    oak: {
          monthly: "com.kindred.oak.monthly",
          annual: "com.kindred.oak.annual",
    },
    redwood: {
          monthly: "com.kindred.redwood.monthly",
          annual: "com.kindred.redwood.annual",
    },
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

    // Only initialize on iOS
    if (!isNative || platform !== "ios") {
          console.log("[Kindred] RevenueCat: skipping init (not iOS native)");
          return false;
    }

    if (!REVENUECAT_API_KEY) {
          console.warn("[Kindred] RevenueCat: REACT_APP_REVENUECAT_IOS_KEY not configured");
          return false;
    }

    const initCore = (async () => {
          try {
                  console.log("[Kindred] RevenueCat: configuring with key:", REVENUECAT_API_KEY?.substring(0, 8) + "...");
                  await Purchases.configure({
                            apiKey: REVENUECAT_API_KEY,
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
                  }).catch((offerErr) => {
                    console.warn("[Kindred] RevenueCat offerings pre-fetch failed:", offerErr);
                  });

                  return true;
          } catch (error) {
                  console.error("[Kindred] Failed to initialize RevenueCat:", error?.message || error);
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
    } catch (error) {
          console.error("[Kindred] Error fetching RevenueCat offerings:", error);
          return null;
    }
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
    } catch (error) {
          console.error("[Kindred] Error fetching package:", error);
          return null;
    }
};

/**
 * Make purchase on iOS
 * Handles transaction and receipt validation.
 */
export const makePurchase = async (productId) => {
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

      const purchaseResult = await Purchases.purchasePackage({ aPackage: pkg });

      if (purchaseResult?.customerInfo?.entitlements?.active) {
              return {
                        success: true,
                        customerInfo: purchaseResult.customerInfo,
                        message: "Purchase successful",
              };
      }

      return {
              success: false,
              message: "Purchase was not completed. Please try again.",
      };
    } catch (error) {
          console.error("[Kindred] Purchase error:", error);
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
          console.log("[Kindred] RevenueCat user synced:", userId);
    } catch (error) {
          console.error("[Kindred] Error syncing RevenueCat user:", error);
    }
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
                  customerInfo,
          };
    } catch (error) {
          console.error("[Kindred] Restore purchases error:", error);
          throw error;
    }
};

/**
 * Check if running on iOS
 */
export const isIOS = () => {
    return Capacitor.isNativePlatform() && Capacitor.getPlatform() === "ios";
};
