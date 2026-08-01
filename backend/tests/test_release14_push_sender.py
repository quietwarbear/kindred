"""Release 14 — disabled-by-default push notifications (synthetic, no network)."""

import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release14_push_unit")

import pytest

import push_sender
from push_sender import (
    PUSH_TEMPLATES,
    PushOutcome,
    PushSendReport,
    build_push_client,
    maybe_notify,
    push_enabled,
    send_push_to_user,
)


class _FakeUsers:
    def __init__(self, tokens):
        self.doc = {"id": "u1", "push_tokens": list(tokens)}
        self.pulls = []

    async def find_one(self, _query, _projection=None):
        return dict(self.doc)

    async def update_one(self, query, update):
        self.pulls.append((query, update))


class _FakeClient:
    def __init__(self, outcomes):
        self.outcomes = dict(outcomes)
        self.delivered = []

    async def deliver(self, device_token, notification):
        self.delivered.append((device_token, notification))
        return self.outcomes.get(device_token, PushOutcome.DELIVERED)


def test_push_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PUSH_NOTIFICATIONS_ENABLED", raising=False)
    assert push_enabled() is False
    monkeypatch.setenv("PUSH_NOTIFICATIONS_ENABLED", "false")
    assert push_enabled() is False
    monkeypatch.setenv("PUSH_NOTIFICATIONS_ENABLED", "true")
    assert push_enabled() is True


def test_client_none_when_unconfigured(monkeypatch):
    for var in (
        "FCM_SERVICE_ACCOUNT_JSON",
        "FCM_PROJECT_ID",
        "FCM_CLIENT_EMAIL",
        "FCM_PRIVATE_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    assert build_push_client() is None


def test_templates_are_content_free():
    # Every template is a fixed title/body pair — no interpolation placeholders.
    for code, tmpl in PUSH_TEMPLATES.items():
        assert set(tmpl) == {"title", "body"}
        for value in tmpl.values():
            assert "{" not in value and "}" not in value
            assert "%" not in value


@pytest.mark.asyncio
async def test_unknown_template_fails_closed():
    report = await send_push_to_user(
        users_collection=_FakeUsers(["t1"]),
        user_id="u1",
        template_code="not_a_template",
        client=_FakeClient({}),
    )
    assert report.status == "unavailable"
    assert report.error_code == "unknown_template"


@pytest.mark.asyncio
async def test_no_tokens_is_a_noop():
    users = _FakeUsers([])
    report = await send_push_to_user(
        users_collection=users,
        user_id="u1",
        template_code="rsvp_received",
        client=_FakeClient({}),
    )
    assert report.status == "processed"
    assert report.delivered == 0
    assert users.pulls == []


@pytest.mark.asyncio
async def test_invalid_tokens_are_pruned_and_counted():
    users = _FakeUsers(["good", "dead", "flaky"])
    client = _FakeClient(
        {
            "good": PushOutcome.DELIVERED,
            "dead": PushOutcome.INVALID,
            "flaky": PushOutcome.TRANSIENT,
        }
    )
    report = await send_push_to_user(
        users_collection=users,
        user_id="u1",
        template_code="rsvp_received",
        client=client,
    )
    assert report.delivered == 1
    assert report.invalid == 1
    assert report.transient == 1
    # Only the permanently-dead token is pruned.
    assert users.pulls == [
        ({"id": "u1"}, {"$pull": {"push_tokens": {"$in": ["dead"]}}})
    ]
    # The delivered notification is the allowlisted content-free template.
    assert client.delivered[0][1] == PUSH_TEMPLATES["rsvp_received"]


def test_report_is_content_free():
    doc = PushSendReport(status="processed", delivered=2).safe_document()
    assert set(doc) == {"status", "error_code", "counts"}
    assert set(doc["counts"]) == {"delivered", "invalid", "transient", "failed"}


@pytest.mark.asyncio
async def test_maybe_notify_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(push_sender, "push_enabled", lambda: False)
    called = {"factory": False}

    def factory():
        called["factory"] = True
        return None

    users = _FakeUsers(["t1"])
    await maybe_notify(
        users_collection=users,
        user_id="u1",
        template_code="rsvp_received",
        client_factory=factory,
    )
    assert called["factory"] is False  # never even built a client
    assert users.pulls == []


@pytest.mark.asyncio
async def test_maybe_notify_swallows_client_errors(monkeypatch):
    monkeypatch.setattr(push_sender, "push_enabled", lambda: True)

    def broken_factory():
        raise RuntimeError("provider blew up")

    # Must not raise into the caller.
    await maybe_notify(
        users_collection=_FakeUsers(["t1"]),
        user_id="u1",
        template_code="rsvp_received",
        client_factory=broken_factory,
    )


@pytest.mark.asyncio
async def test_maybe_notify_noop_without_user_id(monkeypatch):
    monkeypatch.setattr(push_sender, "push_enabled", lambda: True)
    called = {"factory": False}

    def factory():
        called["factory"] = True
        return None

    await maybe_notify(
        users_collection=_FakeUsers(["t1"]),
        user_id="",
        template_code="rsvp_received",
        client_factory=factory,
    )
    assert called["factory"] is False
