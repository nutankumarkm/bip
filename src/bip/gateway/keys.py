"""Ed25519 key management for gateway request signing (ADR-009).

Canonical message format per spec:
<METHOD>\\n<path with query>\\n<timestamp>\\n<sha256 hex of body>
Signature is base64-encoded.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)


def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def public_key_to_b64(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def public_key_from_b64(b64_str: str) -> Ed25519PublicKey:
    raw = base64.b64decode(b64_str)
    return Ed25519PublicKey.from_public_bytes(raw)


def public_key_to_hex(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return raw.hex()


def public_key_from_hex(hex_str: str) -> Ed25519PublicKey:
    raw = bytes.fromhex(hex_str)
    return Ed25519PublicKey.from_public_bytes(raw)


def save_private_key(key: Ed25519PrivateKey, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    # Try Windows DPAPI machine scope if pywin32 is available
    try:
        import win32crypt  # type: ignore[import-untyped]

        encrypted = win32crypt.CryptProtectData(
            pem, "BIP Gateway Private Key", None, None, None, 4
        )  # 4 = CRYPTPROTECT_LOCAL_MACHINE
        path.write_bytes(b"DPAPI:" + encrypted)
        return
    except (ImportError, Exception):
        pass

    path.write_bytes(pem)
    with contextlib.suppress(OSError, NotImplementedError):
        path.chmod(0o600)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    data = path.read_bytes()
    if data.startswith(b"DPAPI:"):
        try:
            import win32crypt  # type: ignore[import-untyped]

            _, decrypted = win32crypt.CryptUnprotectData(data[6:], None, None, None, 0)
            key = load_pem_private_key(decrypted, password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise TypeError("Expected Ed25519 private key")
            return key
        except Exception as e:
            raise ValueError(f"Failed to decrypt DPAPI private key: {e}") from e

    key = load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Expected Ed25519 private key")
    return key


def build_canonical_message(method: str, path_with_query: str, timestamp: int, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{method.upper()}\n{path_with_query}\n{timestamp}\n{body_hash}".encode()


def sign_request(
    private_key: Ed25519PrivateKey,
    method: str,
    path_with_query: str,
    body: bytes,
    timestamp: int,
) -> str:
    message = build_canonical_message(method, path_with_query, timestamp, body)
    sig = private_key.sign(message)
    return base64.b64encode(sig).decode("ascii")


def verify_request(
    public_key: Ed25519PublicKey,
    signature_b64: str,
    method: str,
    path_with_query: str,
    body: bytes,
    timestamp: int,
) -> bool:
    message = build_canonical_message(method, path_with_query, timestamp, body)
    try:
        sig_bytes = base64.b64decode(signature_b64)
        public_key.verify(sig_bytes, message)
        return True
    except Exception:
        return False
