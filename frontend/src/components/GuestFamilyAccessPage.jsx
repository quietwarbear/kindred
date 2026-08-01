import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Clock3, LockKeyhole, RefreshCw, XCircle } from "lucide-react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import {
  clearFamilyAccessOperation,
  clearGuestFamilyClaim,
  familyAccessOperationKey,
  loadGuestFamilyClaim,
} from "@/lib/guestFamilyAccess";
import { toast } from "@/components/ui/sonner";

const STATUS_COPY = {
  pending: ["Request sent", "A family host or organizer will review it. Your RSVP remains saved."],
  approved: ["Welcome to the family space", "Your approved account is now the one canonical member for this family space."],
  declined: ["Request not approved", "Your reunion RSVP is unchanged. You can contact the organizer if you have questions."],
  cancelled: ["Request cancelled", "Your reunion RSVP is unchanged."],
  expired: ["Request expired", "Ask the organizer for a fresh private invitation if you still want to join."],
  conflict: ["Organizer help needed", "Kindred could not safely connect this account. Nothing was merged across family spaces."],
  none: ["No family access request", "Return to your private reunion invitation to start an optional request."],
};

const operationKey = (prefix) => {
  const key = `kindred:family-access:${prefix}`;
  const existing = window.sessionStorage.getItem(key);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `${prefix}:${random}`;
  window.sessionStorage.setItem(key, value);
  return value;
};

export const GuestFamilyAccessPage = ({ session, onSessionRefresh }) => {
  const navigate = useNavigate();
  const [access, setAccess] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const submittedRef = useRef(false);

  const loadStatus = useCallback(async () => {
    const payload = await apiRequest("/family-access/status", { token: session.token });
    setAccess(payload);
    return payload;
  }, [session?.token]);

  useEffect(() => {
    if (!session?.token || submittedRef.current) return;
    submittedRef.current = true;
    const submitOrLoad = async () => {
      setBusy(true);
      setError("");
      try {
        const claim = loadGuestFamilyClaim();
        let payload;
        if (claim) {
          payload = await apiRequest("/family-access/requests", {
            method: "POST",
            token: session.token,
            headers: { "X-Kindred-Guest-Claim": claim },
            data: { idempotency_key: familyAccessOperationKey() },
          });
          clearGuestFamilyClaim();
          clearFamilyAccessOperation();
          trackReunionEvent("guest_family_access_submitted", {
            source: "family_access_boundary",
            request_state: payload.status,
          });
        } else {
          payload = await loadStatus();
        }
        setAccess(payload);
        if (payload.status === "approved") await onSessionRefresh?.();
      } catch (requestError) {
        const detail = requestError.response?.data?.detail;
        setError(typeof detail === "string" ? detail : detail?.message || "This family access request could not be opened safely.");
      } finally {
        setBusy(false);
      }
    };
    submitOrLoad();
  }, [loadStatus, onSessionRefresh, session?.token]);

  if (!session?.token) return <Navigate replace to="/login?intent=family-access" />;

  const refresh = async () => {
    setBusy(true);
    try {
      const payload = await loadStatus();
      trackReunionEvent("guest_family_access_status_viewed", {
        source: "family_access_boundary", request_state: payload.status,
      });
      if (payload.status === "approved") await onSessionRefresh?.();
    } catch {
      toast.error("The latest request status is unavailable.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!access || access.status !== "pending") return;
    setBusy(true);
    try {
      const payload = await apiRequest("/family-access/cancel", {
        method: "POST", token: session.token,
        data: { expected_revision: access.revision, idempotency_key: operationKey("cancel-family-access") },
      });
      setAccess(payload);
      trackReunionEvent("guest_family_access_cancelled", { source: "family_access_boundary", request_state: payload.status });
    } catch (requestError) {
      toast.error(requestError.response?.data?.detail?.message || "This request changed. Refresh before trying again.");
    } finally {
      setBusy(false);
    }
  };

  const confirmAccess = async () => {
    setBusy(true);
    try {
      await apiRequest("/family-access/confirm", { method: "POST", token: session.token });
      await onSessionRefresh?.();
      navigate("/home");
    } catch {
      toast.error("Approved family access could not be confirmed safely.");
    } finally {
      setBusy(false);
    }
  };

  const status = access?.status || "none";
  const [title, copy] = STATUS_COPY[status] || STATUS_COPY.conflict;
  const Icon = status === "approved" ? CheckCircle2 : status === "pending" ? Clock3 : status === "declined" || status === "cancelled" ? XCircle : LockKeyhole;

  return (
    <div className="app-canvas min-h-screen px-6 py-12" data-ph-no-capture="true" data-testid="guest-family-access-page">
      <main className="archival-card mx-auto max-w-2xl text-center">
        <p className="eyebrow-text">Private family access</p>
        <Icon className="mx-auto mt-6 h-9 w-9 text-primary" />
        <h1 className="mt-4 font-display text-4xl">{busy && !access ? "Opening your request…" : title}</h1>
        <p className="mx-auto mt-4 max-w-xl text-sm leading-7 text-muted-foreground">{error || copy}</p>
        {status === "approved" && access?.family_space_name ? <p className="mt-4 text-lg font-semibold">{access.family_space_name}</p> : null}
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          {status === "approved" ? <Button disabled={busy} onClick={confirmAccess} type="button">Confirm and open family space</Button> : null}
          {status === "pending" ? (
            <>
              <Button disabled={busy} onClick={refresh} type="button" variant="outline"><RefreshCw className="mr-2 h-4 w-4" />Check status</Button>
              <Button disabled={busy} onClick={cancel} type="button" variant="ghost">Cancel request</Button>
            </>
          ) : null}
          {status !== "approved" && status !== "pending" ? <Button asChild variant="outline"><Link to="/">Return to Kindred</Link></Button> : null}
        </div>
        <p className="mt-7 text-xs leading-5 text-muted-foreground">This page shows only your own request. Other guests and pending requests are never listed here.</p>
      </main>
    </div>
  );
};

export default GuestFamilyAccessPage;
