import { isContestOpen } from "./planUsage";

export const KEEP_THE_RECORD_RULES_URL = "https://legacytable.app/keeptherecord";

export function gatheringCampaign(now = Date.now()) {
  if (isContestOpen(now)) {
    return {
      active: true,
      preferredType: "holiday_meal",
      startPath: "/reunion/start?type=holiday_meal&campaign=keep-the-record",
      eyebrow: "Keep The Record · Open through December 5",
      headline: "Gather the family. Keep the record.",
      subheadline: "Plan one holiday gathering, bring everyone in, and preserve the recipe or story your family carries.",
      cta: "Plan a holiday gathering",
    };
  }

  return {
    active: false,
    preferredType: "",
    startPath: "/reunion/start",
    eyebrow: "Built for multigenerational families and diaspora organizers",
    headline: "Plan the gathering. Bring everyone in. Keep the stories.",
    subheadline: "One private place for RSVPs, potluck, volunteers, travel, photos, and family stories.",
    cta: "Start a gathering",
  };
}
