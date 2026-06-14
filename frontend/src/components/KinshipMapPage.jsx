import { useCallback, useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { BookOpen, CalendarDays, Camera, GitBranch, Plus, Trash2, Users, X } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const REL_COLORS = {
  parent: "#d97706",
  child: "#16a34a",
  sibling: "#2563eb",
  spouse: "#dc2626",
  grandparent: "#9333ea",
  cousin: "#0891b2",
  "aunt/uncle": "#c026d3",
  "niece/nephew": "#65a30d",
  friend: "#64748b",
};

const getRelColor = (type) => REL_COLORS[type?.toLowerCase()] || "#8b5cf6";

const NODE_COLORS = { host: "#c2410c", organizer: "#b45309", member: "#0284c7", kinship: "#7c3aed" };

const initialForm = {
  personMemberId: "",
  personCustomName: "",
  relatedMemberId: "",
  relatedCustomName: "",
  relationship_type: "parent",
  relationship_scope: "community",
  notes: "",
};

export const KinshipMapPage = ({ token }) => {
  const [graph, setGraph] = useState({ nodes: [], links: [], relationship_types: [] });
  const [relationships, setRelationships] = useState([]);
  const [members, setMembers] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [showForm, setShowForm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [person, setPerson] = useState(null);
  const [personLoading, setPersonLoading] = useState(false);
  const graphRef = useRef();
  const containerRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  const loadData = useCallback(async () => {
    try {
      const [graphData, kinshipData, memberData] = await Promise.all([
        apiRequest("/kinship/graph", { token }),
        apiRequest("/kinship", { token }),
        apiRequest("/community/members", { token }),
      ]);
      setGraph(graphData);
      setRelationships(kinshipData.relationships || []);
      setMembers(memberData.members || []);
    } catch {
      toast.error("Unable to load kinship data.");
    }
  }, [token]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width } = entry.contentRect;
      setDimensions({ width: Math.max(400, width), height: 500 });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const openPerson = useCallback(async (userId) => {
    if (!userId) {
      toast("That person isn't on Kindred yet — invite them to see their full story.");
      return;
    }
    setPersonLoading(true);
    try {
      const data = await apiRequest(`/kinship/person/${userId}`, { token });
      setPerson(data);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to open this person.");
    } finally {
      setPersonLoading(false);
    }
  }, [token]);

  const handleCreate = async (e) => {
    e.preventDefault();
    const personMember = members.find((m) => m.id === form.personMemberId);
    const relatedMember = members.find((m) => m.id === form.relatedMemberId);
    const person_name = personMember ? personMember.full_name : form.personCustomName.trim();
    const related_to_name = relatedMember ? relatedMember.full_name : form.relatedCustomName.trim();
    if (!person_name || !related_to_name) {
      toast.error("Choose or name both people.");
      return;
    }
    setIsSubmitting(true);
    try {
      await apiRequest("/kinship", {
        method: "POST",
        token,
        data: {
          person_name,
          related_to_name,
          person_user_id: form.personMemberId,
          related_to_user_id: form.relatedMemberId,
          relationship_type: form.relationship_type,
          relationship_scope: form.relationship_scope,
          notes: form.notes,
        },
      });
      setForm(initialForm);
      setShowForm(false);
      toast.success("Relationship added.");
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add relationship.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await apiRequest(`/kinship/${id}`, { method: "DELETE", token });
      toast.success("Relationship removed.");
      loadData();
    } catch {
      toast.error("Unable to remove relationship.");
    }
  };

  const paintNode = useCallback((node, ctx) => {
    const size = node.role === "host" ? 8 : 6;
    ctx.beginPath();
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
    ctx.fillStyle = NODE_COLORS[node.role] || NODE_COLORS.kinship;
    ctx.fill();
    ctx.strokeStyle = node.user_id ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.4)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.font = `bold 3.5px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.fillText(node.name || node.id, node.x, node.y + size + 2);
  }, []);

  const paintLink = useCallback((link, ctx) => {
    ctx.beginPath();
    ctx.moveTo(link.source.x, link.source.y);
    ctx.lineTo(link.target.x, link.target.y);
    ctx.strokeStyle = getRelColor(link.label);
    ctx.lineWidth = 1.5;
    ctx.stroke();
    const mx = (link.source.x + link.target.x) / 2;
    const my = (link.source.y + link.target.y) / 2;
    ctx.font = "2.5px sans-serif";
    ctx.textAlign = "center";
    ctx.fillStyle = getRelColor(link.label);
    ctx.fillText(link.label, mx, my - 2);
  }, []);

  const PersonPicker = ({ label, memberKey, customKey, testId }) => (
    <label className="block">
      <span className="text-xs font-semibold text-muted-foreground">{label}</span>
      <select
        className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
        data-testid={`${testId}-member`}
        onChange={(e) => setForm((c) => ({ ...c, [memberKey]: e.target.value }))}
        value={form[memberKey]}
      >
        <option value="">— Someone not on Kindred —</option>
        {members.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
      </select>
      {!form[memberKey] && (
        <Input
          className="field-input mt-2"
          data-testid={`${testId}-custom`}
          onChange={(e) => setForm((c) => ({ ...c, [customKey]: e.target.value }))}
          placeholder="Their name"
          value={form[customKey]}
        />
      )}
    </label>
  );

  return (
    <div className="space-y-6" data-testid="kinship-map-page">
      <div className="archival-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <GitBranch className="h-5 w-5 text-primary" />
            <div>
              <h2 className="font-display text-2xl text-foreground" data-testid="kinship-map-title">Kinship Map</h2>
              <p className="text-sm text-muted-foreground">{graph.total_nodes} people, {graph.total_links} connections · tap anyone to see their story</p>
            </div>
          </div>
          <Button className="rounded-full" data-testid="kinship-add-btn" onClick={() => setShowForm(!showForm)} size="sm">
            <Plus className="mr-1 h-4 w-4" /> Add Relationship
          </Button>
        </div>
      </div>

      {showForm && (
        <div className="archival-card" data-testid="kinship-form">
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleCreate}>
            <PersonPicker label="Person" memberKey="personMemberId" customKey="personCustomName" testId="kinship-person" />
            <PersonPicker label="Related to" memberKey="relatedMemberId" customKey="relatedCustomName" testId="kinship-related-to" />
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">Relationship</span>
              <select className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" data-testid="kinship-type" onChange={(e) => setForm((c) => ({ ...c, relationship_type: e.target.value }))} value={form.relationship_type}>
                {Object.keys(REL_COLORS).map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">Scope</span>
              <select className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" data-testid="kinship-scope" onChange={(e) => setForm((c) => ({ ...c, relationship_scope: e.target.value }))} value={form.relationship_scope}>
                <option value="community">Community</option>
                <option value="family">Family</option>
                <option value="extended">Extended</option>
              </select>
            </label>
            <label className="block sm:col-span-2">
              <span className="text-xs font-semibold text-muted-foreground">Notes</span>
              <Textarea className="field-textarea mt-1" data-testid="kinship-notes" onChange={(e) => setForm((c) => ({ ...c, notes: e.target.value }))} rows={2} value={form.notes} />
            </label>
            <div className="flex gap-2 sm:col-span-2">
              <Button className="rounded-full" data-testid="kinship-submit" disabled={isSubmitting} size="sm" type="submit">
                {isSubmitting ? "Adding..." : "Add to Map"}
              </Button>
              <Button className="rounded-full" onClick={() => setShowForm(false)} size="sm" type="button" variant="outline">Cancel</Button>
            </div>
          </form>
        </div>
      )}

      {person && (
        <div className="archival-card" data-testid="kinship-person-panel">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="eyebrow-text">In the community</p>
              <h3 className="mt-1 font-display text-2xl text-foreground" data-testid="kinship-person-name">{person.person?.full_name}</h3>
              <p className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">{person.person?.role}</p>
            </div>
            <button className="rounded-full p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/60 transition" data-testid="kinship-person-close" onClick={() => setPerson(null)} type="button">
              <X className="h-4 w-4" />
            </button>
          </div>

          {person.relationships?.length > 0 && (
            <div className="mt-4">
              <p className="eyebrow-text">Relationships</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {person.relationships.map((rel) => (
                  <span className="rounded-full bg-muted/60 px-3 py-1.5 text-xs text-foreground" key={rel.id}>
                    {rel.person_name} · {rel.relationship_type} · {rel.related_to_name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <div>
              <div className="flex items-center gap-1.5"><CalendarDays className="h-3.5 w-3.5 text-primary" /><p className="eyebrow-text">Gatherings</p></div>
              {person.gatherings?.length ? (
                <ul className="mt-2 space-y-1.5">
                  {person.gatherings.slice(0, 5).map((g) => (
                    <li className="text-sm text-muted-foreground" key={g.id}>{g.title}<span className="block text-xs">{formatDateTime(g.start_at)}</span></li>
                  ))}
                </ul>
              ) : <p className="mt-2 text-xs text-muted-foreground">None yet.</p>}
            </div>
            <div>
              <div className="flex items-center gap-1.5"><Camera className="h-3.5 w-3.5 text-primary" /><p className="eyebrow-text">Memories</p></div>
              {person.memories?.length ? (
                <ul className="mt-2 space-y-1.5">
                  {person.memories.slice(0, 5).map((m) => <li className="text-sm text-muted-foreground" key={m.id}>{m.title}</li>)}
                </ul>
              ) : <p className="mt-2 text-xs text-muted-foreground">None yet.</p>}
            </div>
            <div>
              <div className="flex items-center gap-1.5"><BookOpen className="h-3.5 w-3.5 text-primary" /><p className="eyebrow-text">Stories</p></div>
              {person.threads?.length ? (
                <ul className="mt-2 space-y-1.5">
                  {person.threads.slice(0, 5).map((t) => <li className="text-sm text-muted-foreground" key={t.id}>{t.title}</li>)}
                </ul>
              ) : <p className="mt-2 text-xs text-muted-foreground">None yet.</p>}
            </div>
          </div>

          <div className="mt-4 flex gap-4">
            <Link className="text-sm font-semibold text-primary" to="/gatherings">Gatherings</Link>
            <Link className="text-sm font-semibold text-primary" to="/memories">Memory Vault</Link>
            <Link className="text-sm font-semibold text-primary" to="/legacy-threads">Legacy Threads</Link>
          </div>
        </div>
      )}

      <div className="archival-card overflow-hidden" data-testid="kinship-graph-container" ref={containerRef}>
        {graph.nodes.length > 0 ? (
          <>
            <div className="rounded-2xl bg-[#1a1a2e] overflow-hidden" style={{ height: 500 }}>
              <ForceGraph2D
                ref={graphRef}
                graphData={graph}
                width={dimensions.width}
                height={dimensions.height}
                backgroundColor="#1a1a2e"
                nodeCanvasObject={paintNode}
                linkCanvasObject={paintLink}
                onNodeClick={(node) => openPerson(node.user_id)}
                nodeRelSize={6}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={0.7}
                d3AlphaDecay={0.04}
                d3VelocityDecay={0.3}
                cooldownTicks={100}
                enableNodeDrag={true}
                enableZoomInteraction={true}
              />
            </div>
            {personLoading && <p className="mt-3 text-xs text-muted-foreground" data-testid="kinship-person-loading">Opening their story…</p>}
            {graph.relationship_types.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-3" data-testid="kinship-legend">
                {graph.relationship_types.map((type) => (
                  <div className="flex items-center gap-1.5" key={type}>
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: getRelColor(type) }} />
                    <span className="text-xs font-medium text-muted-foreground">{type}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Users className="h-12 w-12 text-muted-foreground/30 mb-4" />
            <p className="text-sm text-muted-foreground">No relationships added yet. Add connections to see your kinship network come alive.</p>
          </div>
        )}
      </div>

      {relationships.length > 0 && (
        <div className="archival-card" data-testid="kinship-list">
          <h3 className="font-display text-xl text-foreground mb-4">All Relationships</h3>
          <div className="divide-y divide-border/50">
            {relationships.map((rel) => (
              <div className="flex items-center justify-between py-3 gap-3" data-testid={`kinship-row-${rel.id}`} key={rel.id}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="inline-block h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: getRelColor(rel.relationship_type) }} />
                    <p className="text-sm font-semibold text-foreground truncate">
                      {rel.person_name} <span className="font-normal text-muted-foreground">is {rel.relationship_type} of</span> {rel.related_to_name}
                    </p>
                  </div>
                  {rel.notes && <p className="ml-4 mt-0.5 text-xs text-muted-foreground truncate">{rel.notes}</p>}
                </div>
                <button
                  className="rounded-full p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors shrink-0"
                  data-testid={`kinship-delete-${rel.id}`}
                  onClick={() => handleDelete(rel.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
