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

  test("drops the minified form of Facebook's iOS performance bridge failure", () => {
    const event = {
      contexts: { browser: { name: "Facebook", version: "544.0.0" } },
      exception: {
        values: [
          {
            type: "TypeError",
            value:
              "undefined is not an object (evaluating 'window.webkit.messageHandlers')",
            stacktrace: {
              frames: [
                { filename: "https://heykindred.org/", function: "e" },
                { filename: "https://heykindred.org/", function: "?" },
              ],
            },
          },
        ],
      },
      request: {
        url: "https://heykindred.org/?fbclid=test&utm_source=fb",
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

  test("drops Facebook's alternate Android Java-exception bridge failure", () => {
    const event = {
      contexts: { browser: { name: "Facebook", version: "542.0.0" } },
      exception: {
        values: [
          {
            type: "Error",
            value:
              "Error invoking postMessage: Java exception was raised during method invocation",
            stacktrace: {
              frames: [
                {
                  filename: "app:///<anonymous>",
                  function: "window.__call_iabjs_unified_bridge",
                },
                { filename: "app:///<anonymous>", function: "Object.init" },
              ],
            },
          },
        ],
      },
      request: {
        url: "https://heykindred.org/?fbclid=test&utm_source=fb",
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

  test("keeps alternate Java-exception bridge failures with Kindred frames", () => {
    const appError = {
      contexts: { browser: { name: "Facebook" } },
      exception: {
        values: [
          {
            type: "Error",
            value:
              "Error invoking postMessage: Java exception was raised during method invocation",
            stacktrace: {
              frames: [
                { filename: "https://heykindred.org/static/js/main.js" },
              ],
            },
          },
        ],
      },
    };

    expect(filterInjectedBrowserNoise(appError)).toBe(appError);
  });

  test("drops Facebook's injected iOS performance bridge failures", () => {
    const event = {
      contexts: { browser: { name: "Facebook", version: "565.0.0" } },
      exception: {
        values: [
          {
            type: "TypeError",
            value:
              "undefined is not an object (evaluating 'window.webkit.messageHandlers')",
            stacktrace: {
              frames: [
                {
                  filename: "https://heykindred.org/",
                  function: "sendDataToNative",
                },
                {
                  filename: "https://heykindred.org/",
                  function: "processLargestContentfulPaintEvent",
                },
              ],
            },
          },
        ],
      },
      request: {
        url: "https://heykindred.org/?fbclid=test&utm_source=fb",
      },
    };

    expect(filterInjectedBrowserNoise(event)).toBeNull();
  });

  test("drops Facebook's injected TTRC DOM callback failure", () => {
    const event = {
      contexts: { browser: { name: "Facebook", version: "524.0.0" } },
      exception: {
        values: [
          {
            type: "TypeError",
            value: "TTRCCallbacks.onDomContentLoaded is not a function",
            stacktrace: {
              frames: [{ filename: "app:///<anonymous>" }],
            },
          },
        ],
      },
    };

    expect(filterInjectedBrowserNoise(event)).toBeNull();
  });

  test("drops Facebook's injected document parse failure below the real document", () => {
    const event = {
      contexts: { browser: { name: "Facebook", version: "543.0.0" } },
      exception: {
        values: [
          {
            type: "SyntaxError",
            value: "Unexpected end of input",
            stacktrace: {
              frames: [
                { filename: "https://heykindred.org/", lineno: 36 },
              ],
            },
          },
        ],
      },
      request: {
        url: "https://heykindred.org/?fbclid=test&utm_source=fb",
      },
    };

    expect(filterInjectedBrowserNoise(event)).toBeNull();
  });

  test("keeps lookalike runtime failures with Kindred application frames", () => {
    const appError = {
      contexts: { browser: { name: "Facebook" } },
      exception: {
        values: [
          {
            type: "TypeError",
            value:
              "undefined is not an object (evaluating 'window.webkit.messageHandlers')",
            stacktrace: {
              frames: [
                {
                  filename: "https://heykindred.org/static/js/main.js",
                  function: "sendDataToNative",
                },
                {
                  filename: "https://heykindred.org/static/js/main.js",
                  function: "processLargestContentfulPaintEvent",
                },
              ],
            },
          },
        ],
      },
    };

    expect(filterInjectedBrowserNoise(appError)).toBe(appError);
  });

  test("keeps a document bridge failure without a verified Meta landing request", () => {
    const unverifiedError = {
      contexts: { browser: { name: "Facebook" } },
      exception: {
        values: [
          {
            type: "TypeError",
            value:
              "undefined is not an object (evaluating 'window.webkit.messageHandlers')",
            stacktrace: {
              frames: [{ filename: "https://heykindred.org/", function: "e" }],
            },
          },
        ],
      },
      request: { url: "https://heykindred.org/" },
    };

    expect(filterInjectedBrowserNoise(unverifiedError)).toBe(unverifiedError);
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
