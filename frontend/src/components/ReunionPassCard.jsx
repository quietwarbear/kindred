import { ArrowRight, CalendarCheck, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/pricing";

// The pass sits BESIDE the tier ladder, not in it (decision 2026-09-23), so
// it gets its own card rather than a sixth column. A reunion is a project
// with an end date; the ladder sells months. This is the reunion-shaped door,
// and it has to read as a different kind of thing at a glance.
export const ReunionPassCard = ({ pass, onChoose }) => {
  if (!pass) return null;

  return (
    <section
      className="rounded-2xl border-2 border-primary/30 bg-primary/5 p-6 sm:p-8"
      data-testid="reunion-pass-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="max-w-xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-primary">
            Planning one reunion?
          </p>
          <h2 className="mt-2 font-display text-3xl text-foreground">
            {pass.name} — {formatPrice(pass.amount)}, once.
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{pass.tagline}</p>

          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <span className="flex items-center gap-2 font-medium text-foreground">
              <Users className="h-4 w-4 text-primary" /> No member limit
            </span>
            <span className="flex items-center gap-2 font-medium text-foreground">
              <CalendarCheck className="h-4 w-4 text-primary" /> Twelve months
            </span>
          </div>

          <ul className="mt-5 grid gap-2 sm:grid-cols-2">
            {pass.features?.map((feature) => (
              <li className="text-sm text-muted-foreground" key={feature}>• {feature}</li>
            ))}
          </ul>
        </div>

        <div className="w-full sm:w-auto sm:min-w-[200px]">
          {onChoose && (
            <Button
              className="w-full"
              data-testid="reunion-pass-choose"
              onClick={() => onChoose(pass.id)}
              size="lg"
            >
              Get the Reunion Pass <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          )}
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            One payment. It does not renew — after twelve months it simply ends,
            and your family space stays readable.
          </p>
        </div>
      </div>
    </section>
  );
};
