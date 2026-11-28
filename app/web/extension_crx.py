"""CRX3 extension packaging, signing key management, and Enterprise Policy generators."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import uuid
import zipfile
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from app.core.models import ROOT

EXTENSION_DIR = ROOT / "tools" / "chrome-diving-radar"

EXTENSION_FILES = (
    "manifest.json",
    "content.js",
    "diving-avoid.js",
    "diving-human.js",
    "diving-open.js",
    "diving-route.js",
    "diving-shark.js",
    "ojol.js",
    "mancing.js",
    "tpu.js",
    "berburu.js",
    "berburu-inject.js",
    "inject.js",
    "popup.html",
    "popup.js",
    "README.md",
    "package.json",
)

_CRX3_MAGIC = b"Cr24"
_CRX3_VERSION = 3
_CRX3_SIGNATURE_PREFIX = b"CRX3 SignedData\x00"
_KEY_LOCK = threading.Lock()
_CRX_CACHE_LOCK = threading.Lock()
_CRX_CACHE: dict[tuple[str, tuple[tuple[str, int], ...]], tuple[bytes, str, str]] = {}


def _openssl_bin() -> str:
    path = shutil.which("openssl")
    if not path:
        raise RuntimeError("OpenSSL binary tidak ditemukan untuk menandatangani CRX3")
    return path


def _run_openssl(args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(  # noqa: S603
        [_openssl_bin(), *args],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"OpenSSL gagal ({proc.returncode}): {err or 'unknown error'}")
    return proc.stdout


def get_signing_key_path(runtime_dir: Path) -> Path:
    """Return the persistent RSA signing key path inside runtime_dir."""
    return runtime_dir / "extension-signing-key.pem"


def ensure_signing_key(key_path: Path) -> Path:
    """Ensure a persistent RSA-2048 private key exists at key_path."""
    if key_path.is_file():
        return key_path
    with _KEY_LOCK:
        if key_path.is_file():
            return key_path
        key_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".ext-key-", suffix=".pem", dir=key_path.parent)
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            _run_openssl(
                [
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    "rsa_keygen_bits:2048",
                    "-out",
                    str(tmp_path),
                ]
            )
            tmp_path.chmod(0o600)
            tmp_path.replace(key_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
    return key_path


def get_public_key_der(key_path: Path) -> bytes:
    """Export SubjectPublicKeyInfo DER bytes from the RSA private key."""
    return _run_openssl(["pkey", "-in", str(key_path), "-pubout", "-outform", "DER"])


def derive_extension_id(public_key_der: bytes) -> str:
    """Compute Chrome's 32-char a-p extension ID from SPKI DER public key bytes."""
    digest = hashlib.sha256(public_key_der).digest()[:16]
    chars: list[str] = []
    for byte in digest:
        chars.append(chr(ord("a") + ((byte >> 4) & 0x0F)))
        chars.append(chr(ord("a") + (byte & 0x0F)))
    return "".join(chars)


def read_extension_version(extension_dir: Path = EXTENSION_DIR) -> str:
    """Read extension version from manifest.json."""
    manifest_path = extension_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("manifest.json ekstensi tidak ditemukan")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = str(manifest.get("version", "")).strip()
    if not version:
        raise ValueError("Versi ekstensi tidak ditemukan di manifest.json")
    return version


def _manifest_referenced_files(manifest: dict[str, object]) -> list[str]:
    """Collect relative file paths referenced by a Chrome extension manifest."""
    refs: list[str] = []

    def _add(val: object) -> None:
        if isinstance(val, str):
            cleaned = val.strip().lstrip("./")
            if cleaned and "*" not in cleaned and cleaned not in refs:
                refs.append(cleaned)

    action = manifest.get("action")
    if isinstance(action, dict):
        _add(action.get("default_popup"))

    background = manifest.get("background")
    if isinstance(background, dict):
        _add(background.get("service_worker"))

    content_scripts = manifest.get("content_scripts")
    if isinstance(content_scripts, list):
        for entry in content_scripts:
            if not isinstance(entry, dict):
                continue
            for key in ("js", "css"):
                items = entry.get(key)
                if isinstance(items, list):
                    for item in items:
                        _add(item)

    web_resources = manifest.get("web_accessible_resources")
    if isinstance(web_resources, list):
        for entry in web_resources:
            if isinstance(entry, dict):
                resources = entry.get("resources")
                if isinstance(resources, list):
                    for item in resources:
                        _add(item)
            else:
                _add(entry)

    icons = manifest.get("icons")
    if isinstance(icons, dict):
        for item in icons.values():
            _add(item)

    return refs


