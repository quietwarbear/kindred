const fs = require("fs");
const path = require("path");
const swift = fs.readFileSync(path.resolve(__dirname, "../../ios/App/App/AppDelegate.swift"), "utf8");

// Source regression guard complements native compilation and device testing.
// The SDK creates NSTimers on the calling run loop, so both configuration and
// initialization must be inside the main-queue closure, not just the callback.
test("iOS creates TikTok configuration and initializes inside the main queue", () => {
  const start = swift.split("@objc func start(")[1].split("@objc func requestTracking(")[0];
  expect(start).toMatch(/DispatchQueue\.main\.async\s*\{[\s\S]*TikTokConfig\([\s\S]*TikTokBusiness\.initializeSdk/);
  expect(start.indexOf("DispatchQueue.main.async")).toBeLessThan(start.indexOf("TikTokConfig("));
  expect(start).toContain('call.reject("Missing TikTok config")');
  expect(start).toContain("#if DEBUG");
  expect(start).toContain("config.setDelayForATTUserAuthorizationInSeconds(20)");
});

test("iOS requests ATT on the main queue", () => {
  const tracking = swift.split("@objc func requestTracking(")[1].split("@objc func track(")[0];
  expect(tracking).toMatch(/DispatchQueue\.main\.async\s*\{\s*TikTokBusiness\.requestTrackingAuthorization/);
});
