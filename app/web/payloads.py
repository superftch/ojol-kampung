"""Decode web requests and report validation errors without echoing input."""

from typing import Any
from urllib.parse import parse_qs

from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError


def validate_payload[Payload: BaseModel](model: type[Payload], data: object) -> Payload:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_context=False, include_url=False)[0]
        field = ".".join(map(str, error["loc"]))
        message = f"{field}: {error['msg']}" if field else error["msg"]
        raise ValueError(message) from None


async def read_json[Payload: BaseModel](request: Request, model: type[Payload]) -> Payload:
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "JSON tidak valid") from None
    try:
        return validate_payload(model, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


def is_json_request(request: Request) -> bool:
    return request.headers.get("content-type", "").startswith("application/json")


async def parse_body(request: Request) -> tuple[dict[str, Any], bool]:
    """Parse either JSON or application/x-www-form-urlencoded request payloads."""
    is_json = is_json_request(request)
    if is_json:
        try:
            data = await request.json()
            return (data if isinstance(data, dict) else {}), True
        except ValueError:
            return {}, True
    body_bytes = await request.body()
    parsed = parse_qs(body_bytes.decode("utf-8", errors="replace"))
    return {k: v[0] for k, v in parsed.items()}, False
