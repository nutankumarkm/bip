"""Gateway agent updater with Ed25519 signed manifest verification and rollback (section 11)."""

from __future__ import annotations

import base64
import hashlib
import shutil
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def build_manifest_canonical_bytes(version: str, url: str, sha256_hash: str) -> bytes:
    """Build canonical payload for manifest signing."""
    return f"{version}\n{url}\n{sha256_hash}".encode()


def verify_manifest_signature(
    manifest: dict[str, Any],
    public_key: Ed25519PublicKey,
) -> bool:
    """Verify Ed25519 signature of the update manifest against a pinned public key."""
    version = manifest.get("version", "")
    url = manifest.get("url", "")
    sha256_hash = manifest.get("sha256", "")
    signature_b64 = manifest.get("signature", "")

    if not (version and url and sha256_hash and signature_b64):
        return False

    message = build_manifest_canonical_bytes(version, url, sha256_hash)
    try:
        sig_bytes = base64.b64decode(signature_b64)
        public_key.verify(sig_bytes, message)
        return True
    except Exception:
        return False


class AgentUpdater:
    """Manages downloading, verifying, staging, and rolling back gateway agent updates."""

    def __init__(
        self,
        cloud_url: str,
        pinned_public_key: Ed25519PublicKey,
        stage_dir: Path,
        current_dir: Path,
        backup_dir: Path,
    ) -> None:
        self.cloud_url = cloud_url.rstrip("/")
        self.pinned_public_key = pinned_public_key
        self.stage_dir = stage_dir
        self.current_dir = current_dir
        self.backup_dir = backup_dir

    async def check_release(self, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
        """Fetch the latest release manifest from cloud and verify its signature."""
        http = client or httpx.AsyncClient(timeout=10.0)
        close = client is None

        try:
            url = f"{self.cloud_url}/gw/v1/release"
            resp = await http.get(url)
            if resp.status_code != 200:
                return None

            manifest = resp.json()
            if not verify_manifest_signature(manifest, self.pinned_public_key):
                raise ValueError("Manifest signature verification failed: invalid signature")

            return manifest
        finally:
            if close:
                await http.aclose()

    def verify_file_hash(self, file_path: Path, expected_sha256: str) -> bool:
        """Verify the SHA-256 hash of a downloaded file."""
        if not file_path.exists():
            return False
        h = hashlib.sha256()
        h.update(file_path.read_bytes())
        return h.hexdigest().lower() == expected_sha256.lower()

    def stage_file(self, source_path: Path, filename: str) -> Path:
        """Stage an update file into the staging directory."""
        self.stage_dir.mkdir(parents=True, exist_ok=True)
        dest = self.stage_dir / filename
        shutil.copy2(source_path, dest)
        return dest

    def swap_and_backup(self) -> bool:
        """Swap staged version into current, backing up previous version."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            if self.current_dir.exists():
                for item in self.current_dir.iterdir():
                    dest = self.backup_dir / item.name
                    if item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)

            self.current_dir.mkdir(parents=True, exist_ok=True)
            if self.stage_dir.exists():
                for item in self.stage_dir.iterdir():
                    dest = self.current_dir / item.name
                    if item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
            return True
        except Exception:
            self.rollback()
            return False

    def rollback(self) -> bool:
        """Restore previous version from backup directory."""
        try:
            if not self.backup_dir.exists():
                return False
            for item in self.backup_dir.iterdir():
                dest = self.current_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            return True
        except Exception:
            return False
