import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

export const TermsOfServicePage = () => (
  <div className="min-h-screen bg-background px-4 py-12 sm:px-6 lg:px-8">
    <div className="mx-auto max-w-3xl" data-testid="terms-of-service-page">
      <Link className="inline-flex items-center gap-2 text-sm font-semibold text-primary mb-8 hover:underline" data-testid="terms-back-link" to="/">
        <ArrowLeft className="h-4 w-4" /> Back to Kindred
      </Link>

      <h1 className="font-display text-4xl text-foreground" data-testid="terms-title">Terms of Service</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated: March 15, 2026</p>

      <div className="mt-8 space-y-8 text-sm leading-7 text-muted-foreground">
        <section>
          <h2 className="text-lg font-semibold text-foreground">1. Acceptance of Terms</h2>
          <p className="mt-2">
            By accessing or using the Kindred application ("Service"), operated by Ubuntu Market LLC ("we," "us," or "our"),
            you agree to be bound by these Terms of Service. If you do not agree, you may not use the Service.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">2. Description of Service</h2>
          <p className="mt-2">
            Kindred is a private, invitation-only community platform designed for families, churches, and intentional
            communities. The Service provides tools for event planning, memory archiving, communication, community management,
            and subscription-based features.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">3. Account Registration</h2>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li>You must be at least 13 years old to create an account.</li>
            <li>You are responsible for maintaining the security of your account credentials.</li>
            <li>You agree to provide accurate and complete information during registration.</li>
            <li>You may not create accounts for others without their consent.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">4. Community Rules</h2>
          <p className="mt-2">As a Kindred user, you agree not to:</p>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li>Upload illegal, harmful, threatening, abusive, or defamatory content.</li>
            <li>Impersonate other individuals or entities.</li>
            <li>Interfere with or disrupt the Service or servers.</li>
            <li>Attempt to gain unauthorized access to other accounts or systems.</li>
            <li>Use the Service for commercial spam or unsolicited advertising.</li>
            <li>Harvest or collect personal data of other users without consent.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">5. Content Ownership</h2>
          <p className="mt-2">
            You retain ownership of all content you create or upload to Kindred (photos, voice notes, text, etc.).
            By uploading content, you grant us a limited, non-exclusive license to host, display, and process your
            content solely for the purpose of providing the Service.
          </p>
          <p className="mt-2">
            You are responsible for ensuring you have the right to share any content you upload.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">6. Subscriptions and Payments</h2>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li>Kindred offers free and paid subscription tiers with varying feature access.</li>
            <li>Payments are processed securely through Stripe (web) and RevenueCat/App Store/Google Play (mobile).</li>
            <li>Subscription renewals are automatic unless canceled before the renewal date.</li>
            <li>Refunds are handled according to the policies of the respective payment platform (Stripe, Apple, Google).</li>
            <li>We reserve the right to modify pricing with 30 days' notice to existing subscribers.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">7. Account Deletion</h2>
          <p className="mt-2">
            You may delete your account at any time through Settings &gt; Delete Account. Upon deletion:
          </p>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li>Your personal data will be permanently removed within 30 days.</li>
            <li>Active subscriptions will be canceled.</li>
            <li>Community content you created may be retained in anonymized form.</li>
            <li>This action is irreversible.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">8. Intellectual Property</h2>
          <p className="mt-2">
            The Kindred name, logo, and application design are the intellectual property of Ubuntu Market LLC.
            You may not copy, modify, or distribute any part of the Service without prior written permission.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">9. Limitation of Liability</h2>
          <p className="mt-2">
            The Service is provided "as is" without warranties of any kind. Ubuntu Market LLC shall not be liable
            for any indirect, incidental, special, consequential, or punitive damages arising from your use of the Service.
            Our total liability shall not exceed the amount you paid us in the 12 months preceding the claim.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">10. Termination</h2>
          <p className="mt-2">
            We reserve the right to suspend or terminate your account if you violate these Terms. You may also
            terminate your account at any time by deleting it through the Settings page.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">11. Changes to Terms</h2>
          <p className="mt-2">
            We may update these Terms from time to time. We will notify you of material changes through the app or email.
            Continued use of the Service after changes constitutes acceptance.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">12. Governing Law</h2>
          <p className="mt-2">
            These Terms are governed by the laws of the State of Delaware, United States, without regard to
            conflict of law provisions. Any disputes shall be resolved in the courts of Delaware.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">13. Contact</h2>
          <p className="mt-2">
            For questions about these Terms, contact us at:
          </p>
          <p className="mt-2 font-medium text-foreground">
            Ubuntu Market LLC<br />
            Email: legal@ubuntumarket.com
          </p>
        </section>
      </div>
    </div>
  </div>
);
