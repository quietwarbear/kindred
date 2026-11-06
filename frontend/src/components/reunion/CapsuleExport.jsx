import { useState } from "react";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import { apiBlobRequest, errorDetail } from "@/lib/api";

export const capsuleExportPath = (eventId) => `/events/${eventId}/memory-capsule/export`;

export const capsuleExportFilename = (title, now = new Date()) => {
  const slug = String(title || "")
    .normalize("NFKD")
    .replace(/[^\x00-\x7F]/g, "")
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase()
    .slice(0, 60);
  return `memory-capsule-${slug || "event"}-${now.toISOString().slice(0, 10)}.zip`;
};

const saveBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
};

// Organizer-only: a ZIP of every published story, photo and voice note shared
// to this event. The server enforces the role; this only hides the control.
export const CapsuleExport = ({ eventId, title, token }) => {
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    try {
      const blob = await apiBlobRequest(capsuleExportPath(eventId), { token, timeout: 180000 });
      saveBlob(blob, capsuleExportFilename(title));
      toast.success("Memory capsule downloaded.");
    } catch (error) {
      const status = error?.response?.status;
      toast.error(
        status === 413
          ? "This capsule is too large to download in one file. Contact support for a full export."
          : errorDetail(error, "Unable to download the memory capsule.")
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <Button aria-busy={busy} disabled={busy} onClick={download} variant="outline">
        <Download aria-hidden="true" className="mr-2 h-4 w-4" />
        {busy ? "Preparing download…" : "Download everything (ZIP)"}
      </Button>
      <p className="text-sm text-muted-foreground">
        Stories, photos and voice notes as a ZIP. Unpublished drafts are not included.
      </p>
    </div>
  );
};

export default CapsuleExport;