def list_extension_files(extension_dir: Path = EXTENSION_DIR) -> tuple[str, ...]:
    """Return ordered list of files to package, ensuring all manifest references exist."""
    manifest_path = extension_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("manifest.json ekstensi tidak ditemukan")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resolved_root = extension_dir.resolve()
    manifest_refs = _manifest_referenced_files(manifest)

    missing: list[str] = []
    for rel in manifest_refs:
        candidate = (extension_dir / rel).resolve()
        if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
            missing.append(rel)
    if missing:
        raise FileNotFoundError(
            f"File ekstensi yang dirujuk manifest.json tidak ditemukan: {', '.join(missing)}"
        )

    ordered: list[str] = []
    for rel in (*EXTENSION_FILES, *manifest_refs):
        if rel in ordered:
            continue
        candidate = (extension_dir / rel).resolve()
        if candidate.is_relative_to(resolved_root) and candidate.is_file():
            ordered.append(rel)
    return tuple(ordered)


def build_extension_zip(
    extension_dir: Path = EXTENSION_DIR,
    *,
    root_prefix: str = "kampungsebelah-extension/",
) -> bytes:
    """Build deterministic ZIP archive of extension files."""
    files = list_extension_files(extension_dir)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in files:
            fpath = extension_dir / fname
            arcname = f"{root_prefix}{fname}" if root_prefix else fname
            info = zipfile.ZipInfo(filename=arcname, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, fpath.read_bytes())
    return buf.getvalue()


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def _protobuf_bytes(field_number: int, data: bytes) -> bytes:
    tag = _encode_varint((field_number << 3) | 2)
    return tag + _encode_varint(len(data)) + data


def _sign_crx3_payload(key_path: Path, payload: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(prefix=".crx-payload-", delete=True) as tmp_in:
        tmp_in.write(payload)
        tmp_in.flush()
        return _run_openssl(["dgst", "-sha256", "-sign", str(key_path), tmp_in.name])


def _extension_cache_fingerprint(
    key_path: Path, extension_dir: Path
) -> tuple[str, tuple[tuple[str, int], ...]]:
    stats: list[tuple[str, int]] = []
    if key_path.is_file():
        stats.append(("__key__", key_path.stat().st_mtime_ns))
    for fname in list_extension_files(extension_dir):
        fpath = extension_dir / fname
        if fpath.is_file():
            stats.append((fname, fpath.stat().st_mtime_ns))
    return (str(key_path.resolve()), tuple(stats))


def build_extension_crx3(
    runtime_dir: Path,
    extension_dir: Path = EXTENSION_DIR,
) -> tuple[bytes, str, str]:
    """Build and sign a CRX3 package, returning (crx_bytes, extension_id, version)."""
    key_path = ensure_signing_key(get_signing_key_path(runtime_dir))
    cache_key = _extension_cache_fingerprint(key_path, extension_dir)
    with _CRX_CACHE_LOCK:
        cached = _CRX_CACHE.get(cache_key)
        if cached is not None:
            return cached

    version = read_extension_version(extension_dir)
    zip_bytes = build_extension_zip(extension_dir, root_prefix="")
    public_key_der = get_public_key_der(key_path)
    crx_id = hashlib.sha256(public_key_der).digest()[:16]
    extension_id = derive_extension_id(public_key_der)

    signed_header_data = _protobuf_bytes(1, crx_id)
    signed_payload = (
        _CRX3_SIGNATURE_PREFIX
        + struct.pack("<I", len(signed_header_data))
        + signed_header_data
        + zip_bytes
    )
    signature = _sign_crx3_payload(key_path, signed_payload)

    proof = _protobuf_bytes(1, public_key_der) + _protobuf_bytes(2, signature)
    crx_header = _protobuf_bytes(2, proof) + _protobuf_bytes(10000, signed_header_data)

    crx_bytes = (
        _CRX3_MAGIC + struct.pack("<II", _CRX3_VERSION, len(crx_header)) + crx_header + zip_bytes
    )

    result = (crx_bytes, extension_id, version)
    with _CRX_CACHE_LOCK:
        _CRX_CACHE.clear()
        _CRX_CACHE[cache_key] = result
    return result


def get_extension_identity(
    runtime_dir: Path,
    extension_dir: Path = EXTENSION_DIR,
) -> tuple[str, str]:
    """Return (extension_id, version) using the persistent signing key."""
    key_path = ensure_signing_key(get_signing_key_path(runtime_dir))
    public_key_der = get_public_key_der(key_path)
    return derive_extension_id(public_key_der), read_extension_version(extension_dir)


def build_update_xml(extension_id: str, version: str, codebase_url: str) -> str:
    """Build Chrome CRX update manifest XML (gupdate protocol 2.0)."""
    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>\n"
        f"  <app appid='{escape(extension_id, quote=True)}'>\n"
        f"    <updatecheck codebase='{escape(codebase_url, quote=True)}' "
        f"version='{escape(version, quote=True)}' />\n"
        "  </app>\n"
        "</gupdate>\n"
    )


