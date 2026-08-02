import { useCallback, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { pilotActionLabel, pilotStatusLabel } from "@/lib/pilotCohort";
import { toast } from "@/components/ui/sonner";

const STATUS_PILL = {
  enrolled: "bg-sky-100 text-sky-800 dark:bg-sky-950/40 dark:text-sky-200",
  consented: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200",
  active: "bg-primary/15 text-primary",
  completed: "bg-muted text-muted-foreground",
  withdrawn: "bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200",
  not_enrolled: "bg-muted text-muted-foreground",
};

export const PilotCohortPage = ({ token, user }) => {
  const [cohort, setCohort] = useState(null);
  const [enrollId, setEnrollId] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    try {
      const payload = await apiRequest("/pilot/cohort", { token });
      setCohort(payload);
      setEnrollId(payload.available?.[0]?.community_id || "");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load the pilot cohort.");
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const act = useCallback(
    async (communityId, action) => {
      if (action === "record_consent") {
        const ok = window.confirm(
          "Confirm the organizer has explicitly agreed to take part in the pilot and understands what data will be entered. Only record consent if that conversation actually happened."
        );
        if (!ok) return;
      }
      setBusyId(communityId + action);
      try {
        await apiRequest(`/pilot/cohort/${communityId}/action`, {
          method: "POST",
          token,
          data: {
            action,
            consent_confirmed: action === "record_consent",
          },
        });
        toast.success(`${pilotActionLabel(action)} recorded.`);
        await load();
      } catch (error) {
        toast.error(
          error.response?.data?.detail?.code ||
            error.response?.data?.detail ||
            "That action wasn't allowed."
        );
      } finally {
        setBusyId("");
      }
    },
    [load, token]
  );

  if (!user?.is_platform_admin) {
    return (
      <div className="soft-panel" data-testid="pilot-cohort-denied">
        <p className="text-sm text-muted-foreground">
          Pilot cohort management is available to platform admins only.
        </p>
      </div>
    );
  }

  const counts = cohort?.counts || {};

  return (
    <div className="flex flex-col gap-4" data-testid="pilot-cohort-page">
      <div className="soft-panel">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <p className="eyebrow-text">Pilot cohort</p>
        </div>
        <h2 className="mt-2 font-display text-2xl text-foreground">
          Consent &amp; cohort management
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Enroll a community, record the organizer's explicit consent, and track the
          pilot's status. Recording consent here is bookkeeping for a conversation you
          have out of band — it sends nothing and enables no delivery.
        </p>

        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          {["enrolled", "consented", "active", "completed", "withdrawn"].map((s) => (
            <span
              key={s}
              className={`rounded-full px-3 py-1 font-semibold ${STATUS_PILL[s]}`}
              data-testid={`cohort-count-${s}`}
            >
              {pilotStatusLabel(s)}: {counts[s] || 0}
            </span>
          ))}
        </div>
      </div>

      <div className="soft-panel">
        <p className="text-sm font-semibold text-foreground">Enroll a community</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            className="field-input max-w-xs"
            data-testid="cohort-enroll-select"
            onChange={(e) => setEnrollId(e.target.value)}
            value={enrollId}
          >
            {(cohort?.available || []).length === 0 ? (
              <option value="">No communities available</option>
            ) : (
              (cohort?.available || []).map((c) => (
                <option key={c.community_id} value={c.community_id}>
                  {c.community_name || c.community_id}
                </option>
              ))
            )}
          </select>
          <Button
            className="rounded-full"
            data-testid="cohort-enroll-button"
            disabled={!enrollId || busyId === enrollId + "enroll"}
            onClick={() => act(enrollId, "enroll")}
            size="sm"
            type="button"
          >
            Enroll
          </Button>
        </div>
      </div>

      <div className="soft-panel">
        <p className="text-sm font-semibold text-foreground">
          In the cohort ({cohort?.cohort_size || 0})
        </p>
        <div className="mt-3 flex flex-col gap-2" data-testid="cohort-list">
          {(cohort?.cohort || []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No communities enrolled yet.
            </p>
          ) : (
            (cohort?.cohort || []).map((c) => (
              <div
                className="flex flex-col gap-2 rounded-xl border border-border bg-background/70 p-3 sm:flex-row sm:items-center sm:justify-between"
                data-testid={`cohort-row-${c.community_id}`}
                key={c.community_id}
              >
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {c.community_name || c.community_id}
                  </p>
                  <span
                    className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_PILL[c.status]}`}
                  >
                    {pilotStatusLabel(c.status)}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(c.allowed_actions || []).map((action) => (
                    <button
                      className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted/60"
                      data-testid={`cohort-action-${c.community_id}-${action}`}
                      disabled={busyId === c.community_id + action}
                      key={action}
                      onClick={() => act(c.community_id, action)}
                      type="button"
                    >
                      {pilotActionLabel(action)}
                    </button>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
