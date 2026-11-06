import { NATIVE_IOS_CLASS, applyNativeTextScale } from "./textScale";

jest.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: () => false, getPlatform: () => "web" } }));

const fake = (native, platform) => ({ isNativePlatform: () => native, getPlatform: () => platform });

test("opts the native iOS app into Dynamic Type", () => {
  const root = document.createElement("html");
  expect(applyNativeTextScale(root, fake(true, "ios"))).toBe(true);
  expect(root.classList.contains(NATIVE_IOS_CLASS)).toBe(true);
});

test("leaves Android and the web alone", () => {
  for (const [native, platform] of [[true, "android"], [false, "web"]]) {
    const root = document.createElement("html");
    expect(applyNativeTextScale(root, fake(native, platform))).toBe(false);
    expect(root.classList.length).toBe(0);
  }
});

test("never throws", () => {
  const broken = { isNativePlatform: () => { throw new Error("x"); } };
  expect(applyNativeTextScale(document.createElement("html"), broken)).toBe(false);
});
