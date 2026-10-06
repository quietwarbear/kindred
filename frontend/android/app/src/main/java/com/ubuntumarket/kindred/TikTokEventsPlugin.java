package com.ubuntumarket.kindred;

import android.content.pm.ApplicationInfo;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.tiktok.TikTokBusinessSdk;
import com.tiktok.appevents.base.TTBaseEvent;

import java.util.Iterator;

/**
 * TikTok App Events (tiktok-business-android-sdk) — JS side is
 * src/lib/tiktokEvents.js. Nothing here runs unless JS calls start(), which it
 * only does when REACT_APP_TIKTOK_APP_SECRET_ANDROID was present at build time.
 */
@CapacitorPlugin(name = "TikTokEvents")
public class TikTokEventsPlugin extends Plugin {

    @PluginMethod
    public void start(final PluginCall call) {
        String accessToken = call.getString("accessToken");
        String appId = call.getString("appId");
        String ttAppId = call.getString("ttAppId");
        if (isEmpty(accessToken) || isEmpty(appId) || isEmpty(ttAppId)) {
            call.reject("Missing TikTok config");
            return;
        }
        // initializeSdk() is a silent no-op the second time (e.g. after the
        // WebView reloads), so answer here or JS would wait forever.
        if (TikTokBusinessSdk.isInitialized()) {
            call.resolve();
            return;
        }
        TikTokBusinessSdk.TTConfig config =
            new TikTokBusinessSdk.TTConfig(getContext().getApplicationContext(), accessToken)
                .setAppId(appId)
                .setTTAppId(ttAppId);
        // React's production bundle is also embedded in Android debug APKs, so
        // NODE_ENV cannot identify a native debug build. The package flag can.
        boolean isDebuggable =
            (getContext().getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
        if (isDebuggable || Boolean.TRUE.equals(call.getBoolean("debug", false))) {
            config.openDebugMode();
            config.setLogLevel(TikTokBusinessSdk.LogLevel.DEBUG);
        }
        TikTokBusinessSdk.initializeSdk(
            config,
            new TikTokBusinessSdk.TTInitCallback() {
                @Override
                public void success() {
                    call.resolve();
                }

                @Override
                public void fail(int code, String msg) {
                    call.reject(msg != null ? msg : "TikTok SDK init failed (" + code + ")");
                }
            }
        );
    }

    // The tracking prompt is iOS-only.
    @PluginMethod
    public void requestTracking(PluginCall call) {
        call.resolve();
    }

    @PluginMethod
    public void track(PluginCall call) {
        String name = call.getString("event");
        if (isEmpty(name)) {
            call.reject("Missing event name");
            return;
        }
        TTBaseEvent.Builder builder = TTBaseEvent.newBuilder(name);
        JSObject properties = call.getObject("properties", new JSObject());
        if (properties != null) {
            Iterator<String> keys = properties.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                Object value = properties.opt(key);
                if (value != null) {
                    builder.addProperty(key, value);
                }
            }
        }
        TikTokBusinessSdk.trackTTEvent(builder.build());
        call.resolve();
    }

    private static boolean isEmpty(String value) {
        return value == null || value.isEmpty();
    }
}
