import { useCallback, useEffect, useState } from "react";
import { Activity, Calendar, ChevronLeft, ChevronRight, Filter, MessageSquare, Users, Vote, CreditCard, Bell, Megaphone } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiRequest, formatDateTime } from "@/lib/api";

const EVENT_TYPE_META = {
  "event-create": { icon: Calendar, label: "Gathering Created", color: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40" },
  "rsvp-update": { icon: Users, label: "RSVP Update", color: "text-blue-600 bg-blue-50 dark:bg-blue-950/40" },
  "announcement": { icon: Megaphone, label: "Announcement", color: "text-amber-600 bg-amber-50 dark:bg-amber-950/40" },
  "announcement-comment": { icon: MessageSquare, label: "Comment", color: "text-amber-500 bg-amber-50 dark:bg-amber-950/40" },
  "poll-create": { icon: Vote, label: "New Poll", color: "text-violet-600 bg-violet-50 dark:bg-violet-950/40" },
  "member-invite": { icon: Users, label: "Invite Sent", color: "text-cyan-600 bg-cyan-50 dark:bg-cyan-950/40" },
  "ownership-transfer": { icon: Users, label: "Ownership Transfer", color: "text-rose-600 bg-rose-50 dark:bg-rose-950/40" },
  "reminder-send": { icon: Bell, label: "Reminder Sent", color: "text-orange-600 bg-orange-50 dark:bg-orange-950/40" },
  "event-invite": { icon: Calendar, label: "Event Invite", color: "text-teal-600 bg-teal-50 dark:bg-teal-950/40" },
  "chat-message": { icon: MessageSquare, label: "Chat Message", color: "text-indigo-600 bg-indigo-50 dark:bg-indigo-950/40" },
  "chat-comment": { icon: MessageSquare, label: "Chat Reply", color: "text-indigo-500 bg-indigo-50 dark:bg-indigo-950/40" },
};

const FeedItem = ({ item }) => {
  const meta = EVENT_TYPE_META[item.event_type] || { icon: Activity, label: item.event_type, color: "text-muted-foreground bg-muted" };
  const Icon = meta.icon;
  return (
    <div className="group flex gap-4 py-4 transition-colors" data-testid={`feed-item-${item.id}`}>
      <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${meta.color}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-foreground leading-snug">{item.title}</p>
            <p className="mt-0.5 text-sm text-muted-foreground line-clamp-2">{item.description}</p>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.color}`}>
            {meta.label}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">{item.actor_name}</span>
          <span>{formatDateTime(item.created_at)}</span>
        </div>
      </div>
    </div>
  );
};

export const ActivityFeedPage = ({ token }) => {
  const [feed, setFeed] = useState({ items: [], total: 0, page: 1, total_pages: 1, event_types: [] });
  const [page, setPage] = useState(1);
  const [filterType, setFilterType] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  const loadFeed = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = { page, page_size: 20 };
      if (filterType) params.event_type = filterType;
      const payload = await apiRequest("/activity-feed", { token, params });
      setFeed(payload);
    } catch {
      /* ignore */
    } finally {
      setIsLoading(false);
    }
  }, [token, page, filterType]);

  useEffect(() => { loadFeed(); }, [loadFeed]);

  const handleFilterChange = (type) => {
    setFilterType(type === filterType ? "" : type);
    setPage(1);
  };

  return (
    <div className="space-y-6" data-testid="activity-feed-page">
      <div className="archival-card">
        <div className="flex items-center gap-3 mb-1">
          <Activity className="h-5 w-5 text-primary" />
          <h2 className="font-display text-2xl text-foreground" data-testid="activity-feed-title">Activity Feed</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Everything happening across your community — {feed.total} total activities
        </p>
      </div>

      {feed.event_types.length > 0 && (
        <div className="archival-card" data-testid="activity-feed-filters">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold text-foreground">Filter by type</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {feed.event_types.map((type) => {
              const meta = EVENT_TYPE_META[type] || { label: type, color: "text-muted-foreground bg-muted" };
              const isActive = filterType === type;
              return (
                <button
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                    isActive
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : `${meta.color} hover:opacity-80`
                  }`}
                  data-testid={`filter-${type}`}
                  key={type}
                  onClick={() => handleFilterChange(type)}
                >
                  {meta.label}
                </button>
              );
            })}
            {filterType && (
              <button
                className="rounded-full px-3 py-1.5 text-xs font-semibold text-muted-foreground bg-muted hover:bg-muted/80"
                data-testid="filter-clear"
                onClick={() => handleFilterChange("")}
              >
                Clear filter
              </button>
            )}
          </div>
        </div>
      )}

      <div className="archival-card">
        {isLoading && feed.items.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">Loading activity...</p>
        ) : feed.items.length === 0 ? (
          <div className="py-16 text-center">
            <Activity className="mx-auto h-10 w-10 text-muted-foreground/40" />
            <p className="mt-3 text-sm text-muted-foreground">No activity yet. Start by creating a gathering or announcement!</p>
          </div>
        ) : (
          <div className="divide-y divide-border/60" data-testid="feed-items-list">
            {feed.items.map((item) => (
              <FeedItem item={item} key={item.id} />
            ))}
          </div>
        )}

        {feed.total_pages > 1 && (
          <div className="mt-6 flex items-center justify-between border-t border-border/60 pt-4">
            <Button
              className="rounded-full"
              data-testid="feed-prev-page"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              size="sm"
              variant="outline"
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground" data-testid="feed-page-info">
              Page {feed.page} of {feed.total_pages}
            </span>
            <Button
              className="rounded-full"
              data-testid="feed-next-page"
              disabled={page >= feed.total_pages}
              onClick={() => setPage((p) => Math.min(feed.total_pages, p + 1))}
              size="sm"
              variant="outline"
            >
              Next
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
