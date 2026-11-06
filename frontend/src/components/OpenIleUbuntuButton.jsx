import { useState } from "react";
import { Browser } from "@capacitor/browser";
import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import { apiRequest } from "@/lib/api";
import { isNative } from "@/lib/native-bridge";

// Opens the person's Ile Ubuntu account, already signed in, through the
// Ubuntu Markets one-time sign-in code. Kindred only starts the jump for an
// account whose email is verified (or Google/Apple); the server enforces it.

export const jumpMessage = (error) => {
  const detail = error?.response?.data?.detail;
  if (detail?.code === "email_not_verified") {
    return "Verify your email first. Check your inbox for the link from Kindred, then try again.";
  }
  if (typeof detail === "string") return detail;
  return detail?.message || "Couldn't open Ile Ubuntu right now.";
};

export const OpenIleUbuntuButton = ({ token, label = "Open Ile Ubuntu", size = "sm", variant = "outline" }) => {
  const [busy, setBusy] = useState(false);

  const open = async () => {
    const native = isNative();
    // On the web, open the tab now while the click still counts as a user
    // action, so browsers don't block it once the sign-in code comes back.
    // In the iOS/Android app, use the in-app browser instead.
    const tab = native ? null : window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    setBusy(true);
    try {
      const res = await apiRequest("/federation/jump", { method: "POST", token, data: { target: "ile_ubuntu" } });
      if (native) await Browser.open({ url: res.url });
      else if (tab) tab.location.href = res.url;
      else window.location.assign(res.url);
    } catch (error) {
      if (tab) tab.close();
      toast.error(jumpMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button disabled={busy || !token} onClick={open} size={size} type="button" variant={variant}>
      <ExternalLink aria-hidden="true" className="mr-2 h-4 w-4" />
      {label}
      <span className="sr-only"> (opens in a new tab)</span>
    </Button>
  );
};

export default OpenIleUbuntuButton;
