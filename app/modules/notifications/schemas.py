"""Notification acknowledgement request payloads."""

from pydantic import BaseModel


class NoticeSelection(BaseModel):
    ids: list[str] | None = None
