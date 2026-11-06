import {
  audienceSummary,
  buildOverrides,
  choicesFromSettings,
  deliveryLine,
  describeOffsets,
  offsetLabel,
  readinessNotes,
  toggleOffset,
} from "./eventMessaging";

describe("event messaging helpers", () => {
  it("labels offsets and keeps them sorted, unique and bounded", () => {
    expect(offsetLabel(1440)).toBe("24 hours before");
    expect(offsetLabel(4320)).toBe("3 days before");
    expect(offsetLabel(90)).toBe("90 minutes before");
    expect(describeOffsets([60, 1440])).toBe("24 hours before, 1 hour before");
    expect(describeOffsets([])).toBe("No reminders");
    expect(toggleOffset([60], 1440)).toEqual([1440, 60]);
    expect(toggleOffset([1440, 60], 60)).toEqual([1440]);
    expect(toggleOffset([10080, 2880, 1440, 60], 15)).toEqual([10080, 2880, 1440, 60]);
  });

  it("round-trips per-activity overrides: default omitted, off is empty, custom keeps its own", () => {
    const activities = [{ id: "a" }, { id: "b" }, { id: "c" }];
    const choices = choicesFromSettings(activities, { b: [], c: [180] });
    expect(choices).toEqual({
      a: { mode: "default", offsets: [] },
      b: { mode: "off", offsets: [] },
      c: { mode: "custom", offsets: [180] },
    });
    expect(buildOverrides(choices)).toEqual({ b: [], c: [180] });
  });

  it("summarizes the audience and the delivery without names", () => {
    expect(audienceSummary({ recipients: 0 })).toBe("Nobody matches this audience yet.");
    expect(audienceSummary({ recipients: 3, with_email: 3, with_account: 1 })).toBe("3 people · all with email · 1 in the app");
    expect(audienceSummary({ recipients: 1, with_email: 0, with_account: 1 })).toBe("1 person · 0 with email · 1 in the app");
    expect(deliveryLine({ recipients: 0 })).toBe("In the app only");
    expect(
      deliveryLine({ recipients: 4, pending: 1, opted_out: 1, email: { accepted: 2 }, push: { delivered: 1, no_device: 1 } })
    ).toBe("2 emailed · 1 push · 1 opted out · 1 sending");
  });

  it("explains what is switched off on this deployment", () => {
    expect(readinessNotes({ email: "ready", push: "ready", scheduler: "configured" })).toEqual([]);
    expect(readinessNotes({ email: "unverified_sender", push: "off", scheduler: "not_configured" })).toHaveLength(3);
  });
});
