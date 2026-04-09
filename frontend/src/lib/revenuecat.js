/**
 * RevenueCat integration for iOS in-app purchases via Capacitor
 * Falls back gracefully on web platforms
 */

import { Capacitor } from "@capacitor/core";

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

/**
 * Initialize RevenueCat SDK (iOS only)
 * Safe to call on web - will no-op.
 * Re-entrant: returns the same promise if already in progress.
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

  initPromise = (async () => {
    try {
      const { Purchases } = await import(/* webpackIgnore: true */ "@revenuecat/purchases-capacitor");

      // Configure RevenueCat
      await Purchases.configure({
        apiKey: REVENUECAT_API_KEY,
        appUserID: null, // RevenueCat will generate one, can be overridden later with user ID
      });

      revenueCatInitialized = true;
      console.log("[Kindred] RevenueCat initialized successfully");
      return true;
    } catch (error) {
      console.error("[Kindred] Failed to initialize RevenueCat:", error);
      initPromise = null; // Allow retry
      return false;
    }
  })();

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

  // Ensure initialized before fetching
  const ready = await ensureInitialized();
  if (!ready) return null;

  try {
    const { Purchases } = await import(/* webpackIgnore: true */ "@revenuecat/purchases-capacitor");
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
    const { Purchases } = await import(/* webpackIgnore: true */ "@revenuecat/purchases-capacitor");
    const offerings = await Purchases.getOfferings();

    // Search for the package in current offering
    if (offerings?.current?.availablePackages) {
      const found = offerings.current.availablePackages.find(
        (pkg) => pkg.product.identifier === productId
      );
      if (found) return found;
    }

    // Also search in all offerings (not just current)
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
 * Returns a structured result with clear success/failure info.
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
    const { Purchases } = await import(/* webpackIgnore: true */ "@revenuecat/purchases-capacitor");

    // Get the package first
    const pkg = await getPackageByProductId(productId);
    if (!pkg) {
      throw new Error(
        "This subscription product is not yet available. Please try again later."
      );
    }

    // Purchase the package
    const purchaseResult = await Purchases.purchasePackage({ aPackage: pkg });

    // Check if purchase was successful
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
    const { Purchases } = await import(/* webpackIgnore: true */ "@revenuecat/purchases-capacitor");
    await Purchases.logIn({
      appUserID: userId,
    });
    console.log("[Kindred] RevenueCat user synced:", userId);
  } catch (error) {
    console.error("[Kindred] Error syncing RevenueCat user:", error);
  }
};

/**
 * Check if running on iOS
 */
export const isIOS = () => {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === "ios";
};
