import { useEffect, useMemo, useState } from "react";
import { ThemeProvider } from "next-themes";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AppShell } from "@/components/layout/AppShell";
import { AuthPage } from "@/components/AuthPage";
import { LandingPage } from "@/components/LandingPage";
import { StrategyPage } from "@/components/StrategyPage";
import { apiRequest } from "@/lib/api";

const APP_STATE_KEY = "gathering-cypher-auth";

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
  if (!session?.token) {
    return <Navigate replace to="/login" />;
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

  const handleAuthSuccess = (payload) => {
    const nextSession = {
      token: payload.token,
      user: payload.user,
      community: payload.community,
    };
    setSession(nextSession);
    localStorage.setItem(APP_STATE_KEY, JSON.stringify(nextSession));
  };

  useEffect(() => {
    const validateSession = async () => {
      try {
        const sessionId = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("session_id");
        if (sessionId) {
          const payload = await apiRequest("/auth/google/session", {
            method: "POST",
            data: { session_id: sessionId },
          });
          handleAuthSuccess(payload);
          window.history.replaceState({}, document.title, window.location.pathname);
          return;
        }

        const payload = await apiRequest("/auth/me", session?.token ? { token: session.token } : {});
        handleAuthSuccess({ ...payload, token: payload.token || session?.token });
      } catch {
        if (window.location.hash?.includes("session_id=")) {
          window.history.replaceState({}, document.title, window.location.pathname);
        }
        localStorage.removeItem(APP_STATE_KEY);
        setSession(null);
      } finally {
        setIsLoading(false);
        setHasCheckedSession(true);
      }
    };

    validateSession();
  }, [session?.token]);

  const handleLogout = () => {
    localStorage.removeItem(APP_STATE_KEY);
    setSession(null);
  };

  const handleSessionRefresh = async () => {
    if (!session?.token) return;
    const payload = await apiRequest("/auth/me", { token: session.token });
    handleAuthSuccess({ ...payload, token: session.token });
  };

  const publicAuthPage = useMemo(
    () => <AuthPage onAuthSuccess={handleAuthSuccess} session={session} />,
    [session]
  );

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
            <Route element={<StrategyPage mode="public" />} path="/strategy" />
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
