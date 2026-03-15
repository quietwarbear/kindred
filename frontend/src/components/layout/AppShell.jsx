import { Menu, MoonStar, Sparkles, SunMedium } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { NotificationPanel } from "@/components/layout/NotificationPanel";
import { ContributionsPage } from "@/components/ContributionsPage";
import { CourtyardsPage } from "@/components/CourtyardsPage";
import { FundsTravelPage } from "@/components/FundsTravelPage";
import { GatheringsPage } from "@/components/GatheringsPage";
import { HomePage } from "@/components/HomePage";
import { MemoryVaultPage } from "@/components/MemoryVaultPage";
import { MembersPage } from "@/components/MembersPage";
import { SettingsPage } from "@/components/SettingsPage";
import { StrategyPage } from "@/components/StrategyPage";
import { ThreadsPage } from "@/components/ThreadsPage";
import { TimelinePage } from "@/components/TimelinePage";
import { EventsPage } from "@/components/EventsPage";
import { apiRequest } from "@/lib/api";

const navItems = [
  { label: "Home", path: "/home" },
  { label: "Courtyards", path: "/courtyards" },
  { label: "Timeline", path: "/timeline" },
  { label: "Gatherings", path: "/gatherings" },
  { label: "Funds & Travel", path: "/funds-travel" },
  { label: "Settings", path: "/settings" },
];

export const AppShell = ({ token, user, community, onLogout, onSessionRefresh }) => {
  const { resolvedTheme, setTheme } = useTheme();
  const location = useLocation();
  const [unreadSummary, setUnreadSummary] = useState({ announcements_unread: 0, chat_unread: 0, total_unread: 0 });

  const refreshUnreadSummary = useCallback(async () => {
    try {
      const payload = await apiRequest("/communications/unread-summary", { token });
      setUnreadSummary(payload);
    } catch {
      setUnreadSummary({ announcements_unread: 0, chat_unread: 0, total_unread: 0 });
    }
  }, [token]);

  useEffect(() => {
    refreshUnreadSummary();
  }, [location.pathname, refreshUnreadSummary]);

  return (
    <div className="app-canvas min-h-screen pb-10">
      <div className="page-section pt-6 md:pt-8">
        <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="archival-card flex h-fit flex-col gap-6 lg:sticky lg:top-6">
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <p className="eyebrow-text">Where your circles gather and grow.</p>
                  <h1 className="font-display text-2xl text-foreground">Kindred</h1>
                </div>
              </div>
              <div className="soft-panel space-y-2">
                <p className="text-lg font-semibold text-foreground" data-testid="shell-community-name">
                  {community?.name}
                </p>
                <p className="text-sm text-muted-foreground" data-testid="shell-community-metadata">
                  {community?.community_type} courtyard · {community?.location}
                </p>
                <p className="text-sm text-muted-foreground" data-testid="shell-user-identity">
                  Signed in as {user?.full_name} ({user?.role})
                </p>
              </div>
            </div>

            <nav className="grid gap-2" data-testid="shell-navigation">
              {navItems.map((item) => (
                <NavLink
                  className={({ isActive }) =>
                    `rounded-2xl px-4 py-3 text-sm font-semibold transition duration-300 ${
                      isActive
                        ? "bg-primary text-primary-foreground shadow-[0_16px_36px_-22px_rgba(154,52,18,0.7)]"
                        : "bg-background/70 text-foreground hover:bg-accent/70"
                    }`
                  }
                  data-testid={`nav-link-${item.path.replace(/\//g, "") || "home"}`}
                  key={item.path}
                  to={item.path}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span>{item.label}</span>
                    {item.path === "/courtyards" && unreadSummary.total_unread > 0 ? (
                      <span className="rounded-full bg-primary/15 px-2.5 py-1 text-xs font-semibold text-primary" data-testid="nav-link-courtyards-unread-badge">
                        {unreadSummary.total_unread}
                      </span>
                    ) : null}
                  </span>
                </NavLink>
              ))}
            </nav>

            <div className="flex flex-wrap items-center gap-3">
              <NotificationPanel token={token} />
              <Button
                className="rounded-full"
                data-testid="theme-toggle-button"
                onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
                variant="outline"
              >
                {resolvedTheme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
                {resolvedTheme === "dark" ? "Light mode" : "Dark mode"}
              </Button>
              <Button
                className="rounded-full"
                data-testid="logout-button"
                onClick={onLogout}
                variant="secondary"
              >
                Sign out
              </Button>
            </div>
          </aside>

          <main className="space-y-6">
            <div className="archival-card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="eyebrow-text">Where your circles gather and grow.</p>
                <h2 className="font-display text-3xl text-foreground sm:text-4xl" data-testid="shell-header-title">
                  Plan gatherings like a platform, not a patchwork.
                </h2>
                <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
                  Keep the same warm visual feel while expanding into courtyards, subyards, kinship mapping, smart planning, timelines, shared funds, and travel coordination.
                </p>
              </div>
              <div className="soft-panel flex items-center gap-3 self-start" data-testid="shell-value-pill">
                <Menu className="h-4 w-4 text-primary" />
                <div>
                  <p className="text-sm font-semibold text-foreground">Digital sovereignty</p>
                  <p className="text-xs text-muted-foreground">No feed. No ads. No algorithm.</p>
                </div>
              </div>
            </div>

            <Routes>
              <Route element={<HomePage token={token} />} path="dashboard" />
              <Route element={<HomePage token={token} />} path="home" />
              <Route element={<CourtyardsPage onCommunicationsViewed={refreshUnreadSummary} token={token} user={user} />} path="courtyards" />
              <Route element={<TimelinePage token={token} />} path="timeline" />
              <Route element={<GatheringsPage token={token} user={user} />} path="gatherings" />
              <Route element={<FundsTravelPage token={token} user={user} />} path="funds-travel" />
              <Route element={<SettingsPage onSessionRefresh={onSessionRefresh} token={token} user={user} />} path="settings" />
              <Route
                element={<MembersPage onSessionRefresh={onSessionRefresh} token={token} user={user} />}
                path="members"
              />
              <Route element={<MemoryVaultPage token={token} user={user} />} path="memories" />
              <Route element={<ThreadsPage token={token} user={user} />} path="threads" />
              <Route element={<ContributionsPage token={token} user={user} />} path="contributions" />
              <Route element={<EventsPage token={token} user={user} />} path="events" />
              <Route element={<StrategyPage mode="app" />} path="app-strategy" />
              <Route element={<Navigate replace to="/home" />} path="*" />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  );
};