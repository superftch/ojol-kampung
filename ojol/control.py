"""Compatibility entry point for existing operator commands."""

from app.main import WORKER_SHUTDOWN as WORKER_SHUTDOWN
from app.main import ControlService as ControlService
from app.main import create_app as create_app
from app.main import main as main

if __name__ == "__main__":
    main()
