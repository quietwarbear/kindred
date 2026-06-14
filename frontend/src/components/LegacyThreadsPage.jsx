import { useCallback, useEffect, useState } from "react";
import { BookOpen, Check, MessageSquare, Mic, Plus, Sparkles, Utensils } from "lucide-react";

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

// Prompts that give the archive a starting point so it never sits empty.
// Kept here (static v1) — an Ubuntu Intelligence layer can generate these later.
const ELDER_PROMPTS = [
  { category: "oral-history", text: "What is your earliest happy memory of this family?" },
  { category: "oral-history", text: "Who do you most want the young ones to remember, and why?" },
  { category: "family-lore", text: "Where does our family name come from, and what story travels with it?" },
  { category: "family-lore", text: "What is a tradition we keep that no one remembers the origin of?" },
  { category: "migration-story", text: "Tell the story of how our family came to live where we are now." },
  { category: "migration-story", text: "Who was the first to leave home, and what did they carry with them?" },
  { category: "recipe-tradition", text: "Whose recipe do we make on special days, and what is the secret to it?" },
  { category: "recipe-tradition", text: "Describe a meal that means “home” — who made it, and where?" },
  { category: "sermon", text: "Record a word, scripture, or blessing you want this community to hold onto." },
  { category: "youth-reflection", text: "What is one question you have always wanted to ask an elder?" },
  { category: "community-dialogue", text: "When did this community show up for one of its own?" },
];

// Deterministic per day: everyone sees the same three prompts on a given date.
const promptsForToday = (() => {
  const dayIndex = Math.floor(Date.now() / 86400000);
  const count = Math.min(3, ELDER_PROMPTS.length);
  const start = dayIndex % ELDER_PROMPTS.length;
  return Array.from({ length: count }, (_, i) => ELDER_PROMPTS[(start + i) % ELDER_PROMPTS.length]);
})();

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

  const startFromPrompt = (prompt) => {
    setForm({ ...initialForm, title: prompt.text, category: prompt.category });
    setAudioFile(null);
    setAudioRecording(null);
    setShowForm(true);
  };

  const [lt, setLt] = useState({ sso_enabled: false });
  const [syncingId, setSyncingId] = useState(null);

  const loadLt = useCallback(async () => {
    try {
      const status = await apiRequest("/legacy-table/status", { token });
      setLt(status || { sso_enabled: false });
    } catch {
      /* non-fatal — Legacy Table is optional */
    }
  }, [token]);

  useEffect(() => { loadLt(); }, [loadLt]);

  const sendRecipe = async (threadId) => {
    setSyncingId(threadId);
    try {
      const res = await apiRequest(`/legacy-table/sync-recipe/${threadId}`, { method: "POST", token });
      setThreads((c) => c.map((t) => (t.id === threadId ? { ...t, legacy_table_recipe_id: res.recipe_id, legacy_table_synced_at: res.synced_at } : t)));
      toast.success("Recipe sent to Legacy Table — where family recipes live forever.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't send to Legacy Table.");
    } finally {
      setSyncingId(null);
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

      <div className="archival-card" data-testid="legacy-lt-connect">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
              <Utensils className="h-4 w-4 text-primary" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="font-semibold text-foreground">Legacy Table</p>
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${lt.sso_enabled ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300" : "bg-muted text-muted-foreground"}`} data-testid="legacy-lt-status">
                  {lt.sso_enabled ? (<><Check className="h-3 w-3" /> Connected</>) : "Not connected"}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {lt.sso_enabled
                  ? (<>Recipes you send are saved to Legacy Table as <span className="font-medium text-foreground/80">{lt.connected_as || "you"}</span> — where family recipes live forever. No second login.</>)
                  : "Recipe sync switches on once the shared connection is configured. No extra login — your Kindred identity carries over."}
              </p>
            </div>
          </div>
          {lt.sso_enabled && (
            <div className="shrink-0 text-right">
              <p className="font-display text-2xl text-foreground" data-testid="legacy-lt-synced-count">{lt.recipes_synced || 0}</p>
              <p className="text-xs text-muted-foreground">recipe{(lt.recipes_synced || 0) === 1 ? "" : "s"} sent</p>
            </div>
          )}
        </div>
        {lt.sso_enabled && lt.last_sync_at && (
          <p className="mt-3 text-xs text-muted-foreground" data-testid="legacy-lt-last-sync">
            Last sync: {formatDateTime(lt.last_sync_at)}{lt.last_sync_result ? ` · ${lt.last_sync_result}` : ""}
          </p>
        )}
      </div>

      {!showForm && (
        <div className="archival-card" data-testid="legacy-prompts">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <p className="eyebrow-text">A prompt to get you started</p>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {promptsForToday.map((prompt) => (
              <button
                className="soft-panel text-left transition-all hover:border-primary/40"
                data-testid="legacy-prompt-card"
                key={prompt.text}
                onClick={() => startFromPrompt(prompt)}
                type="button"
              >
                <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${CATEGORY_COLORS[prompt.category] || "bg-muted text-muted-foreground"}`}>
                  {CATEGORIES.find((c) => c.value === prompt.category)?.label || prompt.category}
                </span>
                <p className="mt-2 text-sm leading-6 text-foreground">{prompt.text}</p>
                <span className="mt-2 inline-flex items-center text-xs font-semibold text-primary">Start this thread →</span>
              </button>
            ))}
          </div>
        </div>
      )}

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
            {form.category === "recipe-tradition" && (
              <p className="sm:col-span-2 -mt-1 flex items-center gap-1.5 text-xs text-primary" data-testid="legacy-recipe-hint">
                <Utensils className="h-3.5 w-3.5" /> This can travel to Legacy Table once you save it — where family recipes live forever.
              </p>
            )}
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

              {thread.category === "recipe-tradition" && (
                <div className="mt-3">
                  {thread.legacy_table_recipe_id ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600" data-testid={`legacy-recipe-synced-${thread.id}`}>
                      <Check className="h-3.5 w-3.5" /> Sent to Legacy Table
                    </span>
                  ) : (
                    <button
                      className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary hover:bg-muted/60 transition disabled:opacity-60"
                      data-testid={`legacy-send-recipe-${thread.id}`}
                      disabled={syncingId === thread.id}
                      onClick={() => sendRecipe(thread.id)}
                      type="button"
                    >
                      <Utensils className="h-3.5 w-3.5" />
                      {syncingId === thread.id ? "Sending…" : "Send to Legacy Table"}
                    </button>
                  )}
                </div>
              )}

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
