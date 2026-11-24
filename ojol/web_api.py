"""Compatibility re-exports for modular FastAPI web routes."""

from .web import public_user, register_web_routes

__all__ = ["public_user", "register_web_routes"]
