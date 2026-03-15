import { Bell, BellRing, CheckCheck, Clock, ExternalLink, Settings2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { apiRequest, formatDateTime } from "@/lib/api";

const EVENT_TYPE_LABELS = {
  "reminder-send": "Reminder",
  "announcement-create": "Announcement",
  "chat-message": "Chat",
  "invite-create": "Invite",
  "rsvp-update": "RSVP",
  "event-create": "Gathering",
  "event-update": "Update",
};

const EVENT_TYPE_COLORS = {
  "reminder-send": "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
  "announcement-create": "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  "chat-message": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
  "invite-create": "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300",
  "rsvp-update": "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300",
  "event-create": "bg-primary/10 text-primary",
  "event-update": "bg-primary/10 text-primary",
};

export const NotificationPanel = ({ token }) => {
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isMarking, setIsMarking] = useState(false);
  const intervalRef = useRef(null);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const payload = await apiRequest("/notifications/unread-count", { token });
      setUnreadCount(payload.unread_count || 0);
    } catch {
      /* silent */
    }
  }, [token]);

  const fetchHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const payload = await apiRequest("/notifications/history", { token });
      setItems(payload.items || []);
    } catch {
      /* silent */
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  const prevUnreadRef = useRef(0);

  const requestPushPermission = useCallback(async () => {
    if ("Notification" in window && Notification.permission === "default") {
      await Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    requestPushPermission();
  }, [requestPushPermission]);

  useEffect(() => {
    fetchUnreadCount();
    intervalRef.current = setInterval(fetchUnreadCount, 30_000);
    return () => clearInterval(intervalRef.current);
  }, [fetchUnreadCount]);

  useEffect(() => {
    // Show browser push notification for new notifications
    if (
      unreadCount > prevUnreadRef.current &&
      prevUnreadRef.current > 0 &&
      !open &&
      "Notification" in window &&
      Notification.permission === "granted"
    ) {
      new Notification("Kindred", {
        body: `You have ${unreadCount} unread notification${unreadCount === 1 ? "" : "s"}`,
        icon: "/favicon.ico",
      });
    }
    prevUnreadRef.current = unreadCount;
  }, [unreadCount, open]);

  useEffect(() => {
    if (open) fetchHistory();
  }, [open, fetchHistory]);

  const handleMarkAllRead = async () => {
    setIsMarking(true);
    try {
      await apiRequest("/notifications/mark-read", { method: "POST", token });
      setUnreadCount(0);
      setItems((prev) => prev.map((item) => ({ ...item, is_read: true })));
    } catch {
      /* silent */
    } finally {
      setIsMarking(false);
    }
  };

  const displayItems = items.slice(0, 12);

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger asChild>
        <button
          className="relative flex h-10 w-10 items-center justify-center rounded-full border border-border/60 bg-background/80 text-foreground transition-colors duration-200 hover:bg-accent/70"
          data-testid="notification-bell-button"
        >
          {unreadCount > 0 ? (
            <BellRing className="h-4.5 w-4.5 text-primary" />
          ) : (
            <Bell className="h-4.5 w-4.5" />
          )}
          {unreadCount > 0 && (
            <span
              className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-primary-foreground"
              data-testid="notification-unread-badge"
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="end"
        className="w-[380px] overflow-hidden rounded-xl border border-border/60 p-0 shadow-lg"
        sideOffset={8}
      >
        <div className="flex items-center justify-between border-b border-border/50 px-4 py-3">
          <h3 className="font-display text-lg font-semibold text-foreground" data-testid="notification-panel-title">
            Notifications
          </h3>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <Button
                className="h-7 rounded-full px-2.5 text-xs"
                data-testid="notification-mark-all-read-button"
                disabled={isMarking}
                onClick={handleMarkAllRead}
                variant="ghost"
              >
                <CheckCheck className="mr-1 h-3.5 w-3.5" />
                {isMarking ? "Marking..." : "Mark all read"}
              </Button>
            )}
          </div>
        </div>

        <div className="max-h-[400px] overflow-y-auto" data-testid="notification-items-list">
          {isLoading && !displayItems.length ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">Loading...</div>
          ) : displayItems.length === 0 ? (
            <div className="px-4 py-8 text-center" data-testid="notification-empty-state">
              <Bell className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">No notifications yet</p>
              <p className="mt-1 text-xs text-muted-foreground/70">
                Activity from your circle will show up here
              </p>
            </div>
          ) : (
            displayItems.map((item) => (
              <div
                className={`flex gap-3 border-b border-border/30 px-4 py-3 transition-colors duration-200 last:border-0 ${
                  item.is_read ? "bg-transparent" : "bg-primary/[0.03]"
                }`}
                data-testid={`notification-item-${item.id}`}
                key={item.id}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <p className={`text-sm font-semibold leading-snug ${item.is_read ? "text-foreground/70" : "text-foreground"}`}>
                      {item.title}
                    </p>
                    {!item.is_read && (
                      <span className="mt-1 h-2 w-2 flex-shrink-0 rounded-full bg-primary" />
                    )}
                  </div>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground line-clamp-2">
                    {item.description}
                  </p>
                  <div className="mt-1.5 flex items-center gap-2">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                        EVENT_TYPE_COLORS[item.event_type] || "bg-muted text-muted-foreground"
                      }`}
                    >
                      {EVENT_TYPE_LABELS[item.event_type] || item.event_type}
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-muted-foreground/70">
                      <Clock className="h-2.5 w-2.5" />
                      {formatDateTime(item.created_at)}
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border/50 px-4 py-2.5">
          <Link
            className="flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
            data-testid="notification-view-all-link"
            onClick={() => setOpen(false)}
            to="/settings"
          >
            View full history
            <ExternalLink className="h-3 w-3" />
          </Link>
          <Link
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            data-testid="notification-preferences-link"
            onClick={() => setOpen(false)}
            to="/settings"
          >
            <Settings2 className="h-3 w-3" />
            Preferences
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
};
