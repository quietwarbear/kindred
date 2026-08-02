import {
  invitationActivationSummary,
  toDateTimeLocalValue,
  uniqueGuestCount,
} from "./holidayPilot";

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

  test("summarizes activation counts as non-negative integers", () => {
    expect(
      invitationActivationSummary({
        active_invitations: 5,
        invitations_shared: 3,
        invitations_reached: 4,
        invitations_opened: 2,
        invitations_seen: 3,
        invitations_delivered: 1,
        responses_received: 1,
      })
    ).toEqual({
      prepared: 5,
      shared: 3,
      reached: 4,
      opened: 2,
      seen: 3,
      delivered: 1,
      responses: 1,
      awaiting: 0,
    });
  });

  test("surfaces the awaiting-response follow-up count", () => {
    expect(
      invitationActivationSummary({
        active_invitations: 4,
        invitations_awaiting_response: 2,
      }).awaiting
    ).toBe(2);
  });

  test("coerces missing, negative, or fractional counts to zero-safe integers", () => {
    expect(
      invitationActivationSummary({ invitations_shared: -4, invitations_opened: 2.9 })
    ).toEqual({
      prepared: 0,
      shared: 0,
      reached: 0,
      opened: 2,
      seen: 0,
      delivered: 0,
      responses: 0,
      awaiting: 0,
    });
    expect(invitationActivationSummary(undefined)).toEqual({
      prepared: 0,
      shared: 0,
      reached: 0,
      opened: 0,
      seen: 0,
      delivered: 0,
      responses: 0,
      awaiting: 0,
    });
  });
});
