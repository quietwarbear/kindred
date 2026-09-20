import { gatheringCampaign, KEEP_THE_RECORD_RULES_URL } from "./seasonalCampaign";

describe("gatheringCampaign", () => {
  it("leads with a holiday gathering while Keep The Record is open", () => {
    expect(gatheringCampaign(Date.parse("2026-11-15T12:00:00-08:00"))).toMatchObject({
      active: true,
      preferredType: "holiday_meal",
      startPath: "/reunion/start?type=holiday_meal&campaign=keep-the-record",
      cta: "Plan a holiday gathering",
    });
    expect(KEEP_THE_RECORD_RULES_URL).toBe("https://legacytable.app/keeptherecord");
  });

  it("returns to a gathering-first evergreen entry after the contest", () => {
    expect(gatheringCampaign(Date.parse("2026-12-06T00:00:00-08:00"))).toMatchObject({
      active: false,
      preferredType: "",
      startPath: "/reunion/start",
      headline: "Plan the gathering. Bring everyone in. Keep the stories.",
      cta: "Start a gathering",
    });
  });
});
