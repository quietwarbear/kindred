import { useCallback, useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { GitBranch, Plus, Trash2, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest } from "@/lib/api";
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

const initialForm = { person_name: "", related_to_name: "", relationship_type: "parent", relationship_scope: "community", notes: "", last_seen_at: "" };

export const KinshipMapPage = ({ token }) => {
  const [graph, setGraph] = useState({ nodes: [], links: [], relationship_types: [] });
  const [relationships, setRelationships] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [showForm, setShowForm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const graphRef = useRef();
  const containerRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  const loadData = useCallback(async () => {
    try {
      const [graphData, kinshipData] = await Promise.all([
        apiRequest("/kinship/graph", { token }),
        apiRequest("/kinship", { token }),
      ]);
      setGraph(graphData);
      setRelationships(kinshipData.relationships || []);
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

  const handleCreate = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await apiRequest("/kinship", { method: "POST", token, data: form });
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
    ctx.strokeStyle = "rgba(255,255,255,0.5)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.font = `bold 3.5px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.fillText(node.id, node.x, node.y + size + 2);
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

  return (
    <div className="space-y-6" data-testid="kinship-map-page">
      <div className="archival-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <GitBranch className="h-5 w-5 text-primary" />
            <div>
              <h2 className="font-display text-2xl text-foreground" data-testid="kinship-map-title">Kinship Map</h2>
              <p className="text-sm text-muted-foreground">{graph.total_nodes} people, {graph.total_links} connections</p>
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
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">Person</span>
              <Input className="field-input mt-1" data-testid="kinship-person" onChange={(e) => setForm((c) => ({ ...c, person_name: e.target.value }))} required value={form.person_name} />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">Related to</span>
              <Input className="field-input mt-1" data-testid="kinship-related-to" onChange={(e) => setForm((c) => ({ ...c, related_to_name: e.target.value }))} required value={form.related_to_name} />
            </label>
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
