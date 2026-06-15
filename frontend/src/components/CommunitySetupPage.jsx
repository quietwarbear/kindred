import { useCallback, useEffect, useState } from "react";
import { Check, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

// Community Operating System — module configuration. A steward shapes which modules
// this community runs; the sidebar respects it. Seeded by community type on the backend.
export const CommunitySetupPage = ({ token, user }) => {
  const [catalog, setCatalog] = useState([]);
  const [enabled, setEnabled] = useState([]);
  const [communityType, setCommunityType] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const canEdit = user?.role === "host" || user?.role === "organizer";

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const payload = await apiRequest("/community/modules", { token });
      setCatalog(payload.catalog || []);
      setEnabled(payload.enabled || []);
      setCommunityType(payload.community_type || "");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load community setup.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const toggle = (key) => {
    setEnabled((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = await apiRequest("/community/modules", { method: "PUT", token, data: { modules: enabled } });
      setEnabled(payload.enabled || []);
      toast.success("Community shape saved. The sidebar now reflects it.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't save. Stewards only.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="community-setup-page">
      <section className="archival-card">
        <div className="flex items-start gap-3">
          <Settings2 className="mt-1 h-5 w-5 text-primary" />
          <div>
            <p className="eyebrow-text">Community setup</p>
            <h2 className="mt-1 font-display text-3xl text-foreground" data-testid="setup-title">Shape your community</h2>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">
              Turn on the modules your {communityType || "community"} actually needs — gather, remember, care, contribute.
              What you enable here is what shows in the sidebar. We started you with a shape tuned to your type.
            </p>
          </div>
        </div>
      </section>

      {isLoading ? (
        <section className="archival-card" data-testid="setup-loading">
          <p className="text-sm text-muted-foreground">Loading your community's shape…</p>
        </section>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2">
            {catalog.map((mod) => {
              const on = enabled.includes(mod.key);
              return (
                <button
                  key={mod.key}
                  type="button"
                  disabled={!canEdit}
                  onClick={() => canEdit && toggle(mod.key)}
                  data-testid={`setup-module-${mod.key}`}
                  className={`archival-card text-left transition ${on ? "border-primary/40 bg-primary/5" : "opacity-70"} ${canEdit ? "hover:border-primary/30" : "cursor-default"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-foreground">{mod.label}</p>
                    <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full ${on ? "bg-primary text-primary-foreground" : "border border-border text-transparent"}`}>
                      <Check className="h-3.5 w-3.5" />
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{mod.blurb}</p>
                </button>
              );
            })}
          </section>

          {canEdit ? (
            <div className="flex items-center gap-3">
              <Button className="rounded-full" data-testid="setup-save" disabled={saving} onClick={save}>
                {saving ? "Saving…" : "Save community shape"}
              </Button>
              <p className="text-xs text-muted-foreground">{enabled.length} of {catalog.length} modules on. Home, Activity, Courtyards, Members & Settings are always on.</p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground" data-testid="setup-readonly">Only a host or organizer can change the community's shape.</p>
          )}
        </>
      )}
    </div>
  );
};

export default CommunitySetupPage;
