import { validateRevenueCatWebProduct } from "./revenuecatWeb";

const expected = {
  product_id: "oak_annual_web_v2",
  offering_id: "oak_access",
  package_id: "$rc_annual",
  entitlement_id: "oak_access",
  amount_micros: 179_990_000,
  currency: "USD",
  period: "P1Y",
};

const validOffering = {
  identifier: "oak_access",
};

const validPackage = {
  identifier: "$rc_annual",
  webBillingProduct: {
    identifier: "oak_annual_web_v2",
    productType: "subscription",
    normalPeriodDuration: "P1Y",
    price: {
      amountMicros: 179_990_000,
      currency: "USD",
      formattedPrice: "$179.99",
    },
    freeTrialPhase: null,
    introPricePhase: null,
  },
};

test("accepts a RevenueCat Billing product only when every invariant agrees", () => {
  expect(
    validateRevenueCatWebProduct(
      validOffering,
      validPackage,
      expected,
      "oak",
      "annual",
    ),
  ).toBe(validPackage.webBillingProduct);
});

test.each([
  ["swapped interval", { normalPeriodDuration: "P1M" }, "billing interval"],
  ["wrong amount", { price: { ...validPackage.webBillingProduct.price, amountMicros: 199_900_000 } }, "amount"],
  ["wrong currency", { price: { ...validPackage.webBillingProduct.price, currency: "CAD" } }, "currency"],
  ["unsupported trial", { freeTrialPhase: { periodDuration: "P14D" } }, "free trial"],
])("fails closed for %s", (_label, productChange, message) => {
  const rcPackage = {
    ...validPackage,
    webBillingProduct: {
      ...validPackage.webBillingProduct,
      ...productChange,
    },
  };
  expect(() => validateRevenueCatWebProduct(
    validOffering,
    rcPackage,
    expected,
    "oak",
    "annual",
  )).toThrow(message);
});
