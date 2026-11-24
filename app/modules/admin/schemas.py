"""Admin approval, quota, and maintenance request payloads."""

from typing import Literal

from pydantic import BaseModel, Field, StrictInt


class ReviewUser(BaseModel):
    user_id: int = Field(gt=0)
    approve: bool


class AccountLimit(BaseModel):
    user_id: int = Field(gt=0)
    maximum: int = Field(ge=1, le=100)


class MaintenanceChange(BaseModel):
    mode: Literal["off", "manual", "scheduled"]
    target: Literal["ojol", "all"] = "ojol"
    start: str = ""
    end: str = ""


class FleetLimit(BaseModel):
    name: Literal["max_accounts_per_user", "max_active_workers"]
    value: StrictInt | str
