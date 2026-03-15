import { useCallback, useEffect, useState } from "react";
import { CircleUserRound, DatabaseZap, LockKeyhole, RefreshCcw, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest, convertFileToDataUrl } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialConfig = {
  base_url: "",
  auth_type: "api-key",
  sync_members: true,
  sync_stories: true,
  sync_events: true,
  sync_relationships: true,
};

export const SettingsPage = ({ token, user, onSessionRefresh }) => {
  const [statusData, setStatusData] = useState(null);
  const [profileForm, setProfileForm] = useState({
    full_name: user?.full_name || "",
    nickname: user?.nickname || "",
    phone_number: user?.phone_number || "",
    profile_image_url: user?.profile_image_url || "",
  });
  const [profileUpload, setProfileUpload] = useState(null);
  const [configForm, setConfigForm] = useState(initialConfig);
  const [isSaving, setIsSaving] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isSavingProfile, setIsSavingProfile] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const [legacyPayload, mePayload] = await Promise.all([
        apiRequest("/legacy-table/status", { token }),
        apiRequest("/auth/me", { token }),
      ]);
      const profileUser = mePayload.user;
      setStatusData(legacyPayload);
      setConfigForm({
        base_url: legacyPayload.base_url || "",
        auth_type: legacyPayload.auth_type || "api-key",
        sync_members: legacyPayload.sync_preferences?.members ?? true,
        sync_stories: legacyPayload.sync_preferences?.stories ?? true,
        sync_events: legacyPayload.sync_preferences?.events ?? true,
        sync_relationships: legacyPayload.sync_preferences?.relationships ?? true,
      });
      setProfileForm({
        full_name: profileUser.full_name || "",
        nickname: profileUser.nickname || "",
        phone_number: profileUser.phone_number || "",
        profile_image_url: profileUser.profile_image_url || profileUser.google_picture || "",
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

  const handleProfileSave = async (event) => {
    event.preventDefault();
    setIsSavingProfile(true);
    try {
      const uploadedImage = profileUpload ? await convertFileToDataUrl(profileUpload) : profileForm.profile_image_url;
      await apiRequest("/auth/profile", {
        method: "PUT",
        token,
        data: { ...profileForm, profile_image_url: uploadedImage || "" },
      });
      await onSessionRefresh?.();
      toast.success("Profile updated.");
      setProfileUpload(null);
      loadStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update profile.");
    } finally {
      setIsSavingProfile(false);
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
        <article className="archival-card" data-testid="settings-profile-card">
          <div className="flex items-center gap-3">
            <CircleUserRound className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Profile</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Member profile</h3>
            </div>
          </div>
          <form className="mt-6 grid gap-4" onSubmit={handleProfileSave}>
            <div className="flex items-center gap-4">
              {profileForm.profile_image_url ? (
                <img alt="Profile" className="h-20 w-20 rounded-full object-cover object-center" data-testid="settings-profile-image" src={profileForm.profile_image_url} />
              ) : (
                <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 text-lg font-semibold text-primary" data-testid="settings-profile-avatar-fallback">
                  {(profileForm.full_name || user?.full_name || "K").slice(0, 1)}
                </div>
              )}
              <label className="flex-1">
                <span className="field-label">Profile photo / avatar</span>
                <Input className="field-input pt-3" data-testid="settings-profile-image-input" onChange={(e) => setProfileUpload(e.target.files?.[0] || null)} type="file" accept="image/*" />
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className="field-label">Full name</span>
                <Input className="field-input" data-testid="settings-profile-full-name-input" onChange={(e) => setProfileForm((current) => ({ ...current, full_name: e.target.value }))} value={profileForm.full_name} />
              </label>
              <label>
                <span className="field-label">Nickname</span>
                <Input className="field-input" data-testid="settings-profile-nickname-input" onChange={(e) => setProfileForm((current) => ({ ...current, nickname: e.target.value }))} value={profileForm.nickname} />
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className="field-label">Email address</span>
                <Input className="field-input" data-testid="settings-profile-email-input" disabled value={user?.email || ""} />
              </label>
              <label>
                <span className="field-label">Phone number</span>
                <Input className="field-input" data-testid="settings-profile-phone-input" onChange={(e) => setProfileForm((current) => ({ ...current, phone_number: e.target.value }))} value={profileForm.phone_number} />
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className="field-label">Member type</span>
                <Input className="field-input" data-testid="settings-profile-role-input" disabled value={user?.role || ""} />
              </label>
              <label>
                <span className="field-label">Google profile photo</span>
                <Input className="field-input" data-testid="settings-profile-google-photo-input" disabled value={user?.google_picture || "Not connected"} />
              </label>
            </div>
            <Button className="rounded-full" data-testid="settings-profile-save-button" disabled={isSavingProfile} type="submit">
              {isSavingProfile ? "Saving..." : "Save profile"}
            </Button>
          </form>
        </article>

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