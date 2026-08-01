import { buildActivationFunnel, NEXT_ACTION_LABELS } from "./activationFunnel";

describe("activation funnel", () => {
  test("orders the funnel with monotonic stages and percentages of prepared", () => {
    const funnel = buildActivationFunnel(
      {
        active_invitations: 10,
        invitations_shared: 8,
        invitations_reached: 9,
        invitations_opened: 5,
        invitations_seen: 6,
        invitations_delivered: 4,
        responses_received: 2,
        invitations_awaiting_response: 3,
      },
      "send_reminders"
    );
    // prepared >= reached >= opened(seen) >= responded — never inverts.
    expect(funnel.stages.map((s) => [s.key, s.count, s.pct])).toEqual([
      ["prepared", 10, 100],
      ["reached", 9, 90],
      ["opened", 6, 60],
      ["responded", 2, 20],
    ]);
    const counts = funnel.stages.map((s) => s.count);
    expect(counts).toEqual([...counts].sort((a, b) => b - a)); // monotonic
    expect(funnel.awaiting).toBe(3);
    expect(funnel.delivered).toBe(4);
    expect(funnel.shared).toBe(8);
    expect(funnel.hasActivity).toBe(true);
    expect(funnel.nextAction).toEqual({
      code: "send_reminders",
      label: "Send a reminder",
    });
  });

  test("is safe with no invitations yet", () => {
    const funnel = buildActivationFunnel({}, "prepare_invitations");
    expect(funnel.hasActivity).toBe(false);
    expect(funnel.stages.every((s) => s.count === 0)).toBe(true);
    expect(funnel.stages[0].pct).toBe(0);
    expect(funnel.nextAction.label).toBe("Prepare invitations");
  });

  test("clamps a malformed out-of-range count so no bar exceeds 100%", () => {
    // Real payloads are nested (server-guaranteed); this is defensive only.
    const funnel = buildActivationFunnel(
      { active_invitations: 4, invitations_seen: 9 },
      ""
    );
    const opened = funnel.stages.find((s) => s.key === "opened");
    expect(opened.pct).toBe(100); // bar width capped at prepared
    expect(funnel.nextAction).toBeNull();
  });

  test("falls back to a sensible label for an unknown action code", () => {
    expect(buildActivationFunnel({}, "mystery_code").nextAction.label).toBe(
      "Review the plan"
    );
    expect(NEXT_ACTION_LABELS.send_reminders).toBe("Send a reminder");
  });
});
