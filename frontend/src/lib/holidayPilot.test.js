import { toDateTimeLocalValue, uniqueGuestCount } from "./holidayPilot";

describe("Thanksgiving pilot organizer helpers", () => {
  test("preserves an existing local wall time", () => {
    expect(toDateTimeLocalValue("2026-11-26T16:00:00", "America/Los_Angeles"))
      .toBe("2026-11-26T16:00");
  });

  test("renders an offset timestamp in the event timezone", () => {
    expect(toDateTimeLocalValue("2026-11-27T00:00:00Z", "America/Los_Angeles"))
      .toBe("2026-11-26T16:00");
  });

  test("fails closed for malformed timestamps", () => {
    expect(toDateTimeLocalValue("not-a-dateZ", "America/Los_Angeles")).toBe("");
  });

  test("deduplicates guest plan entries without returning addresses", () => {
    expect(uniqueGuestCount("One@example.invalid, one@example.invalid, two@example.invalid"))
      .toBe(2);
  });
});
