"""Gateway network discovery for finding devices on LAN (section 11).

Scans admin-entered CIDR ranges on ports 4370, 80 and 443 to identify devices.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any

from bip.connectors.zk_tcp.adapter import ZKConnector
from bip.sdk.events import DeviceTarget


class NetworkDiscovery:
    """Discovers biometric devices on LAN subnets."""

    def __init__(self, ports: list[int] | None = None, timeout: float = 0.5) -> None:
        self.ports = ports or [4370, 80, 443]
        self.timeout = timeout

    async def check_port(self, host: str, port: int) -> bool:
        """Check if a TCP port is open."""

        def _check() -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                try:
                    s.connect((host, port))
                    return True
                except (TimeoutError, ConnectionRefusedError, OSError):
                    return False

        return await asyncio.to_thread(_check)

    async def scan_cidr(self, cidr: str, max_hosts: int = 256) -> list[dict[str, Any]]:
        """Scan a CIDR network range for responsive biometric terminal ports."""
        network = ipaddress.ip_network(cidr, strict=False)
        hosts = list(network.hosts())[:max_hosts]

        discovered: list[dict[str, Any]] = []

        async def _probe_host(host_ip: str) -> None:
            for port in self.ports:
                is_open = await self.check_port(host_ip, port)
                if not is_open:
                    continue

                device_info: dict[str, Any] = {
                    "ip": host_ip,
                    "port": port,
                    "family": "zk_tcp" if port == 4370 else "hik_isapi",
                    "serial": None,
                }

                # Attempt identification on port 4370
                if port == 4370:
                    try:
                        conn = ZKConnector(target=DeviceTarget(address=host_ip, port=port))
                        probe_res = await asyncio.wait_for(conn.probe(conn.target), timeout=2.0)
                        device_info["serial"] = probe_res.serial
                        device_info["model"] = probe_res.model
                        device_info["firmware"] = probe_res.firmware
                    except Exception:
                        pass

                discovered.append(device_info)

        # Scan hosts concurrently with a concurrency limit
        sem = asyncio.Semaphore(20)

        async def _bounded_probe(host: str) -> None:
            async with sem:
                await _probe_host(host)

        await asyncio.gather(*[_bounded_probe(str(h)) for h in hosts])
        return discovered
