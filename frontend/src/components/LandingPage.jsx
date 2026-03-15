import {
  ArrowRight,
  CalendarDays,
  Camera,
  Coins,
  Landmark,
  LockKeyhole,
  MessageCircleHeart,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

const heroImage =
  "https://images.unsplash.com/photo-1768244016470-271b210a8407?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzV8MHwxfHNlYXJjaHwzfHxtdWx0aWdlbmVyYXRpb25hbCUyMGJsYWNrJTIwZmFtaWx5JTIwcmV1bmlvbiUyMGpveSUyMG91dGRvb3J8ZW58MHx8fHwxNzcyODQxMzI0fDA&ixlib=rb-4.1.0&q=85";

const pillars = [
  {
    icon: CalendarDays,
    title: "Events Hub",
    copy: "Create private gatherings with agendas, volunteer slots, potluck planning, maps, and RSVP visibility.",
  },
  {
    icon: Camera,
    title: "Memory Vault",
    copy: "Capture photos, voice notes, and AI-generated tags so every gathering becomes an accessible archive.",
  },
  {
    icon: MessageCircleHeart,
    title: "Legacy Threads",
    copy: "Preserve oral histories, sermons, intergenerational dialogue, and reflections in one living record.",
  },
  {
    icon: Coins,
    title: "Shared Contributions",
    copy: "Collect dues, reunion support, and scholarship funds with transparent contribution records.",
  },
];

const audience = ["Family reunions", "Church communities", "Greek organizations", "Cultural collectives"];

export const LandingPage = ({ isAuthenticated }) => {
  return (
    <div className="app-canvas min-h-screen">
      <section className="page-section py-6 md:py-8">
        <div className="archival-card overflow-hidden p-0">
          <div className="grid lg:grid-cols-[1.05fr_0.95fr]">
            <div className="flex flex-col justify-between gap-10 p-6 sm:p-8 lg:p-10">
              <div className="space-y-6">
                <p className="eyebrow-text" data-testid="landing-eyebrow">
                  Closed, invitation-only digital home
                </p>
                <div className="space-y-4">
                  <h1 className="font-display text-4xl leading-tight text-foreground sm:text-5xl lg:text-6xl" data-testid="landing-headline">
                    A private ecosystem for communities to gather, plan, remember, and build.
                  </h1>
                  <p className="max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="landing-subheadline">
                    Kindred gives families, churches, and intentional communities ownership over memory,
                    coordination, and narrative without ads, public profiles, or algorithmic interference.
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Link
                    className="pill-button"
                    data-testid="landing-primary-cta"
                    to={isAuthenticated ? "/dashboard" : "/login"}
                  >
                    {isAuthenticated ? "Open your community" : "Launch your community"}
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                  <Link className="pill-button-secondary" data-testid="landing-strategy-cta" to="/strategy">
                    Explore the strategy deck
                  </Link>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="soft-panel" data-testid="landing-value-security">
                  <LockKeyhole className="h-5 w-5 text-primary" />
                  <p className="mt-3 text-base font-semibold text-foreground">Invitation-only privacy</p>
                  <p className="mt-2 text-sm text-muted-foreground">No public profiles. Admin-controlled access.</p>
                </div>
                <div className="soft-panel" data-testid="landing-value-community">
                  <Users className="h-5 w-5 text-primary" />
                  <p className="mt-3 text-base font-semibold text-foreground">Built for real gatherings</p>
                  <p className="mt-2 text-sm text-muted-foreground">Designed around reunions, ministries, and mutual care.</p>
                </div>
                <div className="soft-panel" data-testid="landing-value-legacy">
                  <Landmark className="h-5 w-5 text-primary" />
                  <p className="mt-3 text-base font-semibold text-foreground">Archive-first memory</p>
                  <p className="mt-2 text-sm text-muted-foreground">Preserve stories, photos, and voice notes in one place.</p>
                </div>
              </div>
            </div>

            <div className="relative min-h-[420px] bg-muted">
              <img
                alt="Joyful multigenerational family gathering"
                className="absolute inset-0 h-full w-full object-cover object-center"
                data-testid="landing-hero-image"
                src={heroImage}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-stone-950/55 via-stone-950/15 to-transparent" />
              <div className="absolute bottom-6 left-6 right-6 rounded-[24px] border border-white/20 bg-stone-950/45 p-5 text-white backdrop-blur-md">
                <p className="eyebrow-text text-orange-200">Positioning</p>
                <p className="mt-2 font-display text-2xl" data-testid="landing-positioning-title">
                  Where your circles gather and grow.
                </p>
                <p className="mt-2 text-sm text-stone-100/80" data-testid="landing-positioning-copy">
                  A permanent home for gathering logistics, oral history, contributions, and kinship coordination.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="page-section py-10 md:py-16">
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {pillars.map(({ icon: Icon, title, copy }) => (
            <article className="archival-card" data-testid={`landing-feature-${title.toLowerCase().replace(/\s+/g, "-")}`} key={title}>
              <Icon className="h-5 w-5 text-primary" />
              <h2 className="mt-4 font-display text-2xl text-foreground">{title}</h2>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">{copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="page-section pb-16">
        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <article className="archival-card" data-testid="landing-audience-card">
            <p className="eyebrow-text">Who it is for</p>
            <h2 className="mt-3 font-display text-3xl text-foreground">Infrastructure for communities tired of generic social platforms.</h2>
            <div className="mt-6 flex flex-wrap gap-3">
              {audience.map((item) => (
                <span className="rounded-full border border-border bg-background/80 px-4 py-2 text-sm text-foreground" data-testid={`landing-audience-${item.toLowerCase().replace(/\s+/g, "-")}`} key={item}>
                  {item}
                </span>
              ))}
            </div>
          </article>

          <article className="archival-card" data-testid="landing-business-card">
            <p className="eyebrow-text">Strategic framing</p>
            <h2 className="mt-3 font-display text-3xl text-foreground">Not another app. Community infrastructure.</h2>
            <p className="mt-4 text-sm leading-7 text-muted-foreground">
              The model supports recurring revenue through paid community tiers while preserving private ownership over memory, logistics, and membership.
            </p>
            <Link className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-primary" data-testid="landing-read-strategy-link" to="/strategy">
              Read the full roadmap <ArrowRight className="h-4 w-4" />
            </Link>
          </article>
        </div>
      </section>

      <footer className="page-section border-t border-border/40 py-8" data-testid="landing-footer">
        <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
          <p className="text-xs text-muted-foreground">&copy; {new Date().getFullYear()} Ubuntu Market LLC. All rights reserved.</p>
          <nav className="flex gap-6">
            <Link className="text-xs text-muted-foreground hover:text-foreground transition-colors" data-testid="landing-footer-privacy-link" to="/privacy">
              Privacy Policy
            </Link>
            <Link className="text-xs text-muted-foreground hover:text-foreground transition-colors" data-testid="landing-footer-terms-link" to="/terms">
              Terms of Service
            </Link>
            <Link className="text-xs text-muted-foreground hover:text-foreground transition-colors" data-testid="landing-footer-support-link" to="/support">
              Support
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
};