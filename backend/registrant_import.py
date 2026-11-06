"""Registrant import: bring people registered elsewhere into a Kindred event.

An organizer sells tickets on an outside platform and brings the registrants
into Kindred two ways: a CSV upload, or a signed inbound webhook (see
``docs/REGISTRANT_WEBHOOK.md``). Both feed the same pure pipeline here:

- Each registrant becomes ONE invitation, keyed on the normalized email.
  Re-importing the same file changes nothing (idempotent): the row reports
  ``skipped``.
- Each registrant is pre-marked "coming" for exactly the sessions they bought.
  Under K4 that unlocks those sessions' virtual links and no others. Marks the
  import made earlier for a session that is no longer listed are withdrawn. An
  answer the person gave themselves is never overwritten.
- K9 (first half): a registrant whose NAME matches an existing invitee under a
  DIFFERENT email is not created. The row is flagged for the organizer, who can
  create a separate invitation, apply the sessions to the existing invitee, or
  dismiss it.

Everything in this module is pure (no I/O) so that it can run inside the RSVP
compare-and-swap mutation and be tested without a database.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from itinerary import activity_summaries, published_activities

IMPORT_VIA = "registrant-import"
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 2_000
MAX_NAME_LENGTH = 120
MAX_EMAIL_LENGTH = 254

ROW_CREATED = "created"
ROW_UPDATED = "updated"
ROW_SKIPPED = "skipped"
ROW_FLAGGED = "flagged"
ROW_ERROR = "error"

FLAG_PENDING = "pending"
FLAG_CREATE_SEPARATE = "create_separate"
FLAG_APPLY_TO_EXISTING = "apply_to_existing"
FLAG_DISMISSED = "dismissed"
FLAG_RESOLUTIONS = {FLAG_CREATE_SEPARATE, FLAG_APPLY_TO_EXISTING, FLAG_DISMISSED}

ALL_SESSIONS_WORDS = {"all", "all sessions", "all activities"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SESSION_SPLIT_RE = re.compile(r"[;|\n]+")

# Header aliases, compared after lowercasing and dropping non-alphanumerics, so
# "Email Address", "email_address" and "E-mail" all match.
_NAME_HEADERS = {"name", "fullname", "attendeename", "registrantname", "attendee"}
_FIRST_NAME_HEADERS = {"firstname", "first", "givenname"}
_LAST_NAME_HEADERS = {"lastname", "last", "surname", "familyname"}
_EMAIL_HEADERS = {"email", "emailaddress", "attendeeemail", "registrantemail"}
_SESSION_HEADERS = {
    "sessions",
    "sessionspurchased",
    "session",
    "activities",
    "activity",
    "tickets",
    "ticket",
    "tickettype",
    "tickettypes",
}


def normalize_import_email(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_person_name(value: Any) -> str:
    """Comparable form of a person's name: NFKC, casefolded, single-spaced."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def _clean_name(value: Any) -> str:
    return " ".join(str(value or "").split())[:MAX_NAME_LENGTH]


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def valid_email(value: str) -> bool:
    return bool(value) and len(value) <= MAX_EMAIL_LENGTH and bool(_EMAIL_RE.match(value))


@dataclass
class Registrant:
    """One person to bring in, after per-email aggregation."""

    row: int
    email: str
    name: str
    session_refs: list[str] = field(default_factory=list)
    extra_rows: list[int] = field(default_factory=list)


@dataclass
class ParsedImport:
    registrants: list[Registrant]
    row_results: list[dict[str, Any]]  # rows rejected or merged during parsing


