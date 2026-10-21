"""ZKBioTime vendor connector adapter (ADR-002, section 8.4)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, ClassVar, Literal

import httpx

from bip.sdk.capabilities import Capability
from bip.sdk.errors import ProtocolError, Unreachable, Unsupported
from bip.sdk.events import (
    Checkpoint,
    CommandResult,
    DevicePerson,
    DeviceTarget,
    HealthReport,
    ProbeResult,
    RawPunch,
    VerifyMode,
)


class BioTimeConnector:
    """Connector for ZKBioTime attendance server integration."""

    family: str = "biotime"
    mode: Literal["vendor"] = "vendor"

    CAPABILITIES: ClassVar[set[Capability]] = {
        Capability.PUNCHES_PULL,
        Capability.PEOPLE_READ,
        Capability.PEOPLE_WRITE,
        Capability.PEOPLE_DELETE,
        Capability.DEVICE_INFO,
    }

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        token: str = "biotime-mock-valid-token",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._external_client = client

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        headers = {"Authorization": f"Token {self.token}"}
        if self._external_client:
            return self._external_client, False
        return httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=10.0), True

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        """Probe BioTime server API reachability."""
        http, close = self._get_client()
        try:
            resp = await http.get("/personnel/api/employees/?page_size=1")
            if resp.status_code not in (200, 401, 403):
                raise Unreachable(f"BioTime server returned HTTP {resp.status_code}")
            return ProbeResult(
                serial=target.serial or "BIOTIME-SERVER",
                model="ZKBioTime Server",
                firmware="8.5+",
                capabilities=[c.value for c in self.CAPABILITIES],
                extra={"server_url": self.base_url},
            )
        except Exception as e:
            if isinstance(e, Unreachable):
                raise
            raise Unreachable(f"Failed to probe BioTime server: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def fetch_punches(self, since: Checkpoint) -> AsyncIterator[RawPunch]:
        """Fetch transactions from BioTime server newer than cursor."""
        http, close = self._get_client()
        try:
            page = 1
            page_size = 100
            cursor_str = since.cursor.strip() if since.cursor else None

            cursor_dt = None
            if cursor_str:
                with contextlib.suppress(ValueError):
                    cursor_dt = datetime.fromisoformat(cursor_str)
                if cursor_dt is None:
                    with contextlib.suppress(ValueError):
                        cursor_dt = datetime.strptime(cursor_str, "%Y-%m-%d %H:%M:%S")

            more = True
            while more:
                params: dict[str, Any] = {"page": page, "page_size": page_size}
                if cursor_str:
                    params["start_time"] = cursor_str

                resp = await http.get("/iclock/api/transactions/", params=params)
                if resp.status_code != 200:
                    raise ProtocolError(f"BioTime transactions query failed with HTTP {resp.status_code}")

                data = resp.json()
                records = data.get("data", [])
                if not records:
                    break

                for rec in records:
                    pt_str = rec.get("punch_time", "")
                    try:
                        punch_dt = datetime.strptime(pt_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        with contextlib.suppress(ValueError):
                            punch_dt = datetime.fromisoformat(pt_str)
                        if not pt_str:
                            continue

                    if cursor_dt and punch_dt <= cursor_dt:
                        continue

                    verify_type = rec.get("verify_type", 0)
                    verify_mode: VerifyMode = "fingerprint"
                    if verify_type == 1:
                        verify_mode = "fingerprint"
                    elif verify_type == 2:
                        verify_mode = "pin"
                    elif verify_type == 3:
                        verify_mode = "card"
                    elif verify_type == 4:
                        verify_mode = "face"

                    yield RawPunch(
                        device_pin=str(rec.get("emp_code", "")),
                        device_local_time=punch_dt,
                        verify_mode=verify_mode,
                        raw=rec,
                    )

                if not data.get("next"):
                    more = False
                else:
                    page += 1
        finally:
            if close:
                await http.aclose()

    async def list_people(self) -> list[DevicePerson]:
        """List employees from BioTime server."""
        http, close = self._get_client()
        try:
            resp = await http.get("/personnel/api/employees/?page_size=500")
            if resp.status_code != 200:
                raise ProtocolError(f"BioTime employees query failed with HTTP {resp.status_code}")
            employees = resp.json().get("data", [])
            people = []
            for emp in employees:
                first = emp.get("first_name", "")
                last = emp.get("last_name", "")
                name = f"{first} {last}".strip() or emp.get("name", "")
                people.append(
                    DevicePerson(
                        pin=str(emp.get("emp_code", "")),
                        name=name,
                        card_no=str(emp.get("card_no", "")) if emp.get("card_no") else None,
                    )
                )
            return people
        finally:
            if close:
                await http.aclose()

    async def upsert_person(self, person: DevicePerson) -> CommandResult:
        """Upsert employee in BioTime server."""
        http, close = self._get_client()
        try:
            body = {
                "emp_code": person.pin,
                "first_name": person.name,
                "card_no": person.card_no or "",
            }
            resp = await http.post("/personnel/api/employees/", json=body)
            if resp.status_code in (200, 201):
                return CommandResult(success=True, message=f"Upserted employee {person.pin}")
            return CommandResult(success=False, return_code=resp.status_code, message=resp.text)
        except Exception as e:
            raise ProtocolError(f"Failed to upsert person in BioTime: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def delete_person(self, pin: str) -> CommandResult:
        """Delete employee in BioTime server."""
        http, close = self._get_client()
        try:
            resp = await http.delete(f"/personnel/api/employees/{pin}/")
            if resp.status_code in (200, 204):
                return CommandResult(success=True, message=f"Deleted employee {pin}")
            return CommandResult(success=False, return_code=resp.status_code, message=resp.text)
        except Exception as e:
            raise ProtocolError(f"Failed to delete person in BioTime: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def set_time(self, now: datetime) -> CommandResult:
        """BioTime server does not support setting device time via API."""
        raise Unsupported("BioTime server does not support setting terminal clock via REST API")

    async def health(self) -> HealthReport:
        """Check BioTime server connection status."""
        http, close = self._get_client()
        try:
            resp = await http.get("/personnel/api/employees/?page_size=1")
            reachable = resp.status_code in (200, 401, 403)
            return HealthReport(reachable=reachable, serial="BIOTIME-SERVER")
        except Exception as e:
            return HealthReport(reachable=False, extra={"error": str(e)})
        finally:
            if close:
                await http.aclose()
