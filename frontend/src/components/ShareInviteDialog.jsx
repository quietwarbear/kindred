import { useState } from "react";
import { Check, Copy, Link2, Hash, Share2, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const INVITE_BASE_URL = "https://kindred.ubuntumarket.com/invite/";

export const ShareInviteDialog = ({ inviteCode, contextLabel, onClose }) => {
  const [mode, setMode] = useState("link"); // "link" | "code"
  const [copied, setCopied] = useState(false);

  const inviteLink = `${INVITE_BASE_URL}${inviteCode}`;
  const shareContent = mode === "link" ? inviteLink : inviteCode;
  const shareText =
    mode === "link"
      ? `Join me on heyKindred${contextLabel ? ` — ${contextLabel}` : ""}! ${inviteLink}`
      : `Join me on heyKindred${contextLabel ? ` — ${contextLabel}` : ""}! Use invite code: ${inviteCode}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(shareContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = shareContent;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: "Join me on heyKindred", text: shareText });
      } catch {
        // User cancelled or share failed — no-op
      }
    } else {
      handleCopy();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div
        className="relative w-full max-w-sm rounded-2xl border border-border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="absolute right-3 top-3 rounded-full p-1.5 text-muted-foreground hover:bg-muted/60"
          onClick={onClose}
          type="button"
        >
          <X className="h-4 w-4" />
        </button>

        <p className="eyebrow-text mb-1">Share invite</p>
        <h3 className="font-display text-2xl text-foreground">
          {contextLabel || "Community invite"}
        </h3>

        {/* Toggle */}
        <div className="mt-5 flex gap-2">
          <button
            className={`flex flex-1 items-center justify-center gap-2 rounded-full border px-4 py-2.5 text-sm font-semibold transition ${
              mode === "link"
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-muted/40"
            }`}
            onClick={() => { setMode("link"); setCopied(false); }}
            type="button"
          >
            <Link2 className="h-4 w-4" />
            Link
          </button>
          <button
            className={`flex flex-1 items-center justify-center gap-2 rounded-full border px-4 py-2.5 text-sm font-semibold transition ${
              mode === "code"
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-muted/40"
            }`}
            onClick={() => { setMode("code"); setCopied(false); }}
            type="button"
          >
            <Hash className="h-4 w-4" />
            Code
          </button>
        </div>

        {/* Display */}
        <div className="mt-4 rounded-xl border border-border bg-muted/30 px-4 py-3 text-center">
          <p className={`font-mono ${mode === "code" ? "text-2xl font-bold tracking-[0.2em]" : "text-sm break-all"} text-foreground`}>
            {shareContent}
          </p>
        </div>

        {/* Actions */}
        <div className="mt-5 flex gap-3">
          <Button
            className="flex-1 gap-2 rounded-full"
            onClick={handleCopy}
            variant="outline"
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? "Copied!" : "Copy"}
          </Button>
          <Button
            className="flex-1 gap-2 rounded-full"
            onClick={handleShare}
            variant="default"
          >
            <Share2 className="h-4 w-4" />
            Share
          </Button>
        </div>
      </div>
    </div>
  );
};
