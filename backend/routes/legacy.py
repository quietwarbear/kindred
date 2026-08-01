"""Privacy-safe Legacy Table preview, grant, payload, and receipt routes."""

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pymongo.errors import PyMongoError
from starlette.responses import JSONResponse, Response

from db import client, db
from dependencies import get_current_user, get_thread_for_user
from legacy_table_transfer import (
    TRANSFER_ORIGIN,
    TransferFailure,
    acknowledge_transfer,
    activate_grant,
    ensure_transfer_indexes,
    operation_for_grant,
    prepare_operation,
    retrieve_payload,
    revoke_grant,
    require_transfer_configuration,
    safe_projection,
    transfer_configuration,
    validate_owned_recipe,
)
from models import (
    LegacyTableRecipePreviewRequest,
    LegacyTableTransferAcknowledgement,
    LegacyTableTransferStartRequest,
)
from routes.federation import mint_sso_code

router = APIRouter(prefix="/api")
_NO_STORE = {
    "Cache-Control": "no-store, max-age=0",
    "Referrer-Policy": "no-referrer",
}


def _safe_failure(exc: TransferFailure) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"status": exc.safe_state, "error_code": exc.code},
        headers=_NO_STORE,
    )


def _cross_origin_headers() -> dict[str, str]:
    return {
        **_NO_STORE,
        "Access-Control-Allow-Origin": TRANSFER_ORIGIN,
        "Access-Control-Allow-Credentials": "false",
        "Access-Control-Allow-Headers": "Content-Type, X-Kindred-Transfer",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Vary": "Origin",
    }


@router.get("/legacy-table/status")
async def legacy_table_status(current_user: dict[str, Any] = Depends(get_current_user)):
    config = transfer_configuration()
    return {
        "connection_status": config["status"],
        "sso_status": "ready" if config["ready"] else config["status"],
        "transfer_status": "ready" if config["ready"] else "unavailable",
        "error_code": None if config["ready"] else "transfer_configuration_unavailable",
        "capabilities": ["recipe_preview", "cross_product_sign_in", "recipe_import"],
    }


@router.post("/legacy-table/recipe-preview")
async def legacy_table_recipe_preview(
    payload: LegacyTableRecipePreviewRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    thread = await get_thread_for_user(payload.thread_id, current_user)
    try:
        validate_owned_recipe(thread, current_user)
    except TransferFailure as exc:
        raise HTTPException(
            status_code=exc.http_status, detail="Recipe transfer preview not found."
        ) from exc
    config = transfer_configuration()
    return {
        "preview_state": "ready",
        "selected_content": {
            "title": thread.get("title", ""),
            "instructions_or_story": thread.get("body", ""),
        },
        "data_categories": [
            "account_identity_for_cross_product_sign_in",
            "selected_recipe_title",
            "selected_recipe_instructions_or_story",
        ],
        "destination_behavior": {
            "family_cookbook": "destination_managed",
            "family_creation": "explicit_choice_required",
            "retention_and_deletion": "managed_independently_by_legacy_table",
        },
        "transfer_status": "ready" if config["ready"] else "unavailable",
        "error_code": None if config["ready"] else "transfer_configuration_unavailable",
    }


@router.post("/legacy-table/transfers/start")
async def start_legacy_table_transfer(
    payload: LegacyTableTransferStartRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Create or resume one stable author/source/revision operation."""
    thread = await get_thread_for_user(payload.thread_id, current_user)
    try:
        require_transfer_configuration()
        validate_owned_recipe(thread, current_user)
        await ensure_transfer_indexes(db)
        operation = await prepare_operation(db, client, thread, current_user)
        code, web_origin = await mint_sso_code("legacy_table", current_user)
        credential, operation = await activate_grant(db, operation)
    except TransferFailure as exc:
        return _safe_failure(exc)
    except HTTPException:
        return _safe_failure(TransferFailure("destination_sso_unavailable", 502))
    except PyMongoError:
        return _safe_failure(TransferFailure("transfer_storage_unavailable", 503))
    landing = f"{web_origin}/sso?{urlencode({'code': code})}#transfer={credential}"
    return JSONResponse(
        status_code=200,
        content={
            "operation_id": operation["operation_id"],
            "status": operation["state"],
            "url": landing,
        },
        headers=_NO_STORE,
    )


@router.options("/legacy-table/transfer-payload")
@router.options("/legacy-table/transfer-acknowledgement")
@router.options("/legacy-table/transfer-revoke")
async def transfer_preflight(request: Request):
    if request.headers.get("origin") != TRANSFER_ORIGIN:
        return Response(status_code=404, headers=_NO_STORE)
    return Response(status_code=204, headers=_cross_origin_headers())


@router.post("/legacy-table/transfer-payload")
async def legacy_table_transfer_payload(
    request: Request,
    x_kindred_transfer: str = Header(default="", alias="X-Kindred-Transfer"),
):
    try:
        _, payload = await retrieve_payload(
            db, x_kindred_transfer, request.headers.get("origin", "")
        )
    except TransferFailure as exc:
        response = _safe_failure(exc)
        response.headers.update(_cross_origin_headers())
        return response
    except PyMongoError:
        response = _safe_failure(TransferFailure("transfer_storage_unavailable", 503))
        response.headers.update(_cross_origin_headers())
        return response
    return JSONResponse(content=payload, headers=_cross_origin_headers())


@router.post("/legacy-table/transfer-acknowledgement")
async def legacy_table_transfer_acknowledgement(
    payload: LegacyTableTransferAcknowledgement,
    request: Request,
    x_kindred_transfer: str = Header(default="", alias="X-Kindred-Transfer"),
):
    try:
        operation = await operation_for_grant(
            db, x_kindred_transfer, request.headers.get("origin", "")
        )
        operation = await acknowledge_transfer(
            db, client, operation, payload.model_dump()
        )
    except TransferFailure as exc:
        response = _safe_failure(exc)
        response.headers.update(_cross_origin_headers())
        return response
    except PyMongoError:
        response = _safe_failure(TransferFailure("transfer_storage_unavailable", 503))
        response.headers.update(_cross_origin_headers())
        return response
    return JSONResponse(
        content=safe_projection(operation), headers=_cross_origin_headers()
    )


@router.post("/legacy-table/transfer-revoke")
async def legacy_table_transfer_revoke(
    request: Request,
    x_kindred_transfer: str = Header(default="", alias="X-Kindred-Transfer"),
):
    try:
        operation = await operation_for_grant(
            db, x_kindred_transfer, request.headers.get("origin", "")
        )
        operation = await revoke_grant(db, operation)
    except TransferFailure as exc:
        response = _safe_failure(exc)
        response.headers.update(_cross_origin_headers())
        return response
    except PyMongoError:
        response = _safe_failure(TransferFailure("transfer_storage_unavailable", 503))
        response.headers.update(_cross_origin_headers())
        return response
    return JSONResponse(
        content=safe_projection(operation), headers=_cross_origin_headers()
    )


@router.post("/legacy-table/sync-recipe/{thread_id}")
async def legacy_table_transfer_unavailable(
    thread_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    thread = await get_thread_for_user(thread_id, current_user)
    try:
        validate_owned_recipe(thread, current_user)
    except TransferFailure as exc:
        raise HTTPException(
            status_code=exc.http_status, detail="Recipe transfer not found."
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "legacy_transfer_route_retired",
            "message": "Use the consent-bound transfer flow.",
        },
    )


@router.post("/legacy-table/sync-preview")
async def retired_bulk_preview(
    current_user: dict[str, Any] = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "bulk_export_retired",
            "message": "Bulk Legacy Table export is not available.",
        },
    )
