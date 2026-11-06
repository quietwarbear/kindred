/**
 * Kindred's store privacy answers say the app does not track people across
 * other companies' apps: no App Tracking Transparency prompt on iOS, no
 * advertising ID on Android. These checks fail if an ad-attribution SDK or
 * the tracking prompt is added back to the native shells without that
 * decision being revisited (and the App Store / Play declarations changed).
 */
import fs from "fs";
import path from "path";

const frontendRoot = path.resolve(__dirname, "../..");
const read = (relative) => fs.readFileSync(path.join(frontendRoot, relative), "utf8");

// Ad-attribution and cross-app tracking signatures. The match is case
// insensitive, so it covers the SDK, the pod, the Gradle coordinate and the
// Capacitor plugin.
const TRACKING_SIGNATURES = [
  /tiktok/i,
  /AppTrackingTransparency/,
  /ATTrackingManager/,
  /requestTrackingAuthorization/,
  /NSUserTrackingUsageDescription/,
  /advertisingIdentifier/,
  /com\.google\.android\.gms\.permission\.AD_ID/,
  /play-services-ads-identifier/,
  /installreferrer/i,
  /jitpack\.io/,
];

const NATIVE_FILES = [
  "ios/App/Podfile",
  "ios/App/App/AppDelegate.swift",
  "ios/App/App/Info.plist",
  "ios/App/App/Base.lproj/Main.storyboard",
  "android/build.gradle",
  "android/app/build.gradle",
  "android/app/src/main/AndroidManifest.xml",
  "android/app/src/main/java/com/ubuntumarket/kindred/MainActivity.java",
];

describe("native shells carry no cross-app tracking", () => {
  it.each(NATIVE_FILES)("%s has no tracking SDK or tracking prompt", (file) => {
    const source = read(file);
    TRACKING_SIGNATURES.forEach((signature) => {
      expect({ file, match: source.match(signature)?.[0] ?? null }).toEqual({ file, match: null });
    });
  });

  it("the iOS root view controller is Capacitor's own bridge controller", () => {
    expect(read("ios/App/App/Base.lproj/Main.storyboard")).toMatch(
      /customClass="CAPBridgeViewController" customModule="Capacitor"/,
    );
  });

  it("Android registers no app-local tracking plugin", () => {
    expect(read("android/app/src/main/java/com/ubuntumarket/kindred/MainActivity.java")).not.toMatch(
      /registerPlugin/,
    );
  });

  it("no source file loads an ad-attribution bridge", () => {
    const srcRoot = path.join(frontendRoot, "src");
    const offenders = [];
    const walk = (dir) => {
      fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) return walk(full);
        if (!/\.(jsx?|tsx?)$/.test(entry.name) || full === __filename) return;
        const text = fs.readFileSync(full, "utf8");
        if (/registerPlugin\(\s*["']TikTokEvents["']|from\s+["']@\/lib\/tiktokEvents["']/.test(text)) {
          offenders.push(path.relative(frontendRoot, full));
        }
      });
    };
    walk(srcRoot);
    expect(offenders).toEqual([]);
  });
});
