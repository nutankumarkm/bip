"""Command line interface for bip-gateway agent."""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import socket
import sys
from pathlib import Path

import httpx

from bip.gateway.command_runner import CommandRunner
from bip.gateway.config import GatewayConfig
from bip.gateway.heartbeat import HeartbeatSender
from bip.gateway.keys import generate_keypair, load_private_key, public_key_to_b64, save_private_key
from bip.gateway.local_feed import create_local_feed_app
from bip.gateway.outbox import LocalOutbox
from bip.gateway.poller import DevicePoller
from bip.gateway.uploader import OutboxUploader


def get_default_config_dir() -> Path:
    if platform.system() == "Windows":
        prog_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(prog_data) / "bip-gateway"
    return Path("/etc/bip-gateway")


def cmd_pair(server_url: str, code: str, config_dir: Path | None = None) -> None:
    """Pair gateway agent with the BIP cloud platform."""
    base_dir = config_dir or get_default_config_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    key_path = base_dir / "gateway_ed25519.key"
    config_path = base_dir / "gateway.json"

    print("Generating Ed25519 keypair for gateway pairing...")
    private_key, public_key = generate_keypair()
    pub_b64 = public_key_to_b64(public_key)

    url = f"{server_url.rstrip('/')}/gw/v1/pair"
    payload = {
        "code": code,
        "public_key": pub_b64,
        "hostname": socket.gethostname(),
        "version": "0.1.0",
    }

    print(f"Contacting BIP server at {url}...")
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, json=payload)
        if resp.status_code != 200:
            print(f"Pairing failed with HTTP {resp.status_code}: {resp.text}")
            sys.exit(1)

        data = resp.json()
        gateway_id = data["gateway_id"]

    # Save private key securely
    save_private_key(private_key, key_path)
    print(f"Private key saved securely to {key_path}")

    # Save config
    config = GatewayConfig(
        gateway_id=gateway_id,
        cloud_url=server_url,
        data_dir=base_dir / "data",
        private_key_path=key_path,
    )
    config.save(config_path)
    print(f"Config saved to {config_path}")
    print(f"Successfully paired! Gateway ID: {gateway_id}")


async def run_agent(config: GatewayConfig) -> None:
    """Run the gateway agent background services."""
    key_path = config.get_key_path()
    if not key_path.exists():
        raise FileNotFoundError(f"Private key not found at {key_path}. Did you pair first?")

    private_key = load_private_key(key_path)
    outbox = LocalOutbox(config.get_outbox_db_path())

    poller = DevicePoller(outbox)
    uploader = OutboxUploader(
        outbox=outbox,
        cloud_url=config.cloud_url,
        gateway_id=config.gateway_id,
        private_key=private_key,
        batch_size=config.upload_batch_size,
    )
    command_runner = CommandRunner(
        cloud_url=config.cloud_url,
        gateway_id=config.gateway_id,
        private_key=private_key,
        connectors=poller._connectors,
    )
    heartbeat_sender = HeartbeatSender(
        cloud_url=config.cloud_url,
        gateway_id=config.gateway_id,
        private_key=private_key,
        outbox=outbox,
        connectors=poller._connectors,
        version=config.version,
    )

    print(f"Starting BIP Gateway Agent {config.version} (ID: {config.gateway_id})...")

    # Start local feed
    local_app = create_local_feed_app(
        outbox=outbox,
        token_path=config.get_local_token_path(),
        static_token=config.local_feed_token,
    )

    import uvicorn

    server_config = uvicorn.Config(
        local_app,
        host=config.local_feed_host,
        port=config.local_feed_port,
        log_level=config.log_level.lower(),
    )
    server = uvicorn.Server(server_config)

    tasks = [
        asyncio.create_task(uploader.run_loop()),
        asyncio.create_task(command_runner.run_loop()),
        asyncio.create_task(heartbeat_sender.run_loop(config.heartbeat_interval_seconds)),
        asyncio.create_task(poller.run_loop(config.poll_interval_seconds)),
        asyncio.create_task(server.serve()),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        poller.stop()
        uploader.stop()
        command_runner.stop()
        heartbeat_sender.stop()
        outbox.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="BIP Gateway Agent CLI")
    subparsers = parser.add_subparsers(dest="command")

    pair_parser = subparsers.add_parser("pair", help="Pair gateway with cloud")
    pair_parser.add_argument("--server", required=True, help="BIP cloud server base URL")
    pair_parser.add_argument("--code", required=True, help="8-digit pairing code")
    pair_parser.add_argument("--config-dir", default=None, help="Directory to store config and key")

    run_parser = subparsers.add_parser("run", help="Run the gateway service")
    run_parser.add_argument("--config", default=None, help="Path to config file")

    args = parser.parse_args()

    if args.command == "pair":
        cmd_pair(
            server_url=args.server,
            code=args.code,
            config_dir=Path(args.config_dir) if args.config_dir else None,
        )
    elif args.command == "run":
        cfg_path = Path(args.config) if args.config else get_default_config_dir() / "gateway.json"
        config = GatewayConfig.load(cfg_path)
        asyncio.run(run_agent(config))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
