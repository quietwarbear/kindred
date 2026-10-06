const loadModule = ({ native, platform, env = {} }) => {
  jest.resetModules();
  const saved = { ...process.env };
  Object.assign(process.env, env);
  const start = jest.fn().mockResolvedValue(undefined);
  const track = jest.fn().mockResolvedValue(undefined);
  const requestTracking = jest.fn().mockResolvedValue({ status: 3 });
  const registerPlugin = jest.fn(() => ({ start, track, requestTracking }));
  jest.doMock("@capacitor/core", () => ({
    Capacitor: {
      isNativePlatform: () => native,
      getPlatform: () => platform,
    },
    registerPlugin,
  }));
  const lib = require("./tiktokEvents");
  process.env = saved;
  return { lib, start, track, requestTracking, registerPlugin };
};

describe("TikTok App Events", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("does nothing on the web, even with a secret present", async () => {
    const { lib, registerPlugin } = loadModule({
      native: false,
      platform: "web",
      env: { REACT_APP_TIKTOK_APP_SECRET_IOS: "s" },
    });
    expect(await lib.initTikTokEvents()).toBe(false);
    expect(await lib.trackTikTokEvent("Subscribe")).toBe(false);
    expect(registerPlugin).not.toHaveBeenCalled();
  });

  it("does nothing in a native build without a secret", async () => {
    const { lib, registerPlugin } = loadModule({ native: true, platform: "android" });
    expect(lib.tiktokEventsEnabled()).toBe(false);
    expect(await lib.initTikTokEvents()).toBe(false);
    expect(await lib.trackTikTokEvent("Subscribe")).toBe(false);
    expect(registerPlugin).not.toHaveBeenCalled();
  });

  it("starts with the Android app ids and sends events", async () => {
    const { lib, start, track, requestTracking } = loadModule({
      native: true,
      platform: "android",
      env: { REACT_APP_TIKTOK_APP_SECRET_ANDROID: "android-secret" },
    });
    expect(await lib.initTikTokEvents()).toBe(true);
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({
        accessToken: "android-secret",
        appId: "com.ubuntumarket.kindred",
        ttAppId: "7692523677824401429",
      })
    );
    expect(await lib.trackTikTokEvent("Subscribe", { value: 4.99 })).toBe(true);
    expect(track).toHaveBeenCalledWith({ event: "Subscribe", properties: { value: 4.99 } });
    expect(requestTracking).not.toHaveBeenCalled();
  });

  it("asks for tracking permission on iOS only after the SDK has started", async () => {
    jest.useFakeTimers();
    const { lib, start, requestTracking } = loadModule({
      native: true,
      platform: "ios",
      env: { REACT_APP_TIKTOK_APP_SECRET_IOS: "ios-secret" },
    });
    expect(await lib.initTikTokEvents()).toBe(true);
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({ appId: "6760608478", ttAppId: "7692520905070706689" })
    );
    expect(requestTracking).not.toHaveBeenCalled();
    jest.advanceTimersByTime(1500);
    expect(requestTracking).toHaveBeenCalledTimes(1);
  });

  it("never throws when the native call fails", async () => {
    const { lib, start } = loadModule({
      native: true,
      platform: "android",
      env: { REACT_APP_TIKTOK_APP_SECRET_ANDROID: "s" },
    });
    start.mockRejectedValueOnce(new Error("boom"));
    const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
    expect(await lib.initTikTokEvents()).toBe(false);
    expect(await lib.trackTikTokEvent("Subscribe")).toBe(false);
    warn.mockRestore();
  });
});
