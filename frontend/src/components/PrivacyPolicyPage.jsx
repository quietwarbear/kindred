import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

export const PrivacyPolicyPage = () => (
  <div className="min-h-screen bg-background px-4 py-12 sm:px-6 lg:px-8">
    <div className="mx-auto max-w-3xl" data-testid="privacy-policy-page">
      <Link className="inline-flex items-center gap-2 text-sm font-semibold text-primary mb-8 hover:underline" data-testid="privacy-back-link" to="/">
        <ArrowLeft className="h-4 w-4" /> Back to Kindred
      </Link>

      <h1 className="font-display text-4xl text-foreground" data-testid="privacy-title">Privacy Policy</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated: March 15, 2026</p>

      <div className="mt-8 space-y-8 text-sm leading-7 text-muted-foreground">
        <section>
          <h2 className="text-lg font-semibold text-foreground">1. Introduction</h2>
          <p className="mt-2">
            Kindred ("we," "us," or "our") is operated by Ubuntu Market LLC. This Privacy Policy describes how we collect,
            use, and protect your personal information when you use the Kindred application (the "Service"), available at
            kindred.ubuntumarket.com and through the Kindred mobile application (bundle ID: com.ubuntumarket.kindred).
          </p>
          <p className="mt-2">
            By using Kindred, you agree to the collection and use of information in accordance with this policy.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">2. Information We Collect</h2>
          <h3 className="mt-3 font-semibold text-foreground">2.1 Information You Provide</h3>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li><strong>Account information:</strong> Full name, email address, password (stored as a one-way hash).</li>
            <li><strong>Profile information:</strong> Nickname, phone number, profile image.</li>
            <li><strong>Community content:</strong> Events, memories, announcements, chat messages, polls, threads, and voice recordings you create or upload.</li>
            <li><strong>Payment information:</strong> Processed securely through Stripe and RevenueCat. We do not store credit card numbers.</li>
          </ul>

          <h3 className="mt-3 font-semibold text-foreground">2.2 Information Collected Automatically</h3>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li><strong>Device information:</strong> Device type, operating system, and push notification tokens (mobile only).</li>
            <li><strong>Usage data:</strong> Pages visited, features used, and interaction timestamps for improving the Service.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">3. How We Use Your Information</h2>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li>To provide, maintain, and improve the Service.</li>
            <li>To authenticate your identity and manage your account.</li>
            <li>To process payments and manage subscriptions.</li>
            <li>To send notifications about community activity (events, announcements, etc.).</li>
            <li>To provide AI-powered features such as memory auto-tagging (via Google Gemini). Content is sent to Google's API solely for tag generation and is not stored by Google.</li>
            <li>To respond to your support requests.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">4. Data Sharing</h2>
          <p className="mt-2">
            We do not sell, rent, or trade your personal information. We share data only with:
          </p>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li><strong>Stripe:</strong> For payment processing.</li>
            <li><strong>RevenueCat:</strong> For mobile subscription management.</li>
            <li><strong>Google (Gemini API):</strong> For AI-powered memory tagging (text and images only, no personal identifiers).</li>
            <li><strong>Google OAuth:</strong> If you choose to sign in with Google.</li>
          </ul>
          <p className="mt-2">
            We may also disclose information if required by law or to protect the rights and safety of our users.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">5. Data Storage and Security</h2>
          <p className="mt-2">
            Your data is stored on secure servers using MongoDB with encryption at rest. Passwords are hashed using bcrypt.
            All data transmission uses HTTPS/TLS encryption. We implement industry-standard security measures to protect your data.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">6. Your Rights</h2>
          <p className="mt-2">You have the right to:</p>
          <ul className="mt-2 list-disc pl-6 space-y-1">
            <li><strong>Access</strong> your personal data through the Settings page.</li>
            <li><strong>Correct</strong> inaccurate data by editing your profile.</li>
            <li><strong>Delete</strong> your account and all associated data through Settings &gt; Delete Account. This action is irreversible and removes all your data from our servers within 30 days.</li>
            <li><strong>Export</strong> your community timeline data via the Timeline CSV export feature.</li>
            <li><strong>Withdraw consent</strong> for push notifications through your device settings.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">7. Data Retention</h2>
          <p className="mt-2">
            We retain your data for as long as your account is active. When you delete your account, all personal data
            is permanently removed within 30 days. Community content you created (events, memories) may be retained
            in anonymized form for the community's archive unless the community owner also deletes them.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">8. Children's Privacy</h2>
          <p className="mt-2">
            Kindred is not intended for children under 13. We do not knowingly collect personal information from children
            under 13. If you believe a child has provided us with personal data, please contact us immediately.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">9. Changes to This Policy</h2>
          <p className="mt-2">
            We may update this Privacy Policy from time to time. We will notify you of significant changes through the
            app or via email. Continued use of the Service after changes constitutes acceptance of the updated policy.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">10. Contact Us</h2>
          <p className="mt-2">
            If you have questions about this Privacy Policy or wish to exercise your data rights, contact us at:
          </p>
          <p className="mt-2 font-medium text-foreground">
            Ubuntu Market LLC<br />
            Email: privacy@ubuntumarket.com
          </p>
        </section>
      </div>
    </div>
  </div>
);
