"""Subscription email notifications via Resend."""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "Kindred <noreply@heykindred.org>")
APP_URL = os.environ.get("APP_URL", "https://www.heykindred.org")


async def _send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend. Returns True on success."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email to %s: %s", to, subject)
        return False

    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": FROM_EMAIL,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
        if resp.status_code in (200, 201):
            logger.info("Email sent to %s: %s", to, subject)
            return True
        logger.error("Resend error %d: %s", resp.status_code, resp.text)
        return False
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False


def _base_template(title: str, body: str) -> str:
    """Wrap body HTML in a styled email template."""
    return f"""
    <div style="max-width:600px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1a1a1a;">
        <div style="background:linear-gradient(135deg,#2d1810 0%,#4a2c1f 100%);padding:32px 24px;text-align:center;border-radius:12px 12px 0 0;">
            <h1 style="color:#d4a574;margin:0;font-size:28px;font-weight:700;">Kindred</h1>
            <p style="color:#c4956a;margin:8px 0 0;font-size:14px;">Where your circles gather and grow</p>
        </div>
        <div style="background:#ffffff;padding:32px 24px;border:1px solid #e8e0d8;border-top:none;">
            <h2 style="color:#2d1810;margin:0 0 16px;font-size:22px;">{title}</h2>
            {body}
        </div>
        <div style="background:#f9f5f0;padding:20px 24px;text-align:center;border:1px solid #e8e0d8;border-top:none;border-radius:0 0 12px 12px;">
            <p style="color:#8b7355;margin:0;font-size:12px;">
                <a href="{APP_URL}/subscription" style="color:#8b7355;">Manage Subscription</a> &middot;
                <a href="{APP_URL}" style="color:#8b7355;">Open Kindred</a>
            </p>
            <p style="color:#a89880;margin:8px 0 0;font-size:11px;">&copy; Ubuntu Market LLC</p>
        </div>
    </div>
    """


async def send_subscription_welcome(email: str, plan_name: str, billing_cycle: str, amount: float):
    """Welcome email after a successful new subscription."""
    cycle_label = "month" if billing_cycle == "monthly" else "year"
    body = f"""
    <p style="font-size:16px;line-height:1.6;">Welcome to the <strong>{plan_name}</strong> plan! Your community just leveled up.</p>
    <div style="background:#f9f5f0;border-radius:8px;padding:16px 20px;margin:20px 0;">
        <p style="margin:0;font-size:14px;color:#5a4a3a;">
            <strong>Plan:</strong> {plan_name}<br>
            <strong>Billing:</strong> ${amount:.2f}/{cycle_label} (auto-renews)<br>
        </p>
    </div>
    <p style="font-size:14px;line-height:1.6;color:#5a4a3a;">
        Your subscription renews automatically so your community never misses a beat.
        You can manage or cancel anytime from your subscription settings.
    </p>
    <div style="text-align:center;margin:28px 0;">
        <a href="{APP_URL}/subscription" style="background:#d4a574;color:#2d1810;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">View Your Plan</a>
    </div>
    """
    await _send_email(email, f"Welcome to Kindred {plan_name}!", _base_template("You're all set!", body))


async def send_subscription_renewed(email: str, plan_name: str, amount: float, next_renewal: str):
    """Email after a successful recurring payment."""
    body = f"""
    <p style="font-size:16px;line-height:1.6;">Your <strong>{plan_name}</strong> subscription has been renewed successfully.</p>
    <div style="background:#f9f5f0;border-radius:8px;padding:16px 20px;margin:20px 0;">
        <p style="margin:0;font-size:14px;color:#5a4a3a;">
            <strong>Amount charged:</strong> ${amount:.2f}<br>
            <strong>Next renewal:</strong> {next_renewal}<br>
        </p>
    </div>
    <p style="font-size:14px;line-height:1.6;color:#5a4a3a;">No action needed — your community access continues uninterrupted.</p>
    """
    await _send_email(email, f"Kindred {plan_name} renewed", _base_template("Payment received", body))


async def send_subscription_cancelled(email: str, plan_name: str, access_until: str):
    """Email after subscription cancellation."""
    body = f"""
    <p style="font-size:16px;line-height:1.6;">Your <strong>{plan_name}</strong> subscription has been cancelled.</p>
    <div style="background:#fff5f0;border-radius:8px;padding:16px 20px;margin:20px 0;border-left:4px solid #d4a574;">
        <p style="margin:0;font-size:14px;color:#5a4a3a;">
            You'll keep full <strong>{plan_name}</strong> access until <strong>{access_until}</strong>.
            After that, your community will revert to the free Seedling plan.
        </p>
    </div>
    <p style="font-size:14px;line-height:1.6;color:#5a4a3a;">
        Changed your mind? You can resubscribe anytime before your access expires.
    </p>
    <div style="text-align:center;margin:28px 0;">
        <a href="{APP_URL}/subscription" style="background:#d4a574;color:#2d1810;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">Resubscribe</a>
    </div>
    """
    await _send_email(email, f"Kindred {plan_name} cancelled", _base_template("Subscription cancelled", body))


