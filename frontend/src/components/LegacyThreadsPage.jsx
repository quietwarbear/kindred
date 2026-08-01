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

export const LegacyThreadsPage = ({ token, user }) => {
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

  const [lt, setLt] = useState({ connection_status: "unavailable", transfer_status: "unavailable" });
  const [recipePreview, setRecipePreview] = useState(null);
  const [previewingId, setPreviewingId] = useState(null);
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [transferBusy, setTransferBusy] = useState(false);

  const loadLt = useCallback(async () => {
    try {
      const status = await apiRequest("/legacy-table/status", { token });
      setLt(status || { connection_status: "unavailable", transfer_status: "unavailable" });
    } catch {
      /* non-fatal — Legacy Table is optional */
    }
  }, [token]);

  useEffect(() => { loadLt(); }, [loadLt]);

  const openLegacyTable = async () => {
    try {
      const res = await apiRequest("/federation/jump", { method: "POST", token, data: { target: "legacy_table" } });
      window.open(res.url, "_blank", "noopener");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't open Legacy Table.");
    }
  };

  const previewRecipe = async (threadId) => {
    setPreviewingId(threadId);
    setConsentAccepted(false);
    try {
      const preview = await apiRequest("/legacy-table/recipe-preview", { method: "POST", token, data: { thread_id: threadId } });
      setRecipePreview({ ...preview, threadId });
    } catch (error) {
      toast.error(error.response?.data?.detail || "This recipe cannot be previewed for transfer.");
    } finally {
      setPreviewingId(null);
    }
  };

  const startRecipeTransfer = async () => {
    if (!recipePreview?.threadId || !consentAccepted || lt.transfer_status !== "ready") return;
    setTransferBusy(true);
    try {
      const result = await apiRequest("/legacy-table/transfers/start", {
        method: "POST",
        token,
        data: { thread_id: recipePreview.threadId, consent_confirmed: true },
      });
      const resumableStates = new Set(["grant_ready", "payload_retrieved", "destination_pending", "destination_accepted"]);
      if (!result?.url || !resumableStates.has(result.status)) throw new Error("transfer_unavailable");
      window.location.assign(result.url);
    } catch {
      toast.error("The private transfer could not start. Your Kindred recipe is unchanged.");
      setTransferBusy(false);
    }
  };

  const [oralBusy, setOralBusy] = useState({}); // { [threadId]: "transcribe" | "translate" }
  const [langView, setLangView] = useState({}); // { [threadId]: "en" | "es" | "yo" }

  const transcribeThread = async (threadId) => {
    setOralBusy((c) => ({ ...c, [threadId]: "transcribe" }));
    try {
      const payload = await apiRequest(`/threads/${threadId}/transcribe`, { method: "POST", token });
      setThreads((c) => c.map((t) => (t.id === payload.id ? payload : t)));
      toast.success("Voice note transcribed — the words are preserved.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't transcribe right now.");
    } finally {
      setOralBusy((c) => ({ ...c, [threadId]: null }));
    }
  };

  const translateThread = async (threadId) => {
    setOralBusy((c) => ({ ...c, [threadId]: "translate" }));
    try {
      const payload = await apiRequest(`/threads/${threadId}/translate`, { method: "POST", token });
      setThreads((c) => c.map((t) => (t.id === payload.id ? payload : t)));
      toast.success("Story translated — it reaches the whole family now.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't translate right now.");
    } finally {
      setOralBusy((c) => ({ ...c, [threadId]: null }));
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
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${lt.connection_status === "ready" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300" : "bg-muted text-muted-foreground"}`} data-testid="legacy-lt-status">
                  {lt.connection_status === "ready" ? (<><Check className="h-3 w-3" /> Sign-in ready</>) : (lt.connection_status || "unavailable").replaceAll("_", " ")}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Legacy Table is optional. Recipe delivery requires your explicit approval and an authenticated Legacy Table account.
              </p>
            </div>
          </div>
          <span className="shrink-0 rounded-full bg-muted px-3 py-1 text-xs font-semibold text-muted-foreground" data-testid="legacy-lt-transfer-status">Transfer {lt.transfer_status || "unavailable"}</span>
        </div>
        {lt.sso_status === "ready" && (
          <button
            className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-muted/60"
            data-testid="legacy-open-lt"
            onClick={openLegacyTable}
            type="button"
          >
            <Utensils className="h-3.5 w-3.5" /> Open Legacy Table →
          </button>
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
                <Utensils className="h-3.5 w-3.5" /> Kindred keeps the original. Its author can later inspect a read-only Legacy Table transfer preview.
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
                  {thread.legacy_table_transfer_state === "completed" ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600" data-testid={`legacy-recipe-synced-${thread.id}`}>
                      <Check className="h-3.5 w-3.5" /> Sent to Legacy Table
                    </span>
                  ) : thread.created_by_id === user?.id ? (
                    <button
                      className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary hover:bg-muted/60 transition disabled:opacity-60"
                      data-testid={`legacy-send-recipe-${thread.id}`}
                      disabled={previewingId === thread.id}
                      onClick={() => previewRecipe(thread.id)}
                      type="button"
                    >
                      <Utensils className="h-3.5 w-3.5" />
                      {previewingId === thread.id ? "Preparing preview…" : "Preview Legacy Table transfer"}
                    </button>
                  ) : <p className="text-xs text-muted-foreground">Only the recipe author can open a transfer preview.</p>}
                </div>
              )}

              {recipePreview?.threadId === thread.id && (
                <div className="mt-4 rounded-2xl border border-primary/30 bg-primary/5 p-4" data-testid={`legacy-consent-preview-${thread.id}`}>
                  <p className="font-semibold text-foreground">Exact transfer preview</p>
                  <p className="mt-2 text-sm font-medium text-foreground">{recipePreview.selected_content.title}</p>
                  <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{recipePreview.selected_content.instructions_or_story}</p>
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                    <li>Your account identity is required for cross-product sign-in.</li>
                    <li>Only this selected title and instructions or story would leave Kindred.</li>
                    <li>The destination may create a family cookbook and manages its own retention and deletion.</li>
                  </ul>
                  <label className="mt-3 flex items-start gap-2 text-xs text-foreground">
                    <input checked={consentAccepted} data-testid={`legacy-consent-${thread.id}`} onChange={(event) => setConsentAccepted(event.target.checked)} type="checkbox" />
                    I understand exactly what would leave Kindred.
                  </label>
                  {lt.transfer_status !== "ready" && (
                    <p className="mt-3 text-xs font-semibold text-amber-700" data-testid={`legacy-transfer-blocked-${thread.id}`}>Private transfer is not configured. Your Kindred recipe is unchanged.</p>
                  )}
                  <Button
                    className="mt-3 rounded-full"
                    data-testid={`legacy-transfer-confirm-${thread.id}`}
                    disabled={!consentAccepted || lt.transfer_status !== "ready" || transferBusy}
                    onClick={startRecipeTransfer}
                    size="sm"
                  >
                    {transferBusy ? "Opening Legacy Table…" : "Continue to Legacy Table"}
                  </Button>
                  <Button className="ml-2 mt-3 rounded-full" onClick={() => { setRecipePreview(null); setConsentAccepted(false); }} size="sm" variant="outline">Close</Button>
                </div>
              )}

              {thread.voice_note_data_url && (
                <div className="mt-4 soft-panel">
                  <div className="flex items-center gap-2 text-primary mb-2">
                    <Mic className="h-4 w-4" />
                    <span className="text-sm font-semibold">Voice reflection</span>
                  </div>
                  <audio className="w-full" controls src={thread.voice_note_data_url} />
                  {!thread.transcript && (
                    <button
                      className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-muted/60 disabled:opacity-60"
                      data-testid={`legacy-transcribe-${thread.id}`}
                      disabled={oralBusy[thread.id] === "transcribe"}
                      onClick={() => transcribeThread(thread.id)}
                      type="button"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      {oralBusy[thread.id] === "transcribe" ? "Transcribing…" : "Transcribe this voice note"}
                    </button>
                  )}
                </div>
              )}

              {(thread.transcript || (thread.translations && (thread.translations.es || thread.translations.yo))) && (
                <div className="mt-4 soft-panel" data-testid={`legacy-oral-${thread.id}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-primary">
                      <BookOpen className="h-4 w-4" />
                      <span className="text-sm font-semibold">Preserved words</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {[
                        { key: "en", label: "Original" },
                        { key: "es", label: "Español" },
                        { key: "yo", label: "Yorùbá" },
                      ].map((opt) => {
                        const available = opt.key === "en" ? !!thread.transcript : !!(thread.translations && thread.translations[opt.key]);
                        if (!available) return null;
                        const active = (langView[thread.id] || "en") === opt.key;
                        return (
                          <button
                            className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:opacity-80"}`}
                            data-testid={`legacy-lang-${opt.key}-${thread.id}`}
                            key={opt.key}
                            onClick={() => setLangView((c) => ({ ...c, [thread.id]: opt.key }))}
                            type="button"
                          >
                            {opt.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <p className="mt-3 whitespace-pre-line text-sm leading-7 text-foreground/90" data-testid={`legacy-transcript-${thread.id}`}>
                    {(langView[thread.id] || "en") === "en"
                      ? thread.transcript
                      : (thread.translations && thread.translations[langView[thread.id]]) || thread.transcript}
                  </p>
                  {(thread.transcript || thread.body) && !(thread.translations && (thread.translations.es || thread.translations.yo)) && (
                    <button
                      className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-muted/60 disabled:opacity-60"
                      data-testid={`legacy-translate-${thread.id}`}
                      disabled={oralBusy[thread.id] === "translate"}
                      onClick={() => translateThread(thread.id)}
                      type="button"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      {oralBusy[thread.id] === "translate" ? "Translating…" : "Translate to Español + Yorùbá"}
                    </button>
                  )}
                </div>
              )}

              {!thread.voice_note_data_url && !thread.transcript && thread.body && !(thread.translations && (thread.translations.es || thread.translations.yo)) && (
                <div className="mt-3">
                  <button
                    className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-muted/60 disabled:opacity-60"
                    data-testid={`legacy-translate-body-${thread.id}`}
                    disabled={oralBusy[thread.id] === "translate"}
                    onClick={() => translateThread(thread.id)}
                    type="button"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {oralBusy[thread.id] === "translate" ? "Translating…" : "Translate to Español + Yorùbá"}
                  </button>
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