def build_windows_reg(extension_id: str, update_url: str) -> str:
    """Build a Windows Registry (.reg) file for Chrome ExtensionInstallForcelist."""
    policy_value = f"{extension_id};{update_url}".replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        "Windows Registry Editor Version 5.00",
        "",
        "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Google\\Chrome\\ExtensionInstallForcelist]",
        f'"1"="{policy_value}"',
        "",
    ]
    return "\r\n".join(lines)


def build_linux_policy_json(extension_id: str, update_url: str) -> str:
    """Build a Linux Chrome managed policy JSON file."""
    payload = {
        "ExtensionInstallForcelist": [f"{extension_id};{update_url}"],
    }
    return json.dumps(payload, indent=2) + "\n"


def build_macos_mobileconfig(extension_id: str, update_url: str) -> str:
    """Build a macOS configuration profile (.mobileconfig) for Chrome ExtensionInstallForcelist."""
    policy_value = escape(f"{extension_id};{update_url}")
    top_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"kampungsebelah-top-{extension_id}")).upper()
    inner_uuid = str(
        uuid.uuid5(uuid.NAMESPACE_DNS, f"kampungsebelah-chrome-{extension_id}")
    ).upper()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>PayloadContent</key>\n"
        "  <array>\n"
        "    <dict>\n"
        "      <key>ExtensionInstallForcelist</key>\n"
        "      <array>\n"
        f"        <string>{policy_value}</string>\n"
        "      </array>\n"
        "      <key>PayloadDisplayName</key>\n"
        "      <string>Google Chrome Extension Policy - KampungSebelah Helper</string>\n"
        "      <key>PayloadIdentifier</key>\n"
        f"      <string>com.kampungsebelah.helper.chrome.{escape(extension_id)}</string>\n"
        "      <key>PayloadType</key>\n"
        "      <string>com.google.Chrome</string>\n"
        "      <key>PayloadUUID</key>\n"
        f"      <string>{inner_uuid}</string>\n"
        "      <key>PayloadVersion</key>\n"
        "      <integer>1</integer>\n"
        "    </dict>\n"
        "  </array>\n"
        "  <key>PayloadDisplayName</key>\n"
        "  <string>KampungSebelah Helper Chrome Policy</string>\n"
        "  <key>PayloadIdentifier</key>\n"
        "  <string>com.kampungsebelah.helper.policy</string>\n"
        "  <key>PayloadRemovalDisallowed</key>\n"
        "  <false/>\n"
        "  <key>PayloadType</key>\n"
        "  <string>Configuration</string>\n"
        "  <key>PayloadUUID</key>\n"
        f"  <string>{top_uuid}</string>\n"
        "  <key>PayloadVersion</key>\n"
        "  <integer>1</integer>\n"
        "</dict>\n"
        "</plist>\n"
    )


def resolve_public_origin(
    request_base_url: str, headers: dict[str, str], configured_url: str
) -> str:
    """Resolve the public origin URL for update.xml and policy files."""
    candidate = (configured_url or "").strip().rstrip("/")
    parsed_cfg = urlsplit(candidate) if candidate else None
    is_default_local = (
        not parsed_cfg
        or not parsed_cfg.hostname
        or (parsed_cfg.hostname in {"localhost", "127.0.0.1"} and parsed_cfg.port == 6080)
    )
    if not is_default_local:
        return candidate

    fwd_host = (
        headers.get("x-forwarded-host", "").split(",")[0].strip() or headers.get("host", "").strip()
    )
    fwd_proto = headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if fwd_host and fwd_proto in {"http", "https"}:
        return f"{fwd_proto}://{fwd_host}".rstrip("/")

    return request_base_url.rstrip("/")
