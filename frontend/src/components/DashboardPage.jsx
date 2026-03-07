import { useEffect, useState } from "react";
import { ArrowRight, CalendarClock, Camera, Coins, MessageSquareQuote, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { apiRequest, formatDateTime, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const statConfig = [
  { key: "members", label: "Members", icon: Users },
  { key: "events", label: "Events", icon: CalendarClock },
  { key: "memories", label: "Memories", icon: Camera },
  { key: "threads", label: "Threads", icon: MessageSquareQuote },
  { key: "funds_raised", label: "Raised", icon: Coins },
];

export const DashboardPage = ({ token, community }) => {
  const [overview, setOverview] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadOverview = async () => {
      try {
        const payload = await apiRequest("/community/overview", { token });
        setOverview(payload);
      } catch (error) {
        toast.error(error.response?.data?.detail || "Unable to load the dashboard.");
      } finally {
        setIsLoading(false);
      }
    };

    loadOverview();
  }, [token]);

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Community pulse</p>
        <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl" data-testid="dashboard-community-title">
              {community?.name}
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="dashboard-community-description">
              {community?.description}
            </p>
          </div>
          <div className="soft-panel max-w-sm" data-testid="dashboard-community-motto">
            <p className="eyebrow-text">Community motto</p>
            <p className="mt-2 text-sm leading-7 text-foreground">{community?.motto || "Rooted in memory, gathered in purpose."}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-5">
        {statConfig.map(({ key, label, icon: Icon }) => (
          <article className="archival-card" data-testid={`dashboard-stat-${key}`} key={key}>
            <Icon className="h-5 w-5 text-primary" />
            <p className="mt-4 text-sm text-muted-foreground">{label}</p>
            <p className="mt-2 font-display text-4xl text-foreground">
              {key === "funds_raised"
                ? shortCurrency(overview?.stats?.[key] || 0)
                : isLoading
                  ? "…"
                  : overview?.stats?.[key] || 0}
            </p>
          </article>
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="archival-card" data-testid="dashboard-upcoming-events">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="eyebrow-text">Next gatherings</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Upcoming events</h3>
            </div>
            <Link className="text-sm font-semibold text-primary" data-testid="dashboard-go-events-link" to="/events">
              Open Events Hub
            </Link>
          </div>
          <div className="mt-6 space-y-4">
            {overview?.upcoming_events?.length ? (
              overview.upcoming_events.map((event) => (
                <div className="soft-panel" data-testid={`dashboard-event-${event.id}`} key={event.id}>
                  <p className="text-lg font-semibold text-foreground">{event.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{formatDateTime(event.start_at)} · {event.location}</p>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">{event.description}</p>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="dashboard-events-empty">
                <p className="text-sm text-muted-foreground">No gatherings scheduled yet. Start with your first event in the Events Hub.</p>
              </div>
            )}
          </div>
        </article>

        <div className="space-y-6">
          <article className="archival-card" data-testid="dashboard-recent-memories">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="eyebrow-text">Living archive</p>
                <h3 className="mt-2 font-display text-3xl text-foreground">Recent memories</h3>
              </div>
              <Link className="text-sm font-semibold text-primary" data-testid="dashboard-go-memories-link" to="/memories">
                Open vault
              </Link>
            </div>
            <div className="mt-6 space-y-4">
              {overview?.recent_memories?.length ? (
                overview.recent_memories.slice(0, 3).map((memory) => (
                  <div className="soft-panel" data-testid={`dashboard-memory-${memory.id}`} key={memory.id}>
                    <p className="text-base font-semibold text-foreground">{memory.title}</p>
                    <p className="mt-2 text-sm text-muted-foreground">{memory.event_title}</p>
                    <p className="mt-3 text-sm leading-7 text-muted-foreground">{memory.ai_summary || memory.description}</p>
                  </div>
                ))
              ) : (
                <div className="soft-panel" data-testid="dashboard-memories-empty">
                  <p className="text-sm text-muted-foreground">Your archive starts with one memory. Upload a photo or voice note to begin.</p>
                </div>
              )}
            </div>
          </article>

          <article className="archival-card" data-testid="dashboard-recent-threads">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="eyebrow-text">Epistemology</p>
                <h3 className="mt-2 font-display text-3xl text-foreground">Legacy threads</h3>
              </div>
              <Link className="text-sm font-semibold text-primary" data-testid="dashboard-go-threads-link" to="/threads">
                Enter threads
              </Link>
            </div>
            <div className="mt-6 space-y-4">
              {overview?.recent_threads?.length ? (
                overview.recent_threads.slice(0, 3).map((thread) => (
                  <div className="soft-panel" data-testid={`dashboard-thread-${thread.id}`} key={thread.id}>
                    <p className="text-base font-semibold text-foreground">{thread.title}</p>
                    <p className="mt-2 text-sm text-muted-foreground">{thread.category}</p>
                    <p className="mt-3 line-clamp-3 text-sm leading-7 text-muted-foreground">{thread.body}</p>
                  </div>
                ))
              ) : (
                <div className="soft-panel" data-testid="dashboard-threads-empty">
                  <p className="text-sm text-muted-foreground">Create the first oral history or reflection thread to anchor the archive.</p>
                </div>
              )}
            </div>
          </article>
        </div>
      </section>

      <section className="archival-card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between" data-testid="dashboard-action-banner">
        <div>
          <p className="eyebrow-text">Next move</p>
          <h3 className="mt-2 font-display text-3xl text-foreground">Invite your organizers and start planning the next gathering.</h3>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">Hosts and organizers can bring in members, assign roles, and move from vision to coordination fast.</p>
        </div>
        <Link className="pill-button" data-testid="dashboard-invite-cta" to="/members">
          Open members space
          <ArrowRight className="ml-2 h-4 w-4" />
        </Link>
      </section>
    </div>
  );
};