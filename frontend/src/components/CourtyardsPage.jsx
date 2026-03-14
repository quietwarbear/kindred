import { useCallback, useEffect, useMemo, useState } from "react";
import { GitBranch, Network, ShieldCheck, UserPlus, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime } from "@/lib/api";
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

export const CourtyardsPage = ({ token, user }) => {
  const [structure, setStructure] = useState(null);
  const [subyardForm, setSubyardForm] = useState(initialSubyardForm);
  const [kinshipForm, setKinshipForm] = useState(initialKinshipForm);
  const [inviteForm, setInviteForm] = useState(initialInviteForm);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canManage = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);

  const loadStructure = useCallback(async () => {
    try {
      const payload = await apiRequest("/courtyard/structure", { token });
      setStructure(payload);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load courtyard structure.");
    }
  }, [token]);

  useEffect(() => {
    loadStructure();
  }, [loadStructure]);

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
    </div>
  );
};