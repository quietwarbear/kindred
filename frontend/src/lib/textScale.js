import { Capacitor } from "@capacitor/core";

// iOS WKWebView ignores the system text size (Dynamic Type) unless the page
// opts in with the -apple-system-body font. Android's WebView already follows
// the system font scale, and browsers have their own zoom, so only the native
// iOS app needs this. See `html.native-ios` in index.css.
export const NATIVE_IOS_CLASS = "native-ios";

export const applyNativeTextScale = (root = document.documentElement, capacitor = Capacitor) => {
  try {
    if (capacitor.isNativePlatform() && capacitor.getPlatform() === "ios") {
      root.classList.add(NATIVE_IOS_CLASS);
      return true;
    }
  } catch {
    // Never block start-up on this.
  }
  return false;
};
