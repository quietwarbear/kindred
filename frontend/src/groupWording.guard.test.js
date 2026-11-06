/**
 * @jest-environment node
 */
// K3 guard: no new hard-coded "family" in screens inside a Kindred space.
// Run `node scripts/check-group-wording.cjs` to list offenders with line numbers.
const path = require("path");

const guard = require(path.resolve(__dirname, "..", "scripts", "check-group-wording.cjs"));

const flags = (line) => {
  guard.WORD.lastIndex = 0;
  const hit = guard.WORD.test(guard.stripComments(line));
  guard.WORD.lastIndex = 0;
  return hit;
};

test("space screens route the group word through the helper", () => {
  expect(guard.findOffenders()).toEqual([]);
});

test("every allowlisted file says why", () => {
  Object.values(guard.ALLOWED_FILES).forEach((reason) => expect(reason).toMatch(/\w{4,}/));
});

test.each([
  '<p>Open family activity</p>',
  'toast.error("Your family is full");',
  "heading = 'Families welcome';",
  '<span>Family-space name</span>',
  "label: \"Review the family's recap\",",
])("flags %s", (line) => {
  expect(flags(line)).toBe(true);
});

test.each([
  'const familyName = "";',
  'navigate("/family/join");',
  'data-testid="family-space-activate-button"',
  'trackReunionEvent("family_today_viewed");',
  'if (intent === "family-access") return null;',
  "// a comment about the family",
  "{/* the family home card */}",
  'import { GuestFamilyAccessPage } from "@/components/GuestFamilyAccessPage";',
  'const words = fill("{Group} Today");',
])("ignores %s", (line) => {
  expect(flags(line)).toBe(false);
});
