import { ArrowLeft, ArrowRight, CalendarHeart, MessageCircleHeart, Users } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { trackReunionEvent } from "@/lib/analytics";

const INTENTS = [
  {
    key: "plan",
    icon: CalendarHeart,
    title: "Plan a gathering",
    blurb: "A reunion, holiday meal, or celebration. Draft it in minutes and see exactly what family will receive — before you make an account.",
    action: "Start planning",
    to: "/reunion/start",
    testid: "intent-plan",
  },
  {
    key: "join",
    icon: Users,
    title: "Join my family",
    blurb: "Someone already invited you. Enter your invite code to RSVP and step into your family's private space.",
    action: "Enter an invite code",
    to: "/login?intent=join",
    testid: "intent-join",
  },
  {
    key: "preserve",
    icon: MessageCircleHeart,
    title: "Preserve a story",
    blurb: "Start a private family space around the memories that matter. Capture the first story now; plan a gathering around it whenever you're ready.",
    action: "Start with a story",
    to: "/reunion/start?focus=memory",
    testid: "intent-preserve",
  },
];

export const IntentChooserPage = () => {
  const navigate = useNavigate();

  const choose = (intent) => {
    trackReunionEvent("intent_selected", { intent: intent.key });
    navigate(intent.to);
  };

  return (
    <div className="app-canvas min-h-screen py-8 sm:py-12" data-ph-no-capture="true">
      <main className="page-section">
        <Link className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline" to="/">
          <ArrowLeft className="h-4 w-4" /> Back to Kindred
        </Link>

        <div className="mt-8 max-w-2xl">
          <p className="eyebrow-text">Welcome to Kindred</p>
          <h1 className="mt-3 font-display text-4xl leading-tight text-foreground sm:text-5xl" data-testid="intent-chooser-headline">
            What brings you here today?
          </h1>
          <p className="mt-4 text-sm leading-7 text-muted-foreground sm:text-base">
            Pick the one that fits right now. You can do all three later — this just gets you to the right place fastest.
          </p>
        </div>

        <div className="mt-8 grid gap-5 lg:grid-cols-3" role="list">
          {INTENTS.map((intent) => {
            const Icon = intent.icon;
            return (
              <button
                className="archival-card flex h-full flex-col items-start gap-4 text-left transition duration-300 hover:border-primary hover:shadow-md"
                data-testid={intent.testid}
                key={intent.key}
                onClick={() => choose(intent)}
                role="listitem"
                type="button"
              >
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Icon className="h-6 w-6" />
                </span>
                <div className="flex-1">
                  <h2 className="font-display text-2xl text-foreground">{intent.title}</h2>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{intent.blurb}</p>
                </div>
                <span className="inline-flex items-center gap-2 text-sm font-semibold text-primary">
                  {intent.action} <ArrowRight className="h-4 w-4" />
                </span>
              </button>
            );
          })}
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
          <span>Already have a family space?</span>
          <Button asChild variant="link">
            <Link data-testid="intent-signin-link" to="/login?intent=guest">Sign in</Link>
          </Button>
        </div>
      </main>
    </div>
  );
};

export default IntentChooserPage;
