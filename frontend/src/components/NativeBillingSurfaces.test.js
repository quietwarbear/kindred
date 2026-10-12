import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { LandingPage } from "./LandingPage";
import { PricingPage } from "./PricingPage";
import { SubscriptionPage } from "./SubscriptionPage";

const mockPlatform = { native: false };
jest.mock("@/lib/native-bridge", () => ({ isNative: () => mockPlatform.native }));
jest.mock("react-router-dom", () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
  useNavigate: () => jest.fn(),
}), { virtual: true });
jest.mock("@/lib/analytics", () => ({ trackReunionEvent: jest.fn() }));
jest.mock("@/lib/revenuecat", () => ({ isNativeBilling: () => false }));
jest.mock("@/lib/api", () => ({ apiRequest: jest.fn() }));
jest.mock("@/hooks/usePublicPlans", () => ({
  usePublicPlans: () => ({ plans: [], reunionPass: null, loading: false, error: null }),
}));

afterEach(() => { mockPlatform.native = false; });

test.each(["ios", "android"])("%s public screens exclude web billing", () => {
  mockPlatform.native = true;
  const landing = renderToStaticMarkup(<LandingPage isAuthenticated />);
  const pricing = renderToStaticMarkup(<PricingPage session={{ token: "synthetic" }} />);
  expect(landing).not.toContain('id="plans"');
  expect(landing).not.toContain("Web subscriptions");
  expect(pricing).not.toContain("Web subscriptions");
  expect(pricing).toContain('href="/subscription"');
  expect(pricing).toContain("View in-app plans");
  const subscription = renderToStaticMarkup(<SubscriptionPage token="synthetic" user={{ id: "synthetic", role: "host" }} />);
  expect(subscription).not.toContain("Web subscriptions");
  expect(subscription).not.toContain("web billing portal");
  expect(subscription).not.toContain("web purchase flow");
  expect(subscription).not.toContain('data-testid="addons-section"');
  expect(subscription).toContain("device&#x27;s subscription settings");
});

test("native pricing routes signed-out users through sign-in", () => {
  mockPlatform.native = true;
  expect(renderToStaticMarkup(<PricingPage />)).toContain('href="/login?intent=subscribe"');
});

test("web pricing surfaces remain available", () => {
  expect(renderToStaticMarkup(<LandingPage />)).toContain('id="plans"');
  expect(renderToStaticMarkup(<PricingPage />)).toContain('data-testid="public-pricing-page"');
});
