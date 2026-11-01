"""Shared pydantic building blocks."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class Message(BaseModel):
    message: str
    ok: bool = True


class RangeQuery(BaseModel):
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1, le=1000)
    page_size: int = Field(default=24, ge=1, le=100)
