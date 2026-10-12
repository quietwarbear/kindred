import React from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "./AppShell";
import { apiRequest } from "@/lib/api";

jest.mock("@/lib/api", () => ({ apiRequest: jest.fn() }));
jest.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark", setTheme: jest.fn() }) }));
jest.mock("@/lib/sw-register", () => ({ isStandalone: () => true }));
jest.mock("@/components/ui/sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("./NotificationPanel", () => ({ NotificationPanel: () => null }));
jest.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: "/home" }),
  NavLink: ({ children, to, className, ...props }) => <a href={to} className={typeof className === "function" ? className({ isActive: false }) : className} {...props}>{children}</a>,
  Routes: () => null, Route: () => null, Navigate: () => null,
}), { virtual: true });
jest.mock("@/components/ActivityFeedPage", () => ({ ActivityFeedPage: () => null }));
jest.mock("@/components/CourtyardsPage", () => ({ CourtyardsPage: () => null }));
jest.mock("@/components/FundsTravelPage", () => ({ FundsTravelPage: () => null }));
jest.mock("@/components/GatheringsPage", () => ({ GatheringsPage: () => null }));
jest.mock("@/components/CarePage", () => ({ CarePage: () => null }));
jest.mock("@/components/CommunitySetupPage", () => ({ CommunitySetupPage: () => null }));
jest.mock("@/components/HealthDashboardPage", () => ({ HealthDashboardPage: () => null }));
jest.mock("@/components/HomePage", () => ({ HomePage: () => null }));
jest.mock("@/components/KinshipMapPage", () => ({ KinshipMapPage: () => null }));
jest.mock("@/components/LegacyThreadsPage", () => ({ LegacyThreadsPage: () => null }));
jest.mock("@/components/MemoryVaultPage", () => ({ MemoryVaultPage: () => null }));
jest.mock("@/components/MembersPage", () => ({ MembersPage: () => null }));
jest.mock("@/components/PilotCohortPage", () => ({ PilotCohortPage: () => null }));
jest.mock("@/components/PollsPage", () => ({ PollsPage: () => null }));
jest.mock("@/components/SettingsPage", () => ({ SettingsPage: () => null }));
jest.mock("@/components/StewardPage", () => ({ StewardPage: () => null }));
jest.mock("@/components/StrategyPage", () => ({ StrategyPage: () => null }));
jest.mock("@/components/SubscriptionPage", () => ({ SubscriptionPage: () => null }));
jest.mock("@/components/ThreadsPage", () => ({ ThreadsPage: () => null }));
jest.mock("@/components/TimelinePage", () => ({ TimelinePage: () => null }));
jest.mock("@/components/EventsPage", () => ({ EventsPage: () => null }));
jest.mock("@/components/GatheringDetailPage", () => ({ GatheringDetailPage: () => null }));
jest.mock("@/components/GatheringProposalsPage", () => ({ GatheringProposalsPage: () => null }));
jest.mock("@/components/CourtyardDetailPage", () => ({ CourtyardDetailPage: () => null }));

let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  apiRequest.mockImplementation(async (path) => {
    if (path === "/today") throw { response: { status: 404 } };
    if (path === "/community/modules") return { enabled: ["gatherings", "memory"] };
    return {};
  });
});
afterEach(async () => {
  await React.act(async () => root.unmount());
  container.remove();
});
const renderShell = async (role = "member") => React.act(async () => root.render(
  <AppShell token="synthetic" user={{ role, full_name: "Test Member" }} community={{ id: "synthetic", name: "Test Family" }} onLogout={jest.fn()} onSessionRefresh={jest.fn()} />
));
const openMenu = async () => React.act(async () => {
  const trigger = container.querySelector('[data-testid="mobile-menu-toggle"]');
  trigger.dispatchEvent(new MouseEvent("click", { bubbles: true }));
});
test("hamburger opens a named dialog with visible tools, without navigating", async () => {
  await renderShell();
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  await openMenu();
  const dialog = document.querySelector('[role="dialog"]');
  expect(dialog).not.toBeNull();
  expect(dialog.textContent).toContain("Kindred family menu");
  const nav = dialog.querySelector('[data-testid="mobile-navigation"]');
  expect(nav.querySelector('a[href="/activity"]')).not.toBeNull();
  expect(nav.querySelector('a[href="/gatherings"]')).not.toBeNull();
  expect(nav.querySelector('a[href="/settings"]')).not.toBeNull();
  expect(nav.querySelector('a[href="/care"]')).toBeNull();
  expect(nav.querySelector('[data-testid="nav-more-toggle"]')).toBeNull();
  expect(container.querySelector('[data-testid="mobile-menu-toggle"]').getAttribute("aria-expanded")).toBe("true");
});
test("selecting a destination closes the drawer", async () => {
  await renderShell();
  await openMenu();
  await React.act(async () => document.querySelector('[role="dialog"] a[href="/activity"]').dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});
test("close button dismisses menu and restores focus to hamburger", async () => {
  await renderShell();
  await openMenu();
  const close = [...document.querySelectorAll('[role="dialog"] button')].find(b => b.textContent === "Close");
  await React.act(async () => close.click());
  await React.act(async () => new Promise(resolve => setTimeout(resolve, 10)));
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(document.activeElement).toBe(container.querySelector('[data-testid="mobile-menu-toggle"]'));
});
test.each([["host", true], ["member", false]])("Today unavailable keeps %s role navigation without promoting members", async (role, allowed) => {
  await renderShell(role);
  await openMenu();
  const nav = document.querySelector('[data-testid="mobile-menu-drawer"] [data-testid="mobile-navigation"]');
  expect(Boolean(nav.querySelector('a[href="/subscription"]'))).toBe(allowed);
  expect(Boolean(nav.querySelector('a[href="/setup"]'))).toBe(allowed);
});
