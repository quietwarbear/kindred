import {
  csvTemplateFor,
  deliverySummary,
  reportSummary,
  sortReportRows,
  webhookUrl,
} from "./registrantImport";

describe("registrant import helpers", () => {
  it("builds the full webhook URL from the API host and the server path", () => {
    expect(webhookUrl("https://api.example.invalid/", "/api/inbound/registrants/abc")).toBe(
      "https://api.example.invalid/api/inbound/registrants/abc"
    );
    expect(webhookUrl("https://api.example.invalid", "")).toBe("");
  });

  it("summarizes the report counts in plain words", () => {
    expect(reportSummary({ created: 3, updated: 0, skipped: 1, flagged: 1, error: 2 })).toBe(
      "3 invited · 1 unchanged · 1 possible duplicate · 2 errors"
    );
    expect(reportSummary({})).toBe("Nothing to import.");
  });

  it("explains delivery outcomes, including when email is off", () => {
    expect(deliverySummary({ status: "not_requested" })).toBe("");
    expect(deliverySummary({ status: "unavailable", error_code: "delivery_disabled" })).toMatch(/off/);
    expect(
      deliverySummary({ status: "processed", counts: { submitted: 2, skipped: 1, rejected: 1 } })
    ).toBe("Emailed 2 invitations. 1 already had one. 1 could not be sent.");
  });

  it("puts errors and flags first, then row order", () => {
    const rows = [
      { row: 2, status: "created" },
      { row: 5, status: "error" },
      { row: 3, status: "flagged" },
      { row: 4, status: "error" },
    ];
    expect(sortReportRows(rows).map((r) => r.row)).toEqual([4, 5, 3, 2]);
  });

  it("fills the template with this event's own session titles", () => {
    const event = {
      agenda: [
        { title: "Opening; Night", visibility: "published" },
        { title: "Workshop", visibility: "published" },
        { title: "Hidden", visibility: "draft" },
      ],
    };
    expect(csvTemplateFor(event)).toBe(
      'Name,Email,Sessions purchased\nAda Example,ada@example.com,"Opening  Night; Workshop"\n'
    );
    expect(csvTemplateFor({ agenda: [] })).toContain("Day One; Day Two");
  });
});
