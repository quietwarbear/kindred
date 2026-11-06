import { useRef, useState } from "react";
import { FileText, Image as ImageIcon, Lock, Paperclip, Trash2 } from "lucide-react";

import { apiBlobRequest, apiRequest, convertFileToDataUrl } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const MATERIALS_WITHHELD_NOTICE = "Materials shared with registered attendees.";
export const MATERIAL_ACCEPT = "application/pdf,image/png,image/jpeg,image/gif,image/webp";
export const MAX_MATERIAL_BYTES = 5 * 1024 * 1024;

export const formatMaterialSize = (bytes) => {
  const size = Number(bytes) || 0;
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${Math.round(size / 1024)} KB`;
  return `${size} B`;
};

/** Member view downloads by event; guests download with their invitation token. */
export const materialDownloadPath = (material, eventId) => (
  eventId ? `/events/${eventId}/materials/${material.id}` : `/public/rsvp/materials/${material.id}`
);

const materialError = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  return fallback;
};

/**
 * Fetch a file with the viewer's bearer token and hand it to the browser as a
 * download. Files are never linked by URL, so the token never lands in a URL,
 * a log, or browser history.
 */
export const downloadMaterial = async (material, { eventId, token }) => {
  const blob = await apiBlobRequest(materialDownloadPath(material, eventId), { token });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = material.name || "material";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
};

/**
 * An activity's supply list and files. The server decides who receives them;
 * this component only renders what it was sent. Organizers (``canManage``) can
 * attach and remove files.
 */
export const ActivityMaterials = ({ activity, eventId = "", token = "", canManage = false, onUpdate, className = "" }) => {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState("");
  const materials = activity?.materials || [];
  const supplyList = activity?.supply_list || "";

  if (activity?.materials_withheld && !canManage) {
    return (
      <p className={`flex items-center gap-2 text-sm text-muted-foreground ${className}`} data-testid={`activity-materials-withheld-${activity.id}`}>
        <Lock aria-hidden="true" className="h-4 w-4 shrink-0" />
        {activity.materials_notice || MATERIALS_WITHHELD_NOTICE}
      </p>
    );
  }
  if (!supplyList && !materials.length && !canManage) return null;

  const download = async (material) => {
    setBusy(material.id);
    try {
      await downloadMaterial(material, { eventId, token });
    } catch (error) {
      toast.error("That file isn’t available to you.");
    } finally {
      setBusy("");
    }
  };

  const upload = async (changeEvent) => {
    const file = changeEvent.target.files?.[0];
    changeEvent.target.value = "";
    if (!file) return;
    if (file.size > MAX_MATERIAL_BYTES) {
      toast.error("Files can be up to 5 MB.");
      return;
    }
    setBusy("upload");
    try {
      const payload = await apiRequest(`/events/${eventId}/agenda/${activity.id}/materials`, {
        method: "POST",
        token,
        timeout: 60000,
        data: { name: file.name, data_url: await convertFileToDataUrl(file) },
      });
      onUpdate?.(payload);
      toast.success("File attached.");
    } catch (error) {
      toast.error(materialError(error, "Unable to attach that file."));
    } finally {
      setBusy("");
    }
  };

  const remove = async (material) => {
    setBusy(material.id);
    try {
      const payload = await apiRequest(`/events/${eventId}/agenda/${activity.id}/materials/${material.id}`, {
        method: "DELETE",
        token,
      });
      onUpdate?.(payload);
      toast.success("File removed.");
    } catch (error) {
      toast.error(materialError(error, "Unable to remove that file."));
    } finally {
      setBusy("");
    }
  };

  return (
    <section aria-label={`Materials for ${activity.title || "this activity"}`} className={`rounded-xl border border-border/70 p-3 text-sm ${className}`} data-testid={`activity-materials-${activity.id}`}>
      {supplyList ? (
        <div>
          <p className="font-semibold">What to bring</p>
          <p className="mt-1 whitespace-pre-line text-muted-foreground" data-testid={`activity-supply-list-${activity.id}`}>{supplyList}</p>
        </div>
      ) : null}
      {materials.length ? (
        <ul className={supplyList ? "mt-3 space-y-1" : "space-y-1"}>
          {materials.map((material) => {
            const Icon = material.mime_type === "application/pdf" ? FileText : ImageIcon;
            return (
              <li className="flex flex-wrap items-center gap-2" key={material.id}>
                <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
                <button
                  className="font-semibold underline disabled:opacity-60"
                  data-testid={`activity-material-download-${material.id}`}
                  disabled={busy === material.id}
                  onClick={() => download(material)}
                  type="button"
                >
                  {material.name}
                </button>
                <span className="text-xs text-muted-foreground">{formatMaterialSize(material.size)}</span>
                {canManage ? (
                  <button
                    aria-label={`Remove ${material.name}`}
                    className="ml-auto rounded p-1 text-muted-foreground hover:text-destructive disabled:opacity-60"
                    data-testid={`activity-material-remove-${material.id}`}
                    disabled={busy === material.id}
                    onClick={() => remove(material)}
                    type="button"
                  >
                    <Trash2 aria-hidden="true" className="h-4 w-4" />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      {canManage ? (
        <div className={supplyList || materials.length ? "mt-3" : ""}>
          <input
            accept={MATERIAL_ACCEPT}
            aria-label={`Attach a file to ${activity.title || "this activity"}`}
            className="sr-only"
            data-testid={`activity-material-input-${activity.id}`}
            onChange={upload}
            ref={inputRef}
            type="file"
          />
          <button
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-60"
            disabled={busy === "upload"}
            onClick={() => inputRef.current?.click()}
            type="button"
          >
            <Paperclip aria-hidden="true" className="h-3.5 w-3.5" />
            {busy === "upload" ? "Attaching…" : "Attach PDF or image"}
          </button>
          <p className="mt-1 text-xs text-muted-foreground">Up to 5 MB. Only people coming to this activity can open it.</p>
        </div>
      ) : null}
    </section>
  );
};
