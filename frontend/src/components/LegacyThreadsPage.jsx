import { useCallback, useEffect, useState } from "react";
import { BookOpen, MessageSquare, Mic, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, convertFileToDataUrl, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { VoiceRecorder } from "@/components/VoiceRecorder";

const CATEGORIES = [
  { value: "oral-history", label: "Oral History" },
  { value: "sermon", label: "Sermon Archive" },
  { value: "youth-reflection", label: "Youth Reflection" },
  { value: "community-dialogue", label: "Community Dialogue" },
  { value: "family-lore", label: "Family Lore" },
  { value: "migration-story", label: "Migration Story" },
  { value: "recipe-tradition", label: "Recipe / Tradition" },
];

const CATEGORY_COLORS = {
  "oral-history": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  sermon: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  "youth-reflection": "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  "community-dialogue": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  "family-lore": "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
  "migration-story": "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  "recipe-tradition": "bg-lime-100 text-lime-800 dark:bg-lime-900/40 dark:text-lime-300",
};

const initialForm = { title: "", category: "oral-history", body: "", elder_name: "" };

export const LegacyThreadsPage = ({ token }) => {
  const [threads, setThreads] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [audioFile, setAudioFile] = useState(null);
  const [audioRecording, setAudioRecording] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [commentDrafts, setCommentDrafts] = useState({});
  const [expandedThread, setExpandedThread] = useState(null);
  const [filterCategory, setFilterCategory] = useState("");

  const loadThreads = useCallback(async () => {
    try {
      const payload = await apiRequest("/threads", { token });
      setThreads(payload || []);
    } catch {
      toast.error("Unable to load legacy threads.");
    }
  }, [token]);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const voice_note_data_url = await convertFileToDataUrl(audioFile);
      const finalVoice = audioRecording || voice_note_data_url;
      const payload = await apiRequest("/threads", {
        method: "POST",
        token,
        data: { ...form, voice_note_data_url: finalVoice || undefined },
      });
      setThreads((c) => [payload, ...c]);
      setForm(initialForm);
      setAudioFile(null);
      setAudioRecording(null);
      setShowForm(false);
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
        token,
        data: { text: commentDrafts[threadId] },
      });
      setThreads((c) => c.map((t) => (t.id === payload.id ? payload : t)));
      setCommentDrafts((c) => ({ ...c, [threadId]: "" }));
      toast.success("Response added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add response.");
    }
  };

  const filtered = filterCategory ? threads.filter((t) => t.category === filterCategory) : threads;

  return (
    <div className="space-y-6" data-testid="legacy-threads-page">
      <div className="archival-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BookOpen className="h-5 w-5 text-primary" />
            <div>
              <h2 className="font-display text-2xl text-foreground" data-testid="legacy-threads-title">Legacy Threads</h2>
              <p className="text-sm text-muted-foreground">Preserve stories, wisdom, and oral traditions. {threads.length} threads in the archive.</p>
            </div>
          </div>
          <Button className="rounded-full" data-testid="legacy-add-btn" onClick={() => setShowForm(!showForm)} size="sm">
            <Plus className="mr-1 h-4 w-4" /> New Thread
          </Button>
        </div>
      </div>

      {showForm && (
        <div className="archival-card" data-testid="legacy-form">
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleCreate}>
            <label className="block sm:col-span-2">
              <span className="text-xs font-semibold text-muted-foreground">Title</span>
              <Input className="field-input mt-1" data-testid="legacy-title" onChange={(e) => setForm((c) => ({ ...c, title: e.target.value }))} required value={form.title} />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">Category</span>
              <select className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" data-testid="legacy-category" onChange={(e) => setForm((c) => ({ ...c, category: e.target.value }))} value={form.category}>
                {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-muted-foreground">Speaker / Elder</span>
              <Input className="field-input mt-1" data-testid="legacy-elder" onChange={(e) => setForm((c) => ({ ...c, elder_name: e.target.value }))} value={form.elder_name} />
            </label>
            <label className="block sm:col-span-2">
              <span className="text-xs font-semibold text-muted-foreground">Thread body</span>
              <Textarea className="field-textarea mt-1" data-testid="legacy-body" onChange={(e) => setForm((c) => ({ ...c, body: e.target.value }))} required rows={4} value={form.body} />
            </label>
            <div className="sm:col-span-2 space-y-2">
              <span className="text-xs font-semibold text-muted-foreground">Voice reflection</span>
              <VoiceRecorder disabled={isSubmitting} onRecordingComplete={setAudioRecording} />
              <p className="text-xs text-muted-foreground">Or upload a file:</p>
              <Input className="field-input pt-3" data-testid="legacy-audio" onChange={(e) => setAudioFile(e.target.files?.[0] || null)} type="file" accept="audio/*" />
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <Button className="rounded-full" data-testid="legacy-submit" disabled={isSubmitting} size="sm" type="submit">
                {isSubmitting ? "Creating..." : "Create Thread"}
              </Button>
              <Button className="rounded-full" onClick={() => setShowForm(false)} size="sm" type="button" variant="outline">Cancel</Button>
            </div>
          </form>
        </div>
      )}

      {threads.length > 0 && (
        <div className="flex flex-wrap gap-2" data-testid="legacy-category-filters">
          {CATEGORIES.map((c) => (
            <button
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                filterCategory === c.value ? "bg-primary text-primary-foreground" : `${CATEGORY_COLORS[c.value] || "bg-muted text-muted-foreground"} hover:opacity-80`
              }`}
              data-testid={`legacy-filter-${c.value}`}
              key={c.value}
              onClick={() => setFilterCategory(filterCategory === c.value ? "" : c.value)}
            >
              {c.label}
            </button>
          ))}
          {filterCategory && (
            <button className="rounded-full px-3 py-1.5 text-xs font-semibold text-muted-foreground bg-muted" data-testid="legacy-filter-clear" onClick={() => setFilterCategory("")}>Clear</button>
          )}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        {filtered.length ? (
          filtered.map((thread) => (
            <article className="archival-card" data-testid={`legacy-thread-${thread.id}`} key={thread.id}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold mb-2 ${CATEGORY_COLORS[thread.category] || "bg-muted text-muted-foreground"}`}>
                    {CATEGORIES.find((c) => c.value === thread.category)?.label || thread.category}
                  </span>
                  <h3 className="text-lg font-semibold text-foreground leading-snug">{thread.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {thread.elder_name && <><span className="font-medium text-foreground/80">{thread.elder_name}</span> · </>}
                    {thread.author_name} · {formatDateTime(thread.created_at)}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm leading-7 text-muted-foreground line-clamp-4">{thread.body}</p>

              {thread.voice_note_data_url && (
                <div className="mt-4 soft-panel">
                  <div className="flex items-center gap-2 text-primary mb-2">
                    <Mic className="h-4 w-4" />
                    <span className="text-sm font-semibold">Voice reflection</span>
                  </div>
                  <audio className="w-full" controls src={thread.voice_note_data_url} />
                </div>
              )}

              <div className="mt-4">
                <button
                  className="text-sm font-medium text-primary hover:underline"
                  data-testid={`legacy-toggle-comments-${thread.id}`}
                  onClick={() => setExpandedThread(expandedThread === thread.id ? null : thread.id)}
                >
                  <MessageSquare className="inline h-3.5 w-3.5 mr-1" />
                  {thread.comments?.length || 0} responses {expandedThread === thread.id ? "(hide)" : "(show)"}
                </button>

                {expandedThread === thread.id && (
                  <div className="mt-3 space-y-3">
                    {thread.comments?.map((comment) => (
                      <div className="rounded-xl border border-border/60 bg-muted/30 px-4 py-3" key={comment.id}>
                        <p className="text-sm font-semibold text-foreground">{comment.author_name}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{comment.text}</p>
                      </div>
                    ))}
                    <div className="flex gap-2">
                      <Textarea
                        className="field-textarea flex-1"
                        data-testid={`legacy-comment-input-${thread.id}`}
                        onChange={(e) => setCommentDrafts((c) => ({ ...c, [thread.id]: e.target.value }))}
                        placeholder="Add a response to this thread..."
                        rows={2}
                        value={commentDrafts[thread.id] || ""}
                      />
                    </div>
                    <Button
                      className="rounded-full"
                      data-testid={`legacy-comment-submit-${thread.id}`}
                      onClick={() => handleComment(thread.id)}
                      size="sm"
                      variant="secondary"
                    >
                      Post Response
                    </Button>
                  </div>
                )}
              </div>
            </article>
          ))
        ) : (
          <div className="archival-card lg:col-span-2 text-center py-12" data-testid="legacy-empty-state">
            <BookOpen className="mx-auto h-10 w-10 text-muted-foreground/30 mb-4" />
            <p className="text-sm text-muted-foreground">
              {filterCategory ? "No threads in this category." : "No legacy threads yet. Start preserving stories and wisdom."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
