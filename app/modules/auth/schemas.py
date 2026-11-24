"""Credentials submitted by the web forms or JSON clients."""

from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = ""
    password: str = Field(default="", repr=False)


class PasswordConfirmation(Credentials):
    confirm_password: str = Field(default="", repr=False)


class Registration(PasswordConfirmation):
    name: str = ""


class CookieImportForm(BaseModel):
    csrf: str = Field(default="", repr=False)
    cookie: str = Field(default="", repr=False)
