import { filterInjectedBrowserNoise } from "./sentry";

jest.mock("@sentry/capacitor", () => ({ init: jest.fn() }));
jest.mock("@sentry/react", () => ({ init: jest.fn() }));

describe("filterInjectedBrowserNoise", () => {
  test("drops errors raised by Meta's injected iabjs script", () => {
    const event = {
      exception: {
        values: [
          {
            type: "SyntaxError",
            value: "Invalid regular expression: missing /",
            stacktrace: {
              frames: [
                { filename: "app:///iabjs://iab_inner_frame_ota" },
              ],
            },
          },
        ],
      },
    };

    expect(filterInjectedBrowserNoise(event)).toBeNull();
  });

  test("drops Facebook's injected Android Java-bridge failure", () => {
    const event = {
      contexts: { browser: { name: "Facebook", version: "534.0.0" } },
      exception: {
        values: [
          {
            type: "Error",
            value:
              "Error invoking postMessage: Java bridge method invocation error",
            stacktrace: {
              frames: [
                { filename: "app:///<anonymous>" },
                { filename: "app:///<anonymous>" },
              ],
            },
          },
        ],
      },
      request: {
        headers: {
          "User-Agent": "Mozilla/5.0 [FB_IAB/FB4A;FBAV/534.0.0.56.76;]",
        },
      },
    };

    expect(filterInjectedBrowserNoise(event)).toBeNull();
  });

  test("keeps Java-bridge failures outside Facebook's anonymous injected script", () => {
    const nativeAppError = {
      contexts: { browser: { name: "Chrome" } },
      exception: {
        values: [
          {
            type: "Error",
            value:
              "Error invoking postMessage: Java bridge method invocation error",
            stacktrace: {
              frames: [{ filename: "app:///static/js/main.js" }],
            },
          },
        ],
      },
    };

    expect(filterInjectedBrowserNoise(nativeAppError)).toBe(nativeAppError);
  });

  test("drops Honor Browser's injected ad-loader timeout rejection", () => {
    const event = {
      exception: {
        values: [
          {
            type: "UnhandledRejection",
            value:
              "Object captured as promise rejection with keys: code, message",
          },
        ],
      },
      extra: {
        __serialized__: {
          code: 30013,
          message:
            "The ad loading process exceeded the timeout period set by the developer.",
        },
      },
    };

    expect(filterInjectedBrowserNoise(event)).toBeNull();
  });

  test("keeps genuine application errors and unrelated promise rejections", () => {
    const appError = {
      exception: {
        values: [
          {
            type: "TypeError",
            value: "Cannot read properties of undefined",
            stacktrace: {
              frames: [{ filename: "https://heykindred.org/static/js/main.js" }],
            },
          },
        ],
      },
    };
    const unrelatedRejection = {
      extra: {
        __serialized__: {
          code: 30013,
          message: "A Kindred operation failed",
        },
      },
    };

    expect(filterInjectedBrowserNoise(appError)).toBe(appError);
    expect(filterInjectedBrowserNoise(unrelatedRejection)).toBe(
      unrelatedRejection,
    );
  });
});