class CSVImportError(ValueError):
    """The file as a whole cannot be read (as opposed to one bad row)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _row_result(
    row: int, status: str, *, email: str = "", name: str = "", detail: str = "", **extra
) -> dict[str, Any]:
    result = {"row": row, "status": status, "email": email, "name": name, "detail": detail}
    result.update(extra)
    return result


def split_session_refs(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for item in value:
            parts.extend(split_session_refs(item))
        return parts
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in _SESSION_SPLIT_RE.split(text) if part.strip()]


def parse_registrant_csv(text: str) -> ParsedImport:
    """Read an organizer CSV into registrants plus per-row parse problems.

    Row numbers match what the organizer sees in a spreadsheet: the header is
    row 1, the first registrant is row 2. Several rows with the same email (one
    per ticket, as many platforms export) become one registrant whose sessions
    are combined.
    """
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise CSVImportError("csv_too_large", "That file is larger than 1 MB.")
    text = text.lstrip("﻿")
    if not text.strip():
        raise CSVImportError("csv_empty", "That file is empty.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise CSVImportError("csv_unreadable", "That file could not be read as CSV.") from exc

    keys = [_header_key(cell) for cell in header]

    def column(aliases: set[str]) -> int | None:
        return next((index for index, key in enumerate(keys) if key in aliases), None)

    email_col = column(_EMAIL_HEADERS)
    name_col = column(_NAME_HEADERS)
    first_col = column(_FIRST_NAME_HEADERS)
    last_col = column(_LAST_NAME_HEADERS)
    session_col = column(_SESSION_HEADERS)
    if email_col is None:
        raise CSVImportError(
            "csv_missing_email_column",
            "The first row must name the columns, including an email column.",
        )

    by_email: dict[str, Registrant] = {}
    order: list[str] = []
    row_results: list[dict[str, Any]] = []
    data_rows = 0
    try:
        for row_number, cells in enumerate(reader, start=2):
            if not any(str(cell).strip() for cell in cells):
                continue
            data_rows += 1
            if data_rows > MAX_CSV_ROWS:
                raise CSVImportError(
                    "csv_too_many_rows",
                    f"Import at most {MAX_CSV_ROWS} rows at a time.",
                )

            def cell(index: int | None) -> str:
                if index is None or index >= len(cells):
                    return ""
                return str(cells[index]).strip()

            raw_email = cell(email_col)
            email = normalize_import_email(raw_email)
            if name_col is not None and cell(name_col):
                name = _clean_name(cell(name_col))
            else:
                name = _clean_name(f"{cell(first_col)} {cell(last_col)}")
            if not valid_email(email):
                row_results.append(
                    _row_result(
                        row_number,
                        ROW_ERROR,
                        email=raw_email[:MAX_EMAIL_LENGTH],
                        name=name,
                        detail="Missing or invalid email address.",
                        code="invalid_email",
                    )
                )
                continue
            refs = split_session_refs(cell(session_col))
            existing = by_email.get(email)
            if existing is None:
                by_email[email] = Registrant(
                    row=row_number, email=email, name=name, session_refs=refs
                )
                order.append(email)
                continue
            for ref in refs:
                if ref not in existing.session_refs:
                    existing.session_refs.append(ref)
            if not existing.name and name:
                existing.name = name
            existing.extra_rows.append(row_number)
            row_results.append(
                _row_result(
                    row_number,
                    ROW_SKIPPED,
                    email=email,
                    name=name,
                    detail=f"Same email as row {existing.row}; sessions combined there.",
                    code="merged_with_earlier_row",
                )
            )
    except csv.Error as exc:
        raise CSVImportError("csv_unreadable", "That file could not be read as CSV.") from exc
    if not data_rows:
        raise CSVImportError("csv_empty", "That file has no registrant rows.")
    return ParsedImport(
        registrants=[by_email[email] for email in order], row_results=row_results
    )


def importable_activities(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Published sessions that take attendance — the ones a ticket can cover."""
    return [
        activity
        for activity in published_activities(event)
        if activity.get("id") and activity.get("attendance_requested", True)
    ]


