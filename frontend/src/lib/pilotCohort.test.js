import {
  isInCohort,
  pilotActionLabel,
  pilotStatusLabel,
  PILOT_STATUS_LABELS,
} from "./pilotCohort";

describe("pilot cohort labels", () => {
  test("maps every backend status to a friendly label", () => {
    for (const status of [
      "not_enrolled",
      "enrolled",
      "consented",
      "active",
      "completed",
      "withdrawn",
    ]) {
      expect(PILOT_STATUS_LABELS[status]).toBeTruthy();
      expect(pilotStatusLabel(status)).toBe(PILOT_STATUS_LABELS[status]);
    }
  });

  test("falls back safely for unknown status/action", () => {
    expect(pilotStatusLabel("mystery")).toBe("Not enrolled");
    expect(pilotStatusLabel(undefined)).toBe("Not enrolled");
    expect(pilotActionLabel("mystery")).toBe("mystery");
  });

  test("records the friendly action labels", () => {
    expect(pilotActionLabel("record_consent")).toBe("Record consent");
    expect(pilotActionLabel("withdraw")).toBe("Withdraw");
  });

  test("isInCohort is true only past not_enrolled", () => {
    expect(isInCohort("not_enrolled")).toBe(false);
    expect(isInCohort("")).toBe(false);
    expect(isInCohort(undefined)).toBe(false);
    expect(isInCohort("consented")).toBe(true);
  });
});
