const mockCapacitor = { native: true, platform: "android" };

jest.mock("@capacitor/core", () => ({
  Capacitor: {
    isNativePlatform: () => mockCapacitor.native,
    getPlatform: () => mockCapacitor.platform,
  },
}));

jest.mock("@capacitor/browser", () => ({ Browser: { open: jest.fn() } }));

jest.mock("@revenuecat/purchases-capacitor", () => ({
  Purchases: {
    configure: jest.fn(),
    getOfferings: jest.fn(),
    purchasePackage: jest.fn(),
    logIn: jest.fn(),
    restorePurchases: jest.fn(),
    getCustomerInfo: jest.fn(),
  },
}));

jest.mock("@/lib/api", () => ({ apiRequest: jest.fn() }));

const PLAY_MONTHLY = "kindred_sapling:sapling-monthly";

const playOfferings = {
  current: null,
  all: {
    sapling_access: {
      availablePackages: [
        {
          identifier: "$rc_monthly",
          product: {
            identifier: PLAY_MONTHLY,
            price: 4.99,
            priceString: "$4.99",
            currencyCode: "USD",
          },
        },
      ],
    },
  },
};

// The module caches its init state, so each test loads a fresh copy.
const loadModule = ({ platform, native = true, keys = {} }) => {
  jest.resetModules();
  mockCapacitor.native = native;
  mockCapacitor.platform = platform;
  process.env.REACT_APP_REVENUECAT_IOS_KEY = keys.ios || "";
  process.env.REACT_APP_REVENUECAT_ANDROID_KEY = keys.android || "";
  const { Purchases } = require("@revenuecat/purchases-capacitor");
  Purchases.configure.mockResolvedValue(undefined);
  Purchases.getOfferings.mockResolvedValue(playOfferings);
  return { lib: require("./revenuecat"), Purchases };
};

afterEach(() => {
  delete process.env.REACT_APP_REVENUECAT_IOS_KEY;
  delete process.env.REACT_APP_REVENUECAT_ANDROID_KEY;
});

describe("RevenueCat on Android", () => {
  const android = { platform: "android", keys: { android: "goog_test" } };

  it("buys a Play package instead of throwing an iOS-only error", async () => {
    const { lib, Purchases } = loadModule(android);
    Purchases.purchasePackage.mockResolvedValue({
      customerInfo: { entitlements: { active: { sapling: {} } } },
    });

    const result = await lib.makePurchase(PLAY_MONTHLY, "monthly", "sapling");

    expect(result.success).toBe(true);
    expect(Purchases.purchasePackage).toHaveBeenCalledWith({
      aPackage: playOfferings.all.sapling_access.availablePackages[0],
    });
  });

  it("restores purchases", async () => {
    const { lib, Purchases } = loadModule(android);
    Purchases.restorePurchases.mockResolvedValue({
      customerInfo: { entitlements: { active: { oak: {} } } },
    });

    await expect(lib.restorePurchases()).resolves.toEqual({
      success: true,
      hasActiveSubscription: true,
    });
  });

  it("links the RevenueCat customer to the Kindred user", async () => {
    const { lib, Purchases } = loadModule(android);
    await lib.syncRevenueCatUser("user-123");
    expect(Purchases.logIn).toHaveBeenCalledWith({ appUserID: "user-123" });
  });

  it("returns Play-localized pricing", async () => {
    const { lib } = loadModule(android);
    const pricing = await lib.getLocalizedRevenueCatPricing({
      sapling: { monthly: PLAY_MONTHLY },
    });
    expect(pricing.sapling.monthly.formattedPrice).toBe("$4.99");
  });
});

describe("RevenueCat off native store platforms", () => {
  it("still refuses purchase and restore on the web", async () => {
    const { lib, Purchases } = loadModule({ platform: "web", native: false });
    await expect(lib.makePurchase(PLAY_MONTHLY, "monthly")).rejects.toThrow(
      "only available in the Kindred mobile app"
    );
    await expect(lib.restorePurchases()).rejects.toThrow(
      "only available in the Kindred mobile app"
    );
    expect(await lib.fetchOfferings()).toBeNull();
    expect(Purchases.configure).not.toHaveBeenCalled();
  });
});