async def send_payment_failed(email: str, plan_name: str):
    """Email when a renewal payment fails."""
    body = f"""
    <p style="font-size:16px;line-height:1.6;">We weren't able to process payment for your <strong>{plan_name}</strong> subscription.</p>
    <div style="background:#fff0f0;border-radius:8px;padding:16px 20px;margin:20px 0;border-left:4px solid #e74c3c;">
        <p style="margin:0;font-size:14px;color:#5a4a3a;">
            Please update your payment method to keep your community features active.
            Stripe will automatically retry the charge, but if it continues to fail your subscription may be cancelled.
        </p>
    </div>
    <div style="text-align:center;margin:28px 0;">
        <a href="{APP_URL}/subscription" style="background:#e74c3c;color:#ffffff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">Update Payment</a>
    </div>
    """
    await _send_email(email, f"Action needed: payment failed for Kindred {plan_name}", _base_template("Payment issue", body))


async def send_subscription_upgraded(email: str, old_plan: str, new_plan: str, amount: float, billing_cycle: str):
    """Email when user upgrades/downgrades their plan."""
    cycle_label = "month" if billing_cycle == "monthly" else "year"
    body = f"""
    <p style="font-size:16px;line-height:1.6;">Your subscription has been updated from <strong>{old_plan}</strong> to <strong>{new_plan}</strong>.</p>
    <div style="background:#f0f9f0;border-radius:8px;padding:16px 20px;margin:20px 0;border-left:4px solid #27ae60;">
        <p style="margin:0;font-size:14px;color:#5a4a3a;">
            <strong>New plan:</strong> {new_plan}<br>
            <strong>Billing:</strong> ${amount:.2f}/{cycle_label}<br>
        </p>
    </div>
    <p style="font-size:14px;line-height:1.6;color:#5a4a3a;">Your new features are available immediately.</p>
    """
    await _send_email(email, f"Upgraded to Kindred {new_plan}", _base_template("Plan updated", body))


def build_digest_body(digest: dict) -> str:
    """Render the weekly community digest body HTML from a digest dict.

    digest = {community_name, member_count, upcoming_events:[{title,when,location}],
              recent_memories:[{title}], recent_threads:[{title,category}],
              funds_raised, new_members}
    """
    def _section(title, rows_html):
        return (
            f'<div style="margin:22px 0;">'
            f'<p style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#a8865c;margin:0 0 8px;">{title}</p>'
            f'{rows_html}</div>'
        )

    events = digest.get("upcoming_events") or []
    if events:
        rows = "".join(
            f'<div style="background:#f9f5f0;border-radius:8px;padding:12px 16px;margin-bottom:8px;">'
            f'<p style="margin:0;font-size:15px;font-weight:600;color:#2d1810;">{e.get("title","")}</p>'
            f'<p style="margin:4px 0 0;font-size:13px;color:#8b7355;">{e.get("when","")}{(" · " + e["location"]) if e.get("location") else ""}</p>'
            f'</div>'
            for e in events[:5]
        )
        events_html = _section("Coming up", rows)
    else:
        events_html = _section(
            "Coming up",
            f'<p style="margin:0;font-size:14px;color:#5a4a3a;">No gatherings on the calendar yet. '
            f'<a href="{APP_URL}/events" style="color:#9A3412;font-weight:600;">Plan one →</a></p>',
        )

    mems = digest.get("recent_memories") or []
    threads = digest.get("recent_threads") or []
    archive_rows = ""
    if mems:
        archive_rows += "".join(
            f'<p style="margin:0 0 6px;font-size:14px;color:#5a4a3a;">📷 {m.get("title","A new memory")}</p>' for m in mems[:4]
        )
    if threads:
        archive_rows += "".join(
            f'<p style="margin:0 0 6px;font-size:14px;color:#5a4a3a;">📖 {t.get("title","A new story")}</p>' for t in threads[:4]
        )
    archive_html = _section("Newly remembered", archive_rows) if archive_rows else ""

    pulse = (
        f'<div style="display:block;background:#f9f5f0;border-radius:8px;padding:16px 20px;margin:8px 0 0;">'
        f'<p style="margin:0;font-size:14px;color:#5a4a3a;">'
        f'<strong>{digest.get("member_count", 0)}</strong> members'
        + (f' · <strong>{digest["new_members"]}</strong> new this week' if digest.get("new_members") else "")
        + (f' · <strong>${digest.get("funds_raised", 0):.0f}</strong> contributed' if digest.get("funds_raised") else "")
        + "</p></div>"
    )

    unsub_url = digest.get("unsubscribe_url")
    unsub_html = (
        f'<p style="text-align:center;font-size:12px;color:#a89880;margin:18px 0 0;">'
        f'Don&#39;t want these weekly notes? '
        f'<a href="{unsub_url}" style="color:#a89880;text-decoration:underline;">Unsubscribe</a>.</p>'
    ) if unsub_url else ""

    return (
        f'<p style="font-size:16px;line-height:1.6;color:#2d1810;">Here is what is happening in '
        f'<strong>{digest.get("community_name","your community")}</strong> this week.</p>'
        f"{pulse}{events_html}{archive_html}"
        f'<div style="text-align:center;margin:28px 0;">'
        f'<a href="{APP_URL}" style="background:#9A3412;color:#ffffff;padding:12px 32px;border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;">Open {digest.get("community_name","Kindred")}</a>'
        f"</div>"
        f"{unsub_html}"
    )


async def send_community_digest(email: str, digest: dict) -> bool:
    """Send one weekly digest email to a single member."""
    community_name = digest.get("community_name", "your community")
    body = build_digest_body(digest)
    return await _send_email(
        email,
        f"This week in {community_name}",
        _base_template(f"This week in {community_name}", body),
    )
