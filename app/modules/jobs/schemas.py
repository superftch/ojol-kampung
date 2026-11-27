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


class JobSniperConfigRequest(BaseModel):
    """Payload to update scheduled Job Sniper settings."""

    enabled: bool = False
    interval_seconds: int = Field(default=30, ge=10, le=3600)
    schedule_enabled: bool = False
    start_time: str = Field(default="00:00", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(default="23:59", pattern=r"^\d{2}:\d{2}$")
    source_filter: Literal["all", "facility", "business"] = "all"
    skill_track_id: str = Field(default="", max_length=80)
    min_salary_milli: int = Field(default=0, ge=0)
    allow_switch_job: bool = True
    allow_fee: bool = False
    auto_stop_on_success: bool = True
