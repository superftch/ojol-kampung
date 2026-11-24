"""Account selection and update request payloads."""

from pydantic import BaseModel, StrictBool


class AccountSelection(BaseModel):
    account_id: str | None = None


class AccountName(BaseModel):
    name: str | None = None


class AccountRename(AccountSelection, AccountName):
    pass


class AccountArchive(AccountSelection):
    archived: StrictBool = True
