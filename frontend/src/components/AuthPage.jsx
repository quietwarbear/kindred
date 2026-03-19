import { useState } from "react";
import { ArrowRight, LockKeyhole, Users } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

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

export const AuthPage = ({ onAuthSuccess }) => {
  const navigate = useNavigate();
  const [launchForm, setLaunchForm] = useState(initialLaunchState);
  const [joinForm, setJoinForm] = useState(initialJoinState);
  const [loginForm, setLoginForm] = useState(initialLoginState);
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [recoveryPassword, setRecoveryPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  

  const handleSuccess = (payload, message) => {
    onAuthSuccess(payload);
    toast.success(message);
    navigate("/dashboard");
  };

  const handleLaunch = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = await apiRequest("/auth/bootstrap", { data: launchForm, method: "POST" });
      handleSuccess(payload, "Your private community has been opened.");
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
      handleSuccess(payload, "Welcome into the community.");
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
      handleSuccess(payload, "Welcome back to your digital hearth.");
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
    <><div className="app-canvas min-h-screen py-8">
      <div className="page-section grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="archival-card flex flex-col justify-between gap-8 bg-stone-950 text-white">
          <div>
            <p className="eyebrow-text text-orange-200">Invitation-only access</p>
            <h1 className="mt-4 font-display text-4xl sm:text-5xl" data-testid="auth-headline">
              Welcome to the digital home your community owns.
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-7 text-stone-200 sm:text-base">
              Create a host account for your community, join with an invite code, or sign back in to plan events, share memories, and preserve legacy.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-5" data-testid="auth-highlight-security">
              <LockKeyhole className="h-5 w-5 text-orange-200" />
              <p className="mt-3 text-lg font-semibold">Roles that protect trust</p>
              <p className="mt-2 text-sm text-stone-300">Hosts, organizers, and members each get the right level of access.</p>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-5" data-testid="auth-highlight-belonging">
              <Users className="h-5 w-5 text-orange-200" />
              <p className="mt-3 text-lg font-semibold">Built for belonging</p>
              <p className="mt-2 text-sm text-stone-300">Perfect for reunions, ministries, cultural organizations, and diaspora circles.</p>
            </div>
          </div>
        </div>

        <div className="archival-card">
        <Tabs defaultValue="launch">
          <TabsList className="grid h-auto w-full grid-cols-3 rounded-full bg-muted/70 p-1">
            <TabsTrigger className="rounded-full py-2" data-testid="auth-tab-launch" value="launch">
              Launch
            </TabsTrigger>
            <TabsTrigger className="rounded-full py-2" data-testid="auth-tab-join" value="join">
              Join
            </TabsTrigger>
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
              <div className="grid gap-4 sm:grid-cols-2">
                <label>
                  <span className="field-label">Password</span>
                  <Input className="field-input" data-testid="launch-password-input" minLength={8} onChange={(e) => setLaunchForm((current) => ({ ...current, password: e.target.value }))} required type="password" value={launchForm.password} />
                </label>
                <label>
                  <span className="field-label">Community type</span>
                  <Input className="field-input" data-testid="launch-community-type-input" onChange={(e) => setLaunchForm((current) => ({ ...current, community_type: e.target.value }))} required value={launchForm.community_type} />
                </label>
              </div>
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
              <Button className="rounded-full py-6 text-base" data-testid="launch-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Opening community..." : "Launch Kindred"}
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