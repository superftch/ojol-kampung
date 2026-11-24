"""Payloads for human review of digit templates."""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, FiniteFloat, StrictInt, StringConstraints

Digit = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[0-9]$"),
    BeforeValidator(lambda value: str(value) if type(value) is int else value),
]
Point = Annotated[list[FiniteFloat], Field(min_length=2, max_length=2)]
Stroke = Annotated[list[Point], Field(min_length=1)]
Glyph = Annotated[list[Stroke], Field(min_length=1)]


class ReviewSelection(BaseModel):
    review_id: str | None = None
    error_id: str | None = None


class TemplateSave(ReviewSelection):
    digit: Digit
    glyph: Glyph


class TemplateDelete(BaseModel):
    digit: Digit
    index: Annotated[StrictInt, Field(ge=0)]


class ReviewDismissal(ReviewSelection):
    glyph: Glyph | None = None
