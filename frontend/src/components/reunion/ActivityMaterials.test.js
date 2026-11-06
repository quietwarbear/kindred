import React from "react";
import { createRoot } from "react-dom/client";
import { apiBlobRequest } from "@/lib/api";

import {
  ActivityMaterials,
  MATERIALS_WITHHELD_NOTICE,
  downloadMaterial,
  formatMaterialSize,
  materialDownloadPath,
} from "./ActivityMaterials";

jest.mock("@/lib/api", () => ({
  apiBlobRequest: jest.fn(),
  apiRequest: jest.fn(),
  convertFileToDataUrl: jest.fn(),
}));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const act = React.act || require("react-dom/test-utils").act;

let container;
let root;

beforeAll(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
});

const render = async (element) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(element); });
};

afterEach(async () => {
  if (root) await act(async () => { root.unmount(); });
  container?.remove();
  root = null;
  container = null;
  apiBlobRequest.mockReset();
});

const MATERIAL = { id: "m-1", name: "Site map.pdf", mime_type: "application/pdf", size: 2048 };

const activity = (overrides = {}) => ({
  id: "session-a",
  title: "Morning walk",
  supply_list: "",
  materials: [],
  materials_withheld: false,
  materials_notice: "",
  ...overrides,
});

const byTestId = (id) => container.querySelector(`[data-testid="${id}"]`);

describe("ActivityMaterials", () => {
  it("shows the withheld notice and nothing else to people not coming", async () => {
    await render(<ActivityMaterials activity={activity({ materials_withheld: true, materials_notice: MATERIALS_WITHHELD_NOTICE })} />);
    expect(byTestId("activity-materials-withheld-session-a").textContent).toBe(MATERIALS_WITHHELD_NOTICE);
    expect(byTestId("activity-materials-session-a")).toBeNull();
  });

  it("renders nothing when there is nothing to share", async () => {
    await render(<ActivityMaterials activity={activity()} />);
    expect(container.innerHTML).toBe("");
  });

  it("shows the supply list and files to people coming", async () => {
    await render(<ActivityMaterials activity={activity({ supply_list: "Chair\nWater", materials: [MATERIAL] })} />);
    expect(byTestId("activity-supply-list-session-a").textContent).toBe("Chair\nWater");
    expect(byTestId("activity-material-download-m-1").textContent).toBe("Site map.pdf");
    expect(container.textContent).toContain("2 KB");
    expect(byTestId("activity-material-remove-m-1")).toBeNull();
    expect(byTestId("activity-material-input-session-a")).toBeNull();
  });

  it("gives organizers attach and remove controls", async () => {
    await render(<ActivityMaterials activity={activity({ materials: [MATERIAL] })} canManage eventId="event-1" />);
    expect(byTestId("activity-material-remove-m-1").getAttribute("aria-label")).toBe("Remove Site map.pdf");
    const input = byTestId("activity-material-input-session-a");
    expect(input.getAttribute("accept")).toContain("application/pdf");
    expect(input.getAttribute("aria-label")).toBe("Attach a file to Morning walk");
  });

  it("downloads with a bearer header, never a URL token", async () => {
    const blob = new Blob(["%PDF-"], { type: "application/pdf" });
    apiBlobRequest.mockResolvedValue(blob);
    global.URL.createObjectURL = jest.fn(() => "blob:local");
    global.URL.revokeObjectURL = jest.fn();
    const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await downloadMaterial(MATERIAL, { token: "invite-token" });
    const [path, options] = apiBlobRequest.mock.calls[0];
    expect(path).toBe("/public/rsvp/materials/m-1");
    expect(path).not.toContain("invite-token");
    expect(options).toEqual({ token: "invite-token" });
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });
});

describe("material helpers", () => {
  it("chooses the member or guest download path", () => {
    expect(materialDownloadPath(MATERIAL, "event-1")).toBe("/events/event-1/materials/m-1");
    expect(materialDownloadPath(MATERIAL, "")).toBe("/public/rsvp/materials/m-1");
  });

  it("formats sizes", () => {
    expect(formatMaterialSize(512)).toBe("512 B");
    expect(formatMaterialSize(2048)).toBe("2 KB");
    expect(formatMaterialSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});
