import { Menu, MoonStar, Sparkles, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { DashboardPage } from "@/components/DashboardPage";
import { ContributionsPage } from "@/components/ContributionsPage";
import { EventsPage } from "@/components/EventsPage";
import { MemoryVaultPage } from "@/components/MemoryVaultPage";
import { MembersPage } from "@/components/MembersPage";
import { StrategyPage } from "@/components/StrategyPage";
import { ThreadsPage } from "@/components/ThreadsPage";

const navItems = [
  { label: "Dashboard", path: "/dashboard" },
  { label: "Events Hub", path: "/events" },
  { label: "Memory Vault", path: "/memories" },
  { label: "Legacy Threads", path: "/threads" },
  { label: "Contributions", path: "/contributions" },
  { label: "Members", path: "/members" },
  { label: "Strategy Deck", path: "/app-strategy" },
];

export const AppShell = ({ token, user, community, onLogout, onSessionRefresh }) => {
  const { resolvedTheme, setTheme } = useTheme();

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
                  <p className="eyebrow-text">Private community OS</p>
                  <h1 className="font-display text-2xl text-foreground">Gathering Cypher</h1>
                </div>
              </div>
              <div className="soft-panel space-y-2">
                <p className="text-lg font-semibold text-foreground" data-testid="shell-community-name">
                  {community?.name}
                </p>
                <p className="text-sm text-muted-foreground" data-testid="shell-community-metadata">
                  {community?.community_type} · {community?.location}
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
                  {item.label}
                </NavLink>
              ))}
            </nav>

            <div className="flex flex-wrap gap-3">
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
                <p className="eyebrow-text">Invitation-only coordination</p>
                <h2 className="font-display text-3xl text-foreground sm:text-4xl" data-testid="shell-header-title">
                  Build memory, not noise.
                </h2>
                <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
                  Organize gatherings, preserve oral history, and track contributions inside a space your community controls.
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
              <Route
                element={<DashboardPage community={community} token={token} user={user} />}
                path="dashboard"
              />
              <Route element={<EventsPage token={token} user={user} />} path="events" />
              <Route element={<MemoryVaultPage token={token} user={user} />} path="memories" />
              <Route element={<ThreadsPage token={token} user={user} />} path="threads" />
              <Route element={<ContributionsPage token={token} user={user} />} path="contributions" />
              <Route
                element={<MembersPage onSessionRefresh={onSessionRefresh} token={token} user={user} />}
                path="members"
              />
              <Route element={<StrategyPage mode="app" />} path="app-strategy" />
              <Route element={<Navigate replace to="/dashboard" />} path="*" />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  );
};