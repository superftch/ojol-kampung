"""Modular FastAPI web package for Kampung Ojol Automation."""

from .app import create_app, register_web_routes
from .deps import public_user

__all__ = ["create_app", "public_user", "register_web_routes"]
