/**
 * Native bridge — abstracts Capacitor native APIs with web fallbacks.
 * Safe to import anywhere: returns web behavior when not in a native app.
 */
import { Capacitor } from "@capacitor/core";

export const isNative = () => Capacitor.isNativePlatform();
export const getPlatform = () => Capacitor.getPlatform(); // 'ios' | 'android' | 'web'

/**
 * Camera — take photo or pick from gallery
 */
export const takePhoto = async () => {
  if (!isNative()) return null;
  const { Camera, CameraResultType, CameraSource } = await import("@capacitor/camera");
  const image = await Camera.getPhoto({
    quality: 80,
    allowEditing: false,
    resultType: CameraResultType.DataUrl,
    source: CameraSource.Prompt, // asks user: camera or gallery
    width: 1200,
  });
  return image.dataUrl || null;
};

/**
 * Push Notifications — register and listen
 */
export const registerPush = async (onToken, onNotification) => {
  if (!isNative()) return;
  const { PushNotifications } = await import("@capacitor/push-notifications");

  const permission = await PushNotifications.requestPermissions();
  if (permission.receive !== "granted") return;

  await PushNotifications.register();

  PushNotifications.addListener("registration", (token) => {
    onToken?.(token.value);
  });

  PushNotifications.addListener("pushNotificationReceived", (notification) => {
    onNotification?.(notification);
  });

  PushNotifications.addListener("pushNotificationActionPerformed", (action) => {
    const url = action.notification?.data?.url;
    if (url) window.location.href = url;
  });
};

/**
 * Haptics — light feedback on interactions
 */
export const hapticLight = async () => {
  if (!isNative()) return;
  const { Haptics, ImpactStyle } = await import("@capacitor/haptics");
  await Haptics.impact({ style: ImpactStyle.Light });
};

export const hapticMedium = async () => {
  if (!isNative()) return;
  const { Haptics, ImpactStyle } = await import("@capacitor/haptics");
  await Haptics.impact({ style: ImpactStyle.Medium });
};

export const hapticSuccess = async () => {
  if (!isNative()) return;
  const { Haptics, NotificationType } = await import("@capacitor/haptics");
  await Haptics.notification({ type: NotificationType.Success });
};

/**
 * Status Bar — style on native
 */
export const configureStatusBar = async () => {
  if (!isNative()) return;
  const { StatusBar, Style } = await import("@capacitor/status-bar");
  await StatusBar.setStyle({ style: Style.Dark });
  if (getPlatform() === "android") {
    await StatusBar.setBackgroundColor({ color: "#1a1a2e" });
  }
};

/**
 * App lifecycle — handle back button, URL open
 */
export const setupAppListeners = async (onBackButton, onUrlOpen) => {
  if (!isNative()) return;
  const { App } = await import("@capacitor/app");

  App.addListener("backButton", ({ canGoBack }) => {
    if (canGoBack) {
      window.history.back();
    } else {
      onBackButton?.();
    }
  });

  App.addListener("appUrlOpen", (data) => {
    onUrlOpen?.(data.url);
  });
};

/**
 * Keyboard — listen for show/hide on native
 */
export const setupKeyboardListeners = async (onShow, onHide) => {
  if (!isNative()) return;
  const { Keyboard } = await import("@capacitor/keyboard");
  Keyboard.addListener("keyboardWillShow", (info) => onShow?.(info.keyboardHeight));
  Keyboard.addListener("keyboardWillHide", () => onHide?.());
};
