/**
 * TikTok App Events — ad attribution for TikTok App Promotion campaigns.
 *
 * Native apps only (iOS / Android). A thin wrapper over the local Capacitor
 * plugin "TikTokEvents", whose native halves live in
 *   ios/App/App/AppDelegate.swift
 *   android/app/src/main/java/com/ubuntumarket/kindred/TikTokEventsPlugin.java
 *
 * Entirely no-op on the web, and in native builds unless an App Secret is
 * supplied at build time:
 *   REACT_APP_TIKTOK_APP_SECRET_IOS / REACT_APP_TIKTOK_APP_SECRET_ANDROID
 *
 * Same rule as the Meta Pixel: TikTok receives standard event NAMES only.
 * The one exception is Subscribe, which carries the store product id, price
 * and currency — none of which is family content. No user identity is sent.
 * Install and app-launch events are sent automatically by the native SDK.
 */
import { Capacitor, registerPlugin } from "@capacitor/core";

// Registered on first use, not at import: this module is imported by web code
// paths (and tests) that never touch the native plugin.
let plugin = null;
const tiktokPlugin = () => {
  if (!plugin) plugin = registerPlugin("TikTokEvents");
  return plugin;
};

// App IDs identify the app in TikTok Events Manager; they are not secret.
const TIKTOK_APPS = {
  ios: {
    appId: "6760608478",
    ttAppId: "7692520905070706689",
    accessToken: process.env.REACT_APP_TIKTOK_APP_SECRET_IOS || "",
  },
  android: {
    appId: "com.ubuntumarket.kindred",
    ttAppId: "7692523677824401429",
    accessToken: process.env.REACT_APP_TIKTOK_APP_SECRET_ANDROID || "",
  },
};

let started = null; // Promise<boolean> once init has been attempted

const platformConfig = () => {
  if (!Capacitor.isNativePlatform()) return null;
  if (process.env.REACT_APP_DISABLE_ANALYTICS === "true") return null;
  const config = TIKTOK_APPS[Capacitor.getPlatform()];
  return config && config.accessToken ? config : null;
};

export const tiktokEventsEnabled = () => Boolean(platformConfig());

/**
 * Start the SDK, then (iOS only) show Apple's tracking prompt once the app is
 * on screen. Safe to call more than once; never throws.
 */
export function initTikTokEvents() {
  if (started) return started;
  const config = platformConfig();
  if (!config) {
    started = Promise.resolve(false);
    return started;
  }
  started = tiktokPlugin().start({
    ...config,
    debug: process.env.NODE_ENV !== "production",
  })
    .then(() => {
      if (Capacitor.getPlatform() === "ios") {
        setTimeout(() => {
          tiktokPlugin().requestTracking().catch(() => {});
        }, 1500);
      }
      return true;
    })
    .catch((error) => {
      console.warn("[Kindred] TikTok SDK init failed", error);
      return false;
    });
  return started;
}

/** Send one TikTok standard event. Never throws; resolves false if not sent. */
export async function trackTikTokEvent(event, properties = {}) {
  if (!started || !(await started)) return false;
  try {
    await tiktokPlugin().track({ event, properties });
    return true;
  } catch (error) {
    console.warn(`[Kindred] TikTok track(${event}) failed`, error);
    return false;
  }
}
