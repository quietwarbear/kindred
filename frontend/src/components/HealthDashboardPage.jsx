import { useCallback, useEffect, useState } from "react";
import { Activity, HandHeart, HeartPulse, Sprout, Users } from "lucide-react";

import { apiRequest, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const Stat = ({ value, label, testId }) => (
  <div className="soft-panel" data-testid={testId}>
    <p className="font-display text-3xl text-foreground">{value}</p>
    <p className="mt-1 text-sm text-muted-foreground">{label}</p>
  </div>
);

export const HealthDashboardPage = ({ token }) => {
  const [data, setData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      setData(await apiRequest("/community/health", { token }));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load community health.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const p = data?.participation;
  const c = data?.contribution;
  const l = data?.leadership;
  const g = data?.intergenerational;
  const a = data?.archive;

  return (
    <div className="space-y-6" data-testid="health-dashboard-page">
      <section className="archival-card">
        <div className="flex items-start gap-3">
          <HeartPulse className="mt-1 h-5 w-5 text-primary" />
          <div>
            <p className="eyebrow-text">Community health</p>
            <h2 className="mt-1 font-display text-3xl text-foreground" data-testid="health-title">
              How is the village doing?
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">
              Signals that matter more than likes — who's taking part, who's giving and leading,
              and whether elders and youth are both in the room. A mirror, not a leaderboard.
            </p>
          </div>
        </div>
      </section>

      {isLoading ? (
        <section className="archival-card" data-testid="health-loading">
          <p className="text-sm text-muted-foreground">Reading the room…</p>
        </section>
      ) : !data ? null : (
        <>
          <section className="archival-card" data-testid="health-participation">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <p className="eyebrow-text">Participation</p>
            </div>
            <div className="mt-3 flex flex-wrap items-end gap-6">
              <div>
                <p className="font-display text-5xl text-foreground" data-testid="health-participation-rate">{p?.rate ?? 0}%</p>
                <p className="mt-1 text-sm text-muted-foreground">of members active in the last 90 days</p>
              </div>
              <p className="text-sm text-muted-foreground">
                <span className="font-semibold text-foreground">{p?.active ?? 0}</span> of {p?.total ?? 0} members
                have added a memory or story, or RSVP'd to a gathering recently.
              </p>
            </div>
          </section>

          <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            <Stat value={c ? shortCurrency(c.funds_raised || 0) : "$0"} label="Contributed to date" testId="health-funds" />
            <Stat value={c?.content_contributors ?? 0} label="Members who've shared a memory or story" testId="health-contributors" />
            <Stat value={c?.volunteers ?? 0} label="Volunteers signed up across gatherings" testId="health-volunteers" />
            <Stat value={l?.stewards ?? 0} label="Members carrying a role (leadership)" testId="health-stewards" />
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <article className="archival-card" data-testid="health-intergenerational">
              <div className="flex items-center gap-2">
                <Sprout className="h-4 w-4 text-primary" />
                <p className="eyebrow-text">Across generations</p>
              </div>
              <div className="mt-3 flex gap-8">
                <div>
                  <p className="font-display text-3xl text-foreground">{g?.elder_voices ?? 0}</p>
                  <p className="mt-1 text-sm text-muted-foreground">elder voices preserved</p>
                </div>
                <div>
                  <p className="font-display text-3xl text-foreground">{g?.youth_reflections ?? 0}</p>
                  <p className="mt-1 text-sm text-muted-foreground">youth reflections</p>
                </div>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                A first read on intergenerational care — both generations contributing to the archive.
              </p>
            </article>

            <article className="archival-card" data-testid="health-leadership">
              <div className="flex items-center gap-2">
                <HandHeart className="h-4 w-4 text-primary" />
                <p className="eyebrow-text">Who's stepping up</p>
              </div>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">
                <span className="font-semibold text-foreground">{l?.stewards ?? 0}</span> members hold a role beyond member.
              </p>
              {l?.roles?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {l.roles.map((role) => (
                    <span className="rounded-full bg-muted/60 px-3 py-1.5 text-xs font-medium text-foreground" key={role}>{role}</span>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-muted-foreground">No roles assigned yet — a chance to invite people into leadership.</p>
              )}
            </article>
          </section>

          <section className="archival-card" data-testid="health-archive">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-primary" />
              <p className="eyebrow-text">The living record</p>
            </div>
            <div className="mt-3 grid gap-5 sm:grid-cols-3">
              <Stat value={a?.gatherings ?? 0} label="Gatherings" testId="health-gatherings" />
              <Stat value={a?.memories ?? 0} label="Memories" testId="health-memories" />
              <Stat value={a?.stories ?? 0} label="Stories" testId="health-stories" />
            </div>
          </section>
        </>
      )}
    </div>
  );
};

export default HealthDashboardPage;
