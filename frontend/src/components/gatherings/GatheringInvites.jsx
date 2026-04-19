import { useState } from "react";
import { Check, Copy, MailPlus, Share2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialInviteForm = { member_ids: [], guest_emails: "", note: "" };

const ShareMessageButton = ({ text, testId }) => {
  const [copied, setCopied] = useState(false);
  const handleShare = async () => {
    if (navigator.share) {
      try { await navigator.share({ text }); return; } catch { /* cancelled */ }
    }
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      className="mt-1 shrink-0 rounded-full border border-border p-1.5 text-muted-foreground hover:bg-muted/60 hover:text-primary transition"
      data-testid={testId}
      onClick={handleShare}
      title="Share invite message"
      type="button"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Share2 className="h-3.5 w-3.5" />}
    </button>
  );
};

export const GatheringInvites = ({ event, token, members, onUpdate }) => {
  const [form, setForm] = useState(initialInviteForm);

  const toggleMember = (memberId) => {
    setForm((c) => ({
      ...c,
      member_ids: c.member_ids.includes(memberId)
        ? c.member_ids.filter((id) => id !== memberId)
        : [...c.member_ids, memberId],
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = await apiRequest(`/events/${event.id}/invites`, {
        method: "POST",
        token,
        data: {
          member_ids: form.member_ids,
          guest_emails: form.guest_emails.split(",").map((s) => s.trim()).filter(Boolean),
          note: form.note,
        },
      });
      onUpdate(payload);
      setForm(initialInviteForm);
      toast.success("Event invites created.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create invites.");
    }
  };

  return (
    <div className="soft-panel" data-testid="gatherings-invites-panel">
      <div className="flex items-center gap-3">
        <MailPlus className="h-4 w-4 text-primary" />
        <p className="text-lg font-semibold text-foreground">Invite people to this gathering</p>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {members.map((member) => (
          <button
            className={`rounded-full px-3 py-2 text-xs font-semibold transition ${form.member_ids.includes(member.id) ? "bg-primary text-primary-foreground" : "border border-border bg-background/80 text-foreground"}`}
            data-testid={`gatherings-invite-member-${member.id}`}
            key={member.id}
            onClick={() => toggleMember(member.id)}
            type="button"
          >
            {member.full_name}
          </button>
        ))}
      </div>
      <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
        <Input className="field-input" data-testid="gatherings-invite-guests-input" onChange={(e) => setForm((c) => ({ ...c, guest_emails: e.target.value }))} placeholder="guest1@example.com, guest2@example.com" value={form.guest_emails} />
        <Textarea className="field-textarea" data-testid="gatherings-invite-note-input" onChange={(e) => setForm((c) => ({ ...c, note: e.target.value }))} placeholder="Optional note for invitees" value={form.note} />
        <Button className="w-full rounded-full" data-testid="gatherings-invite-submit-button" type="submit" variant="secondary">
          Create gathering invites
        </Button>
      </form>
      <div className="mt-4 space-y-3">
        {event.event_invites?.map((invite) => (
          <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-event-invite-${invite.id}`} key={invite.id}>
            <p className="text-sm font-semibold text-foreground">{invite.invitee_name} · {invite.email}</p>
            <p className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">{invite.invite_source} · {invite.delivery_status}</p>
            {invite.note ? <p className="mt-2 text-sm text-muted-foreground">{invite.note}</p> : null}
            {invite.zoom_link ? <p className="mt-2 text-sm text-primary" data-testid={`gatherings-event-invite-zoom-${invite.id}`}>Zoom: {invite.zoom_link}</p> : null}
            {invite.share_message && (
              <div className="mt-2 flex items-start gap-2">
                <p className="flex-1 text-sm leading-7 text-muted-foreground" data-testid={`gatherings-event-invite-message-${invite.id}`}>{invite.share_message}</p>
                <ShareMessageButton text={invite.share_message} testId={`gatherings-event-invite-share-${invite.id}`} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