def resolve_session_refs(
    event: dict[str, Any], refs: Iterable[str]
) -> tuple[list[str], list[str], list[str]]:
    """Map session references to activity ids.

    A reference is an activity id or a title (case and spacing ignored). "all"
    means every importable session. Returns (activity ids, unknown refs,
    ambiguous refs) — a title shared by two sessions must be given by id.
    """
    activities = importable_activities(event)
    by_id = {str(activity["id"]): activity for activity in activities}
    by_title: dict[str, list[str]] = {}
    for activity in activities:
        title = normalize_person_name(activity.get("title"))
        if title:
            by_title.setdefault(title, []).append(str(activity["id"]))

    def lookup(ref: str) -> tuple[list[str] | None, bool]:
        if ref in by_id:
            return [ref], False
        matches = by_title.get(normalize_person_name(ref))
        if matches and len(matches) > 1:
            return None, True
        return matches, False

    resolved: list[str] = []
    unknown: list[str] = []
    ambiguous: list[str] = []
    for ref in refs:
        key = normalize_person_name(ref)
        if not key:
            continue
        if key in ALL_SESSIONS_WORDS and key not in by_title:
            ids = list(by_id)
        else:
            ids, is_ambiguous = lookup(ref)
            if is_ambiguous:
                ambiguous.append(ref)
                continue
            if ids is None and "," in ref:
                # "Day 1, Day 2" in one cell: accept only if every part is known.
                parts = [part.strip() for part in ref.split(",") if part.strip()]
                part_ids = [lookup(part) for part in parts]
                if parts and all(found and not amb for found, amb in part_ids):
                    ids = [i for found, _ in part_ids for i in found]
            if ids is None:
                unknown.append(ref)
                continue
        for activity_id in ids:
            if activity_id not in resolved:
                resolved.append(activity_id)
    return resolved, unknown, ambiguous


def _respondent_identity(invite: dict[str, Any]) -> tuple[str, set[str]]:
    invite_id = str(invite.get("id") or "")
    token_identity = f"invite:{invite_id}"
    member_id = str(invite.get("member_id") or "")
    if member_id:
        return member_id, {member_id, token_identity}
    return token_identity, {token_identity}


