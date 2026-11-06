#!/usr/bin/env node
// K3 guard: screens inside a Kindred space must say the organizer's chosen
// group word (useGroupWording / groupWords in src/lib/groupWording.js), never a
// hard-coded "family". Run directly to list offenders:
//   node scripts/check-group-wording.cjs
//
// What counts: the standalone words family / families / Family / Families
// (with or without 's), and prose compounds like "family-space", in code that
// is not a comment. Identifiers and keys such
// as familyName, family_access, "/family/join" or family-access are ignored.
//
// Escape hatches, in order of preference:
//   1. Route the text through the helper.
//   2. A file that is legitimately outside a space goes in ALLOWED_FILES with
//      a reason (marketing, pre-signup, analytics names).
//   3. One line that must keep the word (a data value, a reference to another
//      product) carries the marker  group-wording: allow  on the same line.

const fs = require("fs");
const path = require("path");

const SRC = path.resolve(__dirname, "..", "src");

const ALLOWED_FILES = {
  // Marketing and legal pages: the brand line and public positioning stay family-first.
  "components/LandingPage.jsx": "marketing",
  "components/PricingPage.jsx": "marketing",
  "components/PublicPlanCards.jsx": "marketing",
  "components/NativeWelcomePage.jsx": "marketing (signed-out app welcome)",
  "components/IntentChooserPage.jsx": "marketing (signed-out front door)",
  "components/StrategyPage.jsx": "internal positioning page, platform admin only",
  "components/TermsOfServicePage.jsx": "legal",
  "components/PrivacyPolicyPage.jsx": "legal",
  "components/SupportPage.jsx": "public support page",
  "lib/seasonalCampaign.js": "campaign copy for the Keep The Record contest",
  // Before a space exists there is no organizer choice to read.
  "components/ReunionStartPage.jsx": "pre-signup reunion draft; no space yet",
  "components/AuthPage.jsx": "signed-out sign-in and sign-up; no space is known yet",
  "lib/reunionDraft.js": "pre-signup reunion draft; no space yet",
  // Not user-facing.
  "lib/analytics.js": "analytics event and property names",
  "lib/sentry.js": "error-reporting scrubbing rules",
  "lib/groupWording.js": "the helper itself defines the family preset",
};

const ALLOW_MARKER = "group-wording: allow";
// Standalone words, plus prose compounds such as "family-space" (a space or
// ">" before them); keys like "family-access" or /family/join stay ignored.
const WORD = /(?<![-_/.\w])(?:family|families|Family|Families|FAMILY)(?:'s)?(?![-_\w])|(?<=[\s>])(?:family|Family)-(?=[a-z])/g;

const blankKeepingLines = (text) => text.replace(/[^\n]/g, " ");

const stripComments = (source) => source
  // Block and JSX comments, keeping line numbers.
  .replace(/\/\*[\s\S]*?\*\//g, (match) => blankKeepingLines(match))
  // Line comments: `//` at line start or after whitespace/punctuation that cannot end a URL scheme.
  .replace(/(^|[\s;{}(),])\/\/[^\n]*/gm, (match, lead) => lead);

const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const full = path.join(dir, entry.name);
  if (entry.isDirectory()) return entry.name === "ui" ? [] : walk(full);
  if (!/\.(js|jsx)$/.test(entry.name) || /\.test\.(js|jsx)$/.test(entry.name)) return [];
  return [full];
});

const findOffenders = () => {
  const offenders = [];
  for (const file of walk(SRC)) {
    const relative = path.relative(SRC, file).split(path.sep).join("/");
    if (ALLOWED_FILES[relative]) continue;
    const raw = fs.readFileSync(file, "utf8").split("\n");
    const stripped = stripComments(fs.readFileSync(file, "utf8")).split("\n");
    stripped.forEach((line, index) => {
      if (raw[index].includes(ALLOW_MARKER)) return;
      if (WORD.test(line)) offenders.push(`${relative}:${index + 1}: ${raw[index].trim()}`);
      WORD.lastIndex = 0;
    });
  }
  return offenders;
};

module.exports = { ALLOWED_FILES, findOffenders, stripComments, WORD };

if (require.main === module) {
  const offenders = findOffenders();
  if (offenders.length) {
    console.log(`Hard-coded group wording found (${offenders.length}):`);
    offenders.forEach((line) => console.log(`  ${line}`));
    process.exit(1);
  }
  console.log("No hard-coded group wording in space screens.");
}
