import os
import socket
from pathlib import Path

import pytest

from ojol.config import load_settings
from ojol.models import ROOT, ShopPreview, Snapshot


def pytest_configure(config):
    if os.environ.get("OJOL_TEST_ISOLATED") != "1" or os.environ.get("OJOL_TEST_ENV_FILE") != str(
        ROOT / ".env.testing"
    ):
        raise pytest.UsageError("Wajib scripts/test.py dengan .env.testing terisolasi")
    effective = load_settings(ROOT / ".env.testing")
    if (
        effective.env != "testing"
        or effective.operator_authorized
        or not Path(os.environ["HOME"]).is_relative_to(ROOT / ".local/testing")
    ):
        raise pytest.UsageError("Konfigurasi test efektif tidak terisolasi")
    if any(
        key.endswith(("API_KEY", "TOKEN"))
        or key in {"BU_CDP_URL", "BU_CDP_WS", "DATABASE_URL", "GOOGLE_APPLICATION_CREDENTIALS"}
        for key in os.environ
    ):
        raise pytest.UsageError("Kredensial/target layanan bocor ke test")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original = socket.socket.connect

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Test tidak boleh mengakses jaringan")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **kw: pytest.fail("Network dilarang")
    )


@pytest.fixture
def settings(tmp_path):
    original = load_settings(ROOT / ".env.testing")
    return original.model_copy(update={"runtime_dir": tmp_path})


@pytest.fixture
def state():
    return Snapshot(
        wallet="35.68",
        fuel=72,
        condition=97,
        data=46,
        phase="idle",
        buttons=["🔎 Cari order"],
        history=["17.14 A → B · +0,704"],
    )


@pytest.fixture
def shop_preview():
    def make(products):
        return ShopPreview(
            id="00000000-0000-4000-8000-000000000001",
            plot_id="K22-U07",
            name="Konter fixture",
            category="konter-pulsa",
            distance_squared=0,
            products=products,
        )

    return make
