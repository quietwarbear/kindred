import { useCallback, useEffect, useState } from "react";
import { Camera, Mic, Tags } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, convertFileToDataUrl, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialForm = { description: "", event_id: "", title: "" };

export const MemoryVaultPage = ({ token }) => {
  const [events, setEvents] = useState([]);
  const [memories, setMemories] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [imageFile, setImageFile] = useState(null);
  const [voiceFile, setVoiceFile] = useState(null);
  const [commentDrafts, setCommentDrafts] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [eventsPayload, memoriesPayload] = await Promise.all([
        apiRequest("/events", { token }),
        apiRequest("/memories", { token }),
      ]);
      setEvents(eventsPayload || []);
      setMemories(memoriesPayload || []);
      setForm((current) => ({ ...current, event_id: current.event_id || eventsPayload?.[0]?.id || "" }));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load memory vault.");
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreateMemory = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const [imageDataUrl, voiceDataUrl] = await Promise.all([
        convertFileToDataUrl(imageFile),
        convertFileToDataUrl(voiceFile),
      ]);
      const payload = await apiRequest("/memories", {
        method: "POST",
        data: {
          ...form,
          image_data_url: imageDataUrl || undefined,
          voice_note_data_url: voiceDataUrl || undefined,
        },
        token,
      });
      setMemories((current) => [payload, ...current]);
      setForm({ ...initialForm, event_id: form.event_id || events[0]?.id || "" });
      setImageFile(null);
      setVoiceFile(null);
      toast.success("Memory saved with tags.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to save this memory.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleComment = async (memoryId) => {
    try {
      const payload = await apiRequest(`/memories/${memoryId}/comments`, {
        method: "POST",
        data: { text: commentDrafts[memoryId] },
        token,
      });
      setMemories((current) => current.map((memory) => (memory.id === payload.id ? payload : memory)));
      setCommentDrafts((current) => ({ ...current, [memoryId]: "" }));
      toast.success("Comment added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add your comment.");
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Memory vault</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="memories-page-title">
          Turn every gathering into a living archive.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="memories-page-copy">
          Upload event-linked photos, add voice-note memories, and let AI generate helpful tags for future discovery.
        </p>
      </section>

      <section className="archival-card" data-testid="memories-create-section">
        <div className="flex items-center gap-3">
          <Camera className="h-5 w-5 text-primary" />
          <h3 className="font-display text-3xl text-foreground">Add a memory</h3>
        </div>
        <form className="mt-6 grid gap-4 xl:grid-cols-2" onSubmit={handleCreateMemory}>
          <label>
            <span className="field-label">Event</span>
            <select className="field-input w-full" data-testid="memories-event-select" onChange={(e) => setForm((current) => ({ ...current, event_id: e.target.value }))} required value={form.event_id}>
              <option value="">Select an event</option>
              {events.map((event) => (
                <option key={event.id} value={event.id}>{event.title}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Title</span>
            <Input className="field-input" data-testid="memories-title-input" onChange={(e) => setForm((current) => ({ ...current, title: e.target.value }))} required value={form.title} />
          </label>
          <label className="xl:col-span-2">
            <span className="field-label">Context or story</span>
            <Textarea className="field-textarea" data-testid="memories-description-input" onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))} required value={form.description} />
          </label>
          <label>
            <span className="field-label">Photo upload</span>
            <Input className="field-input pt-3" data-testid="memories-image-input" onChange={(e) => setImageFile(e.target.files?.[0] || null)} type="file" accept="image/*" />
          </label>
          <label>
            <span className="field-label">Voice note upload</span>
            <Input className="field-input pt-3" data-testid="memories-audio-input" onChange={(e) => setVoiceFile(e.target.files?.[0] || null)} type="file" accept="audio/*" />
          </label>
          <div className="xl:col-span-2">
            <Button className="rounded-full py-6 text-base" data-testid="memories-submit-button" disabled={isSubmitting || !events.length} type="submit">
              {isSubmitting ? "Saving memory..." : "Save memory with AI tags"}
            </Button>
          </div>
        </form>
      </section>

      <section className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        {memories.length ? (
          memories.map((memory) => (
            <article className="archival-card overflow-hidden" data-testid={`memory-card-${memory.id}`} key={memory.id}>
              {memory.image_data_url ? (
                <div className="overflow-hidden rounded-[24px] bg-muted">
                  <img alt={memory.title} className="aspect-[4/3] w-full object-cover object-center" data-testid={`memory-image-${memory.id}`} src={memory.image_data_url} />
                </div>
              ) : null}
              <div className="mt-5 space-y-4">
                <div>
                  <p className="text-lg font-semibold text-foreground">{memory.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{memory.event_title} · {formatDateTime(memory.created_at)}</p>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{memory.description}</p>
                </div>
                <div className="soft-panel" data-testid={`memory-tags-panel-${memory.id}`}>
                  <div className="flex items-center gap-2 text-primary">
                    <Tags className="h-4 w-4" />
                    <p className="text-sm font-semibold">AI tags</p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {memory.tags.map((tag) => (
                      <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" data-testid={`memory-tag-${memory.id}-${tag.replace(/\s+/g, "-")}`} key={tag}>
                        {tag}
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground" data-testid={`memory-summary-${memory.id}`}>{memory.ai_summary}</p>
                </div>
                {memory.voice_note_data_url ? (
                  <div className="soft-panel" data-testid={`memory-audio-${memory.id}`}>
                    <div className="mb-3 flex items-center gap-2 text-primary">
                      <Mic className="h-4 w-4" />
                      <p className="text-sm font-semibold">Voice note</p>
                    </div>
                    <audio className="w-full" controls src={memory.voice_note_data_url} />
                  </div>
                ) : null}
                <div className="soft-panel" data-testid={`memory-comments-panel-${memory.id}`}>
                  <p className="text-sm font-semibold text-foreground">Comments</p>
                  <div className="mt-3 space-y-3">
                    {memory.comments.map((comment) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`memory-comment-${comment.id}`} key={comment.id}>
                        <p className="text-sm font-semibold text-foreground">{comment.author_name}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{comment.text}</p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 space-y-3">
                    <Textarea className="field-textarea" data-testid={`memory-comment-input-${memory.id}`} onChange={(e) => setCommentDrafts((current) => ({ ...current, [memory.id]: e.target.value }))} placeholder="Add a memory note or contextual detail" value={commentDrafts[memory.id] || ""} />
                    <Button className="w-full rounded-full" data-testid={`memory-comment-submit-${memory.id}`} onClick={() => handleComment(memory.id)} type="button" variant="secondary">
                      Post comment
                    </Button>
                  </div>
                </div>
              </div>
            </article>
          ))
        ) : (
          <div className="archival-card lg:col-span-2 xl:col-span-3" data-testid="memories-empty-state">
            <p className="text-sm text-muted-foreground">No memories yet. Upload the first photo or voice note from your community archive.</p>
          </div>
        )}
      </section>
    </div>
  );
};