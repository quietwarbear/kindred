import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CircleUserRound, Crown, DatabaseZap, FileText, LockKeyhole, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { requiresPasswordForAccountDeletion } from "@/lib/accountDeletion";
import { apiRequest, convertFileToDataUrl } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const SettingsPage = ({ token, user, onSessionRefresh }) => {
  const deleteRequiresPassword = requiresPasswordForAccountDeletion(user?.auth_provider);
  const [statusData, setStatusData] = useState(null);
  const [notificationHistory, setNotificationHistory] = useState([]);
  const [notificationPreferences, setNotificationPreferences] = useState({
    reminder_notifications: true,
    announcement_notifications: true,
    chat_notifications: true,
    invite_notifications: true,
    rsvp_notifications: true,
    muted_room_ids: [],
    muted_announcement_scopes: [],
  });
  const [chatRooms, setChatRooms] = useState([]);
  const [profileForm, setProfileForm] = useState({
    full_name: user?.full_name || "",
    nickname: user?.nickname || "",
    phone_number: user?.phone_number || "",
    profile_image_url: user?.profile_image_url || "",
  });
  const [profileUpload, setProfileUpload] = useState(null);
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isSavingNotifications, setIsSavingNotifications] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [communityMembers, setCommunityMembers] = useState([]);
  const [selectedTransferUserId, setSelectedTransferUserId] = useState("");
  const [showTransferConfirm, setShowTransferConfirm] = useState(false);
  const [isTransferring, setIsTransferring] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const [legacyPayload, mePayload, historyPayload, preferencePayload, chatPayload] = await Promise.all([
        apiRequest("/legacy-table/status", { token }),
        apiRequest("/auth/me", { token }),
        apiRequest("/notifications/history", { token }),
        apiRequest("/notifications/preferences", { token }),
        apiRequest("/chat/rooms", { token }),
      ]);
      const profileUser = mePayload.user;
      setStatusData(legacyPayload);
      setNotificationHistory(historyPayload.items || []);
      setNotificationPreferences({
        reminder_notifications: preferencePayload.reminder_notifications ?? true,
        announcement_notifications: preferencePayload.announcement_notifications ?? true,
        chat_notifications: preferencePayload.chat_notifications ?? true,
        invite_notifications: preferencePayload.invite_notifications ?? true,
        rsvp_notifications: preferencePayload.rsvp_notifications ?? true,
        muted_room_ids: preferencePayload.muted_room_ids || [],
        muted_announcement_scopes: preferencePayload.muted_announcement_scopes || [],
      });
      setChatRooms(chatPayload.rooms || []);
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

  const handleNotificationSave = async (event) => {
    event.preventDefault();
    setIsSavingNotifications(true);
    try {
      await apiRequest("/notifications/preferences", {
        method: "PUT",
        token,
        data: notificationPreferences,
      });
      toast.success("Notification preferences updated.");
      loadStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to save notification preferences.");
    } finally {
      setIsSavingNotifications(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

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

  const handleDeleteAccount = async () => {
    setIsDeleting(true);
    try {
      await apiRequest("/auth/account", {
        method: "DELETE",
        token,
        data: { password: deletePassword },
      });
      localStorage.removeItem("gathering-cypher-auth");
      window.location.href = "/login";
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to delete account.");
    } finally {
      setIsDeleting(false);
    }
  };

  const loadCommunityMembers = useCallback(async () => {
    try {
      const payload = await apiRequest("/community/members", { token });
      setCommunityMembers((payload.members || []).filter((m) => m.id !== user?.id));
    } catch { /* silent */ }
  }, [token, user?.id]);

  useEffect(() => {
    if (user?.role === "host") loadCommunityMembers();
  }, [user?.role, loadCommunityMembers]);

  const handleTransferOwnership = async () => {
    if (!selectedTransferUserId) return;
    setIsTransferring(true);
    try {
      const result = await apiRequest("/community/transfer-ownership", {
        method: "POST",
        token,
        data: { new_owner_user_id: selectedTransferUserId },
      });
      toast.success(`Ownership transferred to ${result.new_owner_name}.`);
      setShowTransferConfirm(false);
      setSelectedTransferUserId("");
      if (onSessionRefresh) onSessionRefresh();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to transfer ownership.");
    } finally {
      setIsTransferring(false);
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
          </div>
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
          Bulk external syncing is retired. A Legacy Table transfer begins only from an eligible recipe, requires explicit consent, and is limited to that selected content.
        </p>
        <p className="mt-3 text-sm text-muted-foreground" data-testid="settings-current-user-role">
          Current role: {user?.role}
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="archival-card" data-testid="settings-notification-preferences-card">
          <div className="flex items-center gap-3">
            <Settings2 className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Notification preferences</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Control what reaches you</h3>
            </div>
          </div>
          <form className="mt-6 grid gap-4" onSubmit={handleNotificationSave}>
            {[
              ["reminder_notifications", "Recurring invite reminders"],
              ["announcement_notifications", "Announcements"],
              ["chat_notifications", "Chat activity"],
              ["invite_notifications", "Invite updates"],
              ["rsvp_notifications", "RSVP updates"],
            ].map(([key, label]) => (
              <label className="soft-panel flex items-center justify-between gap-3" data-testid={`settings-notification-toggle-${key}`} key={key}>
                <span className="text-sm font-semibold text-foreground">{label}</span>
                <input
                  checked={Boolean(notificationPreferences[key])}
                  onChange={(e) => setNotificationPreferences((current) => ({ ...current, [key]: e.target.checked }))}
                  type="checkbox"
                />
              </label>
            ))}

            <div className="soft-panel" data-testid="settings-muted-announcement-scopes-panel">
              <p className="text-sm font-semibold text-foreground">Mute announcement scopes</p>
              <div className="mt-3 flex flex-wrap gap-3">
                {["courtyard", "subyard"].map((scope) => {
                  const isMuted = notificationPreferences.muted_announcement_scopes.includes(scope);
                  return (
                    <button
                      className={`rounded-full px-4 py-2 text-sm font-semibold ${isMuted ? "bg-primary text-primary-foreground" : "border border-border bg-background/80 text-foreground"}`}
                      data-testid={`settings-muted-scope-${scope}`}
                      key={scope}
                      onClick={() => setNotificationPreferences((current) => ({
                        ...current,
                        muted_announcement_scopes: isMuted
                          ? current.muted_announcement_scopes.filter((item) => item !== scope)
                          : [...current.muted_announcement_scopes, scope],
                      }))}
                      type="button"
                    >
                      {scope}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="soft-panel" data-testid="settings-muted-rooms-panel">
              <p className="text-sm font-semibold text-foreground">Mute specific chat rooms</p>
              <div className="mt-3 flex flex-wrap gap-3">
                {chatRooms.map((room) => {
                  const isMuted = notificationPreferences.muted_room_ids.includes(room.id);
                  return (
                    <button
                      className={`rounded-full px-4 py-2 text-sm font-semibold ${isMuted ? "bg-primary text-primary-foreground" : "border border-border bg-background/80 text-foreground"}`}
                      data-testid={`settings-muted-room-${room.id}`}
                      key={room.id}
                      onClick={() => setNotificationPreferences((current) => ({
                        ...current,
                        muted_room_ids: isMuted
                          ? current.muted_room_ids.filter((item) => item !== room.id)
                          : [...current.muted_room_ids, room.id],
                      }))}
                      type="button"
                    >
                      {room.name}
                    </button>
                  );
                })}
              </div>
            </div>

            <Button className="rounded-full" data-testid="settings-notification-save-button" disabled={isSavingNotifications} type="submit">
              {isSavingNotifications ? "Saving..." : "Save notification preferences"}
            </Button>
          </form>
        </article>

        <article className="archival-card" data-testid="settings-notification-history-card">
          <div className="flex items-center gap-3">
            <RefreshCcw className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Notification history</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">What happened recently</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {notificationHistory.length ? (
              notificationHistory.map((item) => (
                <div className={`soft-panel ${item.is_read ? "opacity-70" : ""}`} data-testid={`settings-notification-history-item-${item.id}`} key={item.id}>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex items-start gap-2">
                      {!item.is_read && <span className="mt-2 h-2 w-2 flex-shrink-0 rounded-full bg-primary" />}
                      <div>
                        <p className="text-base font-semibold text-foreground">{item.title}</p>
                        <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.description}</p>
                      </div>
                    </div>
                    <div className="text-right text-xs uppercase tracking-[0.16em] text-primary">
                      <p>{item.event_type}</p>
                      <p className="mt-1 text-muted-foreground">{item.actor_name}</p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="settings-notification-history-empty-state">
                <p className="text-sm text-muted-foreground">Notification history will appear here as your circle posts announcements, sends invites, updates RSVPs, and chats.</p>
              </div>
            )}
          </div>
        </article>
      </section>

      {user?.role === "host" && (
        <section className="archival-card" data-testid="settings-transfer-ownership-card">
          <div className="flex items-center gap-3">
            <Crown className="h-5 w-5 text-amber-500" />
            <div>
              <p className="eyebrow-text">Community ownership</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Transfer ownership</h3>
            </div>
          </div>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">
            Hand off your community to a trusted member. They will become the new host and you will be demoted to organizer. This is required before you can delete your account.
          </p>

          {communityMembers.length === 0 ? (
            <p className="mt-4 text-sm text-muted-foreground/70" data-testid="transfer-no-members">
              No other members to transfer to. Invite members first.
            </p>
          ) : !showTransferConfirm ? (
            <div className="mt-4 space-y-3">
              <label>
                <span className="field-label">Select new owner</span>
                <select
                  className="field-input mt-1 w-full rounded-xl border border-border/60 bg-background px-4 py-2.5 text-sm text-foreground"
                  data-testid="transfer-member-select"
                  onChange={(e) => setSelectedTransferUserId(e.target.value)}
                  value={selectedTransferUserId}
                >
                  <option value="">Choose a member...</option>
                  {communityMembers.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.full_name} ({m.email}) — {m.role}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                className="rounded-full"
                data-testid="transfer-initiate-button"
                disabled={!selectedTransferUserId}
                onClick={() => setShowTransferConfirm(true)}
                variant="default"
              >
                <Crown className="mr-2 h-4 w-4" /> Transfer ownership
              </Button>
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-amber-300/30 bg-amber-500/[0.03] p-5 space-y-4" data-testid="transfer-confirm-panel">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-500" />
                <div>
                  <p className="text-sm font-semibold text-foreground">Confirm ownership transfer</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    You are about to transfer ownership to <strong>{communityMembers.find((m) => m.id === selectedTransferUserId)?.full_name}</strong>. You will become an organizer and lose host privileges.
                  </p>
                </div>
              </div>
              <div className="flex gap-3">
                <Button
                  className="rounded-full"
                  data-testid="transfer-confirm-button"
                  disabled={isTransferring}
                  onClick={handleTransferOwnership}
                >
                  {isTransferring ? "Transferring..." : "Yes, transfer ownership"}
                </Button>
                <Button
                  className="rounded-full"
                  data-testid="transfer-cancel-button"
                  onClick={() => setShowTransferConfirm(false)}
                  variant="secondary"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </section>
      )}

      <section className="archival-card" data-testid="settings-legal-card">
        <div className="flex items-center gap-3">
          <FileText className="h-5 w-5 text-primary" />
          <div>
            <p className="eyebrow-text">Legal</p>
            <h3 className="mt-2 font-display text-3xl text-foreground">Privacy &amp; Terms</h3>
          </div>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted-foreground">
          Review our data practices and the terms that govern your use of Kindred.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link className="pill-button-secondary inline-flex items-center gap-2 rounded-full border border-border px-5 py-2.5 text-sm font-semibold text-foreground hover:bg-accent/70 transition-colors" data-testid="settings-privacy-link" to="/privacy">
            Privacy Policy
          </Link>
          <Link className="pill-button-secondary inline-flex items-center gap-2 rounded-full border border-border px-5 py-2.5 text-sm font-semibold text-foreground hover:bg-accent/70 transition-colors" data-testid="settings-terms-link" to="/terms">
            Terms of Service
          </Link>
        </div>
      </section>

      <section className="archival-card border-destructive/30" data-testid="settings-delete-account-card">
        <div className="flex items-center gap-3">
          <Trash2 className="h-5 w-5 text-destructive" />
          <div>
            <p className="eyebrow-text text-destructive/80">Danger zone</p>
            <h3 className="mt-2 font-display text-3xl text-foreground">Delete your account</h3>
          </div>
        </div>
        <p className="mt-4 text-sm leading-7 text-muted-foreground" data-testid="settings-delete-account-info">
          Remove your account and the first-party records handled by the deletion endpoint. Shared content, subscription records, provider records, logs, backups, or legally retained records may remain as described in the Privacy Policy. If you are the community owner, you must transfer ownership before deleting unless you are the only member.
        </p>

        {!showDeleteConfirm ? (
          <Button
            className="mt-4 rounded-full"
            data-testid="settings-delete-account-button"
            onClick={() => setShowDeleteConfirm(true)}
            variant="destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete my account
          </Button>
        ) : (
          <div className="mt-4 rounded-2xl border border-destructive/20 bg-destructive/[0.03] p-5 space-y-4" data-testid="settings-delete-confirm-panel">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-destructive" />
              <div>
                <p className="text-sm font-semibold text-foreground">Are you absolutely sure?</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  This will delete your profile, sessions, preferences, and vote references handled by the deletion endpoint. Some shared or externally processed records may remain as described in the Privacy Policy. {user?.role === "host" ? "As the community owner, your entire community will also be deleted if you are the only member." : ""}
                </p>
              </div>
            </div>

            {deleteRequiresPassword && (
              <label>
                <span className="field-label">Enter your password to confirm</span>
                <Input
                  className="field-input"
                  data-testid="settings-delete-password-input"
                  onChange={(e) => setDeletePassword(e.target.value)}
                  placeholder="Your current password"
                  type="password"
                  value={deletePassword}
                />
              </label>
            )}

            <div className="flex gap-3">
              <Button
                className="rounded-full"
                data-testid="settings-delete-confirm-button"
                disabled={isDeleting || (deleteRequiresPassword && !deletePassword)}
                onClick={handleDeleteAccount}
                variant="destructive"
              >
                {isDeleting ? "Deleting..." : "Permanently delete account"}
              </Button>
              <Button
                className="rounded-full"
                data-testid="settings-delete-cancel-button"
                onClick={() => { setShowDeleteConfirm(false); setDeletePassword(""); }}
                variant="secondary"
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};
