import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ apiRequest: jest.fn() }));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/lib/native-bridge", () => ({ isNative: jest.fn(() => false) }));
jest.mock("@capacitor/browser", () => ({ Browser: { open: jest.fn() } }));

const { apiRequest } = require("@/lib/api");
const { toast } = require("@/components/ui/sonner");
const { isNative } = require("@/lib/native-bridge");
const { Browser } = require("@capacitor/browser");
const { OpenIleUbuntuButton, jumpMessage } = require("./OpenIleUbuntuButton");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act || require("react-dom/test-utils").act;

const URL = "https://www.ile-ubuntu.org/sso?code=abc";
let container;
let root;
let tab;

const mount = async () => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<OpenIleUbuntuButton token="t" />));
};
const click = async () => act(async () => container.querySelector("button").click());

beforeEach(() => {
  tab = { opener: "x", location: { href: "" }, close: jest.fn() };
  jest.spyOn(window, "open").mockReturnValue(tab);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.clearAllMocks();
  jest.restoreAllMocks();
  isNative.mockReturnValue(false);
});

test("asks Kindred for an Ile Ubuntu jump and opens it in a new tab", async () => {
  apiRequest.mockResolvedValue({ url: URL });
  await mount();
  expect(container.textContent).toContain("Open Ile Ubuntu");
  expect(container.textContent).toContain("opens in a new tab");
  await click();
  expect(apiRequest).toHaveBeenCalledWith("/federation/jump", {
    method: "POST",
    token: "t",
    data: { target: "ile_ubuntu" },
  });
  expect(window.open).toHaveBeenCalledWith("about:blank", "_blank");
  expect(tab.opener).toBeNull();
  expect(tab.location.href).toBe(URL);
});

test("uses the in-app browser inside the iOS/Android app", async () => {
  isNative.mockReturnValue(true);
  apiRequest.mockResolvedValue({ url: URL });
  await mount();
  await click();
  expect(window.open).not.toHaveBeenCalled();
  expect(Browser.open).toHaveBeenCalledWith({ url: URL });
});

test("an unverified email gets a clear message and the blank tab closes", async () => {
  const error = new Error("403");
  error.response = { data: { detail: { code: "email_not_verified", message: "x" } } };
  apiRequest.mockRejectedValue(error);
  await mount();
  await click();
  expect(tab.close).toHaveBeenCalled();
  expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Verify your email first"));
});

test("jumpMessage falls back for unexpected errors", () => {
  expect(jumpMessage(new Error("boom"))).toBe("Couldn't open Ile Ubuntu right now.");
  expect(jumpMessage({ response: { data: { detail: "Cross-product sign-in was declined." } } })).toBe(
    "Cross-product sign-in was declined."
  );
});
