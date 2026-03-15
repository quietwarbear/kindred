import { ChevronDown, Download, Menu, MoonStar, Sparkles, SunMedium } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NotificationPanel } from "@/components/layout/NotificationPanel";
import { ActivityFeedPage } from "@/components/ActivityFeedPage";
import { ContributionsPage } from "@/components/ContributionsPage";
import { CourtyardsPage } from "@/components/CourtyardsPage";
import { FundsTravelPage } from "@/components/FundsTravelPage";
import { GatheringsPage } from "@/components/GatheringsPage";
import { HomePage } from "@/components/HomePage";
import { KinshipMapPage } from "@/components/KinshipMapPage";
import { LegacyThreadsPage } from "@/components/LegacyThreadsPage";
import { MemoryVaultPage } from "@/components/MemoryVaultPage";
import { MembersPage } from "@/components/MembersPage";
import { PollsPage } from "@/components/PollsPage";
import { SettingsPage } from "@/components/SettingsPage";
import { StrategyPage } from "@/components/StrategyPage";
import { SubscriptionPage } from "@/components/SubscriptionPage";
import { ThreadsPage } from "@/components/ThreadsPage";
import { TimelinePage } from "@/components/TimelinePage";
import { EventsPage } from "@/components/EventsPage";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { isStandalone, setupInstallPrompt, triggerInstall } from "@/lib/sw-register";

const navItems = [
  { label: "Home", path: "/home" },
  { label: "Activity", path: "/activity" },
  { label: "Courtyards", path: "/courtyards" },
  { label: "Timeline", path: "/timeline" },
  { label: "Gatherings", path: "/gatherings" },
  { label: "Legacy Threads", path: "/legacy-threads" },
  { label: "Kinship Map", path: "/kinship-map" },
  { label: "Polls", path: "/polls" },
  { label: "Funds & Travel", path: "/funds-travel" },
  { label: "Subscription", path: "/subscription" },
  { label: "Settings", path: "/settings" },
];

export const AppShell = ({ token, user, community, onLogout, onSessionRefresh }) => {
  const { resolvedTheme, setTheme } = useTheme();
  const location = useLocation();
  const [unreadSummary, setUnreadSummary] = useState({ announcements_unread: 0, chat_unread: 0, total_unread: 0 });
  const [myCommunities, setMyCommunities] = useState([]);
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  const [canInstall, setCanInstall] = useState(false);

  const refreshUnreadSummary = useCallback(async () => {
    try {
      const payload = await apiRequest("/communications/unread-summary", { token });
      setUnreadSummary(payload);
    } catch {
      setUnreadSummary({ announcements_unread: 0, chat_unread: 0, total_unread: 0 });
    }
  }, [token]);

  const loadMyCommunities = useCallback(async () => {
    try {
      const payload = await apiRequest("/communities/mine", { token });
      setMyCommunities(payload.communities || []);
    } catch {
      /* ignore */
    }
  }, [token]);

  useEffect(() => { refreshUnreadSummary(); }, [location.pathname, refreshUnreadSummary]);
  useEffect(() => { loadMyCommunities(); }, [loadMyCommunities]);

  useEffect(() => {
    if (!isStandalone()) setupInstallPrompt(() => setCanInstall(true));
  }, []);

  const handleInstall = async () => {
    const accepted = await triggerInstall();
    if (accepted) {
      setCanInstall(false);
      toast.success("Kindred installed to your device!");
    }
  };

  const handleSwitchCommunity = async (communityId) => {
    try {
      await apiRequest("/communities/switch", { method: "POST", token, data: { community_id: communityId } });
      setShowSwitcher(false);
      onSessionRefresh();
    } catch {
      /* ignore */
    }
  };

  const handleJoinCommunity = async () => {
    if (!joinCode.trim()) return;
    try {
      await apiRequest("/communities/join", { method: "POST", token, data: { invite_code: joinCode } });
      setJoinCode("");
      setShowSwitcher(false);
      onSessionRefresh();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to join community.");
    }
  };

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
                <button
                  className="flex w-full items-center justify-between text-left"
                  data-testid="community-switcher-toggle"
                  onClick={() => setShowSwitcher(!showSwitcher)}
                >
                  <div>
                    <p className="text-lg font-semibold text-foreground" data-testid="shell-community-name">
                      {community?.name}
                    </p>
                    <p className="text-sm text-muted-foreground" data-testid="shell-community-metadata">
                      {community?.community_type} courtyard · {community?.location}
                    </p>
                  </div>
                  {myCommunities.length > 1 && (
                    <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${showSwitcher ? "rotate-180" : ""}`} />
                  )}
                </button>
                <p className="text-sm text-muted-foreground" data-testid="shell-user-identity">
                  Signed in as {user?.full_name} ({user?.role})
                </p>
                {showSwitcher && (
                  <div className="mt-2 space-y-2 border-t border-border/50 pt-2" data-testid="community-switcher-panel">
                    {myCommunities.filter((c) => !c.is_active).map((c) => (
                      <button
                        className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm text-foreground hover:bg-accent/70 transition-colors"
                        data-testid={`switch-community-${c.id}`}
                        key={c.id}
                        onClick={() => handleSwitchCommunity(c.id)}
                      >
                        <span className="font-medium">{c.name}</span>
                        <span className="text-xs text-muted-foreground">{c.member_count} members</span>
                      </button>
                    ))}
                    <div className="flex gap-2 pt-1">
                      <Input
                        className="field-input h-8 text-xs flex-1"
                        data-testid="join-community-input"
                        onChange={(e) => setJoinCode(e.target.value)}
                        placeholder="Invite code"
                        value={joinCode}
                      />
                      <Button className="rounded-full h-8" data-testid="join-community-btn" disabled={!joinCode.trim()} onClick={handleJoinCommunity} size="sm" variant="secondary">
                        Join
                      </Button>
                    </div>
                  </div>
                )}
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
              {canInstall && (
                <Button
                  className="rounded-full w-full"
                  data-testid="pwa-install-btn"
                  onClick={handleInstall}
                  variant="outline"
                >
                  <Download className="mr-2 h-4 w-4" />
                  Install Kindred
                </Button>
              )}
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
              <Route element={<ActivityFeedPage token={token} />} path="activity" />
              <Route element={<CourtyardsPage onCommunicationsViewed={refreshUnreadSummary} token={token} user={user} />} path="courtyards" />
              <Route element={<TimelinePage token={token} />} path="timeline" />
              <Route element={<GatheringsPage token={token} user={user} />} path="gatherings" />
              <Route element={<PollsPage token={token} user={user} />} path="polls" />
              <Route element={<FundsTravelPage token={token} user={user} />} path="funds-travel" />
              <Route element={<SettingsPage onSessionRefresh={onSessionRefresh} token={token} user={user} />} path="settings" />
              <Route element={<SubscriptionPage token={token} user={user} />} path="subscription" />
              <Route
                element={<MembersPage onSessionRefresh={onSessionRefresh} token={token} user={user} />}
                path="members"
              />
              <Route element={<MemoryVaultPage token={token} user={user} />} path="memories" />
              <Route element={<LegacyThreadsPage token={token} />} path="legacy-threads" />
              <Route element={<KinshipMapPage token={token} />} path="kinship-map" />
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