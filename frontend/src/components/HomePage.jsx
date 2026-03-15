import { useEffect, useState } from "react";
import { BellRing, CalendarDays, Coins, Network, Sparkles, Upload, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { apiRequest, formatCountdown, formatDateTime, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const quickActionIcons = {
  "plan-gathering": CalendarDays,
  "upload-story": Upload,
  "check-funds": Wallet,
};

export const HomePage = ({ token }) => {
  const [homeData, setHomeData] = useState(null);

  useEffect(() => {
    const loadHome = async () => {
      try {
        const payload = await apiRequest("/courtyard/home", { token });
        setHomeData(payload);
      } catch (error) {
        toast.error(error.response?.data?.detail || "Unable to load the courtyard home screen.");
      }
    };

    loadHome();
  }, [token]);

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="eyebrow-text">Kindred · Where your circles gather and grow.</p>
            <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="home-page-title">
              Everything your people need to gather, remember, and move together.
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="home-page-copy">
              See upcoming gatherings, active courtyards and subyards, relationship prompts, and your next best actions without changing the visual language your community already knows.
            </p>
          </div>
          <div className="soft-panel max-w-sm" data-testid="home-stats-panel">
            <p className="eyebrow-text">At a glance</p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-muted-foreground">
              <div>
                <p>Members</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">{homeData?.stats?.members || 0}</p>
              </div>
              <div>
                <p>Subyards</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">{homeData?.stats?.subyards || 0}</p>
              </div>
              <div>
                <p>Gatherings</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">{homeData?.stats?.gatherings || 0}</p>
              </div>
              <div>
                <p>Funds raised</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">{shortCurrency(homeData?.stats?.funds_total || 0)}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
        <article className="archival-card" data-testid="home-upcoming-gatherings-card">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="eyebrow-text">Upcoming Gatherings</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Next 3–5 moments to prepare for</h3>
            </div>
            <Link className="text-sm font-semibold text-primary" data-testid="home-goto-gatherings-link" to="/gatherings">
              Open Gatherings
            </Link>
          </div>
          <div className="mt-6 space-y-4">
            {homeData?.upcoming_gatherings?.length ? (
              homeData.upcoming_gatherings.map((gathering) => (
                <div className="soft-panel" data-testid={`home-gathering-card-${gathering.id}`} key={gathering.id}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-lg font-semibold text-foreground">{gathering.title}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{formatDateTime(gathering.start_at)} · {gathering.location}</p>
                      <p className="mt-3 text-sm leading-7 text-muted-foreground">{gathering.description}</p>
                    </div>
                    <div className="rounded-full border border-border bg-background/80 px-4 py-2 text-sm font-semibold text-primary" data-testid={`home-gathering-countdown-${gathering.id}`}>
                      {formatCountdown(gathering.countdown_days)}
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3 text-sm text-muted-foreground">
                    <span data-testid={`home-gathering-rsvp-going-${gathering.id}`}>Going: {gathering.rsvp_summary.going}</span>
                    <span data-testid={`home-gathering-rsvp-maybe-${gathering.id}`}>Maybe: {gathering.rsvp_summary.maybe}</span>
                    <span data-testid={`home-gathering-subyard-${gathering.id}`}>{gathering.subyard_name || gathering.event_template}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="home-gatherings-empty-state">
                <p className="text-sm text-muted-foreground">No gatherings yet. Start with a reunion, birthday, wedding, holiday, or custom moment.</p>
              </div>
            )}
          </div>
        </article>

        <div className="space-y-6">
          <article className="archival-card" data-testid="home-active-courtyards-card">
            <div className="flex items-center gap-3">
              <Network className="h-5 w-5 text-primary" />
              <div>
                <p className="eyebrow-text">Active Courtyards</p>
                <h3 className="mt-2 font-display text-3xl text-foreground">Parent + subyard view</h3>
              </div>
            </div>
            <div className="mt-6 space-y-3">
              {homeData?.active_courtyards?.map((courtyard) => (
                <div className="soft-panel" data-testid={`home-active-courtyard-${courtyard.id}`} key={courtyard.id}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-foreground">{courtyard.name}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{courtyard.kind} · {courtyard.upcoming_gatherings} upcoming gatherings</p>
                    </div>
                    <p className="text-sm text-muted-foreground" data-testid={`home-active-courtyard-members-${courtyard.id}`}>
                      {courtyard.members} members
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="archival-card" data-testid="home-quick-actions-card">
            <p className="eyebrow-text">Quick Actions</p>
            <h3 className="mt-2 font-display text-3xl text-foreground">Move fast without digging through menus</h3>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {homeData?.quick_actions?.map((action) => {
                const Icon = quickActionIcons[action.id] || Sparkles;
                return (
                  <Link
                    className="soft-panel transition duration-300 hover:-translate-y-0.5"
                    data-testid={`home-quick-action-${action.id}`}
                    key={action.id}
                    to={action.target}
                  >
                    <Icon className="h-5 w-5 text-primary" />
                    <p className="mt-3 text-sm font-semibold text-foreground">{action.label}</p>
                  </Link>
                );
              })}
            </div>
          </article>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <article className="archival-card" data-testid="home-notifications-card">
          <div className="flex items-center gap-3">
            <BellRing className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Notifications / Highlights</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">Relationship nudges and community prompts</h3>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {homeData?.notifications?.length ? (
              homeData.notifications.map((item) => (
                <div className="soft-panel" data-testid={`home-notification-${item.id}`} key={item.id}>
                  <p className="text-base font-semibold text-foreground">{item.title}</p>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.description}</p>
                </div>
              ))
            ) : (
              <div className="soft-panel" data-testid="home-notifications-empty-state">
                <p className="text-sm text-muted-foreground">No urgent highlights right now. Your courtyard is caught up.</p>
              </div>
            )}
          </div>
        </article>

        <article className="archival-card" data-testid="home-role-catalog-card">
          <div className="flex items-center gap-3">
            <Coins className="h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Role-enabled tools</p>
              <h3 className="mt-2 font-display text-3xl text-foreground">What each family role unlocks</h3>
            </div>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {homeData?.role_catalog?.map((item) => (
              <div className="soft-panel" data-testid={`home-role-card-${item.role.replace(/\s+/g, "-")}`} key={item.role}>
                <p className="text-base font-semibold capitalize text-foreground">{item.role}</p>
                <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                  {item.tools.map((tool) => (
                    <li key={tool}>• {tool}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
};