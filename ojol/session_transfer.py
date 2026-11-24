"""Compatibility entry point for existing operator commands."""

from app.integrations.kampung.session_transfer import main as main

if __name__ == "__main__":
    raise SystemExit(main())
