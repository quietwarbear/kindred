import { useCallback, useEffect, useState } from "react";
import {
  BookOpen, CalendarPlus, Check, Copy, HeartHandshake,
  MessageCircleQuestion, RefreshCw, Sparkles, UserPlus,
} from "lucide-react";
import { Link } from "react-router-dom";

import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const CopyButton = ({ text, testId }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary hover:bg-muted/60 transition"
      data-testid={testId}
      onClick={handleCopy}
      type="button"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
};

export const StewardPage = ({ token }) => {
  const [briefing, setBriefing] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [chronicle, setChronicle] = useState("");
  const [writing, setWriting] = useState(false);

  const writeChronicle = async () => {
    setWriting(true);
    try {
      const res = await apiRequest("/steward/history", { method: "POST", token });
      setChronicle(res.history || "");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't write the chronicle.");
    } finally {
      setWriting(false);
    }
  };

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const payload = await apiRequest("/steward/briefing", { token });
      setBriefing(payload);
    } catch (error) {
      toast.error(error.response?.data?.detail || "The steward is resting. Try again shortly.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const welcome = briefing?.welcome;
  const quiet = briefing?.quiet_members || [];
  const rediscover = briefing?.rediscover;
  const gathering = briefing?.suggested_gathering;
  const reflection = briefing?.reflection;

  return (
    <div className="space-y-6" data-testid="steward-page">
      <section className="archival-card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <Sparkles className="mt-1 h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Ubuntu Guide</p>
              <h2 className="mt-1 font-display text-3xl text-foreground" data-testid="steward-title">
                A word from your steward
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">
                Gentle, private suggestions to help {briefing?.community_name || "your community"} gather,
                remember, and look out for one another. The steward suggests — it never acts on its own.
              </p>
            </div>
          </div>
          <button
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:text-primary hover:bg-muted/60 transition"
            data-testid="steward-refresh"
            disabled={isLoading}
            onClick={load}
            type="button"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
        {briefing && briefing.ai_enabled === false && (
          <p className="mt-4 rounded-xl bg-muted/50 px-4 py-2 text-xs text-muted-foreground" data-testid="steward-simple-mode">
            Running in simple mode — set an AI key to let the steward speak in your community's voice.
          </p>
        )}
      </section>

      <section className="archival-card" data-testid="steward-chronicle">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-2">
            <BookOpen className="mt-0.5 h-4 w-4 text-primary" />
            <div>
              <p className="eyebrow-text">Our chronicle</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Let the steward weave your gatherings, memories, and stories into a chronicle to read aloud.
              </p>
            </div>
          </div>
          <button
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-primary hover:bg-muted/60 transition disabled:opacity-60"
            data-testid="steward-write-chronicle"
            disabled={writing}
            onClick={writeChronicle}
            type="button"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {writing ? "Writing…" : chronicle ? "Rewrite" : "Tell our story"}
          </button>
        </div>
        {chronicle && (
          <div className="mt-4 flex items-start gap-2">
            <p className="flex-1 whitespace-pre-line font-display text-lg leading-8 text-foreground" data-testid="steward-chronicle-text">{chronicle}</p>
            <CopyButton text={chronicle} testId="steward-chronicle-copy" />
          </div>
        )}
      </section>

      {isLoading ? (
        <section className="archival-card" data-testid="steward-loading">
          <p className="text-sm text-muted-foreground">The steward is listening to your community…</p>
        </section>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {welcome && (
            <article className="archival-card" data-testid="steward-welcome">
              <div className="flex items-center gap-2">
                <UserPlus className="h-4 w-4 text-primary" />
                <p className="eyebrow-text">Welcome someone new</p>
              </div>
              <h3 className="mt-2 font-display text-2xl text-foreground">{welcome.member_name}</h3>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">{welcome.message}</p>
              <div className="mt-4 flex items-center gap-2">
                <CopyButton text={welcome.message} testId="steward-welcome-copy" />
                <Link className="text-sm font-semibold text-primary" data-testid="steward-welcome-members-link" to="/members">
                  Open members
                </Link>
              </div>
            </article>
          )}

          <article className="archival-card" data-testid="steward-reach-out">
            <div className="flex items-center gap-2">
              <HeartHandshake className="h-4 w-4 text-primary" />
              <p className="eyebrow-text">Reach out</p>
            </div>
            {quiet.length ? (
              <>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">
                  We haven't heard from these folks in a while. A small hello goes a long way.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {quiet.map((m) => (
                    <span className="rounded-full bg-muted/60 px-3 py-1.5 text-sm font-medium text-foreground" data-testid={`steward-quiet-${m.id}`} key={m.id}>
                      {m.name}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm leading-7 text-muted-foreground">
                Everyone's been part of things lately. Your circle is well-tended.
              </p>
            )}
          </article>

          {rediscover && (
            <article className="archival-card" data-testid="steward-rediscover">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-primary" />
                <p className="eyebrow-text">Worth remembering</p>
              </div>
              <h3 className="mt-2 text-lg font-semibold text-foreground">{rediscover.title}</h3>
              <p className="mt-2 text-sm leading-7 text-muted-foreground">{rediscover.note}</p>
              <Link
                className="mt-3 inline-block text-sm font-semibold text-primary"
                data-testid="steward-rediscover-link"
                to={rediscover.type === "thread" ? "/legacy-threads" : "/memories"}
              >
                {rediscover.type === "thread" ? "Open the story" : "Open the memory"}
              </Link>
            </article>
          )}

          {gathering?.title && (
            <article className="archival-card" data-testid="steward-gathering">
              <div className="flex items-center gap-2">
                <CalendarPlus className="h-4 w-4 text-primary" />
                <p className="eyebrow-text">An idea for next time</p>
              </div>
              <h3 className="mt-2 font-display text-2xl text-foreground">{gathering.title}</h3>
              {gathering.why && <p className="mt-2 text-sm leading-7 text-muted-foreground">{gathering.why}</p>}
              <Link className="mt-3 inline-block text-sm font-semibold text-primary" data-testid="steward-gathering-link" to="/gatherings">
                Plan a gathering
              </Link>
            </article>
          )}

          {reflection && (
            <article className="archival-card lg:col-span-2" data-testid="steward-reflection">
              <div className="flex items-center gap-2">
                <MessageCircleQuestion className="h-4 w-4 text-primary" />
                <p className="eyebrow-text">To sit with this week</p>
              </div>
              <p className="mt-3 font-display text-2xl leading-snug text-foreground">{reflection}</p>
            </article>
          )}
        </div>
      )}
    </div>
  );
};

export default StewardPage;
