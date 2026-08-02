import { ArrowRight, TrendingUp } from "lucide-react";

import { buildActivationFunnel } from "@/lib/activationFunnel";

const STAGE_HINT = {
  prepared: "invitations created",
  reached: "invitations that left the app",
  opened: "opened by guests",
  responded: "people have replied",
};

// An at-a-glance activation funnel for organizers. It renders ONLY the bounded,
// content-free counts from the readiness signal — never names, contacts, or
// links — and surfaces the single next best action.
export const ActivationFunnel = ({ readiness, onAction }) => {
  const funnel = buildActivationFunnel(
    readiness?.aggregate_counts || {},
    readiness?.next_action_code
  );

  return (
    <section
      className="rounded-2xl border border-border bg-background/70 p-4"
      data-testid="activation-funnel"
    >
      <div className="flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-primary" />
        <p className="eyebrow-text">Activation</p>
      </div>

      {funnel.hasActivity ? (
        <>
          <div className="mt-4 flex flex-col gap-3">
            {funnel.stages.map((stage) => (
              <div key={stage.key} data-testid={`funnel-stage-${stage.key}`}>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-semibold text-foreground">
                    {stage.label}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      {STAGE_HINT[stage.key]}
                    </span>
                  </span>
                  <span className="tabular-nums font-semibold text-foreground">
                    {stage.count}
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      · {stage.pct}%
                    </span>
                  </span>
                </div>
                <div
                  className="mt-1 h-2 overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  aria-label={`${stage.label}: ${stage.count} of ${funnel.prepared}`}
                  aria-valuenow={stage.pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${stage.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {funnel.delivered > 0 || funnel.shared > 0 ? (
            <p
              className="mt-3 text-xs text-muted-foreground"
              data-testid="funnel-reached-breakdown"
            >
              Of those reached: {funnel.delivered} delivered by email
              {funnel.shared > 0 ? `, ${funnel.shared} shared by you` : ""}.
            </p>
          ) : null}

          {funnel.awaiting > 0 ? (
            <p
              className="mt-3 rounded-xl border border-amber-300 bg-amber-50/70 px-3 py-2 text-xs leading-5 text-amber-900 dark:bg-amber-950/20 dark:text-amber-200"
              data-testid="funnel-awaiting"
            >
              {funnel.awaiting} {funnel.awaiting === 1 ? "person was" : "people were"}{" "}
              reached but {funnel.awaiting === 1 ? "hasn't" : "haven't"} answered yet.
            </p>
          ) : null}
        </>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground" data-testid="funnel-empty">
          No invitations yet. Once you prepare and share them, you'll see how many
          were opened and answered here.
        </p>
      )}

      {funnel.nextAction ? (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-xl bg-primary/5 px-3 py-2">
          <span className="text-xs uppercase tracking-[0.12em] text-primary">
            Next best step
          </span>
          {onAction ? (
            <button
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
              data-testid="funnel-next-action"
              onClick={() => onAction(funnel.nextAction.code)}
              type="button"
            >
              {funnel.nextAction.label}
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          ) : (
            <span
              className="text-xs font-semibold text-foreground"
              data-testid="funnel-next-action"
            >
              {funnel.nextAction.label}
            </span>
          )}
        </div>
      ) : null}

      <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
        Measured privately from bounded counts only — never names, contacts, or links.
      </p>
    </section>
  );
};
