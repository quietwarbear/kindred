import { useCallback, useEffect, useMemo, useState } from "react";
import { Mail, Shield, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialInviteForm = { email: "", role: "member" };

export const MembersPage = ({ token, user }) => {
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [inviteForm, setInviteForm] = useState(initialInviteForm);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canManageInvites = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);

  const loadData = useCallback(async () => {
    try {
      const [membersPayload, invitesPayload] = await Promise.all([
        apiRequest("/community/members", { token }),
        apiRequest("/invites", { token }),
      ]);
      setMembers(membersPayload.members || []);
      setInvites(invitesPayload.invites || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load membership data.");
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleInvite = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await apiRequest("/invites", { method: "POST", data: inviteForm, token });
      toast.success("Invite code created.");
      setInviteForm(initialInviteForm);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create invite.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">People + permissions</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="members-page-title">
          Community membership and invites
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="members-page-copy">
          Keep access deliberate. Hosts and organizers can create invite codes that map directly to the right role.
        </p>
      </section>

      {canManageInvites ? (
        <section className="archival-card" data-testid="members-invite-section">
          <div className="flex items-center gap-3">
            <UserPlus className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Create an invite</h3>
          </div>
          <form className="mt-6 grid gap-4 md:grid-cols-[1fr_180px_180px]" onSubmit={handleInvite}>
            <label>
              <span className="field-label">Invitee email</span>
              <Input className="field-input" data-testid="members-invite-email-input" onChange={(e) => setInviteForm((current) => ({ ...current, email: e.target.value }))} required type="email" value={inviteForm.email} />
            </label>
            <label>
              <span className="field-label">Role</span>
              <select className="field-input w-full" data-testid="members-invite-role-select" onChange={(e) => setInviteForm((current) => ({ ...current, role: e.target.value }))} value={inviteForm.role}>
                <option value="member">Member</option>
                <option value="organizer">Organizer</option>
              </select>
            </label>
            <div className="flex items-end">
              <Button className="h-12 w-full rounded-full" data-testid="members-invite-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Creating..." : "Create invite"}
              </Button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <article className="archival-card" data-testid="members-roster-card">
          <div className="flex items-center gap-3">
            <Shield className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Member roster</h3>
          </div>
          <div className="mt-6 space-y-4">
            {members.map((member) => (
              <div className="soft-panel flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between" data-testid={`member-row-${member.id}`} key={member.id}>
                <div>
                  <p className="text-lg font-semibold text-foreground">{member.full_name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{member.email}</p>
                </div>
                <div className="text-sm text-muted-foreground">
                  <p data-testid={`member-role-${member.id}`}>{member.role}</p>
                  <p>{formatDateTime(member.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="archival-card" data-testid="members-invite-list-card">
          <div className="flex items-center gap-3">
            <Mail className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Invite ledger</h3>
          </div>
          <div className="mt-6 space-y-4">
            {invites.length ? (
              invites.map((invite) => (
                <div className="soft-panel" data-testid={`invite-row-${invite.id}`} key={invite.id}>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-lg font-semibold text-foreground">{invite.email}</p>
                      <p className="mt-1 text-sm text-muted-foreground">Role: {invite.role}</p>
                    </div>
                    <div className="rounded-full border border-border bg-background/80 px-4 py-2 text-sm font-semibold text-primary" data-testid={`invite-code-${invite.id}`}>
                      {invite.code}
                    </div>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">Status: {invite.status} · Created {formatDateTime(invite.created_at)}</p>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="invite-empty-state">
                <p className="text-sm text-muted-foreground">No invites yet. Create one to start welcoming people into the community.</p>
              </div>
            )}
          </div>
        </article>
      </section>
    </div>
  );
};