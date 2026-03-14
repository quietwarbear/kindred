import { useCallback, useEffect, useState } from "react";
import { DatabaseZap, LockKeyhole, RefreshCcw, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialConfig = {
  base_url: "",
  auth_type: "api-key",
  sync_members: true,
  sync_stories: true,
  sync_events: true,
  sync_relationships: true,
};

export const SettingsPage = ({ token, user }) => {
  const [statusData, setStatusData] = useState(null);
  const [configForm, setConfigForm] = useState(initialConfig);
  const [isSaving, setIsSaving] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const payload = await apiRequest("/legacy-table/status", { token });
      setStatusData(payload);
      setConfigForm({
        base_url: payload.base_url || "",
        auth_type: payload.auth_type || "api-key",
        sync_members: payload.sync_preferences?.members ?? true,
        sync_stories: payload.sync_preferences?.stories ?? true,
        sync_events: payload.sync_preferences?.events ?? true,
        sync_relationships: payload.sync_preferences?.relationships ?? true,
      });
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load settings.");
    }
  }, [token]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleSave = async (event) => {
    event.preventDefault();
    setIsSaving(true);
    try {
      const payload = await apiRequest("/legacy-table/config", { method: "POST", token, data: configForm });
      setStatusData(payload);
      toast.success("Legacy Table configuration saved.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to save Legacy Table settings.");
    } finally {
      setIsSaving(false);
    }
  };

  const handlePreview = async () => {
    setIsPreviewing(true);
    try {
      const payload = await apiRequest("/legacy-table/sync-preview", { method: "POST", token });
      setStatusData(payload);
      toast.success("Sync preview generated.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to generate sync preview.");
    } finally {
      setIsPreviewing(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Settings / Legacy Table Connect</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="settings-page-title">
          Connection-ready settings for privacy, sync, and long-term kinship infrastructure.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="settings-page-copy">
          The live Legacy Table sync layer is architected now. You can save the connection profile, preview what would sync, and keep the platform independent until credentials are provided.
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <article className="archival-card" data-testid="settings-legacy-status-card">
          <div className="flex items-center gap-3">
            <DatabaseZap className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Legacy Table Connect</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Connection status</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            <div className="soft-panel" data-testid="settings-legacy-status-panel">
              <p className="text-sm text-muted-foreground">Status</p>
              <p className="mt-2 text-xl font-semibold text-foreground">{statusData?.connection_status || "connection-ready"}</p>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">{statusData?.message}</p>
            </div>
            <div className="soft-panel" data-testid="settings-legacy-capabilities-panel">
              <p className="text-sm text-muted-foreground">Capabilities</p>
              <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                {(statusData?.capabilities || []).map((capability) => (
                  <li key={capability}>• {capability}</li>
                ))}
              </ul>
            </div>
            {statusData?.preview_counts ? (
              <div className="soft-panel" data-testid="settings-legacy-preview-panel">
                <p className="text-sm text-muted-foreground">Preview counts</p>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-muted-foreground">
                  {Object.entries(statusData.preview_counts).map(([key, value]) => (
                    <div key={key}>
                      <p className="capitalize">{key}</p>
                      <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </article>

        <article className="archival-card" data-testid="settings-legacy-config-card">
          <div className="flex items-center gap-3">
            <Settings2 className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Connection profile</h3>
          </div>
          <form className="mt-6 grid gap-4" onSubmit={handleSave}>
            <label>
              <span className="field-label">Legacy Table base URL</span>
              <Input className="field-input" data-testid="settings-legacy-base-url-input" onChange={(e) => setConfigForm((current) => ({ ...current, base_url: e.target.value }))} placeholder="https://api.legacytable.example" value={configForm.base_url} />
            </label>
            <label>
              <span className="field-label">Auth type</span>
              <select className="field-input w-full" data-testid="settings-legacy-auth-type-select" onChange={(e) => setConfigForm((current) => ({ ...current, auth_type: e.target.value }))} value={configForm.auth_type}>
                <option value="api-key">API key</option>
                <option value="oauth">OAuth</option>
                <option value="bearer">Bearer token</option>
                <option value="none">None</option>
              </select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ["sync_members", "Sync members"],
                ["sync_stories", "Sync stories"],
                ["sync_events", "Sync gatherings"],
                ["sync_relationships", "Sync kinship graph"],
              ].map(([key, label]) => (
                <label className="soft-panel flex items-center justify-between gap-3" data-testid={`settings-toggle-${key}`} key={key}>
                  <span className="text-sm font-semibold text-foreground">{label}</span>
                  <input
                    checked={Boolean(configForm[key])}
                    data-testid={`settings-checkbox-${key}`}
                    onChange={(e) => setConfigForm((current) => ({ ...current, [key]: e.target.checked }))}
                    type="checkbox"
                  />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-3">
              <Button className="rounded-full" data-testid="settings-legacy-save-button" disabled={isSaving} type="submit">
                {isSaving ? "Saving..." : "Save connection profile"}
              </Button>
              <Button className="rounded-full" data-testid="settings-legacy-preview-button" disabled={isPreviewing} onClick={handlePreview} type="button" variant="secondary">
                <RefreshCcw className="mr-2 h-4 w-4" />
                {isPreviewing ? "Generating..." : "Run sync preview"}
              </Button>
            </div>
          </form>
        </article>
      </section>

      <section className="archival-card" data-testid="settings-privacy-card">
        <div className="flex items-center gap-3">
          <LockKeyhole className="h-5 w-5 text-primary" />
          <div>
            <p className="eyebrow-text">Privacy posture</p>
            <h3 className="mt-2 font-display text-3xl text-foreground">Keep the app independent</h3>
          </div>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted-foreground" data-testid="settings-privacy-copy">
          Live external syncing stays optional. Your courtyard data, timelines, relationship graph, and financial coordination remain first-class inside this platform whether or not Legacy Table is connected.
        </p>
        <p className="mt-3 text-sm text-muted-foreground" data-testid="settings-current-user-role">
          Current role: {user?.role}
        </p>
      </section>
    </div>
  );
};