import {
  ArrowRight,
  CalendarDays,
  Camera,
  CheckCircle2,
  ClipboardList,
  HandHelping,
  LockKeyhole,
  MessageCircleHeart,
  ShieldCheck,
  Soup,
  UserRoundCheck,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { PublicPlanCards } from "@/components/PublicPlanCards";
import { usePublicPlans } from "@/hooks/usePublicPlans";
import { trackReunionEvent } from "@/lib/analytics";
import { isNative } from "@/lib/native-bridge";

const APP_STORE_URL = "https://apps.apple.com/app/heykindred/id6760608478";
const PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.ubuntumarket.kindred";

const steps = [
  {
    number: "01",
    icon: CalendarDays,
    title: "Plan the gathering",
    copy: "Start with the reunion name, approximate date, organizer, and optional location. Kindred creates the working checklist.",
  },
  {
    number: "02",
    icon: Users,
    title: "Invite and coordinate",
    copy: "Create private invite links, collect web RSVPs, and organize potluck items, volunteers, and travel details.",
  },
  {
    number: "03",
    icon: MessageCircleHeart,
    title: "Preserve the memories",
    copy: "Prompt the first story now, then add family photos, voice notes, and oral histories as the gathering takes shape.",
  },
];

const useCases = [
  ["Church communities", "Coordinate ministries, care, gatherings, and shared memory."],
  ["Intentional communities", "Keep member coordination and community history in one private place."],
  ["Greek organizations", "Plan chapter gatherings and preserve intergenerational stories."],
  ["Cultural collectives", "Support diaspora coordination, traditions, and living archives."],
];

export const LandingPage = ({ isAuthenticated }) => {
  const showStoreBadges = !isNative();
  const { plans, loading: plansLoading, error: plansError } = usePublicPlans();

  const trackStart = (source) => {
    trackReunionEvent("reunion_start_clicked", { source });
  };

  return (
    <div className="app-canvas min-h-screen">
      <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-md">
        <nav
          aria-label="Primary navigation"
          className="page-section flex items-center justify-between gap-5 pb-4 pt-4"
          style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 1rem)" }}
        >
          <Link className="font-display text-xl font-semibold text-primary" to="/">Kindred</Link>
          <div className="hidden items-center gap-7 md:flex">
            <a className="text-sm text-foreground/70 transition-colors hover:text-foreground" href="#how">How it works</a>
            <a className="text-sm text-foreground/70 transition-colors hover:text-foreground" href="#use-cases">Other use cases</a>
            <Link className="text-sm text-foreground/70 transition-colors hover:text-foreground" to="/pricing">Pricing</Link>
          </div>
          <Link
            className="text-sm font-semibold text-foreground/70 transition-colors hover:text-foreground"
            to={isAuthenticated ? "/home" : "/login"}
          >
            {isAuthenticated ? "Open Kindred" : "Sign in"}
          </Link>
        </nav>
      </header>

      <main>
        <section className="page-section py-6 md:py-10">
          <div className="archival-card overflow-hidden p-0">
            <div className="grid lg:grid-cols-[1.02fr_0.98fr]">
              <div className="flex flex-col justify-center p-6 sm:p-9 lg:p-12">
                <p className="eyebrow-text" data-testid="landing-eyebrow">Built for multigenerational families and diaspora organizers</p>
                <h1
                  className="mt-5 font-display text-5xl font-semibold leading-[1.02] tracking-tight text-foreground sm:text-6xl"
                  data-testid="landing-headline"
                >
                  Plan the reunion. Bring everyone in. Keep the stories.
                </h1>
                <p
                  className="mt-6 max-w-2xl text-lg leading-8 text-foreground/75"
                  data-testid="landing-subheadline"
                >
                  One private place for RSVPs, potluck, volunteers, travel, photos, and family stories.
                </p>
                <div className="mt-7 flex flex-wrap gap-3">
                  <Link
                    className="pill-button"
                    data-testid="landing-primary-cta"
                    onClick={() => trackStart("homepage_hero")}
                    to="/reunion/start"
                  >
                    Start planning <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                  <a
                    className="inline-flex items-center rounded-full border border-border bg-background px-5 py-3 text-sm font-semibold text-foreground transition hover:bg-muted"
                    data-testid="landing-secondary-cta"
                    href="#how"
                  >
                    See how it works
                  </a>
                </div>
                <p className="mt-5 text-sm text-muted-foreground">
                  Draft and preview without payment. Create an account only when you’re ready to save and share.
                </p>
              </div>

              <div className="bg-stone-950 p-5 text-white sm:p-8" data-testid="landing-interface-evidence">
                <div className="rounded-[28px] border border-white/10 bg-white/5 p-5 shadow-2xl">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-orange-200">Reunion workspace</p>
                      <p className="mt-2 font-display text-3xl">The Family Reunion</p>
                      <p className="mt-2 text-sm text-stone-300">Saturday, July 18 · Oakland, California</p>
                    </div>
                    <span className="rounded-full bg-emerald-300/15 px-3 py-1 text-xs font-semibold text-emerald-200">Private</span>
                  </div>

                  <div className="mt-6 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl bg-white/10 p-4">
                      <p className="flex items-center gap-2 text-sm font-semibold"><UserRoundCheck className="h-4 w-4 text-orange-200" /> RSVP</p>
                      <p className="mt-3 text-2xl font-semibold">18 coming</p>
                      <p className="mt-1 text-xs text-stone-300">7 waiting · 2 maybe</p>
                    </div>
                    <div className="rounded-2xl bg-white/10 p-4">
                      <p className="flex items-center gap-2 text-sm font-semibold"><ClipboardList className="h-4 w-4 text-orange-200" /> Checklist</p>
                      <p className="mt-3 text-2xl font-semibold">6 of 10</p>
                      <p className="mt-1 text-xs text-stone-300">Date, venue, invites, food</p>
                    </div>
                    <div className="rounded-2xl bg-white/10 p-4">
                      <p className="flex items-center gap-2 text-sm font-semibold"><Soup className="h-4 w-4 text-orange-200" /> Potluck</p>
                      <p className="mt-3 text-sm text-stone-200">Mac and cheese · claimed</p>
                      <p className="mt-1 text-sm text-stone-200">Dessert table · open</p>
                    </div>
                    <div className="rounded-2xl bg-white/10 p-4">
                      <p className="flex items-center gap-2 text-sm font-semibold"><HandHelping className="h-4 w-4 text-orange-200" /> Volunteers</p>
                      <p className="mt-3 text-sm text-stone-200">Welcome team · 2/3</p>
                      <p className="mt-1 text-sm text-stone-200">Story team · 1/2</p>
                    </div>
                  </div>

                  <div className="mt-3 rounded-2xl border border-orange-200/15 bg-orange-200/10 p-4">
                    <p className="flex items-center gap-2 text-sm font-semibold"><MessageCircleHeart className="h-4 w-4 text-orange-200" /> Memory prompt</p>
                    <p className="mt-2 text-sm leading-6 text-stone-200">What family story should every younger cousin know?</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section aria-label="Privacy commitments" className="page-section pb-12">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              [LockKeyhole, "Invitation-only", "Access starts with a host or a private invitation."],
              [Users, "No public profiles", "Family membership is not published or searchable."],
              [ShieldCheck, "No advertising", "The experience is not built around an ad feed."],
              [CheckCircle2, "Clear privacy controls", "Invite links reveal only the gathering details needed to respond."],
            ].map(([Icon, title, copy]) => (
              <article className="soft-panel" key={title}>
                <Icon className="h-5 w-5 text-primary" />
                <h2 className="mt-3 text-base font-semibold text-foreground">{title}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="page-section scroll-mt-24 py-10 md:py-16" id="how">
          <div className="max-w-3xl">
            <p className="eyebrow-text">How it works</p>
            <h2 className="mt-3 font-display text-4xl text-foreground sm:text-5xl">The archive begins with a gathering people already care about.</h2>
          </div>
          <div className="mt-8 grid gap-5 lg:grid-cols-3">
            {steps.map(({ number, icon: Icon, title, copy }) => (
              <article className="archival-card" data-testid={`landing-step-${number}`} key={number}>
                <div className="flex items-center justify-between">
                  <Icon className="h-6 w-6 text-primary" />
                  <span className="font-display text-3xl text-primary/30">{number}</span>
                </div>
                <h3 className="mt-6 font-display text-3xl text-foreground">{title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{copy}</p>
              </article>
            ))}
          </div>
          <Link
            className="pill-button mt-7"
            data-testid="landing-how-start-cta"
            onClick={() => trackStart("homepage_how")}
            to="/reunion/start"
          >
            Start a reunion draft <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </section>

        <section className="page-section pb-12" aria-labelledby="implemented-heading">
          <div className="archival-card">
            <p className="eyebrow-text">Already implemented</p>
            <h2 className="mt-3 font-display text-3xl text-foreground" id="implemented-heading">Real coordination tools behind the invitation.</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {[
                [CalendarDays, "No-account web RSVP", "Invitees can respond from a private link without installing an app."],
                [Soup, "Potluck claims", "Organizers list what is needed and signed-in family members claim items."],
                [HandHelping, "Volunteer sign-ups", "Create roles with capacity and see who has stepped in."],
                [Camera, "Photos and stories", "Attach reunion memories to the gathering’s long-term archive."],
              ].map(([Icon, title, copy]) => (
                <div className="soft-panel" key={title}>
                  <Icon className="h-5 w-5 text-primary" />
                  <h3 className="mt-3 font-semibold text-foreground">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="page-section scroll-mt-24 pb-16" id="use-cases">
          <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="archival-card">
              <p className="eyebrow-text">Beyond reunions</p>
              <h2 className="mt-3 font-display text-4xl text-foreground">The same private infrastructure serves other communities.</h2>
              <p className="mt-4 text-sm leading-7 text-muted-foreground">
                Reunion planning is the clearest way to begin. Existing church, intentional-community, Greek-organization, and cultural-collective capabilities remain available.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {useCases.map(([title, copy]) => (
                <article className="soft-panel" data-testid={`landing-use-case-${title.toLowerCase().replace(/\s+/g, "-")}`} key={title}>
                  <h3 className="font-display text-2xl text-foreground">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="page-section pb-16" id="plans">
          <div className="archival-card">
            <p className="eyebrow-text">Pricing</p>
            <h2 className="mt-3 font-display text-3xl text-foreground">Start planning without payment.</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">
              Seedling remains free. Current plan details stay public while web subscription purchasing is temporarily unavailable.
            </p>
            <div className="mt-5 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4" data-testid="landing-billing-notice" role="status">
              <p className="text-sm font-semibold text-foreground">Web subscriptions are temporarily unavailable while billing is being updated.</p>
            </div>
            <div className="mt-8" aria-live="polite">
              {plansLoading && <p className="text-sm text-muted-foreground">Loading current plans…</p>}
              {plansError && <p className="text-sm text-destructive" role="alert">{plansError}</p>}
              {!plansLoading && !plansError && <PublicPlanCards plans={plans.filter((plan) => plan.id !== "elder-grove")} />}
            </div>
            <Link className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-primary" data-testid="landing-see-all-plans-link" to="/pricing">
              See all plans <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="page-section border-t border-border/40 py-8" data-testid="landing-footer">
        <div className="flex flex-col items-center gap-6">
          {showStoreBadges ? (
            <div className="flex flex-wrap items-center justify-center gap-3">
              <a className="inline-block transition-opacity hover:opacity-80" href={APP_STORE_URL} rel="noopener noreferrer" target="_blank">
                <span className="inline-flex min-h-10 items-center rounded-lg border border-border bg-background px-4 text-sm font-semibold text-foreground">
                  Download on the App Store
                </span>
              </a>
              <a className="inline-block transition-opacity hover:opacity-80" href={PLAY_STORE_URL} rel="noopener noreferrer" target="_blank">
                <span className="inline-flex min-h-10 items-center rounded-lg border border-border bg-background px-4 text-sm font-semibold text-foreground">
                  Get it on Google Play
                </span>
              </a>
            </div>
          ) : null}
          <div className="flex w-full flex-col items-center gap-4 sm:flex-row sm:justify-between">
            <p className="text-xs text-muted-foreground">&copy; {new Date().getFullYear()} Ubuntu Market LLC. All rights reserved.</p>
            <nav aria-label="Footer navigation" className="flex gap-6">
              <Link className="text-xs text-muted-foreground transition-colors hover:text-foreground" to="/privacy">Privacy</Link>
              <Link className="text-xs text-muted-foreground transition-colors hover:text-foreground" to="/terms">Terms</Link>
              <Link className="text-xs text-muted-foreground transition-colors hover:text-foreground" to="/support">Support</Link>
            </nav>
          </div>
        </div>
      </footer>
    </div>
  );
};
