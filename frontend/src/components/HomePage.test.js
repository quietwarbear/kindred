import React from "react";
import { createRoot } from "react-dom/client";
import { HomePage } from "./HomePage";
import { todayFailure } from "@/lib/todayRecovery";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }), { virtual: true });
jest.mock("@/lib/api", () => ({ apiRequest: jest.fn() }));
jest.mock("@/lib/analytics", () => ({ trackReunionEvent: jest.fn() }));
jest.mock("@/components/PlanUpgradeCard", () => ({ PlanUpgradeCard: () => null }));
jest.mock("@/components/ui/sonner", () => ({ toast: { error: jest.fn() } }));

let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  mockNavigate.mockClear();
});
afterEach(async () => {
  await React.act(async () => root.unmount());
  container.remove();
});
const render = async (props) => React.act(async () => root.render(<HomePage {...props} />));
const button = (text) => [...container.querySelectorAll("button")].find(b => b.textContent.includes(text));

test.each([403, 404])("%s gives navigation, not endless network retry", async (status) => {
  const retry = jest.fn();
  await render({ todayError: todayFailure({ response: { status } }), onRetryToday: retry });
  expect(button("Try again")).toBeUndefined();
  await React.act(async () => button("Open family activity").click());
  expect(mockNavigate).toHaveBeenCalledWith("/activity");
  expect(retry).not.toHaveBeenCalled();
});

test("retry calls the loader once, shows progress, and allows another attempt", async () => {
  let resolve;
  const retry = jest.fn(() => new Promise(r => { resolve = r; }));
  await render({ todayError: todayFailure({}), onRetryToday: retry });
  await React.act(async () => { button("Try again").click(); button("Try again").click(); });
  expect(retry).toHaveBeenCalledTimes(1);
  expect(button("Refreshing").disabled).toBe(true);
  await React.act(async () => resolve());
  expect(button("Try again").disabled).toBe(false);
});

test("401 asks for sign-in rather than retrying the expired token", async () => {
  const signIn = jest.fn();
  await render({ todayError: todayFailure({ response: { status: 401 } }), onSignInAgain: signIn });
  await React.act(async () => button("Sign in again").click());
  expect(signIn).toHaveBeenCalledTimes(1);
  expect(button("Try again")).toBeUndefined();
});

test("a successful retry replaces the error with the Today summary", async () => {
  const data = {
    viewer_role: "member", lifecycle_state: "active",
    primary_action: { code: "open_family_home", destination_category: "family_home" },
    recent_changes: [], secondary_actions: [], milestone_codes: [],
  };
  const Harness = () => {
    const [payload, setPayload] = React.useState(null);
    return <HomePage todayData={payload} todayError={payload ? null : { kind: "temporary" }} onRetryToday={async () => setPayload(data)} />;
  };
  await React.act(async () => root.render(<Harness />));
  await React.act(async () => button("Try again").click());
  expect(container.querySelector('[data-testid="today-error"]')).toBeNull();
  expect(container.querySelector('[data-testid="family-today-page"]')).not.toBeNull();
});

test("loading has accessible progress", async () => {
  await render({ todayLoading: true });
  expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
});

test.each([500, 502, 503])("%s remains retryable without exposing server details", (status) => {
  expect(todayFailure({ response: { status, data: { detail: "PRIVATE" } } })).toEqual({ kind: "temporary" });
});
