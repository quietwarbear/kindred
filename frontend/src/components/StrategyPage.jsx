import { ArrowRight, BrainCircuit, Compass, Gem, LayoutTemplate, LineChart, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

const namingConcepts = [
  { name: "Gathering Cypher", note: "Signals intimacy, coordination, and cultural code-switching power." },
  { name: "Kinfolk Commons", note: "Warm, familial, and rooted in collective ownership." },
  { name: "Legacy Hearth", note: "Evokes memory, warmth, continuity, and home." },
  { name: "Diaspora Table", note: "Strong fit for trans-local and cultural gathering communities." },
];

const wireframeFlow = [
  "Landing page → launch community or enter with invite code",
  "Host setup → create community profile and first gathering",
  "Dashboard → see members, upcoming events, recent memories, contribution totals",
  "Events Hub → manage RSVPs, agendas, volunteer slots, potluck coordination, map links",
  "Memory Vault → upload images or voice notes, review AI tags, add family or ministry context",
  "Legacy Threads → preserve oral history, sermons, elder reflections, youth responses",
  "Contributions → launch private Stripe checkout and track transparent giving records",
];

const roadmap = [
  {
    phase: "MVP now",
    items: [
      "Invite-only auth with Host, Organizer, Member roles",
      "Events Hub with RSVP, agenda, volunteers, and potluck planning",
      "Memory Vault with image + voice-note uploads and AI tagging",
      "Legacy Threads for oral history, reflection, and commentary",
      "Stripe-backed contributions and private transaction visibility",
    ],
  },
  {
    phase: "Phase 2",
    items: [
      "Polling, board votes, and anonymous suggestion box",
      "Custom branding and institutional admin controls",
      "Deeper memory moderation, download controls, and archival exports",
      "Mentorship matching, scholarship workflows, and documentary generation",
    ],
  },
];

const competition = [
  {
    label: "Facebook Groups",
    edge: "Gathering Cypher wins on privacy, non-algorithmic visibility, and archival intentionality.",
  },
  {
    label: "WhatsApp + Google Drive",
    edge: "Gathering Cypher consolidates conversation, planning, media, and giving in one place.",
  },
  {
    label: "Church management software",
    edge: "Gathering Cypher feels more relational, story-centered, and media-rich for community memory.",
  },
  {
    label: "Event-only tools",
    edge: "Gathering Cypher extends beyond RSVPs into legacy, identity, and long-term engagement.",
  },
];

const sections = [
  {
    icon: Compass,
    title: "Venture pitch framing",
    copy: "Gathering Cypher is digital sovereignty infrastructure for cultural communities that need private gathering logistics, enduring memory, and recurring coordination.",
  },
  {
    icon: BrainCircuit,
    title: "Why it can grow",
    copy: "It replaces fragmented tools with a subscription product that compounds value every time a community gathers, remembers, and gives together.",
  },
  {
    icon: ShieldCheck,
    title: "Why it matters",
    copy: "Ownership over narrative, memory, and coordination becomes a product advantage when communities no longer trust public social platforms.",
  },
];

export const StrategyPage = ({ mode = "public" }) => {
  const wrapperClass = mode === "public" ? "app-canvas min-h-screen py-8" : "";
  const content = (
    <div className="space-y-6">
      <div className="archival-card">
        <p className="eyebrow-text">Strategy deck</p>
        <h1 className="mt-3 font-display text-4xl text-foreground sm:text-5xl" data-testid="strategy-page-title">
          Product framing for a private, legacy-centered community platform.
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="strategy-page-subtitle">
          This deck packages the concept across wireframe flow, naming, venture narrative, feature prioritization, and competitor positioning.
        </p>
        {mode === "public" ? (
          <div className="mt-6 flex flex-wrap gap-3">
            <Link className="pill-button" data-testid="strategy-open-auth-link" to="/login">
              Open the MVP <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
            <Link className="pill-button-secondary" data-testid="strategy-back-home-link" to="/">
              Back to landing page
            </Link>
          </div>
        ) : null}
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        {sections.map(({ icon: Icon, title, copy }) => (
          <article className="archival-card" data-testid={`strategy-section-${title.toLowerCase().replace(/\s+/g, "-")}`} key={title}>
            <Icon className="h-5 w-5 text-primary" />
            <h2 className="mt-4 font-display text-2xl text-foreground">{title}</h2>
            <p className="mt-3 text-sm leading-7 text-muted-foreground">{copy}</p>
          </article>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="archival-card" data-testid="strategy-wireframe-flow">
          <div className="flex items-center gap-3">
            <LayoutTemplate className="h-5 w-5 text-primary" />
            <h2 className="font-display text-3xl text-foreground">Wireframe flow</h2>
          </div>
          <ol className="mt-6 space-y-4 text-sm leading-7 text-muted-foreground">
            {wireframeFlow.map((item, index) => (
              <li className="flex gap-4" data-testid={`strategy-wireframe-step-${index + 1}`} key={item}>
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono-custom text-xs font-semibold text-primary">
                  {index + 1}
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
        </article>

        <article className="archival-card" data-testid="strategy-name-concepts">
          <div className="flex items-center gap-3">
            <Gem className="h-5 w-5 text-primary" />
            <h2 className="font-display text-3xl text-foreground">Brand naming concepts</h2>
          </div>
          <div className="mt-6 space-y-4">
            {namingConcepts.map((item) => (
              <div className="soft-panel" data-testid={`strategy-name-${item.name.toLowerCase().replace(/\s+/g, "-")}`} key={item.name}>
                <p className="text-lg font-semibold text-foreground">{item.name}</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.note}</p>
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="archival-card" data-testid="strategy-roadmap">
          <div className="flex items-center gap-3">
            <LineChart className="h-5 w-5 text-primary" />
            <h2 className="font-display text-3xl text-foreground">Feature prioritization roadmap</h2>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {roadmap.map((group) => (
              <div className="soft-panel" data-testid={`strategy-roadmap-${group.phase.toLowerCase().replace(/\s+/g, "-")}`} key={group.phase}>
                <p className="text-lg font-semibold text-foreground">{group.phase}</p>
                <ul className="mt-3 space-y-2 text-sm leading-7 text-muted-foreground">
                  {group.items.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </article>

        <article className="archival-card" data-testid="strategy-competition">
          <p className="eyebrow-text">Competitive landscape</p>
          <h2 className="mt-3 font-display text-3xl text-foreground">Where Gathering Cypher wins</h2>
          <div className="mt-6 space-y-4">
            {competition.map((item) => (
              <div className="soft-panel" data-testid={`strategy-competitor-${item.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} key={item.label}>
                <p className="text-lg font-semibold text-foreground">{item.label}</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.edge}</p>
              </div>
            ))}
          </div>
        </article>
      </div>
    </div>
  );

  if (mode === "public") {
    return <div className={wrapperClass}><div className="page-section">{content}</div></div>;
  }

  return content;
};