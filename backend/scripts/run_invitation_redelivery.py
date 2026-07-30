#!/usr/bin/env python3
"""Run one aggregate-only, privacy-safe invitation redelivery operation."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from invitation_redelivery import (  # noqa: E402
    CredentialVault,
    InvitationRedeliveryCoordinator,
    InvitationSelection,
    RedeliveryFailure,
    SafeErrorCode,
    SafeOperationReport,
    normalize_application_url,
    validate_operation_id,
)
from invitation_redelivery_provider import (  # noqa: E402
    ResendInvitationDeliveryProvider,
)
from invitation_redelivery_store import (  # noqa: E402
    MongoInvitationRedeliveryStore,
)
from invitation_redelivery_validator import (  # noqa: E402
    PublicRSVPHeaderValidator,
)
from invitation_redelivery_webhook import validate_webhook_secret  # noqa: E402


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rotate a bounded invitation population through the recoverable "
            "privacy-safe redelivery outbox."
        )
    )
    parser.add_argument(
        "--operation-id",
        required=True,
        help="Stable owner-approved opaque incident operation ID.",
    )
    parser.add_argument(
        "--invite-source",
        choices=("guest", "member"),
        required=True,
    )
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument(
        "--created-before",
        required=True,
        help="Timezone-aware ISO-8601 upper boundary.",
    )
    parser.add_argument(
        "--expected-commit",
        required=True,
        help="Exact commit required in RAILWAY_GIT_COMMIT_SHA.",
    )
    return parser.parse_args(argv)


def _safe_failure(
    operation_id: str,
    code: SafeErrorCode,
) -> SafeOperationReport:
    return SafeOperationReport(
        operation_id=operation_id,
        status="preflight_failed",
        failures=1,
        error_code=code.value,
    )


async def _run(args: argparse.Namespace) -> SafeOperationReport:
    operation_id = validate_operation_id(args.operation_id)
    deployed_commit = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
    if len(args.expected_commit) != 40 or deployed_commit != args.expected_commit:
        return _safe_failure(
            operation_id,
            SafeErrorCode.CONFIGURATION_UNAVAILABLE,
        )

    try:
        required_environment = (
            "MONGO_URL",
            "DB_NAME",
            "RESEND_API_KEY",
            "FROM_EMAIL",
            "RESEND_VERIFIED_DOMAIN",
            "RESEND_WEBHOOK_SECRET",
            "PUBLIC_API_BASE_URL",
            "APP_URL",
            "INVITATION_REDELIVERY_RECOVERY_KEY",
        )
        if any(
            not str(os.environ.get(name, "")).strip() for name in required_environment
        ):
            raise RedeliveryFailure(SafeErrorCode.CONFIGURATION_UNAVAILABLE)
        created_before = datetime.fromisoformat(
            args.created_before.replace("Z", "+00:00")
        )
        selection = InvitationSelection(
            invite_source=args.invite_source,
            expected_count=args.expected_count,
            created_before=created_before,
        )
        vault = CredentialVault(
            os.environ.get("INVITATION_REDELIVERY_RECOVERY_KEY", "")
        )
        validate_webhook_secret(os.environ.get("RESEND_WEBHOOK_SECRET", ""))
        app_url = normalize_application_url(os.environ.get("APP_URL", ""))
    except (ValueError, RedeliveryFailure):
        return _safe_failure(
            operation_id,
            SafeErrorCode.CONFIGURATION_UNAVAILABLE,
        )

    from db import (  # noqa: E402
        client,
        events_collection,
        invitation_redelivery_operations_collection,
    )

    store = MongoInvitationRedeliveryStore(
        client=client,
        events_collection=events_collection,
        operations_collection=invitation_redelivery_operations_collection,
        vault=vault,
    )
    provider = ResendInvitationDeliveryProvider(
        api_key=os.environ.get("RESEND_API_KEY", ""),
        from_address=os.environ.get("FROM_EMAIL", ""),
        verified_domain=os.environ.get("RESEND_VERIFIED_DOMAIN", ""),
    )
    validator = PublicRSVPHeaderValidator(
        api_base_url=os.environ.get("PUBLIC_API_BASE_URL", ""),
    )
    coordinator = InvitationRedeliveryCoordinator(
        store=store,
        provider=provider,
        validator=validator,
        app_url=app_url,
    )
    return await coordinator.execute(
        selection,
        operation_id=operation_id,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _arguments()
    try:
        operation_id = validate_operation_id(args.operation_id)
    except RedeliveryFailure:
        invalid_report = {
            "status": "preflight_failed",
            "credentials_selected": 0,
            "credentials_rotated": 0,
            "replacements_delivered": 0,
            "old_credentials_rejected": 0,
            "new_credentials_validated": 0,
            "failures": 1,
            "error_code": SafeErrorCode.OPERATION_MISMATCH.value,
        }
        print(json.dumps(invalid_report, separators=(",", ":"), sort_keys=True))
        return 2
    try:
        report = asyncio.run(_run(args))
    except Exception:
        report = _safe_failure(
            operation_id,
            SafeErrorCode.INTERNAL_FAILURE,
        )
    print(json.dumps(report.to_dict(), separators=(",", ":"), sort_keys=True))
    return 0 if report.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
