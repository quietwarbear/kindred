"""The draft-email endpoint is unauthenticated and sends mail, so its bounds
are the test surface. If these loosen, it becomes a spam relay."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import draft_rescue as dr


@pytest.mark.parametrize("value", [
    "doc@ubuntu-village.org",
    "a.b+tag@sub.example.co",
])
def test_plausible_addresses_pass(value):
    assert dr.valid_email(value) is True


@pytest.mark.parametrize("value", [
    "", "no-at-sign", "two@@at.com", "trailing@dot.", "@nolocal.com",
    "spaced address@example.com", "x" * 250 + "@example.com",
])
def test_implausible_addresses_fail(value):
    assert dr.valid_email(value) is False


def test_draft_fields_are_escaped_before_they_reach_an_email():
    hostile = '<img src=x onerror="alert(1)">'
    cleaned = dr.clean_field(hostile)
    assert "<img" not in cleaned
    assert "&lt;img" in cleaned


def test_draft_fields_are_length_capped():
    assert len(dr.clean_field("x" * 500, 120)) == 120


def test_blank_field_is_empty_not_none():
    assert dr.clean_field(None) == ""
    assert dr.clean_field("   ") == ""


def test_ip_hash_is_stable_and_not_the_ip():
    a = dr.hash_ip("203.0.113.9")
    assert a == dr.hash_ip("203.0.113.9")
    assert a != dr.hash_ip("203.0.113.10")
    assert "203.0.113.9" not in a
    assert len(a) == 64


def test_limits_are_bounded_and_ordered():
    """Per-address must be tighter than per-IP-day, or one mailbox can be
    flooded from a single address's worth of requests."""
    assert 0 < dr.MAX_PER_IP_HOUR <= dr.MAX_PER_IP_DAY
    assert 0 < dr.MAX_PER_EMAIL_DAY < dr.MAX_PER_IP_DAY


class _FakeCollection:
    def __init__(self, count):
        self._count = count
        self.queries = []

    async def count_documents(self, query):
        self.queries.append(query)
        return self._count


@pytest.mark.asyncio
async def test_a_quiet_caller_is_allowed():
    assert await dr.rate_limit_reason(_FakeCollection(0), "hash", "doc@example.com") is None


@pytest.mark.asyncio
async def test_a_noisy_caller_is_refused():
    reason = await dr.rate_limit_reason(_FakeCollection(99), "hash", "doc@example.com")
    assert reason and "Try again" in reason


@pytest.mark.asyncio
async def test_every_limit_is_time_bounded():
    """A limit query without a created_at window would count all history and
    lock the address out forever."""
    fake = _FakeCollection(0)
    await dr.rate_limit_reason(fake, "hash", "doc@example.com")
    assert len(fake.queries) == 3
    for query in fake.queries:
        assert "$gte" in query["created_at"]


class _FakeRequest:
    def __init__(self, headers, host="10.0.0.1"):
        self.headers = headers
        self.client = type("C", (), {"host": host})()


def test_forwarded_for_wins_and_takes_the_first_hop():
    req = _FakeRequest({"x-forwarded-for": "203.0.113.9, 70.41.3.18"})
    assert dr.client_ip(req) == "203.0.113.9"


def test_direct_connection_falls_back_to_peer():
    assert dr.client_ip(_FakeRequest({})) == "10.0.0.1"
