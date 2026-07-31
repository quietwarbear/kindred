import { useCallback, useEffect, useState } from "react";
import { ArrowRight, LockKeyhole, Users } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { isNative } from "@/lib/native-bridge";
import {
  clearReunionDraft,
  loadReunionDraft,
  provisionalCommunityName,
  reunionDraftIsComplete,
  reunionDraftToEventPayload,
} from "@/lib/reunionDraft";
import { toast } from "@/components/ui/sonner";

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || "168719752136-i70p8s13ajg5j8dc8gchm43jb84kv0s5.apps.googleusercontent.com";
const APPLE_CLIENT_ID = process.env.REACT_APP_APPLE_SERVICE_ID || "com.ubuntumarket.kindred.signin";

const initialLaunchState = {
  full_name: "",
  email: "",
  password: "",
  community_name: "",
  community_type: "family reunion",
  location: "",
  description: "",
  motto: "",
};

const initialJoinState = {
  full_name: "",
  email: "",
  password: "",
  invite_code: "",
};

const initialLoginState = {
  email: "",
  password: "",
};

export const AuthPage = ({ onAuthSuccess, onGoogleNativeSignIn, pendingInviteCode, onInviteCodeConsumed }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const intent = new URLSearchParams(location.search).get("intent") || "";
  const [reunionDraft] = useState(() => loadReunionDraft());
  const hasReunionIntent = intent === "reunion" && reunionDraftIsComplete(reunionDraft);
  const hasFamilyAccessIntent = intent === "family-access";
  const hasLightweightIntent = hasReunionIntent || hasFamilyAccessIntent;
  const [launchForm, setLaunchForm] = useState(initialLaunchState);
  const [joinForm, setJoinForm] = useState(initialJoinState);
  const [activeTab, setActiveTab] = useState(pendingInviteCode ? "join" : intent === "guest" ? "login" : hasFamilyAccessIntent ? "login" : "launch");

  // Pre-fill invite code from deep link
  useEffect(() => {
    if (pendingInviteCode) {
      setJoinForm((prev) => ({ ...prev, invite_code: pendingInviteCode }));
      setActiveTab("join");
      onInviteCodeConsumed?.();
    }
  }, [pendingInviteCode, onInviteCodeConsumed]);
  const [loginForm, setLoginForm] = useState(initialLoginState);
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [recoveryPassword, setRecoveryPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!hasReunionIntent) return;
    setLaunchForm((current) => ({
      ...current,
      full_name: current.full_name || reunionDraft.organizer_name,
    }));
  }, [hasReunionIntent, reunionDraft.organizer_name]);

  const completeAuthentication = useCallback(async (payload, message) => {
    onAuthSuccess(payload);
    toast.success(message);
    if (hasReunionIntent) {
      try {
        let activeSession = payload;
        if (!payload.user?.community_id) {
          activeSession = await apiRequest("/auth/onboarding/complete", {
            method: "POST",
            token: payload.token,
            data: {
              full_name: reunionDraft.organizer_name,
              community_name: provisionalCommunityName(reunionDraft),
              community_type: "family reunion",
              creation_mode: "reunion_first",
              location: reunionDraft.location,
            },
          });
          onAuthSuccess(activeSession);
          trackReunionEvent("organizer_intent_confirmed", { source: "account_boundary" });
        }
        const event = await apiRequest("/events", {
          method: "POST",
          token: activeSession.token,
          data: reunionDraftToEventPayload(reunionDraft),
        });
        clearReunionDraft();
        trackReunionEvent("reunion_saved", { source: "account_boundary" });
        navigate(`/reunion/activate/${event.id}`);
      } catch (error) {
        toast.error(error.response?.data?.detail || "Your account is ready, but the reunion draft could not be saved.");
        navigate("/reunion/start");
      }
      return;
    }
    if (hasFamilyAccessIntent) {
      navigate("/family/join");
      return;
    }
    navigate(payload.user?.community_id ? "/home" : "/reunion/start");
  }, [hasFamilyAccessIntent, hasReunionIntent, navigate, onAuthSuccess, reunionDraft]);

  const handleGoogleCredential = useCallback(async (response) => {
    setIsSubmitting(true);
    try {
      const payload = await apiRequest("/auth/google/session", {
        method: "POST",
        data: { credential: response.credential, family_access_intent: hasFamilyAccessIntent },
      });
      await completeAuthentication(payload, "Signed in with Google.");
    } catch (error) {
      const detail = error.response?.data?.detail;
        const msg = Array.isArray(detail) ? detail.map(e => e.msg).join(", ") : detail;
        toast.error(msg || "Unable to sign in with Google.");
    } finally {
      setIsSubmitting(false);
    }
  }, [completeAuthentication, hasFamilyAccessIntent]);

  const handleAppleSignIn = useCallback(async () => {
    setIsSubmitting(true);
    try {
      // On native iOS, use ASAuthorizationAppleIDProvider via the REST approach:
      // Open Apple's authorize endpoint in the system browser, which triggers
      // the native Apple Sign In sheet. The response posts back to our backend
      // which redirects to our deep link with the token.
      if (isNative()) {
        const backendUrl = process.env.REACT_APP_BACKEND_URL || "https://kindred-production-badd.up.railway.app";
        const callbackUrl = hasFamilyAccessIntent ? "kindred://auth/apple/callback?intent=family-access" : "kindred://auth/apple/callback";
        const authUrl = `${backendUrl}/api/auth/apple/start?redirect_uri=${encodeURIComponent(callbackUrl)}`;
        try {
          const { Browser } = await import("@capacitor/browser");
          await Browser.open({ url: authUrl, presentationStyle: "popover" });
        } catch (_) {
          window.location.assign(authUrl);
        }
        setIsSubmitting(false);
        return;
      }

      // Web: use Apple JS SDK popup
      if (!window.AppleID?.auth) {
        toast.error("Apple Sign In is loading. Please try again in a moment.");
        setIsSubmitting(false);
        return;
      }
      const result = await window.AppleID.auth.signIn();
      const idToken = result.authorization?.id_token;
      const fullName = [result.user?.name?.firstName, result.user?.name?.lastName].filter(Boolean).join(" ");
      const email = result.user?.email || "";

      if (!idToken) {
        toast.error("Apple Sign In did not return a valid token.");
        setIsSubmitting(false);
        return;
      }

      const payload = await apiRequest("/auth/apple/session", {
        method: "POST",
        data: { id_token: idToken, full_name: fullName, email, family_access_intent: hasFamilyAccessIntent },
      });
      await completeAuthentication(payload, "Signed in with Apple.");
    } catch (error) {
      // Error code 1001 or popup closed = user cancelled
      if (error?.code === "ERR_CANCELED" || error?.message?.includes("cancelled") || error?.code === 1001 || error?.error === "popup_closed_by_user") {
        // User cancelled — no toast needed
      } else {
        const detail = error.response?.data?.detail;
        const msg = Array.isArray(detail) ? detail.map(e => e.msg).join(", ") : detail;
        toast.error(msg || "Unable to sign in with Apple.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [completeAuthentication, hasFamilyAccessIntent]);

  // Initialize Apple JS SDK
  useEffect(() => {
    const initApple = () => {
      window.AppleID?.auth?.init({
        clientId: APPLE_CLIENT_ID,
        scope: "name email",
        redirectURI: window.location.origin + "/login",
        usePopup: true,
      });
    };
    if (window.AppleID?.auth) {
      initApple();
      return;
    }
    // Load Apple JS SDK if not already present
    const existing = document.querySelector('script[src*="appleid.auth.js"]');
    if (!existing) {
      const script = document.createElement("script");
      script.src = "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js";
      script.onload = initApple;
      document.head.appendChild(script);
    }
  }, []);

  useEffect(() => {
    if (isNative()) {
      return undefined;
    }
    const initGoogle = () => {
      if (!window.google?.accounts?.id) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleGoogleCredential,
        ux_mode: "popup",
      });
    };
    if (window.google?.accounts?.id) {
      initGoogle();
    } else {
      const interval = setInterval(() => {
        if (window.google?.accounts?.id) {
          clearInterval(interval);
          initGoogle();
        }
      }, 200);
      return () => clearInterval(interval);
    }
  }, [handleGoogleCredential]);

  const triggerGoogleSignIn = () => {
    if (isNative()) {
      onGoogleNativeSignIn?.(hasFamilyAccessIntent ? "family-access" : "");
      return;
    }
    if (window.google?.accounts?.id) {
      window.google.accounts.id.prompt();
    } else {
      toast.error("Google sign-in is loading. Please try again in a moment.");
    }
  };

  const handleLaunch = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = await apiRequest(hasFamilyAccessIntent ? "/auth/guest-account" : "/auth/bootstrap", {
        data: hasFamilyAccessIntent
          ? { full_name: launchForm.full_name, email: launchForm.email, password: launchForm.password }
          : hasReunionIntent
          ? {
              ...launchForm,
              community_name: provisionalCommunityName(reunionDraft),
              community_type: "family reunion",
              location: reunionDraft.location,
              description: "A provisional private planning space created for a family reunion.",
              creation_mode: "reunion_first",
              motto: "",
            }
          : launchForm,
        method: "POST",
      });
      await completeAuthentication(payload, hasFamilyAccessIntent ? "Your account is ready. No family access has been granted yet." : hasReunionIntent ? "Your reunion planning account is ready." : "Your private community has been opened.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to launch your community.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleJoin = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = await apiRequest("/auth/register-with-invite", { data: joinForm, method: "POST" });
      await completeAuthentication(payload, "Welcome into the community.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to accept that invite.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLogin = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = await apiRequest("/auth/login", { data: loginForm, method: "POST" });
      await completeAuthentication(payload, "Welcome back to your digital hearth.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to sign in.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRecoveryRequest = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = await apiRequest("/auth/password-recovery/request", {
        method: "POST",
        data: { email: recoveryEmail },
      });
      if (payload.delivery_status === "connection-ready") {
        toast.success("Password recovery is ready. Email delivery activates when the email provider is connected.");
      } else {
        toast.success("Recovery code sent. Check your email.");
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to start password recovery.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRecoveryVerify = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await apiRequest("/auth/password-recovery/verify", {
        method: "POST",
        data: { email: recoveryEmail, code: recoveryCode, new_password: recoveryPassword },
      });
      toast.success("Password updated. You can sign in now.");
      setRecoveryCode("");
      setRecoveryPassword("");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to verify recovery code.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <><div className="app-canvas min-h-screen py-8" data-ph-no-capture="true">
      <div className="page-section grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="archival-card flex flex-col justify-between gap-8 bg-stone-950 text-white">
          <div>
            <p className="eyebrow-text text-orange-200">Invitation-only access</p>
            <h1 className="mt-4 font-display text-4xl sm:text-5xl" data-testid="auth-headline">
              {hasFamilyAccessIntent ? "Ask to stay connected. Keep access deliberate." : hasReunionIntent ? "Save the reunion. Keep setup light." : "Plan the reunion. Bring everyone in. Keep the stories."}
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-7 text-stone-200 sm:text-base">
              {hasFamilyAccessIntent
                ? "Sign in or create an account, then send the private request already connected to your RSVP. An organizer must approve before family access begins."
                : hasReunionIntent
                ? "Your draft stays private until you create this account. We’ll save the gathering first; permanent family-space details can wait."
                : "Start with a private reunion plan, join your family with an invite code, or sign back in. Existing family chats can continue while Kindred keeps the plan together."}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-5" data-testid="auth-highlight-security">
              <LockKeyhole className="h-5 w-5 text-orange-200" />
              <p className="mt-3 text-lg font-semibold">Private organizer controls</p>
              <p className="mt-2 text-sm text-stone-300">Hosts and organizers manage invitations, responses, and planning details.</p>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-5" data-testid="auth-highlight-belonging">
              <Users className="h-5 w-5 text-orange-200" />
              <p className="mt-3 text-lg font-semibold">No-account RSVP</p>
              <p className="mt-2 text-sm text-stone-300">Relatives can respond from a private web invitation without creating an account.</p>
            </div>
          </div>
        </div>

        <div className="archival-card">
          <div className="mb-6">
            <p className="eyebrow-text text-orange-700 dark:text-orange-200">Social sign in / sign up</p>
            <p className="mt-2 text-sm text-muted-foreground">
              {hasFamilyAccessIntent
                ? "Use an account you control. Your email address is not used as proof that you belong to this family."
                : hasReunionIntent
                ? "Use Apple or Google to save the reunion with the organizer identity you already chose."
                : "Use Apple or Google to sign in after starting a reunion plan, or to return to a family space you already joined."}
            </p>
            <button
              className="mt-4 flex w-full items-center justify-center gap-3 rounded-full border border-border/70 bg-background px-6 py-3.5 text-sm font-semibold text-foreground shadow-sm transition-all hover:bg-accent/60 hover:shadow-md disabled:opacity-50"
              data-testid="google-signin-button"
              disabled={isSubmitting}
              onClick={triggerGoogleSignIn}
              type="button"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              Continue with Google
            </button>
            <button
              className="mt-3 flex w-full items-center justify-center gap-3 rounded-full border border-border/70 bg-black px-6 py-3.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-gray-900 hover:shadow-md disabled:opacity-50"
              data-testid="apple-signin-button"
              disabled={isSubmitting}
              onClick={handleAppleSignIn}
              type="button"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
              </svg>
              Sign in with Apple
            </button>
          </div>
          <div className="border-t border-border/50 pt-6" />
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className={`grid h-auto w-full ${hasLightweightIntent ? "grid-cols-2" : "grid-cols-3"} rounded-full bg-muted/70 p-1`}>
            <TabsTrigger className="rounded-full py-2" data-testid="auth-tab-launch" value="launch">
              {hasLightweightIntent ? "Create account" : "Launch"}
            </TabsTrigger>
            {!hasLightweightIntent ? (
              <TabsTrigger className="rounded-full py-2" data-testid="auth-tab-join" value="join">
                Join
              </TabsTrigger>
            ) : null}
            <TabsTrigger className="rounded-full py-2" data-testid="auth-tab-login" value="login">
              Sign in
            </TabsTrigger>
          </TabsList>

          <TabsContent value="launch">
            <form className="mt-6 grid gap-4" onSubmit={handleLaunch}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label>
                  <span className="field-label">Your full name</span>
                  <Input className="field-input" data-testid="launch-full-name-input" onChange={(e) => setLaunchForm((current) => ({ ...current, full_name: e.target.value }))} required value={launchForm.full_name} />
                </label>
                <label>
                  <span className="field-label">Email</span>
                  <Input className="field-input" data-testid="launch-email-input" onChange={(e) => setLaunchForm((current) => ({ ...current, email: e.target.value }))} required type="email" value={launchForm.email} />
                </label>
              </div>
              <div className={hasLightweightIntent ? "grid gap-4" : "grid gap-4 sm:grid-cols-2"}>
                <label>
                  <span className="field-label">Password</span>
                  <Input className="field-input" data-testid="launch-password-input" minLength={8} onChange={(e) => setLaunchForm((current) => ({ ...current, password: e.target.value }))} required type="password" value={launchForm.password} />
                </label>
                {!hasLightweightIntent ? (
                  <label>
                    <span className="field-label">Community type</span>
                    <Input className="field-input" data-testid="launch-community-type-input" onChange={(e) => setLaunchForm((current) => ({ ...current, community_type: e.target.value }))} required value={launchForm.community_type} />
                  </label>
                ) : null}
              </div>
              {!hasLightweightIntent ? (
                <>
                  <label>
                    <span className="field-label">Community name</span>
                    <Input className="field-input" data-testid="launch-community-name-input" onChange={(e) => setLaunchForm((current) => ({ ...current, community_name: e.target.value }))} required value={launchForm.community_name} />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label>
                      <span className="field-label">Location</span>
                      <Input className="field-input" data-testid="launch-location-input" onChange={(e) => setLaunchForm((current) => ({ ...current, location: e.target.value }))} required value={launchForm.location} />
                    </label>
                    <label>
                      <span className="field-label">Motto</span>
                      <Input className="field-input" data-testid="launch-motto-input" onChange={(e) => setLaunchForm((current) => ({ ...current, motto: e.target.value }))} value={launchForm.motto} />
                    </label>
                  </div>
                  <label>
                    <span className="field-label">What brings your people together?</span>
                    <Textarea className="field-textarea" data-testid="launch-description-input" onChange={(e) => setLaunchForm((current) => ({ ...current, description: e.target.value }))} required value={launchForm.description} />
                  </label>
                </>
              ) : hasReunionIntent ? (
                <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4" data-testid="reunion-account-summary">
                  <p className="text-sm font-semibold text-foreground">{reunionDraft.gathering_name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {reunionDraft.approximate_date}
                    {reunionDraft.end_date ? ` through ${reunionDraft.end_date}` : ""}
                    {" · "}
                    {reunionDraft.timezone}
                    {" · "}
                    {reunionDraft.location || "Location to be confirmed"}
                  </p>
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    A provisional planning space will be created behind the scenes. You can name the permanent family space after the first shared action.
                  </p>
                </div>
              ) : (
                <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4" data-testid="family-access-account-summary">
                  <p className="text-sm font-semibold text-foreground">Account first, approval second</p>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">Creating this account does not join a family space. Kindred will submit the private guest claim only after authentication.</p>
                </div>
              )}
              <Button className="rounded-full py-6 text-base" data-testid="launch-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Opening…" : hasFamilyAccessIntent ? "Create account and continue" : hasReunionIntent ? "Save reunion draft" : "Launch Kindred"}
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </form>
          </TabsContent>

          <TabsContent value="join">
            <form className="mt-6 grid gap-4" onSubmit={handleJoin}>
              <label>
                <span className="field-label">Invite code</span>
                <Input className="field-input uppercase" data-testid="join-invite-code-input" onChange={(e) => setJoinForm((current) => ({ ...current, invite_code: e.target.value.toUpperCase() }))} required value={joinForm.invite_code} />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label>
                  <span className="field-label">Your full name</span>
                  <Input className="field-input" data-testid="join-full-name-input" onChange={(e) => setJoinForm((current) => ({ ...current, full_name: e.target.value }))} required value={joinForm.full_name} />
                </label>
                <label>
                  <span className="field-label">Email matching the invite</span>
                  <Input className="field-input" data-testid="join-email-input" onChange={(e) => setJoinForm((current) => ({ ...current, email: e.target.value }))} required type="email" value={joinForm.email} />
                </label>
              </div>
              <label>
                <span className="field-label">Password</span>
                <Input className="field-input" data-testid="join-password-input" minLength={8} onChange={(e) => setJoinForm((current) => ({ ...current, password: e.target.value }))} required type="password" value={joinForm.password} />
              </label>
              <Button className="rounded-full py-6 text-base" data-testid="join-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Joining..." : "Join with invite"}
              </Button>
            </form>
          </TabsContent>

          <TabsContent value="login">
            <form className="mt-6 grid gap-4" onSubmit={handleLogin}>
              <label>
                <span className="field-label">Email</span>
                <Input className="field-input" data-testid="login-email-input" onChange={(e) => setLoginForm((current) => ({ ...current, email: e.target.value }))} required type="email" value={loginForm.email} />
              </label>
              <label>
                <span className="field-label">Password</span>
                <Input className="field-input" data-testid="login-password-input" onChange={(e) => setLoginForm((current) => ({ ...current, password: e.target.value }))} required type="password" value={loginForm.password} />
              </label>
              <Button className="rounded-full py-6 text-base" data-testid="login-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Signing in..." : "Sign in"}
              </Button>
            </form>
            <div className="mt-6 rounded-[24px] border border-border/70 bg-muted/40 p-5">
              <p className="eyebrow-text">Password recovery</p>
              <form className="mt-4 grid gap-3" onSubmit={handleRecoveryRequest}>
                <Input className="field-input" data-testid="password-recovery-email-input" onChange={(e) => setRecoveryEmail(e.target.value)} placeholder="Email for recovery code" type="email" value={recoveryEmail} />
                <Button className="rounded-full" data-testid="password-recovery-request-button" disabled={isSubmitting} type="submit" variant="secondary">
                  Request recovery code
                </Button>
              </form>
              <form className="mt-4 grid gap-3" onSubmit={handleRecoveryVerify}>
                <Input className="field-input" data-testid="password-recovery-code-input" onChange={(e) => setRecoveryCode(e.target.value)} placeholder="6-digit recovery code" value={recoveryCode} />
                <Input className="field-input" data-testid="password-recovery-new-password-input" minLength={8} onChange={(e) => setRecoveryPassword(e.target.value)} placeholder="New password" type="password" value={recoveryPassword} />
                <Button className="rounded-full" data-testid="password-recovery-verify-button" disabled={isSubmitting} type="submit" variant="secondary">
                  Reset password
                </Button>
              </form>
            </div>
          </TabsContent>
        </Tabs>
        </div>
      </div>
    </div><footer className="page-section border-t border-border/40 py-6 mt-8" data-testid="auth-footer">
        <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
          <Link className="text-xs text-muted-foreground hover:text-foreground transition-colors" data-testid="auth-footer-privacy-link" to="/privacy">
            Privacy Policy
          </Link>
          <span className="hidden sm:inline text-xs text-muted-foreground">·</span>
          <Link className="text-xs text-muted-foreground hover:text-foreground transition-colors" data-testid="auth-footer-terms-link" to="/terms">
            Terms of Service
          </Link>
        </div>
      </footer></>
  );
};
