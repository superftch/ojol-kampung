"""Pydantic schemas for job vacancy application requests."""

from typing import Literal

from pydantic import BaseModel, Field


class JobApplyRequest(BaseModel):
    """Payload to apply for a facility or business job vacancy."""

    kind: Literal["facility", "business"]
    profession: str = Field(min_length=1, max_length=120)
    facility_id: str | None = Field(default=None, max_length=120)
    vacancy_id: str | None = Field(default=None, max_length=120)
    switch_job: bool = False
