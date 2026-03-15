import { useCallback, useEffect, useState } from "react";
import { Clock3, Download, Filter, Image as ImageIcon, Mic, MessageSquareQuote, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, BACKEND_URL, convertFileToDataUrl, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { VoiceRecorder } from "@/components/VoiceRecorder";

const initialMemoryForm = {
  event_id: "",
  title: "",
  description: "",
};

const initialStoryForm = {
  title: "",
  category: "oral-history",
  body: "",
  elder_name: "",
};

export const TimelinePage = ({ token }) => {
  const [timeline, setTimeline] = useState([]);
  const [onThisDay, setOnThisDay] = useState([]);
  const [events, setEvents] = useState([]);
  const [memoryForm, setMemoryForm] = useState(initialMemoryForm);
  const [storyForm, setStoryForm] = useState(initialStoryForm);
  const [memoryImage, setMemoryImage] = useState(null);
  const [memoryAudio, setMemoryAudio] = useState(null);
  const [memoryRecording, setMemoryRecording] = useState(null);
  const [storyAudio, setStoryAudio] = useState(null);
  const [storyRecording, setStoryRecording] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState("");

  const loadTimeline = useCallback(async () => {
    try {
      const [timelinePayload, eventsPayload] = await Promise.all([
        apiRequest("/timeline/archive", { token }),
        apiRequest("/events", { token }),
      ]);
      setTimeline(timelinePayload.timeline_items || []);
      setOnThisDay(timelinePayload.on_this_day || []);
      setEvents(eventsPayload || []);
      setMemoryForm((current) => ({ ...current, event_id: current.event_id || eventsPayload?.[0]?.id || "" }));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load timeline archive.");
    }
  }, [token]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  const filteredTimeline = timeline.filter((item) => {
    if (filterType && item.type !== filterType) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        item.title?.toLowerCase().includes(q) ||
        item.description?.toLowerCase().includes(q) ||
        item.subtitle?.toLowerCase().includes(q) ||
        item.tags?.some((tag) => tag.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const handleExportCSV = () => {
    const exportUrl = `${BACKEND_URL}/api/timeline/export?format=csv${filterType ? `&item_type=${filterType}` : ""}`;
    const link = document.createElement("a");
    link.href = exportUrl;
    link.download = "kindred_timeline.csv";
    // For authenticated export, we'll use fetch
    fetch(exportUrl, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "kindred_timeline.csv";
        a.click();
        URL.revokeObjectURL(url);
        toast.success("Timeline exported as CSV.");
      })
      .catch(() => toast.error("Unable to export timeline."));
  };

  const handleCreateMemory = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const [image_data_url, voice_note_data_url] = await Promise.all([
        convertFileToDataUrl(memoryImage),
        convertFileToDataUrl(memoryAudio),
      ]);
      const finalVoice = memoryRecording || voice_note_data_url;
      await apiRequest("/memories", {
        method: "POST",
        token,
        data: {
          ...memoryForm,
          image_data_url: image_data_url || undefined,
          voice_note_data_url: finalVoice || undefined,
        },
      });
      setMemoryForm({ ...initialMemoryForm, event_id: memoryForm.event_id });
      setMemoryImage(null);
      setMemoryAudio(null);
      setMemoryRecording(null);
      toast.success("Memory added to the timeline.");
      loadTimeline();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add memory.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateStory = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const voice_note_data_url = await convertFileToDataUrl(storyAudio);
      const finalVoice = storyRecording || voice_note_data_url;
      await apiRequest("/threads", {
        method: "POST",
        token,
        data: {
          ...storyForm,
          voice_note_data_url: finalVoice || undefined,
        },
      });
      setStoryForm(initialStoryForm);
      setStoryAudio(null);
      setStoryRecording(null);
      toast.success("Story thread added to the archive.");
      loadTimeline();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add story thread.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Timeline & Memory Archive</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="timeline-page-title">
          A living record of gatherings, stories, photos, and reflections.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="timeline-page-copy">
          Capture emotional lock-in through a unified archive: event history, media, oral stories, and the kinds of reminders that bring people back together.
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="archival-card" data-testid="timeline-memory-form-card">
          <div className="flex items-center gap-3">
            <ImageIcon className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Upload Photos / Stories</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Add a memory item</h3>
            </div>
          </div>
          <form className="mt-6 grid gap-4" onSubmit={handleCreateMemory}>
            <label>
              <span className="field-label">Gathering</span>
              <select className="field-input w-full" data-testid="timeline-memory-event-select" onChange={(e) => setMemoryForm((current) => ({ ...current, event_id: e.target.value }))} required value={memoryForm.event_id}>
                <option value="">Select a gathering</option>
                {events.map((eventItem) => (
                  <option key={eventItem.id} value={eventItem.id}>{eventItem.title}</option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">Title</span>
              <Input className="field-input" data-testid="timeline-memory-title-input" onChange={(e) => setMemoryForm((current) => ({ ...current, title: e.target.value }))} required value={memoryForm.title} />
            </label>
            <label>
              <span className="field-label">Story or context</span>
              <Textarea className="field-textarea" data-testid="timeline-memory-description-input" onChange={(e) => setMemoryForm((current) => ({ ...current, description: e.target.value }))} required value={memoryForm.description} />
            </label>
            <label>
              <span className="field-label">Photo</span>
              <Input className="field-input pt-3" data-testid="timeline-memory-image-input" onChange={(e) => setMemoryImage(e.target.files?.[0] || null)} type="file" accept="image/*" />
            </label>
            <div>
              <span className="field-label">Voice note</span>
              <div className="mt-1"><VoiceRecorder disabled={isSubmitting} onRecordingComplete={setMemoryRecording} /></div>
              <p className="mt-2 text-xs text-muted-foreground">Or upload a file:</p>
              <Input className="field-input pt-3" data-testid="timeline-memory-audio-input" onChange={(e) => setMemoryAudio(e.target.files?.[0] || null)} type="file" accept="audio/*" />
            </div>
            <Button className="rounded-full" data-testid="timeline-memory-submit-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Saving..." : "Save memory to timeline"}
            </Button>
          </form>
        </article>

        <article className="archival-card" data-testid="timeline-story-form-card">
          <div className="flex items-center gap-3">
            <MessageSquareQuote className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Legacy Threads</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Add a story thread</h3>
            </div>
          </div>
          <form className="mt-6 grid gap-4" onSubmit={handleCreateStory}>
            <label>
              <span className="field-label">Title</span>
              <Input className="field-input" data-testid="timeline-story-title-input" onChange={(e) => setStoryForm((current) => ({ ...current, title: e.target.value }))} required value={storyForm.title} />
            </label>
            <label>
              <span className="field-label">Category</span>
              <select className="field-input w-full" data-testid="timeline-story-category-select" onChange={(e) => setStoryForm((current) => ({ ...current, category: e.target.value }))} value={storyForm.category}>
                <option value="oral-history">Oral history</option>
                <option value="sermon">Sermon archive</option>
                <option value="youth-reflection">Youth reflection</option>
                <option value="community-dialogue">Community dialogue</option>
              </select>
            </label>
            <label>
              <span className="field-label">Speaker / elder</span>
              <Input className="field-input" data-testid="timeline-story-elder-input" onChange={(e) => setStoryForm((current) => ({ ...current, elder_name: e.target.value }))} value={storyForm.elder_name} />
            </label>
            <label>
              <span className="field-label">Thread body</span>
              <Textarea className="field-textarea" data-testid="timeline-story-body-input" onChange={(e) => setStoryForm((current) => ({ ...current, body: e.target.value }))} required value={storyForm.body} />
            </label>
            <div>
              <span className="field-label">Voice reflection</span>
              <div className="mt-1"><VoiceRecorder disabled={isSubmitting} onRecordingComplete={setStoryRecording} /></div>
              <p className="mt-2 text-xs text-muted-foreground">Or upload a file:</p>
              <Input className="field-input pt-3" data-testid="timeline-story-audio-input" onChange={(e) => setStoryAudio(e.target.files?.[0] || null)} type="file" accept="audio/*" />
            </div>
            <Button className="rounded-full" data-testid="timeline-story-submit-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Saving..." : "Add story thread"}
            </Button>
          </form>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <article className="archival-card" data-testid="timeline-on-this-day-card">
          <div className="flex items-center gap-3">
            <Clock3 className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">On this day</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Anniversary reminders</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {onThisDay.length ? (
              onThisDay.map((item) => (
                <div className="soft-panel" data-testid={`timeline-anniversary-${item.id}`} key={item.id}>
                  <p className="text-base font-semibold text-foreground">{item.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{formatDateTime(item.start_at)} · {item.location}</p>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="timeline-anniversary-empty-state">
                <p className="text-sm text-muted-foreground">No exact-date anniversaries today yet, but the archive is ready for them.</p>
              </div>
            )}
          </div>
        </article>

        <article className="archival-card" data-testid="timeline-feed-card">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="eyebrow-text">Automatic Timeline Generation</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Unified archive feed</h3>
            </div>
            <Button className="rounded-full shrink-0" data-testid="timeline-export-csv" onClick={handleExportCSV} size="sm" variant="outline">
              <Download className="mr-1 h-3.5 w-3.5" /> Export CSV
            </Button>
          </div>

          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="field-input pl-9"
                data-testid="timeline-search-input"
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search timeline..."
                value={searchQuery}
              />
            </div>
            <div className="flex gap-2">
              {["gathering", "memory", "story"].map((type) => (
                <button
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                    filterType === type
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                  data-testid={`timeline-filter-${type}`}
                  key={type}
                  onClick={() => setFilterType(filterType === type ? "" : type)}
                >
                  {type}
                </button>
              ))}
              {(filterType || searchQuery) && (
                <button
                  className="rounded-full px-3 py-1.5 text-xs font-semibold text-muted-foreground bg-muted hover:bg-muted/80"
                  data-testid="timeline-filter-clear"
                  onClick={() => { setFilterType(""); setSearchQuery(""); }}
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          <p className="mt-3 text-xs text-muted-foreground">{filteredTimeline.length} of {timeline.length} items</p>

          <div className="mt-4 space-y-4">
            {filteredTimeline.length ? (
              filteredTimeline.map((item) => (
                <div className="soft-panel" data-testid={`timeline-item-${item.type}-${item.id}`} key={`${item.type}-${item.id}`}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-lg font-semibold text-foreground">{item.title}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{item.subtitle || item.type} · {formatDateTime(item.occurred_at)}</p>
                    </div>
                    <div className="rounded-full border border-border bg-background/80 px-4 py-2 text-xs uppercase tracking-[0.16em] text-primary" data-testid={`timeline-item-type-${item.id}`}>
                      {item.type}
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{item.description}</p>
                  {item.image_data_url ? <img alt={item.title} className="mt-4 aspect-[4/3] w-full rounded-[20px] object-cover object-center" data-testid={`timeline-item-image-${item.id}`} src={item.image_data_url} /> : null}
                  {item.voice_note_data_url ? (
                    <div className="mt-4">
                      <div className="mb-2 flex items-center gap-2 text-primary">
                        <Mic className="h-4 w-4" />
                        <p className="text-sm font-semibold">Attached audio</p>
                      </div>
                      <audio className="w-full" controls src={item.voice_note_data_url} />
                    </div>
                  ) : null}
                  <div className="mt-4 flex flex-wrap gap-2">
                    {item.tags?.map((tag) => (
                      <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" data-testid={`timeline-item-tag-${item.id}-${tag.replace(/\s+/g, "-")}`} key={`${item.id}-${tag}`}>
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="timeline-feed-empty-state">
                <p className="text-sm text-muted-foreground">
                  {searchQuery || filterType
                    ? "No items match your filters. Try broadening your search."
                    : "The timeline will fill up as your community gathers, uploads memories, and records reflections."}
                </p>
              </div>
            )}
          </div>
        </article>
      </section>
    </div>
  );
};