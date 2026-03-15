import { ArrowLeft, Mail, MessageCircle, Shield } from "lucide-react";
import { Link } from "react-router-dom";

export const SupportPage = () => (
  <div className="min-h-screen bg-background px-4 py-12 sm:px-6 lg:px-8">
    <div className="mx-auto max-w-3xl" data-testid="support-page">
      <Link className="inline-flex items-center gap-2 text-sm font-semibold text-primary mb-8 hover:underline" data-testid="support-back-link" to="/">
        <ArrowLeft className="h-4 w-4" /> Back to Kindred
      </Link>

      <h1 className="font-display text-4xl text-foreground" data-testid="support-title">Support &amp; Contact</h1>
      <p className="mt-2 text-sm text-muted-foreground">We are here to help your community thrive.</p>

      <div className="mt-10 grid gap-6 sm:grid-cols-2">
        <div className="rounded-[24px] border border-border/60 bg-background/80 p-6" data-testid="support-email-card">
          <Mail className="h-6 w-6 text-primary" />
          <h2 className="mt-4 text-lg font-semibold text-foreground">Email Support</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            For general questions, feature requests, or account help, email us directly.
          </p>
          <a className="mt-4 inline-block text-sm font-semibold text-primary hover:underline" data-testid="support-email-link" href="mailto:support@ubuntumarket.com">
            support@ubuntumarket.com
          </a>
        </div>

        <div className="rounded-[24px] border border-border/60 bg-background/80 p-6" data-testid="support-feedback-card">
          <MessageCircle className="h-6 w-6 text-primary" />
          <h2 className="mt-4 text-lg font-semibold text-foreground">Feedback &amp; Ideas</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            Kindred is shaped by the communities that use it. Share ideas for new features or improvements.
          </p>
          <a className="mt-4 inline-block text-sm font-semibold text-primary hover:underline" data-testid="support-feedback-link" href="mailto:feedback@ubuntumarket.com">
            feedback@ubuntumarket.com
          </a>
        </div>
      </div>

      <div className="mt-8 rounded-[24px] border border-border/60 bg-background/80 p-6" data-testid="support-privacy-card">
        <div className="flex items-center gap-3">
          <Shield className="h-6 w-6 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">Privacy &amp; Data Requests</h2>
        </div>
        <p className="mt-3 text-sm leading-7 text-muted-foreground">
          To exercise your data rights — including access, correction, export, or deletion of your personal data — you can:
        </p>
        <ul className="mt-3 list-disc pl-6 space-y-2 text-sm leading-7 text-muted-foreground">
          <li>Use the <strong>Settings</strong> page in the app to manage your profile or delete your account.</li>
          <li>Export your community timeline via the <strong>Timeline &gt; CSV Export</strong> feature.</li>
          <li>Email <a className="font-semibold text-primary hover:underline" href="mailto:privacy@ubuntumarket.com">privacy@ubuntumarket.com</a> for any data request we will respond within 30 days.</li>
        </ul>
      </div>

      <div className="mt-8 space-y-6 text-sm leading-7 text-muted-foreground">
        <section>
          <h2 className="text-lg font-semibold text-foreground">Frequently Asked Questions</h2>

          <div className="mt-4 space-y-5">
            <div data-testid="support-faq-1">
              <p className="font-semibold text-foreground">How do I invite people to my community?</p>
              <p className="mt-1">Go to Courtyards &gt; Members and use the invite feature. Each community has a unique invite code you can share. You can also invite directly from the Kinship Map.</p>
            </div>

            <div data-testid="support-faq-2">
              <p className="font-semibold text-foreground">Is my data private?</p>
              <p className="mt-1">Yes. Kindred is invitation-only with no public profiles, no ads, and no data mining. Your community data is encrypted and never shared with advertisers. See our <Link className="font-semibold text-primary hover:underline" to="/privacy">Privacy Policy</Link> for full details.</p>
            </div>

            <div data-testid="support-faq-3">
              <p className="font-semibold text-foreground">How do I cancel my subscription?</p>
              <p className="mt-1">For web subscriptions, go to Settings &gt; Subscription. For mobile subscriptions, manage them through your device's App Store or Google Play settings. Refunds follow the policies of the respective payment platform.</p>
            </div>

            <div data-testid="support-faq-4">
              <p className="font-semibold text-foreground">Can I delete my account?</p>
              <p className="mt-1">Yes. Go to Settings &gt; Delete Account. All personal data is permanently removed within 30 days. If you are the community owner, transfer ownership first or your community will be deleted.</p>
            </div>

            <div data-testid="support-faq-5">
              <p className="font-semibold text-foreground">How do I report a problem?</p>
              <p className="mt-1">Email <a className="font-semibold text-primary hover:underline" href="mailto:support@ubuntumarket.com">support@ubuntumarket.com</a> with a description of the issue. Include your device type and what you were doing when the problem occurred.</p>
            </div>
          </div>
        </section>
      </div>

      <div className="mt-10 border-t border-border/40 pt-6">
        <p className="text-sm text-muted-foreground">
          Ubuntu Market LLC · Atlanta, GA
        </p>
        <div className="mt-2 flex gap-6">
          <Link className="text-sm text-muted-foreground hover:text-foreground transition-colors" to="/privacy">Privacy Policy</Link>
          <Link className="text-sm text-muted-foreground hover:text-foreground transition-colors" to="/terms">Terms of Service</Link>
        </div>
      </div>
    </div>
  </div>
);
