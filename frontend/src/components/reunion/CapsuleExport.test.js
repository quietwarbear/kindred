import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({
  apiBlobRequest: jest.fn(),
  errorDetail: (_e, fallback) => fallback,
}));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { apiBlobRequest } = require("@/lib/api");
const { toast } = require("@/components/ui/sonner");
const { CapsuleExport, capsuleExportFilename, capsuleExportPath } = require("./CapsuleExport");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act || require("react-dom/test-utils").act;

let container;
let root;
beforeEach(async () => {
  window.URL.createObjectURL = jest.fn(() => "blob:capsule");
  window.URL.revokeObjectURL = jest.fn();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<CapsuleExport eventId="event-1" title="Harvest Gathering" token="tok" />));
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.clearAllMocks();
});

const press = async () => act(async () => container.querySelector("button").click());

test("downloads the ZIP with bearer auth and saves it", async () => {
  apiBlobRequest.mockResolvedValue(new Blob(["zip"]));
  const clicks = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  await press();
  expect(apiBlobRequest).toHaveBeenCalledWith("/events/event-1/memory-capsule/export", { token: "tok", timeout: 180000 });
  expect(clicks).toHaveBeenCalled();
  expect(toast.success).toHaveBeenCalledWith("Memory capsule downloaded.");
  clicks.mockRestore();
});

test("explains an oversized capsule", async () => {
  apiBlobRequest.mockRejectedValue({ response: { status: 413 } });
  await press();
  expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("too large"));
  expect(container.querySelector("button").disabled).toBe(false);
});

test("helpers build the path and a safe filename", () => {
  expect(capsuleExportPath("e-2")).toBe("/events/e-2/memory-capsule/export");
  expect(capsuleExportFilename("Fête d'été!", new Date("2026-11-30T12:00:00Z"))).toBe("memory-capsule-fete-d-ete-2026-11-30.zip");
  expect(capsuleExportFilename("", new Date("2026-11-30T12:00:00Z"))).toBe("memory-capsule-event-2026-11-30.zip");
});
