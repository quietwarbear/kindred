const fs = require("fs");
const path = require("path");

const page = fs.readFileSync(path.join(__dirname, "../components/LegacyThreadsPage.jsx"), "utf8");
const api = fs.readFileSync(path.join(__dirname, "../../../backend/routes/legacy.py"), "utf8");

test("recipe transfer requires explicit unchecked consent", () => {
  expect(page).toContain("useState(false)");
  expect(page).toContain('consent_confirmed: true');
  expect(page).toContain('"payload_retrieved", "destination_pending", "destination_accepted"');
  expect(page).toContain('disabled={!consentAccepted');
  expect(page).toContain('window.location.assign(result.url)');
});

test("Kindred grants use fragment landing and header-only payload routes", () => {
  expect(api).toContain('#transfer={credential}');
  expect(api).toContain('alias="X-Kindred-Transfer"');
  expect(api).not.toMatch(/transfer-payload\/\{|transfer-acknowledgement\/\{|\?transfer=/);
  expect(api).toContain('"Cache-Control": "no-store, max-age=0"');
  expect(api).toContain('"Referrer-Policy": "no-referrer"');
});
