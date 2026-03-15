import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BellRing, GitBranch, MessageSquare, Network, Pin, ShieldCheck, UserPlus, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, convertFileToDataUrl, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialSubyardForm = {
  name: "",
  description: "",
  role_focus: "organizer, historian",
};

const initialKinshipForm = {
  person_name: "",
  related_to_name: "",
  relationship_type: "cousin branch",
  relationship_scope: "blood",
  notes: "",
  last_seen_at: "",
};

const initialInviteForm = {
  email: "",
  role: "member",
};

const initialAnnouncementForm = {
  title: "",
  body: "",
  scope: "courtyard",
  subyard_id: "",
};

export const CourtyardsPage = ({ token, user, onCommunicationsViewed }) => {
  const initialCommunicationLoadRef = useRef(false);
  const [structure, setStructure] = useState(null);
  const [announcements, setAnnouncements] = useState([]);
  const [announcementsUnread, setAnnouncementsUnread] = useState(0);
  const [chatRooms, setChatRooms] = useState([]);
  const [activeRoomId, setActiveRoomId] = useState("");
  const [subyardForm, setSubyardForm] = useState(initialSubyardForm);
  const [kinshipForm, setKinshipForm] = useState(initialKinshipForm);
  const [inviteForm, setInviteForm] = useState(initialInviteForm);
  const [announcementForm, setAnnouncementForm] = useState(initialAnnouncementForm);
  const [announcementFiles, setAnnouncementFiles] = useState([]);
  const [chatFiles, setChatFiles] = useState([]);
  const [chatText, setChatText] = useState("");
  const [announcementCommentDrafts, setAnnouncementCommentDrafts] = useState({});
  const [chatCommentDrafts, setChatCommentDrafts] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canManage = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);
  const activeRoom = useMemo(() => chatRooms.find((room) => room.id === activeRoomId) || null, [activeRoomId, chatRooms]);
  const orderedMessages = useMemo(() => {
    if (!activeRoom?.messages?.length) return [];
    return [...activeRoom.messages].sort((a, b) => Number(b.is_pinned) - Number(a.is_pinned));
  }, [activeRoom]);

  const filesToAttachments = async (fileList) => {
    const files = Array.from(fileList || []);
    return Promise.all(
      files.map(async (file) => ({
        name: file.name,
        data_url: await convertFileToDataUrl(file),
        mime_type: file.type || "",
      }))
    );
  };

  const loadStructure = useCallback(async () => {
    try {
      const [structurePayload, announcementPayload, chatPayload] = await Promise.all([
        apiRequest("/courtyard/structure", { token }),
        apiRequest("/announcements", { token }),
        apiRequest("/chat/rooms", { token }),
      ]);
      setStructure(structurePayload);
      setAnnouncements(announcementPayload.announcements || []);
      const unreadBeforeView = announcementPayload.unread_before_view || 0;
      if (!initialCommunicationLoadRef.current || unreadBeforeView > 0) {
        setAnnouncementsUnread(unreadBeforeView);
      }
      setChatRooms(chatPayload.rooms || []);
      initialCommunicationLoadRef.current = true;
      onCommunicationsViewed?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load courtyard structure.");
    }
  }, [onCommunicationsViewed, token]);

  useEffect(() => {
    loadStructure();
  }, [loadStructure]);

  useEffect(() => {
    if (!activeRoomId) return;

    const viewRoom = async () => {
      try {
        const payload = await apiRequest(`/chat/rooms/${activeRoomId}`, { token });
        setChatRooms((current) => current.map((room) => (room.id === payload.id ? payload : room)));
        onCommunicationsViewed?.();
      } catch {
        // no-op
      }
    };

    viewRoom();
  }, [activeRoomId, onCommunicationsViewed, token]);

  const handleCreateSubyard = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await apiRequest("/subyards", {
        method: "POST",
        token,
        data: {
          name: subyardForm.name,
          description: subyardForm.description,
          inherited_roles: true,
          role_focus: subyardForm.role_focus.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean),
          visibility: "shared",
        },
      });
      setSubyardForm(initialSubyardForm);
      toast.success("Subyard created.");
      loadStructure();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create subyard.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateKinship = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await apiRequest("/kinship", {
        method: "POST",
        token,
        data: {
          ...kinshipForm,
          last_seen_at: kinshipForm.last_seen_at ? new Date(kinshipForm.last_seen_at).toISOString() : null,
        },
      });
      setKinshipForm(initialKinshipForm);
      toast.success("Kinship relationship saved.");
      loadStructure();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to save kinship relationship.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateInvite = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await apiRequest("/invites", { method: "POST", token, data: inviteForm });
      setInviteForm(initialInviteForm);
      toast.success("Invite created.");
      loadStructure();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create invite.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateAnnouncement = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const attachments = await filesToAttachments(announcementFiles);
      await apiRequest("/announcements", {
        method: "POST",
        token,
        data: {
          ...announcementForm,
          subyard_id: announcementForm.scope === "subyard" ? announcementForm.subyard_id : "",
          attachments,
        },
      });
      setAnnouncementForm(initialAnnouncementForm);
      setAnnouncementFiles([]);
      toast.success("Announcement posted.");
      loadStructure();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to post announcement.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAnnouncementComment = async (announcementId) => {
    try {
      await apiRequest(`/announcements/${announcementId}/comments`, {
        method: "POST",
        token,
        data: { text: announcementCommentDrafts[announcementId] },
      });
      setAnnouncementCommentDrafts((current) => ({ ...current, [announcementId]: "" }));
      toast.success("Announcement comment added.");
      loadStructure();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add comment.");
    }
  };

  const handleSendMessage = async (event) => {
    event.preventDefault();
    if (!activeRoomId) return;
    setIsSubmitting(true);
    try {
      const attachments = await filesToAttachments(chatFiles);
      const payload = await apiRequest(`/chat/rooms/${activeRoomId}/messages`, {
        method: "POST",
        token,
        data: { text: chatText, attachments },
      });
      setChatRooms((current) => current.map((room) => (room.id === payload.id ? payload : room)));
      setChatText("");
      setChatFiles([]);
      toast.success("Message sent.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to send message.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePinMessage = async (messageId) => {
    if (!activeRoomId) return;
    try {
      const payload = await apiRequest(`/chat/rooms/${activeRoomId}/messages/${messageId}/pin`, { method: "POST", token });
      setChatRooms((current) => current.map((room) => (room.id === payload.id ? payload : room)));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to pin message.");
    }
  };

  const handleChatComment = async (messageId) => {
    if (!activeRoomId) return;
    try {
      const payload = await apiRequest(`/chat/rooms/${activeRoomId}/messages/${messageId}/comments`, {
        method: "POST",
        token,
        data: { text: chatCommentDrafts[messageId] },
      });
      setChatRooms((current) => current.map((room) => (room.id === payload.id ? payload : room)));
      setChatCommentDrafts((current) => ({ ...current, [messageId]: "" }));
      toast.success("Reply added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add reply.");
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Courtyard / Subyard Structure</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="courtyards-page-title">
          Modular spaces for the full family network and the teams inside it.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="courtyards-page-copy">
          Shape the parent courtyard, create subyards like cousins groups or elders councils, assign roles, and track kinship relationships that help with smarter invitations and more grounded memory-keeping.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2" data-testid="courtyards-communications-summary-section">
        <article className="archival-card" data-testid="courtyards-announcements-summary-card">
          <p className="eyebrow-text">Announcements</p>
          <div className="mt-3 flex items-center justify-between gap-4">
            <div>
              <h3 className="font-display text-2xl text-foreground">Broadcast updates</h3>
              <p className="mt-2 text-sm text-muted-foreground">Unread updates clear as soon as you view the announcement list.</p>
            </div>
            <div className="rounded-full bg-primary/15 px-4 py-2 text-sm font-semibold text-primary" data-testid="courtyards-announcements-summary-badge">
              {announcementsUnread} unread
            </div>
          </div>
        </article>

        <article className="archival-card" data-testid="courtyards-chat-summary-card">
          <p className="eyebrow-text">Internal chat</p>
          <div className="mt-3 flex items-center justify-between gap-4">
            <div>
              <h3 className="font-display text-2xl text-foreground">Room activity</h3>
              <p className="mt-2 text-sm text-muted-foreground">Unread chat clears when you open the specific room.</p>
            </div>
            <div className="rounded-full bg-primary/15 px-4 py-2 text-sm font-semibold text-primary" data-testid="courtyards-chat-summary-badge">
              {chatRooms.reduce((sum, room) => sum + (room.unread_count || 0), 0)} unread
            </div>
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="archival-card" data-testid="courtyards-parent-card">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Parent Courtyard</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">{structure?.courtyard?.name}</h3>
            </div>
          </div>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">{structure?.courtyard?.description}</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="soft-panel" data-testid="courtyards-parent-members">
              <p className="text-sm text-muted-foreground">Members</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{structure?.members?.length || 0}</p>
            </div>
            <div className="soft-panel" data-testid="courtyards-parent-subyards">
              <p className="text-sm text-muted-foreground">Subyards</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{structure?.subyards?.length || 0}</p>
            </div>
            <div className="soft-panel" data-testid="courtyards-parent-invites">
              <p className="text-sm text-muted-foreground">Invites</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{structure?.invites?.length || 0}</p>
            </div>
          </div>
        </article>

        <article className="archival-card" data-testid="courtyards-role-catalog-card">
          <div className="flex items-center gap-3">
            <Network className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Role Assignments</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Permission-aware family roles</h3>
            </div>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {structure?.role_catalog?.map((item) => (
              <div className="soft-panel" data-testid={`courtyards-role-card-${item.role.replace(/\s+/g, "-")}`} key={item.role}>
                <p className="text-base font-semibold capitalize text-foreground">{item.role}</p>
                <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                  {item.tools.map((tool) => (
                    <li key={tool}>• {tool}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <article className="archival-card" data-testid="courtyards-subyards-card">
          <div className="flex items-center gap-3">
            <GitBranch className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Subyards</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Nested teams and circles</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {structure?.subyards?.map((subyard) => (
              <div className="soft-panel" data-testid={`courtyard-subyard-${subyard.id}`} key={subyard.id}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-lg font-semibold text-foreground">{subyard.name}</p>
                    <p className="mt-2 text-sm leading-7 text-muted-foreground">{subyard.description}</p>
                  </div>
                  <div className="rounded-full border border-border bg-background/80 px-4 py-2 text-xs uppercase tracking-[0.16em] text-primary" data-testid={`courtyard-subyard-visibility-${subyard.id}`}>
                    {subyard.visibility}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {subyard.role_focus.map((role) => (
                    <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" data-testid={`courtyard-subyard-role-${subyard.id}-${role.replace(/\s+/g, "-")}`} key={role}>
                      {role}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {canManage ? (
            <form className="mt-6 grid gap-4" onSubmit={handleCreateSubyard}>
              <label>
                <span className="field-label">Subyard name</span>
                <Input className="field-input" data-testid="courtyard-subyard-name-input" onChange={(e) => setSubyardForm((current) => ({ ...current, name: e.target.value }))} required value={subyardForm.name} />
              </label>
              <label>
                <span className="field-label">Description</span>
                <Textarea className="field-textarea" data-testid="courtyard-subyard-description-input" onChange={(e) => setSubyardForm((current) => ({ ...current, description: e.target.value }))} required value={subyardForm.description} />
              </label>
              <label>
                <span className="field-label">Role focus</span>
                <Input className="field-input" data-testid="courtyard-subyard-role-focus-input" onChange={(e) => setSubyardForm((current) => ({ ...current, role_focus: e.target.value }))} value={subyardForm.role_focus} />
              </label>
              <Button className="rounded-full" data-testid="courtyard-subyard-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Saving..." : "Create subyard"}
              </Button>
            </form>
          ) : null}
        </article>

        <article className="archival-card" data-testid="courtyards-kinship-card">
          <div className="flex items-center gap-3">
            <Users className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Kinship / Relationship Layer</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Flexible relationship graph</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {structure?.kinships?.map((relationship) => (
              <div className="soft-panel" data-testid={`courtyard-kinship-${relationship.id}`} key={relationship.id}>
                <p className="text-base font-semibold text-foreground">{relationship.person_name} ↔ {relationship.related_to_name}</p>
                <p className="mt-2 text-sm text-muted-foreground">{relationship.relationship_type} · {relationship.relationship_scope}</p>
                {relationship.last_seen_at ? <p className="mt-2 text-sm text-muted-foreground">Last seen: {formatDateTime(relationship.last_seen_at)}</p> : null}
                {relationship.notes ? <p className="mt-2 text-sm leading-7 text-muted-foreground">{relationship.notes}</p> : null}
              </div>
            ))}
          </div>
          <form className="mt-6 grid gap-4" onSubmit={handleCreateKinship}>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className="field-label">Person</span>
                <Input className="field-input" data-testid="courtyard-kinship-person-input" onChange={(e) => setKinshipForm((current) => ({ ...current, person_name: e.target.value }))} required value={kinshipForm.person_name} />
              </label>
              <label>
                <span className="field-label">Related to</span>
                <Input className="field-input" data-testid="courtyard-kinship-related-to-input" onChange={(e) => setKinshipForm((current) => ({ ...current, related_to_name: e.target.value }))} required value={kinshipForm.related_to_name} />
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className="field-label">Relationship type</span>
                <Input className="field-input" data-testid="courtyard-kinship-type-input" onChange={(e) => setKinshipForm((current) => ({ ...current, relationship_type: e.target.value }))} required value={kinshipForm.relationship_type} />
              </label>
              <label>
                <span className="field-label">Scope</span>
                <select className="field-input w-full" data-testid="courtyard-kinship-scope-select" onChange={(e) => setKinshipForm((current) => ({ ...current, relationship_scope: e.target.value }))} value={kinshipForm.relationship_scope}>
                  <option value="blood">Blood</option>
                  <option value="chosen">Chosen family</option>
                  <option value="mentor">Mentor</option>
                  <option value="neighbor">Neighbor</option>
                  <option value="honorary elder">Honorary elder</option>
                </select>
              </label>
            </div>
            <label>
              <span className="field-label">Last seen date</span>
              <Input className="field-input" data-testid="courtyard-kinship-last-seen-input" onChange={(e) => setKinshipForm((current) => ({ ...current, last_seen_at: e.target.value }))} type="date" value={kinshipForm.last_seen_at} />
            </label>
            <label>
              <span className="field-label">Notes</span>
              <Textarea className="field-textarea" data-testid="courtyard-kinship-notes-input" onChange={(e) => setKinshipForm((current) => ({ ...current, notes: e.target.value }))} value={kinshipForm.notes} />
            </label>
            <Button className="rounded-full" data-testid="courtyard-kinship-submit-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Saving..." : "Add relationship"}
            </Button>
          </form>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <article className="archival-card" data-testid="courtyards-members-card">
          <p className="eyebrow-text">Member access</p>
          <h3 className="mt-2 font-display text-3xl text-foreground">Who’s inside the courtyard</h3>
          <div className="mt-6 space-y-3">
            {structure?.members?.map((member) => (
              <div className="soft-panel flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between" data-testid={`courtyard-member-${member.id}`} key={member.id}>
                <div>
                  <p className="text-base font-semibold text-foreground">{member.full_name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{member.email}</p>
                </div>
                <div className="text-sm text-muted-foreground">
                  <p data-testid={`courtyard-member-role-${member.id}`}>{member.role}</p>
                  <p>{formatDateTime(member.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="archival-card" data-testid="courtyards-invites-card">
          <div className="flex items-center gap-3">
            <UserPlus className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Invitation flow</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Bring people in deliberately</h3>
            </div>
          </div>
          {canManage ? (
            <form className="mt-6 grid gap-4" onSubmit={handleCreateInvite}>
              <label>
                <span className="field-label">Invitee email</span>
                <Input className="field-input" data-testid="courtyard-invite-email-input" onChange={(e) => setInviteForm((current) => ({ ...current, email: e.target.value }))} required type="email" value={inviteForm.email} />
              </label>
              <label>
                <span className="field-label">Role</span>
                <select className="field-input w-full" data-testid="courtyard-invite-role-select" onChange={(e) => setInviteForm((current) => ({ ...current, role: e.target.value }))} value={inviteForm.role}>
                  <option value="member">Member</option>
                  <option value="organizer">Organizer</option>
                </select>
              </label>
              <Button className="rounded-full" data-testid="courtyard-invite-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Saving..." : "Create invite"}
              </Button>
            </form>
          ) : null}
          <div className="mt-6 space-y-3">
            {structure?.invites?.map((invite) => (
              <div className="soft-panel" data-testid={`courtyard-invite-${invite.id}`} key={invite.id}>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-base font-semibold text-foreground">{invite.email}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{invite.role} · {invite.status}</p>
                  </div>
                  <div className="rounded-full border border-border bg-background/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary" data-testid={`courtyard-invite-code-${invite.id}`}>
                    {invite.code}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="archival-card" data-testid="courtyards-announcements-card">
          <div className="flex items-center gap-3">
            <BellRing className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Announcements</p>
              <div className="mt-2 flex items-center gap-3">
                <h3 className="font-display text-3xl text-foreground">Courtyard + subyard broadcasts</h3>
                {announcementsUnread > 0 ? (
                  <span className="rounded-full bg-primary/15 px-3 py-1 text-xs font-semibold text-primary" data-testid="courtyards-announcements-unread-badge">
                    {announcementsUnread} new
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          {canManage ? (
            <form className="mt-6 grid gap-4" onSubmit={handleCreateAnnouncement}>
              <label>
                <span className="field-label">Title</span>
                <Input className="field-input" data-testid="courtyard-announcement-title-input" onChange={(e) => setAnnouncementForm((current) => ({ ...current, title: e.target.value }))} required value={announcementForm.title} />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label>
                  <span className="field-label">Scope</span>
                  <select className="field-input w-full" data-testid="courtyard-announcement-scope-select" onChange={(e) => setAnnouncementForm((current) => ({ ...current, scope: e.target.value }))} value={announcementForm.scope}>
                    <option value="courtyard">Courtyard-wide</option>
                    <option value="subyard">Subyard-specific</option>
                  </select>
                </label>
                <label>
                  <span className="field-label">Subyard</span>
                  <select className="field-input w-full" data-testid="courtyard-announcement-subyard-select" disabled={announcementForm.scope !== "subyard"} onChange={(e) => setAnnouncementForm((current) => ({ ...current, subyard_id: e.target.value }))} value={announcementForm.subyard_id}>
                    <option value="">Select subyard</option>
                    {structure?.subyards?.map((subyard) => (
                      <option key={subyard.id} value={subyard.id}>{subyard.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                <span className="field-label">Body</span>
                <Textarea className="field-textarea" data-testid="courtyard-announcement-body-input" onChange={(e) => setAnnouncementForm((current) => ({ ...current, body: e.target.value }))} required value={announcementForm.body} />
              </label>
              <label>
                <span className="field-label">Share files/photos</span>
                <Input className="field-input pt-3" data-testid="courtyard-announcement-files-input" multiple onChange={(e) => setAnnouncementFiles(e.target.files || [])} type="file" />
              </label>
              <Button className="rounded-full" data-testid="courtyard-announcement-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Posting..." : "Post announcement"}
              </Button>
            </form>
          ) : null}
          <div className="mt-6 space-y-4">
            {announcements.map((announcement) => (
              <div className="soft-panel" data-testid={`courtyard-announcement-${announcement.id}`} key={announcement.id}>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-base font-semibold text-foreground">{announcement.title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{announcement.scope} {announcement.subyard_name ? `· ${announcement.subyard_name}` : ""}</p>
                  </div>
                  <p className="text-sm text-muted-foreground">{announcement.created_by_name}</p>
                </div>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{announcement.body}</p>
                {announcement.attachments?.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {announcement.attachments.map((attachment, index) => (
                      <a className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" data-testid={`courtyard-announcement-attachment-${announcement.id}-${index}`} download={attachment.name} href={attachment.data_url} key={`${announcement.id}-${attachment.name}-${index}`}>
                        {attachment.name}
                      </a>
                    ))}
                  </div>
                ) : null}
                <div className="mt-4 space-y-2">
                  {announcement.comments?.map((comment) => (
                    <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`courtyard-announcement-comment-${comment.id}`} key={comment.id}>
                      <p className="text-sm font-semibold text-foreground">{comment.author_name}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{comment.text}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 space-y-3">
                  <Textarea className="field-textarea" data-testid={`courtyard-announcement-comment-input-${announcement.id}`} onChange={(e) => setAnnouncementCommentDrafts((current) => ({ ...current, [announcement.id]: e.target.value }))} placeholder="Add a comment" value={announcementCommentDrafts[announcement.id] || ""} />
                  <Button className="w-full rounded-full" data-testid={`courtyard-announcement-comment-submit-${announcement.id}`} onClick={() => handleAnnouncementComment(announcement.id)} type="button" variant="secondary">
                    Add comment
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="archival-card" data-testid="courtyards-chat-card">
          <div className="flex items-center gap-3">
            <MessageSquare className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Internal chat</p>
              <div className="mt-2 flex items-center gap-3">
                <h3 className="font-display text-3xl text-foreground">Courtyard + subyard rooms</h3>
                {chatRooms.reduce((sum, room) => sum + (room.unread_count || 0), 0) > 0 ? (
                  <span className="rounded-full bg-primary/15 px-3 py-1 text-xs font-semibold text-primary" data-testid="courtyards-chat-unread-badge">
                    {chatRooms.reduce((sum, room) => sum + (room.unread_count || 0), 0)} unread
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            {chatRooms.map((room) => (
              <button
                className={`rounded-full px-4 py-2 text-sm font-semibold transition ${room.id === activeRoomId ? "bg-primary text-primary-foreground" : "border border-border bg-background/80 text-foreground"}`}
                data-testid={`courtyard-chat-room-${room.id}`}
                key={room.id}
                onClick={() => setActiveRoomId(room.id)}
                type="button"
              >
                <span className="flex items-center gap-2">
                  <span>{room.name}</span>
                  {room.unread_count ? (
                    <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary" data-testid={`courtyard-chat-room-badge-${room.id}`}>
                      {room.unread_count}
                    </span>
                  ) : null}
                </span>
              </button>
            ))}
          </div>
          {activeRoom ? (
            <div className="mt-6 space-y-4">
              <div className="soft-panel" data-testid="courtyard-chat-active-room-panel">
                <p className="text-base font-semibold text-foreground">{activeRoom.name}</p>
                <p className="mt-2 text-sm text-muted-foreground">Share text, files, photos, and comments inside the room.</p>
              </div>
              <form className="grid gap-4" onSubmit={handleSendMessage}>
                <label>
                  <span className="field-label">Message</span>
                  <Textarea className="field-textarea" data-testid="courtyard-chat-message-input" onChange={(e) => setChatText(e.target.value)} required value={chatText} />
                </label>
                <label>
                  <span className="field-label">Share files/photos</span>
                  <Input className="field-input pt-3" data-testid="courtyard-chat-files-input" multiple onChange={(e) => setChatFiles(e.target.files || [])} type="file" />
                </label>
                <Button className="rounded-full" data-testid="courtyard-chat-submit-button" disabled={isSubmitting} type="submit">
                  {isSubmitting ? "Sending..." : "Send message"}
                </Button>
              </form>
              <div className="space-y-4">
                {orderedMessages.map((message) => (
                  <div className="soft-panel" data-testid={`courtyard-chat-message-${message.id}`} key={message.id}>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{message.author_name}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{formatDateTime(message.created_at)}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {message.is_pinned ? <span className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Pinned</span> : null}
                        {canManage ? (
                          <Button className="rounded-full" data-testid={`courtyard-chat-pin-${message.id}`} onClick={() => handlePinMessage(message.id)} size="sm" type="button" variant="secondary">
                            <Pin className="mr-2 h-3 w-3" />
                            {message.is_pinned ? "Unpin" : "Pin"}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-muted-foreground">{message.text}</p>
                    {message.attachments?.length ? (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {message.attachments.map((attachment, index) => (
                          <a className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" data-testid={`courtyard-chat-attachment-${message.id}-${index}`} download={attachment.name} href={attachment.data_url} key={`${message.id}-${attachment.name}-${index}`}>
                            {attachment.name}
                          </a>
                        ))}
                      </div>
                    ) : null}
                    <div className="mt-4 space-y-2">
                      {message.comments?.map((comment) => (
                        <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`courtyard-chat-comment-${comment.id}`} key={comment.id}>
                          <p className="text-sm font-semibold text-foreground">{comment.author_name}</p>
                          <p className="mt-1 text-sm text-muted-foreground">{comment.text}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4 space-y-3">
                      <Textarea className="field-textarea" data-testid={`courtyard-chat-comment-input-${message.id}`} onChange={(e) => setChatCommentDrafts((current) => ({ ...current, [message.id]: e.target.value }))} placeholder="Add a reply" value={chatCommentDrafts[message.id] || ""} />
                      <Button className="w-full rounded-full" data-testid={`courtyard-chat-comment-submit-${message.id}`} onClick={() => handleChatComment(message.id)} type="button" variant="secondary">
                        Add reply
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="soft-panel mt-6" data-testid="courtyard-chat-empty-state">
              <p className="text-sm text-muted-foreground">No chat rooms available yet.</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
};