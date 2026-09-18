import { updateServiceWorker } from "./sw-register";

describe("updateServiceWorker", () => {
  const originalServiceWorker = Object.getOwnPropertyDescriptor(
    navigator,
    "serviceWorker",
  );

  afterEach(() => {
    jest.restoreAllMocks();
    if (originalServiceWorker) {
      Object.defineProperty(navigator, "serviceWorker", originalServiceWorker);
    } else {
      delete navigator.serviceWorker;
    }
  });

  function setServiceWorker(value) {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value,
    });
  }

  test("updates the current registration instead of a retained registration", async () => {
    const update = jest.fn().mockResolvedValue(undefined);
    const getRegistration = jest.fn().mockResolvedValue({ update });
    setServiceWorker({ getRegistration });

    await updateServiceWorker();

    expect(getRegistration).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
  });

  test("does nothing when the browser no longer has a registration", async () => {
    const getRegistration = jest.fn().mockResolvedValue(undefined);
    setServiceWorker({ getRegistration });

    await expect(updateServiceWorker()).resolves.toBeUndefined();
    expect(getRegistration).toHaveBeenCalledTimes(1);
  });

  test("contains browser lifecycle failures instead of rejecting", async () => {
    const error = new DOMException("newestWorker is null", "InvalidStateError");
    const getRegistration = jest.fn().mockResolvedValue({
      update: jest.fn().mockRejectedValue(error),
    });
    const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
    setServiceWorker({ getRegistration });

    await expect(updateServiceWorker()).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalledWith("[Kindred] SW update skipped:", error);
  });
});
