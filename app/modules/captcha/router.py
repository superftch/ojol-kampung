"""Shared fleet captcha template bank and pending glyph review routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.modules.captcha import (
    delete_template_from_bank,
    dismiss_review,
    get_all_pending_reviews,
    get_bank_templates,
    resolve_review,
    save_template_to_bank,
)
from app.modules.captcha.schemas import ReviewDismissal, TemplateDelete, TemplateSave
from app.modules.captcha.service import retry_pending_bank_accounts
from app.web.deps import WebContext, get_all_fleet_directories, get_ctx, require_user
from app.web.payloads import parse_body, validate_payload

router = APIRouter()


async def _read_review[Payload: BaseModel](request: Request, schema: type[Payload]) -> Payload:
    body, _ = await parse_body(request)
    try:
        return validate_payload(schema, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/api/bank-angka")
async def get_bank_angka(
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    fleet_dirs, acc_names = get_all_fleet_directories(ctx)
    raw_templates = get_bank_templates(fleet_dirs)
    formatted_templates: dict[str, list[dict]] = {}
    total_variants = 0
    total_contributions = 0

    for digit, variants in raw_templates.items():
        formatted_templates[digit] = []
        for variant in variants:
            total_variants += 1
            if isinstance(variant, dict):
                if variant.get("by"):
                    total_contributions += 1
                formatted_templates[digit].append(
                    {
                        "glyph": variant.get("glyph", []),
                        "by": variant.get("by"),
                        "at": variant.get("at"),
                    }
                )
            else:
                formatted_templates[digit].append({"glyph": variant, "by": None, "at": None})

    pending = get_all_pending_reviews(fleet_dirs, acc_names)
    return {
        "templates": formatted_templates,
        "pending": pending,
        "total_templates": total_variants,
        "pending_count": len(pending),
        "total_contributions": total_contributions,
    }


@router.post("/api/bank-angka/save")
async def save_bank_angka(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await _read_review(request, TemplateSave)
    digit, glyph = body.digit, body.glyph
    review_id, error_id = body.review_id, body.error_id

    fleet_dirs, acc_names = get_all_fleet_directories(ctx)
    user_name = user.get("name") or user.get("username") or "Pengguna"

    save_template_to_bank(fleet_dirs, digit, glyph, contributed_by=user_name)
    if review_id:
        resolve_review(fleet_dirs, review_id, digit=digit, glyph=glyph, resolved_by=user_name)
    if error_id:
        resolve_review(fleet_dirs, error_id, digit=digit, glyph=glyph, resolved_by=user_name)

    retried_accounts = await retry_pending_bank_accounts(
        ctx, fleet_dirs, acc_names, review_id, error_id
    )
    return {"ok": True, "digit": digit, "by": user_name, "retried_accounts": retried_accounts}


@router.post("/api/bank-angka/delete")
async def delete_bank_angka(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await _read_review(request, TemplateDelete)
    digit, index = body.digit, body.index

    fleet_dirs, _ = get_all_fleet_directories(ctx)
    delete_template_from_bank(fleet_dirs, digit, index)
    return {"ok": True, "digit": digit, "deleted_index": index}


@router.post("/api/bank-angka/dismiss")
async def dismiss_bank_angka(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await _read_review(request, ReviewDismissal)
    review_id, error_id = body.review_id, body.error_id
    if not review_id and not error_id:
        raise HTTPException(400, "Review ID atau Error ID diperlukan")

    fleet_dirs, _ = get_all_fleet_directories(ctx)
    glyph = body.glyph
    if review_id:
        dismiss_review(fleet_dirs, review_id, glyph=glyph)
    if error_id:
        dismiss_review(fleet_dirs, error_id, glyph=glyph)
    return {"ok": True}
