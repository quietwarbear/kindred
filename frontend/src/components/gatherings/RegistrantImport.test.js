import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({
  BACKEND_URL: "https://api.example.invalid",
  apiRequest: jest.fn(),
  errorDetail: (_e, fallback) => fallback,
}));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { apiRequest } = require("@/lib/api");
const { RegistrantImport, ImportReport, DuplicateFlags } = require("./RegistrantImport");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act || require("react-dom/test-utils").act;

const event = { id: "event-1", publication_state: "published", agenda: [] };
const HOOK = {
  configured: true,
  path: "/api/inbound/registrants/hook-1",
  secret: "kwhsec_abcdefghijklmnopqrstuvwxyz",
};
const FLAG = {
  id: "flag-1",
  status: "pending",
  name: "Ada Example",
  email: "ada.other@example.invalid",
  matched_name: "Ada Example",
  matched_email: "ada@example.invalid",
  sessions: ["Day One"],
};

let container;
let root;

const mount = async (element) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(element);
  });
  return container;
};

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.clearAllMocks();
});

const routeApi = (overrides = {}) => {
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (overrides[path]) return overrides[path](options);
    if (path.endsWith("/registrants/flags")) return { flags: [FLAG] };
    if (path.endsWith("/registrants/webhook")) return HOOK;
    return {};
  });
};

describe("RegistrantImport panel", () => {
  it("loads the webhook URL, keeps the secret masked until asked, and lists pending duplicates", async () => {
    routeApi();
    const el = await mount(<RegistrantImport event={event} onUpdate={jest.fn()} token="t" />);
    expect(el.querySelector('[data-testid="registrant-webhook-url"]').textContent).toBe(
      "https://api.example.invalid/api/inbound/registrants/hook-1"
    );
    const secret = el.querySelector('[data-testid="registrant-webhook-secret"]');
    expect(secret.textContent).not.toContain("xyz");
    await act(async () => el.querySelector('[data-testid="registrant-webhook-reveal"]').click());
    expect(secret.textContent).toBe(HOOK.secret);
    expect(el.textContent).toContain("Possible duplicates (1)");
    expect(el.querySelector('[data-testid="registrant-flag-flag-1"]')).not.toBeNull();
  });

  it("resolves a duplicate as the same person and refreshes the list", async () => {
    let resolved = false;
    routeApi({
      "/events/event-1/registrants/flags/flag-1/resolve": ({ data }) => {
        expect(data).toEqual({ action: "apply_to_existing", send_invitation: true });
        resolved = true;
        return { status: "apply_to_existing", row: { status: "updated" } };
      },
      "/events/event-1/registrants/flags": () => ({ flags: resolved ? [] : [FLAG] }),
    });
    const el = await mount(<RegistrantImport event={event} onUpdate={jest.fn()} token="t" />);
    await act(async () => el.querySelector('[data-testid="registrant-flag-same-flag-1"]').click());
    expect(resolved).toBe(true);
    expect(el.querySelector('[data-testid="registrant-flags-empty"]')).not.toBeNull();
  });

  it("offers to create the webhook when the event has none", async () => {
    routeApi({
      "/events/event-1/registrants/webhook": () => ({ configured: false }),
      "/events/event-1/registrants/webhook/rotate": () => HOOK,
    });
    const el = await mount(<RegistrantImport event={event} onUpdate={jest.fn()} token="t" />);
    await act(async () => el.querySelector('[data-testid="registrant-webhook-create"]').click());
    expect(el.querySelector('[data-testid="registrant-webhook-url"]')).not.toBeNull();
  });

  it("does nothing for a private draft", async () => {
    routeApi();
    const el = await mount(
      <RegistrantImport event={{ ...event, publication_state: "organizer_draft" }} onUpdate={jest.fn()} token="t" />
    );
    expect(el.querySelector('[data-testid="registrant-import-draft-guard"]')).not.toBeNull();
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

describe("ImportReport", () => {
  it("shows every row with its number, errors first, and flags with the matching invitee", async () => {
    const el = await mount(
      <ImportReport
        report={{
          counts: { created: 1, updated: 0, skipped: 0, flagged: 1, error: 1 },
          rows: [
            { row: 2, status: "created", name: "Bo", email: "bo@example.invalid", sessions: ["Day One"] },
            { row: 3, status: "flagged", name: "Ada", email: "a2@example.invalid", matched_name: "Ada", matched_email: "a@example.invalid" },
            { row: 4, status: "error", name: "", email: "nope", detail: "Missing or invalid email address." },
          ],
          delivery: { status: "processed", counts: { submitted: 1 } },
        }}
      />
    );
    const rows = [...el.querySelectorAll("li")].map((li) => li.getAttribute("data-testid"));
    expect(rows).toEqual(["registrant-import-row-4", "registrant-import-row-3", "registrant-import-row-2"]);
    expect(el.textContent).toContain("1 invited · 1 possible duplicate · 1 error");
    expect(el.textContent).toContain("Emailed 1 invitation.");
    expect(el.textContent).toContain("Same name as Ada (a@example.invalid)");
    expect(el.textContent).toContain("Coming to: Day One");
  });
});

describe("DuplicateFlags", () => {
  it("hides flags that were already reviewed", async () => {
    const el = await mount(<DuplicateFlags flags={[{ ...FLAG, status: "dismissed" }]} onResolve={jest.fn()} />);
    expect(el.textContent).toContain("No possible duplicates to review.");
  });
});
