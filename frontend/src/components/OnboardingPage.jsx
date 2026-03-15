import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, Lightbulb, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, convertFileToDataUrl, formatDateInputValue } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const stepLabels = ["Profile", "Circle", "Subyard", "Gathering", "Invites"];

export const OnboardingPage = ({ onComplete, session, token }) => {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [templates, setTemplates] = useState([]);
  const [profileUpload, setProfileUpload] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState({
    full_name: session?.user?.full_name || "",
    nickname: session?.user?.nickname || "",
    phone_number: session?.user?.phone_number || "",
    profile_image_url: session?.user?.profile_image_url || session?.user?.google_picture || "",
    community_name: session?.community?.name || "",
    community_type: session?.community?.community_type || "community",
    location: session?.community?.location || "",
    motto: session?.community?.motto || "",
    first_subyard_name: "",
    first_subyard_description: "",
    first_gathering_title: "",
    first_gathering_template: "reunion",
    first_gathering_start_at: "",
    first_gathering_location: "",
    invite_emails: "",
  });

  const canConfigureCircle = useMemo(() => ["host", "organizer"].includes(session?.user?.role), [session?.user?.role]);

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const payload = await apiRequest("/gatherings/templates", { token });
        setTemplates(payload.templates || []);
      } catch {
        setTemplates([]);
      }
    };

    loadTemplates();
  }, [token]);

  const recommendations = [
    "Start with a clear circle name and motto so invitees know what they are joining.",
    "Create one focused subyard first — planning team, elders circle, cousins group, or ministry leads.",
    "Launch a starter gathering now so your Google sign-up momentum becomes real activity.",
    "Invite a few core people immediately so the space feels alive from day one.",
  ];

  const handleNext = () => setStep((current) => Math.min(current + 1, stepLabels.length - 1));
  const handleBack = () => setStep((current) => Math.max(current - 1, 0));

  const handleFinish = async () => {
    setIsSaving(true);
    try {
      const profile_image_url = profileUpload ? await convertFileToDataUrl(profileUpload) : form.profile_image_url;
      const payload = await apiRequest("/auth/onboarding/complete", {
        method: "POST",
        token,
        data: {
          ...form,
          profile_image_url,
          first_gathering_start_at: form.first_gathering_start_at ? new Date(form.first_gathering_start_at).toISOString() : null,
          invite_emails: form.invite_emails.split(",").map((item) => item.trim()).filter(Boolean),
        },
      });
      onComplete(payload);
      toast.success("Your Kindred setup is ready.");
      navigate("/home", { replace: true });
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to complete onboarding.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="app-canvas min-h-screen py-8">
      <div className="page-section grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <aside className="archival-card h-fit space-y-6 xl:sticky xl:top-8">
          <div>
            <p className="eyebrow-text">Kindred onboarding</p>
            <h1 className="mt-3 font-display text-4xl text-foreground sm:text-5xl" data-testid="onboarding-page-title">
              Where your circles gather and grow.
            </h1>
            <p className="mt-4 text-sm leading-7 text-muted-foreground sm:text-base">
              This guided setup turns your Google sign-in into a personalized circle, a starter structure, and an active first step.
            </p>
          </div>

          <div className="space-y-3" data-testid="onboarding-step-list">
            {stepLabels.map((label, index) => (
              <div className={`soft-panel ${index === step ? "border-primary bg-primary/5" : ""}`} data-testid={`onboarding-step-${index + 1}`} key={label}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Step {index + 1}</p>
                    <p className="mt-1 text-base text-muted-foreground">{label}</p>
                  </div>
                  {index < step ? <CheckCircle2 className="h-5 w-5 text-primary" /> : <span className="text-sm text-muted-foreground">{index + 1}</span>}
                </div>
              </div>
            ))}
          </div>

          <div className="soft-panel" data-testid="onboarding-recommendations-panel">
            <div className="flex items-center gap-2 text-primary">
              <Lightbulb className="h-4 w-4" />
              <p className="text-sm font-semibold">Recommended next moves</p>
            </div>
            <ul className="mt-3 space-y-3 text-sm leading-7 text-muted-foreground">
              {recommendations.map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
          </div>
        </aside>

        <section className="archival-card space-y-6">
          {step === 0 ? (
            <div data-testid="onboarding-profile-step">
              <p className="eyebrow-text">Profile setup</p>
              <h2 className="mt-2 font-display text-3xl text-foreground">Make your identity feel like yours.</h2>
              <div className="mt-6 grid gap-4">
                <div className="flex items-center gap-4">
                  {form.profile_image_url ? (
                    <img alt="Profile preview" className="h-20 w-20 rounded-full object-cover object-center" data-testid="onboarding-profile-image-preview" src={form.profile_image_url} />
                  ) : (
                    <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 text-lg font-semibold text-primary">
                      {(form.full_name || "K").slice(0, 1)}
                    </div>
                  )}
                  <label className="flex-1">
                    <span className="field-label">Photo or avatar</span>
                    <Input className="field-input pt-3" data-testid="onboarding-profile-image-input" onChange={(e) => setProfileUpload(e.target.files?.[0] || null)} type="file" accept="image/*" />
                  </label>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label>
                    <span className="field-label">Full name</span>
                    <Input className="field-input" data-testid="onboarding-full-name-input" onChange={(e) => setForm((current) => ({ ...current, full_name: e.target.value }))} value={form.full_name} />
                  </label>
                  <label>
                    <span className="field-label">Nickname</span>
                    <Input className="field-input" data-testid="onboarding-nickname-input" onChange={(e) => setForm((current) => ({ ...current, nickname: e.target.value }))} value={form.nickname} />
                  </label>
                </div>
                <label>
                  <span className="field-label">Phone number</span>
                  <Input className="field-input" data-testid="onboarding-phone-input" onChange={(e) => setForm((current) => ({ ...current, phone_number: e.target.value }))} value={form.phone_number} />
                </label>
              </div>
            </div>
          ) : null}

          {step === 1 ? (
            <div data-testid="onboarding-circle-step">
              <p className="eyebrow-text">Circle personalization</p>
              <h2 className="mt-2 font-display text-3xl text-foreground">Name and shape the space people are entering.</h2>
              {canConfigureCircle ? (
                <div className="mt-6 grid gap-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label>
                      <span className="field-label">Circle name</span>
                      <Input className="field-input" data-testid="onboarding-community-name-input" onChange={(e) => setForm((current) => ({ ...current, community_name: e.target.value }))} value={form.community_name} />
                    </label>
                    <label>
                      <span className="field-label">Community type</span>
                      <Input className="field-input" data-testid="onboarding-community-type-input" onChange={(e) => setForm((current) => ({ ...current, community_type: e.target.value }))} value={form.community_type} />
                    </label>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label>
                      <span className="field-label">Location</span>
                      <Input className="field-input" data-testid="onboarding-location-input" onChange={(e) => setForm((current) => ({ ...current, location: e.target.value }))} value={form.location} />
                    </label>
                    <label>
                      <span className="field-label">Tagline / motto</span>
                      <Input className="field-input" data-testid="onboarding-motto-input" onChange={(e) => setForm((current) => ({ ...current, motto: e.target.value }))} value={form.motto} />
                    </label>
                  </div>
                </div>
              ) : (
                <div className="soft-panel mt-6" data-testid="onboarding-circle-locked-panel">
                  <p className="text-sm leading-7 text-muted-foreground">Your host manages the circle identity. You’ll still complete onboarding so your profile is ready and your space feels personal from the start.</p>
                </div>
              )}
            </div>
          ) : null}

          {step === 2 ? (
            <div data-testid="onboarding-subyard-step">
              <p className="eyebrow-text">First subyard</p>
              <h2 className="mt-2 font-display text-3xl text-foreground">Create a focused team or circle to get momentum.</h2>
              {canConfigureCircle ? (
                <div className="mt-6 grid gap-4">
                  <label>
                    <span className="field-label">Subyard name</span>
                    <Input className="field-input" data-testid="onboarding-subyard-name-input" onChange={(e) => setForm((current) => ({ ...current, first_subyard_name: e.target.value }))} placeholder="Planning Team, Elders Circle, Cousins Group..." value={form.first_subyard_name} />
                  </label>
                  <label>
                    <span className="field-label">What is this subyard for?</span>
                    <Textarea className="field-textarea" data-testid="onboarding-subyard-description-input" onChange={(e) => setForm((current) => ({ ...current, first_subyard_description: e.target.value }))} value={form.first_subyard_description} />
                  </label>
                </div>
              ) : (
                <div className="soft-panel mt-6" data-testid="onboarding-subyard-locked-panel">
                  <p className="text-sm leading-7 text-muted-foreground">Subyards are managed by hosts and organizers. You can still finish onboarding and join the right spaces once they are created.</p>
                </div>
              )}
            </div>
          ) : null}

          {step === 3 ? (
            <div data-testid="onboarding-gathering-step">
              <p className="eyebrow-text">First gathering</p>
              <h2 className="mt-2 font-display text-3xl text-foreground">Launch a starter gathering while the energy is fresh.</h2>
              {canConfigureCircle ? (
                <div className="mt-6 grid gap-4">
                  <div className="grid gap-4 lg:grid-cols-3">
                    {(templates.length ? templates : [{ id: "reunion", label: "Reunion", description: "Starter gathering template" }]).map((template) => (
                      <button
                        className={`soft-panel text-left ${form.first_gathering_template === template.id ? "border-primary bg-primary/5" : ""}`}
                        data-testid={`onboarding-template-${template.id}`}
                        key={template.id}
                        onClick={() => setForm((current) => ({ ...current, first_gathering_template: template.id }))}
                        type="button"
                      >
                        <p className="text-base font-semibold text-foreground">{template.label}</p>
                        <p className="mt-2 text-sm leading-7 text-muted-foreground">{template.description}</p>
                      </button>
                    ))}
                  </div>
                  <label>
                    <span className="field-label">Gathering title</span>
                    <Input className="field-input" data-testid="onboarding-gathering-title-input" onChange={(e) => setForm((current) => ({ ...current, first_gathering_title: e.target.value }))} value={form.first_gathering_title} />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label>
                      <span className="field-label">Date + time</span>
                      <Input className="field-input" data-testid="onboarding-gathering-start-input" onChange={(e) => setForm((current) => ({ ...current, first_gathering_start_at: e.target.value }))} type="datetime-local" value={formatDateInputValue(form.first_gathering_start_at)} />
                    </label>
                    <label>
                      <span className="field-label">Location</span>
                      <Input className="field-input" data-testid="onboarding-gathering-location-input" onChange={(e) => setForm((current) => ({ ...current, first_gathering_location: e.target.value }))} value={form.first_gathering_location} />
                    </label>
                  </div>
                </div>
              ) : (
                <div className="soft-panel mt-6" data-testid="onboarding-gathering-locked-panel">
                  <p className="text-sm leading-7 text-muted-foreground">Your host will create the first gathering, but finishing this setup still prepares your profile and makes it easier to join once invites go out.</p>
                </div>
              )}
            </div>
          ) : null}

          {step === 4 ? (
            <div data-testid="onboarding-invites-step">
              <p className="eyebrow-text">Invite your first members</p>
              <h2 className="mt-2 font-display text-3xl text-foreground">Bring in the people who help a circle feel real.</h2>
              {canConfigureCircle ? (
                <div className="mt-6 grid gap-4">
                  <label>
                    <span className="field-label">Invite emails</span>
                    <Textarea className="field-textarea" data-testid="onboarding-invite-emails-input" onChange={(e) => setForm((current) => ({ ...current, invite_emails: e.target.value }))} placeholder="auntie@example.com, cousin@example.com, planninglead@example.com" value={form.invite_emails} />
                  </label>
                </div>
              ) : (
                <div className="soft-panel mt-6" data-testid="onboarding-invites-locked-panel">
                  <p className="text-sm leading-7 text-muted-foreground">Your host manages invitations. Once they bring you in, your profile and preferences will already be ready.</p>
                </div>
              )}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-4">
            <Button className="rounded-full" data-testid="onboarding-back-button" disabled={step === 0 || isSaving} onClick={handleBack} type="button" variant="outline">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
            <div className="flex flex-wrap gap-3">
              {step < stepLabels.length - 1 ? (
                <Button className="rounded-full" data-testid="onboarding-next-button" disabled={isSaving} onClick={handleNext} type="button">
                  Next step
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              ) : (
                <Button className="rounded-full" data-testid="onboarding-finish-button" disabled={isSaving} onClick={handleFinish} type="button">
                  <Sparkles className="mr-2 h-4 w-4" />
                  {isSaving ? "Finishing setup..." : "Finish and enter Kindred"}
                </Button>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};