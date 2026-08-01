"""Privacy-safe Legacy Table preview and availability routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_current_user, get_thread_for_user
from legacy_table_sync import destination_configuration
from models import LegacyTableRecipePreviewRequest

router = APIRouter(prefix="/api")


def _owned_recipe(thread: dict[str, Any], user: dict[str, Any]) -> None:
    if (
        thread.get("category") != "recipe-tradition"
        or not thread.get("created_by")
        or thread.get("created_by") != user.get("id")
        or thread.get("withdrawn_at")
        or thread.get("deleted_at")
        or thread.get("hidden") is True
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe transfer preview not found.")


@router.get("/legacy-table/status")
async def legacy_table_status(current_user: dict[str, Any] = Depends(get_current_user)):
    config = destination_configuration()
    return {
        "connection_status": config["status"],
        "sso_status": "ready" if config["sso_ready"] else config["status"],
        "transfer_status": "unavailable",
        "error_code": "destination_idempotency_contract_required",
        "capabilities": ["recipe_preview", "cross_product_sign_in"],
    }


@router.post("/legacy-table/recipe-preview")
async def legacy_table_recipe_preview(
    payload: LegacyTableRecipePreviewRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    thread = await get_thread_for_user(payload.thread_id, current_user)
    _owned_recipe(thread, current_user)
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
            "family_creation": "may_be_required",
            "retention_and_deletion": "managed_independently_by_legacy_table",
        },
        "transfer_status": "unavailable",
        "error_code": "destination_idempotency_contract_required",
    }


@router.post("/legacy-table/sync-recipe/{thread_id}")
async def legacy_table_transfer_unavailable(
    thread_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    thread = await get_thread_for_user(thread_id, current_user)
    _owned_recipe(thread, current_user)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "destination_idempotency_contract_required",
            "message": "Recipe transfer is unavailable; your Kindred recipe is unchanged.",
        },
    )


@router.post("/legacy-table/sync-preview")
async def retired_bulk_preview(current_user: dict[str, Any] = Depends(get_current_user)):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "bulk_export_retired", "message": "Bulk Legacy Table export is not available."},
    )
