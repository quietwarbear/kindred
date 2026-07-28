import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { PUBLIC_IDENTITY } from "@/config/publicIdentity";

export const PrivacyPolicyPage = () => (
  <div className="min-h-screen bg-background px-4 py-12 sm:px-6 lg:px-8">
    <div className="mx-auto max-w-3xl" data-testid="privacy-policy-page">
      <Link className="mb-8 inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline" data-testid="privacy-back-link" to="/">
        <ArrowLeft className="h-4 w-4" /> Back to Kindred
      </Link>

      <h1 className="font-display text-4xl text-foreground" data-testid="privacy-title">Privacy Policy</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated: July 23, 2026</p>

      <div className="mt-8 space-y-8 text-sm leading-7 text-muted-foreground">
        <section>
          <h2 className="text-lg font-semibold text-foreground">1. About this policy</h2>
          <p className="mt-2">
            Kindred is operated by {PUBLIC_IDENTITY.companyName}. This policy explains how we collect, use, disclose,
            retain, and delete information through {PUBLIC_IDENTITY.canonicalHost}, the Kindred web application, and
            the Kindred mobile application (bundle/package ID com.ubuntumarket.kindred).
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">2. Information we process</h2>
          <ul className="mt-2 list-disc space-y-1 pl-6">
            <li><strong>Account and profile data:</strong> name, nickname, email, phone number, password hash, profile image, authentication provider, role, community membership, and account timestamps.</li>
            <li><strong>Community content:</strong> community details, invitations, events and RSVPs, announcements, chats and attachments, polls and votes, kinship links, care circles, budgets, travel plans, contributions, memories, images, voice notes, transcripts, translations, tags, and legacy threads.</li>
            <li><strong>Payment and subscription data:</strong> plan, billing cycle, amount, payment status, store, transaction and customer identifiers, renewal or expiration dates, and limited checkout metadata. Stripe, Apple, or Google processes payment credentials; Kindred does not receive full card numbers.</li>
            <li><strong>Device and notification data:</strong> push notification tokens, device/platform information made available by the mobile runtime, and notification preferences.</li>
            <li><strong>Usage and diagnostics:</strong> page views, clicks and other interactions, IP-derived and browser/device information, timestamps, product user ID, and technical events collected through Google Analytics/Google Tag Manager and PostHog.</li>
            <li><strong>Support and communications:</strong> support messages, email addresses, email delivery events, and notification or digest preferences.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">3. Why we use information</h2>
          <ul className="mt-2 list-disc space-y-1 pl-6">
            <li>Provide accounts, private communities, invitations, collaboration, archives, and support.</li>
            <li>Authenticate users through passwords, Google Sign-In, or Apple Sign In and protect sessions.</li>
            <li>Process purchases, validate entitlements, prevent billing drift, and manage subscriptions.</li>
            <li>Deliver transactional email, community digests, reminders, and mobile push notifications.</li>
            <li>Measure product use, diagnose reliability issues, and improve Kindred.</li>
            <li>Generate optional AI assistance, including memory tags and summaries, gathering suggestions, stewardship suggestions, voice transcription, and Spanish/Yoruba translations.</li>
            <li>Enable user-requested sign-on handoffs to configured Ubuntu Market sibling products.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">4. Service providers and disclosures</h2>
          <p className="mt-2">We do not sell personal information. Code in the Service can disclose limited data to:</p>
          <ul className="mt-2 list-disc space-y-1 pl-6">
            <li><strong>MongoDB and the configured hosting provider:</strong> application records, content, media stored as data URLs, and operational metadata.</li>
            <li><strong>Stripe:</strong> web checkout, billing, customer, payment, and subscription data.</li>
            <li><strong>RevenueCat, Apple, and Google Play:</strong> mobile purchase identifiers, entitlements, store, status, and subscription dates.</li>
            <li><strong>Google:</strong> Google Sign-In identity data; Google Analytics and Tag Manager usage data; and, when the configured AI model uses Gemini, content supplied to that model.</li>
            <li><strong>PostHog (EU ingestion endpoint):</strong> product analytics, autocaptured interactions, page views, a Kindred user ID after sign-in, and authentication-provider label.</li>
            <li><strong>OpenAI or another LiteLLM-routed model provider:</strong> text, images, or audio submitted to enabled AI features. Whisper is used for voice transcription when configured. The actual provider is controlled by server model configuration.</li>
            <li><strong>Resend:</strong> recipient email address and the content of subscription notices and community digests.</li>
            <li><strong>Apple Push Notification service / Google push infrastructure:</strong> device token and notification delivery data when push notifications are enabled.</li>
            <li><strong>Legacy Table and Ile Ubuntu:</strong> name and email only when an authenticated user initiates a configured cross-product sign-in handoff.</li>
          </ul>
          <p className="mt-2">
            We may also disclose information when required by law, to protect users and the Service, or as part of a
            business transaction subject to appropriate safeguards.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">5. AI features</h2>
          <p className="mt-2">
            AI features are best-effort and are activated by particular user actions or product workflows. Depending
            on the configured model, relevant prompts, community text, uploaded images, or voice recordings may be
            transmitted to Google Gemini, OpenAI, Whisper, or another provider selected through LiteLLM. Do not submit
            sensitive content to an AI feature unless your community authorizes that use. Provider retention and
            training terms depend on the production account and contract configured by Kindred.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">6. Storage, security, and retention</h2>
          <p className="mt-2">
            Kindred stores application data in the configured MongoDB database. Uploaded profile images, community
            attachments, images, and voice notes may be stored in database records as encoded data URLs. Passwords are
            hashed with bcrypt and network traffic is intended to use HTTPS/TLS. Access is restricted by account,
            community, and role checks.
          </p>
          <p className="mt-2">
            Account, community, and subscription records are generally retained while needed to provide the Service
            and meet legal, security, and accounting obligations. One-time SSO codes have an automated short-lived
            database expiration mechanism; most other record categories have no automatic time-based purge in the
            current code. Provider logs, backups, analytics, payment, email, and AI-provider records follow each
            provider's configured retention. Production backup and vendor-retention periods require operator
            confirmation.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">7. Your choices and controls</h2>
          <ul className="mt-2 list-disc space-y-1 pl-6">
            <li>Edit available profile fields and notification or digest preferences in Kindred.</li>
            <li>Disable push notifications in device settings and use available digest unsubscribe controls.</li>
            <li>Manage or cancel subscriptions through Kindred or the applicable Apple/Google account settings.</li>
            <li>Delete individual content where the product provides a delete control.</li>
            <li>Delete your account in Settings. A community owner with other members must first transfer ownership. Sole-owner deletion cascades through the community records handled by the deletion endpoint; non-owner deletion removes the user's account/session records but may leave community content and operational records.</li>
            <li>Use browser or device controls to limit cookies or analytics. Kindred does not currently provide a separate in-product analytics opt-out.</li>
            <li>Request access, correction, deletion, or other applicable privacy rights by contacting us.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">8. Children</h2>
          <p className="mt-2">
            Kindred is not directed to children under 13. Communities should not create accounts for children or upload
            children's personal information unless they have the authority and consent required by applicable law.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">9. Changes and contact</h2>
          <p className="mt-2">
            We may update this policy as the Service or its providers change. We will update the date above and provide
            additional notice when required. For privacy questions or rights requests, contact:
          </p>
          <p className="mt-2 font-medium text-foreground">
            {PUBLIC_IDENTITY.companyName}<br />
            Email: <a className="text-primary hover:underline" href={`mailto:${PUBLIC_IDENTITY.supportEmail}`}>{PUBLIC_IDENTITY.supportEmail}</a>
          </p>
        </section>
      </div>
    </div>
  </div>
);
