/**
 * @jest-environment node
 */
// Runs scripts/check-undefined-names.cjs in its own Node process: ESLint's
// dependencies cannot be loaded through this project's Jest transform.
const path = require("path");
const { spawnSync } = require("child_process");

test("no component or function is used without being imported or declared", () => {
  const script = path.resolve(__dirname, "..", "scripts", "check-undefined-names.cjs");
  const run = spawnSync(process.execPath, [script], { encoding: "utf8" });
  const output = `${run.stdout}${run.stderr}`;

  expect(output).not.toMatch(/Undefined names found/);
  expect(run.status).toBe(0);
}, 60000);
