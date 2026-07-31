import { useCallback, useEffect, useMemo, useState } from "react";
import { ThemeProvider } from "next-themes";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AppShell } from "@/components/layout/AppShell";
import { AuthPage } from "@/components/AuthPage";
import { InviteLandingPage } from "@/components/InviteLandingPage";
import { LandingPage } from "@/components/LandingPage";
import { PricingPage } from "@/components/PricingPage";
import { PrivacyPolicyPage } from "@/components/PrivacyPolicyPage";
import { PublicRSVPPage } from "@/components/PublicRSVPPage";
import { OrganizerCommandCenterPage } from "@/components/OrganizerCommandCenterPage";
import { ReunionAttendeeHubPage } from "@/components/ReunionAttendeeHubPage";
import { ReunionMemoryCapsulePage } from "@/components/ReunionMemoryCapsulePage";
import { FamilySpaceActivationPage } from "@/components/FamilySpaceActivationPage";
import { ReunionActivationPage } from "@/components/ReunionActivationPage";
import { ReunionStartPage } from "@/components/ReunionStartPage";
import { SSOHandoffPage } from "@/components/SSOHandoffPage";
import { SupportPage } from "@/components/SupportPage";
import { TermsOfServicePage } from "@/components/TermsOfServicePage";
import { apiRequest } from "@/lib/api";
import { identifyUser, resetAnalytics } from "@/lib/analytics";
import { configureStatusBar, registerPush, setupAppListeners, isNative } from "@/lib/native-bridge";
import { publicUrl } from "@/config/publicIdentity";

const APP_STATE_KEY = "gathering-cypher-auth";
const MOBILE_GOOGLE_CALLBACK_URL = process.env.REACT_APP_MOBILE_GOOGLE_CALLBACK_URL || "kindred://auth/google/callback";
const MOBILE_APPLE_CALLBACK_URL = "kindred://auth/apple/callback";
const INVITE_SCHEME_PREFIX = "kindred://invite/";
const INVITE_HTTPS_PREFIX = publicUrl("/invite/");

const FullScreenMessage = ({ title, copy }) => (
  <div className="app-canvas flex min-h-screen items-center justify-center px-6 py-16">
    <div className="archival-card max-w-xl text-center">
      <p className="eyebrow-text mb-3">Kindred</p>
      <h1 className="font-display text-4xl text-foreground">{title}</h1>
      <p className="mt-4 text-sm text-muted-foreground sm:text-base">{copy}</p>
    </div>
  </div>
);

const ProtectedApp = ({ session, onLogout, onSessionRefresh }) => {
  const location = useLocation();
  if (!session?.token) {
    return <Navigate replace to="/login" />;
  }

  const needsOrganizerActivation = !session?.user?.community_id;
  if (needsOrganizerActivation && location.pathname !== "/reunion/start") {
    return <Navigate replace to="/reunion/start" />;
  }

  if (!needsOrganizerActivation && location.pathname === "/welcome") {
    return <Navigate replace to="/home" />;
  }

  return (
    <AppShell
      community={session.community}
      onLogout={onLogout}
      onSessionRefresh={onSessionRefresh}
      token={session.token}
      user={session.user}
    />
  );
};

const AuthRoute = ({ session, authPage }) => {
  const location = useLocation();
  const intent = new URLSearchParams(location.search).get("intent");
  if (!session?.token) return authPage;
  if (intent === "reunion") return <Navigate replace to="/reunion/start" />;
  return <Navigate replace to="/dashboard" />;
};

