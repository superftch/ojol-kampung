import io
import json
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

from defusedxml import ElementTree as ET

from app.web.extension_crx import (
    build_extension_crx3,
    build_linux_policy_json,
    build_macos_mobileconfig,
    build_update_xml,
    build_windows_reg,
    derive_extension_id,
    get_extension_identity,
    resolve_public_origin,
)


def _read_varint(buf: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        byte = buf[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7


def _parse_protobuf_fields(buf: bytes) -> dict[int, list[bytes]]:
    fields: dict[int, list[bytes]] = {}
    offset = 0
    while offset < len(buf):
        tag, offset = _read_varint(buf, offset)
        field_num = tag >> 3
        wire_type = tag & 0x07
        assert wire_type == 2
        length, offset = _read_varint(buf, offset)
        fields.setdefault(field_num, []).append(buf[offset : offset + length])
        offset += length
    return fields


def test_build_extension_crx3_and_verify_signature(tmp_path: Path):
    crx_bytes, ext_id, version = build_extension_crx3(tmp_path)
    assert re.fullmatch(r"[a-p]{32}", ext_id)
    assert version == "2.2.0"

    # Header magic + version + header_len
    assert crx_bytes[:4] == b"Cr24"
    crx_version, header_len = struct.unpack("<II", crx_bytes[4:12])
    assert crx_version == 3

    header_bytes = crx_bytes[12 : 12 + header_len]
    zip_bytes = crx_bytes[12 + header_len :]

    header_fields = _parse_protobuf_fields(header_bytes)
    assert 2 in header_fields
    assert 10000 in header_fields

    proof_fields = _parse_protobuf_fields(header_fields[2][0])
    pub_der = proof_fields[1][0]
    signature = proof_fields[2][0]
    signed_header_data = header_fields[10000][0]

    assert derive_extension_id(pub_der) == ext_id

    # Verify ZIP payload has manifest.json at root (required for CRX)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "ojol.js" in names
        assert not any(name.startswith("kampungsebelah-extension/") for name in names)

    # Verify RSA-SHA256 signature with OpenSSL
    openssl = shutil.which("openssl")
    assert openssl is not None
    signed_payload = (
        b"CRX3 SignedData\x00"
        + struct.pack("<I", len(signed_header_data))
        + signed_header_data
        + zip_bytes
    )
    with (
        tempfile.NamedTemporaryFile(suffix=".der") as pub_f,
        tempfile.NamedTemporaryFile(suffix=".sig") as sig_f,
        tempfile.NamedTemporaryFile(suffix=".bin") as data_f,
    ):
        pub_f.write(pub_der)
        pub_f.flush()
        sig_f.write(signature)
        sig_f.flush()
        data_f.write(signed_payload)
        data_f.flush()

        proc = subprocess.run(  # noqa: S603
            [
                openssl,
                "dgst",
                "-sha256",
                "-verify",
                pub_f.name,
                "-keyform",
                "DER",
                "-signature",
                sig_f.name,
                data_f.name,
            ],
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr.decode()

    # Persistent key yields identical Extension ID across calls
    ext_id_2, version_2 = get_extension_identity(tmp_path)
    assert ext_id_2 == ext_id
    assert version_2 == version


def test_policy_and_update_xml_generators():
    ext_id = "abcdefghijklmnopabcdefghijklmnop"
    update_url = "https://ojol.example.com/api/extension/update.xml"
    crx_url = "https://ojol.example.com/api/extension/download.crx"

    xml_str = build_update_xml(ext_id, "2.2.0", crx_url)
    root = ET.fromstring(xml_str)
    assert root.attrib["protocol"] == "2.0"
    app_el = root.find("{http://www.google.com/update2/response}app")
    assert app_el is not None
    assert app_el.attrib["appid"] == ext_id
    check_el = app_el.find("{http://www.google.com/update2/response}updatecheck")
    assert check_el is not None
    assert check_el.attrib["codebase"] == crx_url
    assert check_el.attrib["version"] == "2.2.0"

    reg = build_windows_reg(ext_id, update_url)
    assert "Windows Registry Editor Version 5.00" in reg
    assert "ExtensionInstallForcelist" in reg
    assert f'"{ext_id};{update_url}"' in reg

    linux_json = json.loads(build_linux_policy_json(ext_id, update_url))
    assert linux_json == {"ExtensionInstallForcelist": [f"{ext_id};{update_url}"]}

    plist = build_macos_mobileconfig(ext_id, update_url)
    assert "com.google.Chrome" in plist
    assert f"<string>{ext_id};{update_url}</string>" in plist


def test_resolve_public_origin():
    assert (
        resolve_public_origin(
            "http://127.0.0.1:6080/",
            {"host": "127.0.0.1:6080"},
            "https://ojol.jnck.pl",
        )
        == "https://ojol.jnck.pl"
    )
    assert (
        resolve_public_origin(
            "http://127.0.0.1:6080/",
            {"host": "ojol.jnck.pl", "x-forwarded-proto": "https"},
            "http://localhost:6080",
        )
        == "https://ojol.jnck.pl"
    )
    assert (
        resolve_public_origin(
            "http://testserver/",
            {"host": "testserver"},
            "http://localhost:6080",
        )
        == "http://testserver"
    )
