import { useCallback, useEffect, useState } from "react";
import { Headphones, MessageSquareQuote, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, convertFileToDataUrl, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialThreadForm = {
  title: "",
  category: "oral-history",
  body: "",
  elder_name: "",
};

export const ThreadsPage = ({ token }) => {
  const [threads, setThreads] = useState([]);
  const [threadForm, setThreadForm] = useState(initialThreadForm);
  const [commentDrafts, setCommentDrafts] = useState({});
  const [voiceFile, setVoiceFile] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadThreads = useCallback(async () => {
    try {
      const payload = await apiRequest("/threads", { token });
      setThreads(payload || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load legacy threads.");
    }
  }, [token]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  const handleCreateThread = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const voiceDataUrl = await convertFileToDataUrl(voiceFile);
      const payload = await apiRequest("/threads", {
        method: "POST",
        data: { ...threadForm, voice_note_data_url: voiceDataUrl || undefined },
        token,
      });
      setThreads((current) => [payload, ...current]);
      setThreadForm(initialThreadForm);
      setVoiceFile(null);
      toast.success("Legacy thread created.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create thread.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleComment = async (threadId) => {
    try {
      const payload = await apiRequest(`/threads/${threadId}/comments`, {
        method: "POST",
        data: { text: commentDrafts[threadId] },
        token,
      });
      setThreads((current) => current.map((thread) => (thread.id === payload.id ? payload : thread)));
      setCommentDrafts((current) => ({ ...current, [threadId]: "" }));
      toast.success("Thread reply added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add reply.");
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Legacy threads</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="threads-page-title">
          Hold oral history, sermons, and intergenerational dialogue in one place.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="threads-page-copy">
          Use legacy threads for elder testimony, ministry archives, youth reflections, and moderated community learning.
        </p>
      </section>

      <section className="archival-card" data-testid="threads-create-section">
        <div className="flex items-center gap-3">
          <MessageSquareQuote className="h-5 w-5 text-primary" />
          <h3 className="font-display text-3xl text-foreground">Create a thread</h3>
        </div>
        <form className="mt-6 grid gap-4 xl:grid-cols-2" onSubmit={handleCreateThread}>
          <label>
            <span className="field-label">Title</span>
            <Input className="field-input" data-testid="threads-title-input" onChange={(e) => setThreadForm((current) => ({ ...current, title: e.target.value }))} required value={threadForm.title} />
          </label>
          <label>
            <span className="field-label">Category</span>
            <select className="field-input w-full" data-testid="threads-category-select" onChange={(e) => setThreadForm((current) => ({ ...current, category: e.target.value }))} value={threadForm.category}>
              <option value="oral-history">Oral history</option>
              <option value="sermon">Sermon archive</option>
              <option value="youth-reflection">Youth reflection</option>
              <option value="community-dialogue">Community dialogue</option>
            </select>
          </label>
          <label>
            <span className="field-label">Elder or speaker name</span>
            <Input className="field-input" data-testid="threads-elder-name-input" onChange={(e) => setThreadForm((current) => ({ ...current, elder_name: e.target.value }))} value={threadForm.elder_name} />
          </label>
          <label>
            <span className="field-label">Voice note</span>
            <Input className="field-input pt-3" data-testid="threads-audio-input" onChange={(e) => setVoiceFile(e.target.files?.[0] || null)} type="file" accept="audio/*" />
          </label>
          <label className="xl:col-span-2">
            <span className="field-label">Thread body</span>
            <Textarea className="field-textarea" data-testid="threads-body-input" onChange={(e) => setThreadForm((current) => ({ ...current, body: e.target.value }))} required value={threadForm.body} />
          </label>
          <div className="xl:col-span-2">
            <Button className="rounded-full py-6 text-base" data-testid="threads-submit-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Saving thread..." : "Create legacy thread"}
            </Button>
          </div>
        </form>
      </section>

      <section className="space-y-5">
        {threads.length ? (
          threads.map((thread) => (
            <article className="archival-card" data-testid={`thread-card-${thread.id}`} key={thread.id}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xl font-semibold text-foreground">{thread.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{thread.category} · {thread.elder_name || thread.created_by_name} · {formatDateTime(thread.created_at)}</p>
                </div>
                <div className="rounded-full border border-border bg-background/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary" data-testid={`thread-category-${thread.id}`}>
                  {thread.category}
                </div>
              </div>

              <p className="mt-5 text-sm leading-8 text-muted-foreground" data-testid={`thread-body-${thread.id}`}>{thread.body}</p>

              {thread.voice_note_data_url ? (
                <div className="soft-panel mt-5" data-testid={`thread-audio-${thread.id}`}>
                  <div className="mb-3 flex items-center gap-2 text-primary">
                    <Headphones className="h-4 w-4" />
                    <p className="text-sm font-semibold">Attached reflection</p>
                  </div>
                  <audio className="w-full" controls src={thread.voice_note_data_url} />
                </div>
              ) : null}

              <div className="soft-panel mt-5" data-testid={`thread-comments-panel-${thread.id}`}>
                <div className="mb-3 flex items-center gap-2 text-primary">
                  <Users className="h-4 w-4" />
                  <p className="text-sm font-semibold">Replies and reflections</p>
                </div>
                <div className="space-y-3">
                  {thread.comments.map((comment) => (
                    <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`thread-comment-${comment.id}`} key={comment.id}>
                      <p className="text-sm font-semibold text-foreground">{comment.author_name}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{comment.text}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 space-y-3">
                  <Textarea className="field-textarea" data-testid={`thread-comment-input-${thread.id}`} onChange={(e) => setCommentDrafts((current) => ({ ...current, [thread.id]: e.target.value }))} placeholder="Add a reflection, follow-up question, or testimony" value={commentDrafts[thread.id] || ""} />
                  <Button className="w-full rounded-full" data-testid={`thread-comment-submit-${thread.id}`} onClick={() => handleComment(thread.id)} type="button" variant="secondary">
                    Add reflection
                  </Button>
                </div>
              </div>
            </article>
          ))
        ) : (
          <div className="archival-card" data-testid="threads-empty-state">
            <p className="text-sm text-muted-foreground">No threads yet. Start with an elder reflection, oral history, or sermon archive.</p>
          </div>
        )}
      </section>
    </div>
  );
};