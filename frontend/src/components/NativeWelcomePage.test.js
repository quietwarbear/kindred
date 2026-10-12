import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { NativeWelcomePage } from "./NativeWelcomePage";
import { AuthPage } from "./AuthPage";

const mockLocation = { search: "?intent=create-account" };
jest.mock("react-router-dom", () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>, useNavigate: () => jest.fn(), useLocation: () => mockLocation }), { virtual: true });
jest.mock("@/lib/native-bridge", () => ({ isNative: () => true }));
jest.mock("@/lib/api", () => ({ apiRequest: jest.fn() }));
jest.mock("@/lib/analytics", () => ({ trackReunionEvent: jest.fn(), gaClientId: () => "" }));
jest.mock("@/lib/seasonalCampaign", () => ({ gatheringCampaign: () => ({ active: true, headline: "Campaign" }) }));

test("all entry choices come before the optional campaign", () => {
  const html = renderToStaticMarkup(<NativeWelcomePage />);
  for (const [label, destination] of [["Sign in", "/login?intent=signin"], ["Create an account", "/login?intent=create-account"], ["Continue with an invitation", "/invitation"]]) {
    expect(html).toContain(`href="${destination}"`);
    expect(html.indexOf(label)).toBeLessThan(html.indexOf('data-testid="native-campaign-secondary"'));
  }
  expect(html).not.toContain("Web subscriptions");
});
test("native account entry opens account creation without a pre-existing draft", () => {
  const html = renderToStaticMarkup(<AuthPage />);
  expect(html).toContain('data-testid="launch-full-name-input"');
  expect(html).toContain("Create account and continue");
  expect(html).not.toContain("Save event draft");
  expect(html).toContain("does not grant access");
});
