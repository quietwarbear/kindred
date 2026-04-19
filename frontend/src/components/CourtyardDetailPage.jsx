import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, BellRing, GitBranch, MessageSquare, Share2, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ShareInviteDialog } from "@/components/ShareInviteDialog";
import { apiRequest, formatDateTime, convertFileToDataUrl } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const CourtyardDetailPage = ({ token, user, onCommunicationsViewed }) => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "member" });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sharingInvite, setSharingInvite] = useState(null);

  // Announcements
  const [announcementForm, setAnnouncementForm] = useState({ title: "", body: "" });
  const [announcementFile, setAnnouncementFile] = useState(null);

  // Chat
  const [chatDraft, setChatDraft] = useState("");
  const [chatFile, setChatFile] = useState(null);
  const [chatCommentDrafts, setChatCommentDrafts] = useState({});

  const canManage = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);

  const loadData = useCallback(async () => {
    try {
      const payload = await apiRequest(`/subyards/${id}`, { token });
      setData(payload);
      onCommunicationsViewed?.();
    } catch {
      toast.error("Unable to load courtyard details.");
      navigate("/courtyards");
    } finally {
      setLoading(false);
    }
  }, [id, token, navigate, onCommunicationsViewed]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const subyard = data?.subyard;
  const members = data?.members || [];
  const invites = data?.invites || [];
  const announcements = data?.announcements || [];
  const chatRoom = data?.chat_room;
  const kinships = data?.kinships || [];

  // Invite handlers
  const handleCreateInvite = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await apiRequest("/invites", {
        method: "POST",
        token,
        data: { email: inviteForm.email, role: inviteForm.role },
      });
      setInviteForm({ email: "", role: "member" });
      await loadData();
      toast.success("Invite created.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create invite.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Announcement handlers
  const handleCreateAnnouncement = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      let attachment = null;
      if (announcementFile) {
        attachment = await convertFileToDataUrl(announcementFile);
      }
      await apiRequest("/announcements", {
        method: "POST",
        token,
        data: {
          title: announcementForm.title,
          body: announcementForm.body,
          scope: "subyard",
          subyard_id: id,
          attachment,
        },
      });
      setAnnouncementForm({ title: "", body: "" });
      setAnnouncementFile(null);
      await loadData();
      toast.success("Announcement posted.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create announcement.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Chat handlers
  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatRoom?.id || !chatDraft.trim()) return;
    try {
      let attachment = null;
      if (chatFile) {
        attachment = await convertFileToDataUrl(chatFile);
      }
      await apiRequest(`/chat/rooms/${chatRoom.id}/messages`, {
        method: "POST",
        token,
        data: { text: chatDraft.trim(), attachment },
      });
      setChatDraft("");
      setChatFile(null);
      await loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to send message.");
    }
  };

  const handleChatComment = async (messageId) => {
    if (!chatRoom?.id) return;
    try {
      await apiRequest(`/chat/rooms/${chatRoom.id}/messages/${messageId}/comments`, {
        method: "POST",
        token,
        data: { text: chatCommentDrafts[messageId] },
      });
      setChatCommentDrafts((c) => ({ ...c, [messageId]: "" }));
      await loadData();
      toast.success("Reply added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add reply.");
    }
  };

  if (loading) {
    return (
      <div className="app-canvas flex min-h-[50vh] items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading courtyard...</p>
      </div>
    );
  }

  if (!subyard) return null;

  const sortedMessages = [...(chatRoom?.messages || [])].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1;
    if (!a.is_pinned && b.is_pinned) return 1;
    return 0;
  });

  return (
    <div className="app-canvas space-y-8 px-4 py-6 sm:px-8 lg:px-12" data-testid="courtyard-detail-page">
      {/* Back nav */}
      <button
        className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition"
        data-testid="courtyard-detail-back"
        onClick={() => navigate("/courtyards")}
        type="button"
      >
        <ArrowLeft className="h-4 w-4" />
        All courtyards
      </button>

      {/* Hero */}
      <header className="archival-card relative overflow-hidden" data-testid="courtyard-detail-hero">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none" />
        <div className="relative">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              <GitBranch className="h-3 w-3" />
              Subyard
            </span>
            <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-muted-foreground">
              {subyard.visibility}
            </span>
          </div>
          <h1 className="mt-4 font-display text-4xl text-foreground sm:text-5xl" data-testid="courtyard-detail-title">
            {subyard.name}
          </h1>
          {subyard.description && (
            <p className="mt-4 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base">
              {subyard.description}
            </p>
          )}
          {subyard.role_focus?.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {subyard.role_focus.map((role) => (
                <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" key={role}>
                  {role}
                </span>
              ))}
            </div>
          )}
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="soft-panel">
              <p className="text-sm text-muted-foreground">Community members</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{members.length}</p>
            </div>
            <div className="soft-panel">
              <p className="text-sm text-muted-foreground">Announcements</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{announcements.length}</p>
            </div>
            <div className="soft-panel">
              <p className="text-sm text-muted-foreground">Messages</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{chatRoom?.messages?.length || 0}</p>
            </div>
          </div>
        </div>
      </header>

      {/* Content grid */}
      <section className="grid gap-6 lg:grid-cols-2" data-testid="courtyard-detail-panels">
        {/* Announcements */}
        <article className="archival-card" data-testid="courtyard-detail-announcements">
          <div className="flex items-center gap-3">
            <BellRing className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">Announcements</h2>
          </div>
          {canManage && (
            <form className="mt-4 space-y-3" onSubmit={handleCreateAnnouncement}>
              <Input
                className="field-input"
                onChange={(e) => setAnnouncementForm((c) => ({ ...c, title: e.target.value }))}
                placeholder="Announcement title"
                required
                value={announcementForm.title}
              />
              <Textarea
                className="field-textarea"
                onChange={(e) => setAnnouncementForm((c) => ({ ...c, body: e.target.value }))}
                placeholder="Share an update with the group..."
                required
                value={announcementForm.body}
              />
              <div className="flex items-center gap-3">
                <label className="text-sm text-muted-foreground cursor-pointer hover:text-primary transition">
                  Attach file
                  <input className="hidden" onChange={(e) => setAnnouncementFile(e.target.files?.[0])} type="file" />
                </label>
                {announcementFile && <span className="text-xs text-muted-foreground">{announcementFile.name}</span>}
              </div>
              <Button className="rounded-full" disabled={isSubmitting} type="submit">
                Post announcement
              </Button>
            </form>
          )}
          <div className="mt-4 space-y-3">
            {announcements.length ? (
              announcements.map((ann) => (
                <div className="soft-panel" key={ann.id}>
                  <p className="text-base font-semibold text-foreground">{ann.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {ann.created_by_name} · {ann.scope}{ann.subyard_name ? ` / ${ann.subyard_name}` : ""} · {formatDateTime(ann.created_at)}
                  </p>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{ann.body}</p>
                  {ann.attachments?.map((att, i) =>
                    att.content_type?.startsWith("image/") ? (
                      <img alt="attachment" className="mt-3 max-h-48 rounded-xl object-cover" key={i} src={att.data_url} />
                    ) : (
                      <a className="mt-3 block text-sm text-primary underline" href={att.data_url} key={i} target="_blank" rel="noreferrer">
                        {att.filename}
                      </a>
                    )
                  )}
                  {ann.comments?.length > 0 && (
                    <div className="mt-3 space-y-2 border-l-2 border-border pl-3">
                      {ann.comments.map((comment) => (
                        <div key={comment.id}>
                          <p className="text-xs font-semibold text-foreground">{comment.author_name}</p>
                          <p className="text-sm text-muted-foreground">{comment.text}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No announcements yet.</p>
            )}
          </div>
        </article>

        {/* Chat room */}
        <article className="archival-card" data-testid="courtyard-detail-chat">
          <div className="flex items-center gap-3">
            <MessageSquare className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">
              {chatRoom?.name || "Chat"}
            </h2>
          </div>
          {chatRoom ? (
            <>
              <form className="mt-4 space-y-3" onSubmit={handleSendChat}>
                <Textarea
                  className="field-textarea"
                  onChange={(e) => setChatDraft(e.target.value)}
                  placeholder="Write a message..."
                  value={chatDraft}
                />
                <div className="flex items-center gap-3">
                  <label className="text-sm text-muted-foreground cursor-pointer hover:text-primary transition">
                    Attach file
                    <input className="hidden" onChange={(e) => setChatFile(e.target.files?.[0])} type="file" />
                  </label>
                  {chatFile && <span className="text-xs text-muted-foreground">{chatFile.name}</span>}
                  <Button className="ml-auto rounded-full" disabled={!chatDraft.trim()} type="submit" size="sm">
                    Send
                  </Button>
                </div>
              </form>
              <div className="mt-4 space-y-3 max-h-[500px] overflow-y-auto">
                {sortedMessages.map((msg) => (
                  <div className={`rounded-2xl border px-4 py-3 ${msg.is_pinned ? "border-primary/30 bg-primary/5" : "border-border/70 bg-background/70"}`} key={msg.id}>
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-foreground">{msg.author_name}</p>
                      {msg.is_pinned && <span className="text-xs text-primary font-semibold">Pinned</span>}
                    </div>
                    <p className="mt-1 text-sm leading-7 text-muted-foreground">{msg.text}</p>
                    {msg.attachments?.map((att, i) =>
                      att.content_type?.startsWith("image/") ? (
                        <img alt="attachment" className="mt-2 max-h-36 rounded-lg object-cover" key={i} src={att.data_url} />
                      ) : null
                    )}
                    <p className="mt-2 text-xs text-muted-foreground">{formatDateTime(msg.created_at)}</p>
                    {msg.comments?.length > 0 && (
                      <div className="mt-2 space-y-1 border-l-2 border-border pl-3">
                        {msg.comments.map((c) => (
                          <div key={c.id}>
                            <p className="text-xs font-semibold text-foreground">{c.author_name}</p>
                            <p className="text-sm text-muted-foreground">{c.text}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 flex gap-2">
                      <Input
                        className="field-input text-xs h-8"
                        onChange={(e) => setChatCommentDrafts((c) => ({ ...c, [msg.id]: e.target.value }))}
                        placeholder="Reply..."
                        value={chatCommentDrafts[msg.id] || ""}
                      />
                      <Button
                        className="rounded-full h-8"
                        disabled={!chatCommentDrafts[msg.id]?.trim()}
                        onClick={() => handleChatComment(msg.id)}
                        size="sm"
                        variant="outline"
                      >
                        Reply
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">No chat room for this subyard yet.</p>
          )}
        </article>

        {/* Members */}
        <article className="archival-card" data-testid="courtyard-detail-members">
          <div className="flex items-center gap-3">
            <Users className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">Members</h2>
          </div>
          <div className="mt-4 space-y-3">
            {members.map((member) => (
              <div className="soft-panel flex items-center justify-between" key={member.id}>
                <div>
                  <p className="text-sm font-semibold text-foreground">{member.full_name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{member.email}</p>
                </div>
                <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-muted-foreground">
                  {member.role}
                </span>
              </div>
            ))}
          </div>
        </article>

        {/* Invites */}
        <article className="archival-card" data-testid="courtyard-detail-invites">
          <div className="flex items-center gap-3">
            <UserPlus className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">Invitations</h2>
          </div>
          {canManage && (
            <form className="mt-4 space-y-3" onSubmit={handleCreateInvite}>
              <Input
                className="field-input"
                onChange={(e) => setInviteForm((c) => ({ ...c, email: e.target.value }))}
                placeholder="Email address"
                required
                type="email"
                value={inviteForm.email}
              />
              <div className="flex items-center gap-3">
                <select
                  className="field-input w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                  onChange={(e) => setInviteForm((c) => ({ ...c, role: e.target.value }))}
                  value={inviteForm.role}
                >
                  <option value="member">Member</option>
                  <option value="organizer">Organizer</option>
                </select>
                <Button className="rounded-full" disabled={isSubmitting} type="submit">
                  Invite
                </Button>
              </div>
            </form>
          )}
          <div className="mt-4 space-y-3">
            {invites.map((invite) => (
              <div className="soft-panel" key={invite.id}>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-foreground">{invite.email}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{invite.role} · {invite.status}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-primary">
                      {invite.code}
                    </span>
                    <button
                      className="rounded-full border border-border p-1.5 text-muted-foreground hover:bg-muted/60 hover:text-primary transition"
                      onClick={() => setSharingInvite(invite)}
                      title="Share invite"
                      type="button"
                    >
                      <Share2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </article>

        {/* Kinship connections */}
        {kinships.length > 0 && (
          <article className="archival-card lg:col-span-2" data-testid="courtyard-detail-kinships">
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-semibold text-foreground">Kinship connections</h2>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {kinships.map((rel) => (
                <div className="soft-panel" key={rel.id}>
                  <p className="text-sm font-semibold text-foreground">{rel.person_name} ↔ {rel.related_to_name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{rel.relationship_type} · {rel.relationship_scope}</p>
                </div>
              ))}
            </div>
          </article>
        )}
      </section>

      {sharingInvite && (
        <ShareInviteDialog
          inviteCode={sharingInvite.code}
          contextLabel={`${subyard.name} courtyard`}
          onClose={() => setSharingInvite(null)}
        />
      )}
    </div>
  );
};
