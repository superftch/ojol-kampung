"""Worker settings and direct cookie-import request payloads."""

from typing import Literal

from pydantic import BaseModel, Field, StrictBool


class AutoFlagChange(BaseModel):
    flag: str = ""
    enabled: StrictBool = False


class OjolModeChange(BaseModel):
    mode: Literal["kendara", "otomatis"]


class StudySubjectChange(BaseModel):
    subject: str = ""
    mode: str | None = None


class DirectCookieImport(BaseModel):
    cookie: str = Field(default="", repr=False)
    name: str | None = None
    account_id: str | None = None
