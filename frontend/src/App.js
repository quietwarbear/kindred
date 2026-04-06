import { useCallback, useEffect, useMemo, useState } from "react";
import { ThemeProvider } from "next-themes";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AppShell } from "@/components/layout/AppShell";
import { AuthPage } from "@/components/AuthPage";
import { LandingPage } from "@/components/LandingPage";
import { OnboardingPage } from "@/components/OnboardingPage";
import { PrivacyPolicyPage } from "@/components/PrivacyPolicyPage";
import { SupportPage } from "@/components/SupportPage";
import { TermsOfServicePage } from "@/components/TermsOfServicePage";
import { apiRequest } from "@/lib/api";
import { configureStatusBar, registerPush, setupAppListeners, isNative } from "@/lib/native-bridge";

const APP_STATE_KEY = "gathering-cypher-auth";
const MOBILE_GOOGLE_CALLBACK_URL = process.env.REACT_APP_MOBILE_GOOGLE_CALLBACK_URL || "kindred://auth/google/callback";

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

  const needsGoogleOnboarding = session?.user?.auth_provider === "google" && !session?.user?.onboarding_completed;
  if (needsGoogleOnboarding && location.pathname !== "/welcome") {
    return <Navigate replace to="/welcome" />;
  }

  if (!needsGoogleOnboarding && location.pathname === "/welcome") {
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
  const [freshLogin, setFreshLogin] = useState(false);

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

  const handleNativeGoogleCallback = useCallback(async (url) => {
    if (!url?.startsWith(MOBILE_GOOGLE_CALLBACK_URL)) return;
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

    const validateSession = async () => {
      try {
        const payload = await apiRequest("/auth/me", session?.token ? { token: session.token } : {});
        handleAuthSuccess({ ...payload, token: payload.token || session?.token });
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
      setupAppListeners(undefined, handleNativeGoogleCallback);
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
  }, [session?.token, handleNativeGoogleCallback]);

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
    const authUrl = `${process.env.REACT_APP_BACKEND_URL || ""}/api/auth/google/start?redirect_uri=${encodeURIComponent(MOBILE_GOOGLE_CALLBACK_URL)}`;
    try {
      const { Browser } = await import("@capacitor/browser");
      await Browser.open({ url: authUrl, presentationStyle: "popover" });
    } catch (_) {
      window.location.assign(authUrl);
    }
  }, []);

  const publicAuthPage = useMemo(
    () => <AuthPage onAuthSuccess={handleFreshLogin} onGoogleNativeSignIn={handleNativeGoogleSignIn} session={session} />,
    [handleFreshLogin, handleNativeGoogleSignIn, session]
  );
  const needsGoogleOnboarding = session?.user?.auth_provider === "google" && !session?.user?.onboarding_completed;

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
            <Route
              element={session?.token ? <Navigate replace to="/dashboard" /> : publicAuthPage}
              path="/login"
            />
            <Route
              element={session?.token ? (needsGoogleOnboarding ? <OnboardingPage onComplete={handleAuthSuccess} session={session} token={session.token} /> : <Navigate replace to="/home" />) : <Navigate replace to="/login" />}
              path="/welcome"
            />
            <Route element={<PrivacyPolicyPage />} path="/privacy" />
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