function App() {
  const hasGoogleSessionId = window.location.hash?.includes("session_id=");
  const [session, setSession] = useState(() => {
    try {
      const saved = localStorage.getItem(APP_STATE_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [isLoading, setIsLoading] = useState(Boolean(session?.token));
  const [hasCheckedSession, setHasCheckedSession] = useState(false);

  // Analytics identity follows the session: identify on login/restore,
  // reset on logout so the next login isn't merged into the old person.
  useEffect(() => {
    if (session?.user?.id) {
      identifyUser(session.user);
    } else {
      resetAnalytics();
    }
  }, [session?.user?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const [freshLogin, setFreshLogin] = useState(false);
  const [pendingInviteCode, setPendingInviteCode] = useState(null);

  const handleAuthSuccess = useCallback((payload) => {
    const nextSession = {
      token: payload.token,
      user: payload.user,
      community: payload.community,
    };
    setSession(nextSession);
    localStorage.setItem(APP_STATE_KEY, JSON.stringify(nextSession));
  }, []);

  const handleFreshLogin = useCallback((payload) => {
    setFreshLogin(true);
    handleAuthSuccess(payload);
  }, [handleAuthSuccess]);

  const handleNativeAuthCallback = useCallback(async (url) => {
    // Handle Google callback
    if (url?.startsWith(MOBILE_GOOGLE_CALLBACK_URL)) {
      try {
        const parsed = new URL(url);
        const googleError = parsed.searchParams.get("google_error");
        const googleSuccess = parsed.searchParams.get("google_success");
        const token = parsed.searchParams.get("token");
        try {
          const { Browser } = await import("@capacitor/browser");
          await Browser.close();
        } catch (_) {
          // ignore close failures
        }
        if (googleError) {
          throw new Error(googleError);
        }
        if (!googleSuccess || !token) return;
        const payload = await apiRequest("/auth/me", { token });
        handleFreshLogin({ ...payload, token });
      } catch (error) {
        console.error("[Kindred] Native Google callback failed:", error);
      }
      return;
    }

    // Handle Apple callback
    if (url?.startsWith(MOBILE_APPLE_CALLBACK_URL)) {
      try {
        const parsed = new URL(url);
        const appleError = parsed.searchParams.get("apple_error");
        const appleSuccess = parsed.searchParams.get("apple_success");
        const token = parsed.searchParams.get("token");
        try {
          const { Browser } = await import("@capacitor/browser");
          await Browser.close();
        } catch (_) {
          // ignore close failures
        }
        if (appleError) {
          throw new Error(appleError);
        }
        if (!appleSuccess || !token) return;
        const payload = await apiRequest("/auth/me", { token });
        handleFreshLogin({ ...payload, token });
      } catch (error) {
        console.error("[Kindred] Native Apple callback failed:", error);
      }
      return;
    }

    // Handle invite deep links:
    //   kindred://invite/ABC12345
    //   https://www.heykindred.org/invite/ABC12345
    if (url?.startsWith(INVITE_SCHEME_PREFIX) || url?.startsWith(INVITE_HTTPS_PREFIX)) {
      try {
        let code;
        if (url.startsWith(INVITE_SCHEME_PREFIX)) {
          code = url.slice(INVITE_SCHEME_PREFIX.length).split(/[?#]/)[0];
        } else {
          code = url.slice(INVITE_HTTPS_PREFIX.length).split(/[?#]/)[0];
        }
        code = code.toUpperCase().trim();
        if (code.length === 8) {
          console.log("[Kindred] Invite deep link received, code:", code);
          setPendingInviteCode(code);
        }
      } catch (error) {
        console.error("[Kindred] Invite deep link failed:", error);
      }
    }
  }, [handleFreshLogin]);

  useEffect(() => {
    // Skip re-validation when we just completed a fresh login — the token
    // is already valid and re-calling /auth/me can race on slower devices
    // (iPad, spotty connections) causing the session to be cleared.
    if (freshLogin) {
      setIsLoading(false);
      setHasCheckedSession(true);
      return;
    }

    // No token — nothing to validate, go straight to login
    if (!session?.token) {
      setIsLoading(false);
      setHasCheckedSession(true);
      return;
    }

    const validateSession = async () => {
      try {
        const payload = await apiRequest("/auth/me", { token: session.token });
        handleAuthSuccess({ ...payload, token: payload.token || session.token });
      } catch {
        localStorage.removeItem(APP_STATE_KEY);
        setSession(null);
      } finally {
        setIsLoading(false);
        setHasCheckedSession(true);
      }
    };

    validateSession();
  }, [session?.token, freshLogin, handleAuthSuccess]);

  // Initialize native features when running in Capacitor
  useEffect(() => {
    if (isNative()) {
      configureStatusBar();
      setupAppListeners(undefined, handleNativeAuthCallback);
      if (session?.token) {
        registerPush(
          (pushToken) => {
            // Send push token to backend for server-side push
            apiRequest("/auth/push-token", {
              method: "POST",
              token: session.token,
              data: { push_token: pushToken },
            }).catch(() => {});
          },
          (notification) => {
            console.log("[Kindred] Push received:", notification);
          }
        );
      }
    }
  }, [session?.token, handleNativeAuthCallback]);

  const handleLogout = () => {
    localStorage.removeItem(APP_STATE_KEY);
    setSession(null);
  };

  const handleSessionRefresh = async () => {
    if (!session?.token) return;
    const payload = await apiRequest("/auth/me", { token: session.token });
    handleAuthSuccess({ ...payload, token: session.token });
  };

  const handleNativeGoogleSignIn = useCallback(async () => {
    if (!isNative()) return;
    const authUrl = `${process.env.REACT_APP_BACKEND_URL || "https://kindred-production-badd.up.railway.app"}/api/auth/google/start?redirect_uri=${encodeURIComponent(MOBILE_GOOGLE_CALLBACK_URL)}`;
    try {
      const { Browser } = await import("@capacitor/browser");
      await Browser.open({ url: authUrl, presentationStyle: "popover" });
    } catch (_) {
      window.location.assign(authUrl);
    }
  }, []);

  const publicAuthPage = useMemo(
    () => <AuthPage onAuthSuccess={handleFreshLogin} onGoogleNativeSignIn={handleNativeGoogleSignIn} session={session} pendingInviteCode={pendingInviteCode} onInviteCodeConsumed={() => setPendingInviteCode(null)} />,
    [handleFreshLogin, handleNativeGoogleSignIn, pendingInviteCode, session]
  );
  const needsOrganizerActivation = Boolean(session?.token && !session?.user?.community_id);

  if (hasGoogleSessionId && !session?.token) {
    return <FullScreenMessage copy="Completing your Google sign-in." title="Opening Kindred" />;
  }

  if (isLoading && !hasCheckedSession) {
    return <FullScreenMessage copy="Restoring your private community space." title="Opening the digital hearth" />;
  }

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="App min-h-screen bg-background text-foreground">
        <BrowserRouter>
          <Routes>
            <Route element={<LandingPage isAuthenticated={Boolean(session?.token)} />} path="/" />
            <Route element={<ReunionStartPage onSessionRefresh={handleAuthSuccess} session={session} />} path="/reunion/start" />
            <Route
              element={<ReunionActivationPage session={session} />}
              path="/reunion/activate/:eventId"
            />
            <Route
              element={<OrganizerCommandCenterPage session={session} />}
              path="/reunion/command/:eventId"
            />
            <Route
              element={<ReunionAttendeeHubPage session={session} />}
              path="/reunion/hub/:eventId"
            />
            <Route
              element={<ReunionMemoryCapsulePage session={session} />}
              path="/reunion/memories/:eventId"
            />
            <Route
              element={<FamilySpaceActivationPage onSessionRefresh={handleSessionRefresh} session={session} />}
              path="/family/activate"
            />
            <Route
              element={<AuthRoute authPage={publicAuthPage} session={session} />}
              path="/login"
            />
            <Route
              element={session?.token ? <Navigate replace to={needsOrganizerActivation ? "/reunion/start" : "/home"} /> : <Navigate replace to="/login" />}
              path="/welcome"
            />
            <Route element={<InviteLandingPage />} path="/invite/:code" />
            <Route element={<PublicRSVPPage />} path="/rsvp" />
            <Route element={<PublicRSVPPage />} path="/rsvp/:token" />
            <Route element={<SSOHandoffPage onAuthSuccess={handleFreshLogin} />} path="/sso" />
            <Route element={<PrivacyPolicyPage />} path="/privacy" />
            <Route element={<PricingPage />} path="/pricing" />
            <Route element={<TermsOfServicePage />} path="/terms" />
            <Route element={<SupportPage />} path="/support" />
            <Route
              element={
                <ProtectedApp
                  onLogout={handleLogout}
                  onSessionRefresh={handleSessionRefresh}
                  session={session}
                />
              }
              path="/*"
            />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </div>
    </ThemeProvider>
  );
}

export default App;