def _latest_rows_for(
    responses: list[dict[str, Any]], aliases: set[str]
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in responses:
        activity_id = row.get("activity_id")
        if not activity_id or row.get("respondent_id") not in aliases:
            continue
        current = latest.get(activity_id)
        if current is None or str(row.get("updated_at") or "") >= str(
            current.get("updated_at") or ""
        ):
            latest[activity_id] = row
    return latest


def apply_session_marks(
    responses: list[dict[str, Any]],
    invite: dict[str, Any],
    activity_ids: list[str],
    *,
    now: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Make the import's "coming" marks for one invite equal ``activity_ids``.

    - A listed session with no answer gets an import "coming" row.
    - A listed session the person answered themselves keeps their answer.
    - An import row for a session no longer listed is withdrawn.
    Returns (new responses, change summary).
    """
    respondent_id, aliases = _respondent_identity(invite)
    latest = _latest_rows_for(responses, aliases)
    wanted = set(activity_ids)
    added: list[str] = []
    removed: list[str] = []
    kept_own: list[str] = []

    withdraw = {
        activity_id
        for activity_id, row in latest.items()
        if row.get("via") == IMPORT_VIA and activity_id not in wanted
    }
    next_responses = [
        row
        for row in responses
        if not (row.get("respondent_id") in aliases and row.get("activity_id") in withdraw)
    ]
    removed.extend(sorted(withdraw))

    for activity_id in activity_ids:
        row = latest.get(activity_id)
        if row is None:
            next_responses.append(
                {
                    "activity_id": activity_id,
                    "respondent_id": respondent_id,
                    "respondent_type": "member" if invite.get("member_id") else "public-invite",
                    "display_name": str(invite.get("invitee_name") or "Invited guest"),
                    "status": "coming",
                    "choice": "",
                    "party_size": 1,
                    "updated_at": now,
                    "via": IMPORT_VIA,
                }
            )
            added.append(activity_id)
        elif row.get("via") != IMPORT_VIA and row.get("status") != "coming":
            kept_own.append(activity_id)
    return next_responses, {"added": added, "removed": removed, "kept_own_answer": kept_own}


def new_invite_record(
    event: dict[str, Any],
    registrant: Registrant,
    *,
    member: dict[str, Any] | None,
    source: str,
    share_message_for,
    app_url: str,
    now: str,
) -> dict[str, Any]:
    """Build an invitation in the same shape the organizer's invite form makes."""
    invite_id = str(uuid.uuid4())
    rsvp_link = f"{app_url.rstrip('/')}/rsvp#{invite_id}"
    record: dict[str, Any] = {
        "id": invite_id,
        "invitee_name": registrant.name or registrant.email.split("@")[0],
        "email": registrant.email,
        "invite_source": "member" if member else "guest",
        "import_source": source,
        "status": "invited",
        "rsvp_status": "pending",
        "note": "",
        "zoom_link": (
            event.get("zoom_link", "")
            if event.get("gathering_format") in {"online", "hybrid"}
            else ""
        ),
        "share_message": share_message_for(event, rsvp_link),
        "delivery_status": "ready-for-email",
        "created_at": now,
    }
    if member:
        record["member_id"] = member["id"]
        record["invitee_name"] = member.get("full_name") or record["invitee_name"]
    return record


@dataclass
class ImportOutcome:
    updates: dict[str, Any]
    rows: list[dict[str, Any]]
    new_flags: list[dict[str, Any]]
    touched_invite_ids: list[str]

    def counts(self) -> dict[str, int]:
        totals = {ROW_CREATED: 0, ROW_UPDATED: 0, ROW_SKIPPED: 0, ROW_FLAGGED: 0, ROW_ERROR: 0}
        for row in self.rows:
            totals[row["status"]] = totals.get(row["status"], 0) + 1
        return totals


def apply_registrants(
    event: dict[str, Any],
    registrants: list[Registrant],
    *,
    flags_by_email: dict[str, dict[str, Any]],
    members_by_email: dict[str, dict[str, Any]],
    source: str,
    share_message_for,
    app_url: str,
    now: str,
) -> ImportOutcome:
    """Apply registrants to an event snapshot. Pure: mutates only ``event``.

    ``flags_by_email`` holds this event's existing duplicate flags, so a re-run
    honors the organizer's earlier decision instead of re-flagging.
    """
    invites: list[dict[str, Any]] = event.setdefault("event_invites", [])
    responses: list[dict[str, Any]] = list(event.get("activity_rsvps", []))
    activity_titles = {
        str(activity.get("id")): str(activity.get("title") or "")
        for activity in importable_activities(event)
    }
    rows: list[dict[str, Any]] = []
    new_flags: list[dict[str, Any]] = []
    touched: list[str] = []

    def holder(invite: dict[str, Any]) -> dict[str, Any] | None:
        # K9: a merged invitation's person now lives on the invitation it was
        # merged into.
        seen: set[str] = set()
        while invite is not None and invite.get("merged_into"):
            if invite.get("id") in seen:
                return None
            seen.add(str(invite.get("id")))
            invite = next((i for i in invites if i.get("id") == invite["merged_into"]), None)
        return invite

    def by_email(email: str) -> dict[str, Any] | None:
        found = next(
            (
                i
                for i in invites
                if normalize_import_email(i.get("email")) == email
                or email in (i.get("alternate_emails") or [])
            ),
            None,
        )
        return holder(found) if found is not None else None

    def by_name(name_key: str, email: str) -> dict[str, Any] | None:
        if not name_key:
            return None
        return next(
            (
                i
                for i in invites
                if not i.get("merged_into")
                and normalize_person_name(i.get("invitee_name")) == name_key
                and normalize_import_email(i.get("email")) != email
            ),
            None,
        )

    for registrant in registrants:
        base = {"email": registrant.email, "name": registrant.name}
        activity_ids, unknown, ambiguous = resolve_session_refs(event, registrant.session_refs)
        if unknown or ambiguous:
            problems = []
            if unknown:
                problems.append("unknown session: " + ", ".join(unknown))
            if ambiguous:
                problems.append(
                    "more than one session has this title, use its id: " + ", ".join(ambiguous)
                )
            rows.append(
                _row_result(
                    registrant.row,
                    ROW_ERROR,
                    detail="; ".join(problems).capitalize() + ".",
                    code="unknown_session" if unknown else "ambiguous_session",
                    **base,
                )
            )
            continue
        session_titles = [activity_titles.get(i, i) for i in activity_ids]

        target = by_email(registrant.email)
        flag = flags_by_email.get(registrant.email)
        applied_to_existing = False
        if target is None:
            match = by_name(normalize_person_name(registrant.name), registrant.email)
            if flag and flag.get("status") == FLAG_DISMISSED:
                rows.append(
                    _row_result(
                        registrant.row,
                        ROW_SKIPPED,
                        detail="You dismissed this possible duplicate earlier.",
                        code="duplicate_dismissed",
                        sessions=session_titles,
                        **base,
                    )
                )
                continue
            if flag and flag.get("status") == FLAG_APPLY_TO_EXISTING:
                target = next(
                    (i for i in invites if i.get("id") == flag.get("matched_invite_id")), None
                )
                applied_to_existing = target is not None
            elif match is not None and not (
                flag and flag.get("status") == FLAG_CREATE_SEPARATE
            ):
                if not flag or flag.get("status") == FLAG_PENDING:
                    new_flags.append(
                        {
                            "email": registrant.email,
                            "name": registrant.name,
                            "row": registrant.row,
                            "source": source,
                            "activity_ids": activity_ids,
                            "matched_invite_id": match.get("id"),
                            "matched_name": str(match.get("invitee_name") or ""),
                            "matched_email": str(match.get("email") or ""),
                        }
                    )
                rows.append(
                    _row_result(
                        registrant.row,
                        ROW_FLAGGED,
                        detail=(
                            "Same name as an existing invitee with a different email. "
                            "Review it before anyone is invited twice."
                        ),
                        code="possible_duplicate",
                        sessions=session_titles,
                        matched_name=str(match.get("invitee_name") or ""),
                        matched_email=str(match.get("email") or ""),
                        **base,
                    )
                )
                continue

        if target is None:
            invite = new_invite_record(
                event,
                registrant,
                member=members_by_email.get(registrant.email),
                source=source,
                share_message_for=share_message_for,
                app_url=app_url,
                now=now,
            )
            invites.append(invite)
            responses, changes = apply_session_marks(responses, invite, activity_ids, now=now)
            touched.append(invite["id"])
            rows.append(
                _row_result(
                    registrant.row,
                    ROW_CREATED,
                    invite_id=invite["id"],
                    sessions=session_titles,
                    kept_own_answer=[activity_titles.get(i, i) for i in changes["kept_own_answer"]],
                    **base,
                )
            )
            continue

        renamed = False
        if (
            not applied_to_existing
            and registrant.name
            and not target.get("member_id")
            and target.get("invitee_name") != registrant.name
        ):
            target["invitee_name"] = registrant.name
            renamed = True
        responses, changes = apply_session_marks(responses, target, activity_ids, now=now)
        changed = renamed or bool(changes["added"] or changes["removed"])
        touched.append(str(target.get("id")))
        detail = "Applied to the existing invitee you chose." if applied_to_existing else ""
        rows.append(
            _row_result(
                registrant.row,
                ROW_UPDATED if changed else ROW_SKIPPED,
                invite_id=target.get("id"),
                sessions=session_titles,
                kept_own_answer=[activity_titles.get(i, i) for i in changes["kept_own_answer"]],
                detail=detail or ("" if changed else "Already up to date."),
                code="" if changed else "unchanged",
                **base,
            )
        )

    event["activity_rsvps"] = responses
    event["activity_rsvp_summaries"] = activity_summaries(event)
    return ImportOutcome(
        updates={
            "event_invites": invites,
            "activity_rsvps": responses,
            "activity_rsvp_summaries": event["activity_rsvp_summaries"],
        },
        rows=rows,
        new_flags=new_flags,
        touched_invite_ids=touched,
    )
