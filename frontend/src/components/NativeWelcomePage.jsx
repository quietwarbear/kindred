import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { gatheringCampaign } from "@/lib/seasonalCampaign";
import { privateInvitationDestination } from "@/lib/privateInvitationDestination";

export const NativeWelcomePage = () => {
  const campaign = gatheringCampaign();
  return <main className="app-canvas min-h-screen px-5 pb-8" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 1.5rem)" }} data-ph-no-capture="true" data-testid="native-welcome">
    <div className="mx-auto max-w-md">
      <p className="eyebrow-text">Welcome to Kindred</p>
      <h1 className="mt-3 font-display text-4xl text-foreground">Your private family space.</h1>
      <p className="mt-3 text-muted-foreground">Sign in, create your account, or open the invitation your family sent you.</p>
      <div className="mt-7 grid gap-4" aria-label="Get started">
        <Button asChild className="min-h-14 rounded-2xl text-base"><Link to="/login?intent=signin">Sign in</Link></Button>
        <Button asChild className="min-h-14 rounded-2xl text-base" variant="outline"><Link to="/login?intent=create-account">Create an account</Link></Button>
        <Button asChild className="min-h-14 rounded-2xl text-base" variant="outline"><Link to="/invitation">Continue with an invitation</Link></Button>
      </div>
      <p className="mt-4 text-sm text-muted-foreground">You can RSVP from a private event invitation without creating an account.</p>
      {campaign.active && <aside className="soft-panel mt-8" data-testid="native-campaign-secondary">
        <h2 className="font-display text-xl">Keep The Record</h2>
        <p className="mt-2 text-sm text-muted-foreground">Gather your family and preserve a recipe or story.</p>
        <Link className="mt-3 inline-block text-sm font-semibold text-primary" to="/reunion/start">Explore the gathering campaign</Link>
      </aside>}
      <div className="mt-6 flex gap-5 text-sm text-muted-foreground"><Link to="/privacy">Privacy</Link><Link to="/support">Help</Link></div>
    </div>
  </main>;
};

export const NativeInvitationPage = () => {
  const navigate = useNavigate();
  const [link, setLink] = useState("");
  const [error, setError] = useState("");
  const openInvitation = (event) => {
    event.preventDefault();
    const destination = privateInvitationDestination(link);
    if (!destination) { setError("Paste a private Kindred invitation link, or ask your organizer to send one."); return; }
    navigate(destination);
  };
  return <main className="page-section py-8" data-ph-no-capture="true">
    <Link className="font-semibold text-primary" to="/">Back to Kindred</Link>
    <h1 className="mt-6 font-display text-3xl">Open your invitation</h1>
    <p className="mt-3 text-muted-foreground">Paste the private link your family sent. Event RSVP links don’t require an account; joining a family space still requires its invitation and access checks.</p>
    <form className="mt-6 grid gap-4" onSubmit={openInvitation}>
      <label className="grid gap-2">Invitation link<Input autoCapitalize="none" autoComplete="off" autoCorrect="off" aria-describedby={error ? "invitation-error" : undefined} aria-invalid={Boolean(error)} onChange={e => { setLink(e.target.value); setError(""); }} required type="text" value={link} /></label>
      {error && <p id="invitation-error" role="alert" className="text-sm text-destructive">{error}</p>}
      <Button type="submit">Open invitation</Button>
    </form>
    <Link className="mt-6 inline-block font-semibold text-primary" to="/login?intent=join">Have a family invite code instead?</Link>
  </main>;
};
