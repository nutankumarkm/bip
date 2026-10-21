"""Hikvision ISAPI connector adapter (ADR-002, section 8.3)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar, Literal

import httpx

from bip.sdk.capabilities import Capability
from bip.sdk.errors import ProtocolError, Unreachable
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


class HikvisionISAPIConnector:
    """Adapter for Hikvision access control terminals communicating via ISAPI HTTP/HTTPS."""

    family: str = "hik_isapi"
    mode: Literal["pull"] = "pull"

    CAPABILITIES: ClassVar[set[Capability]] = {
        Capability.PUNCHES_PULL,
        Capability.PEOPLE_READ,
        Capability.PEOPLE_WRITE,
        Capability.PEOPLE_DELETE,
        Capability.TIME_SET,
        Capability.DEVICE_INFO,
    }

    def __init__(
        self,
        target: DeviceTarget | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
    ) -> None:
        self.target = target or DeviceTarget(address="127.0.0.1", port=80)
        self._external_client = client
        if base_url:
            self.base_url = base_url.rstrip("/")
        else:
            proto = "https" if self.target.port == 443 else "http"
            self.base_url = f"{proto}://{self.target.address}:{self.target.port}"

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._external_client:
            return self._external_client, False
        return httpx.AsyncClient(base_url=self.base_url, timeout=10.0), True

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        """Probe Hikvision terminal to read device information."""
        proto = "https" if target.port == 443 else "http"
        url = f"{proto}://{target.address}:{target.port}/ISAPI/System/deviceInfo"

        http, close = self._get_client()
        try:
            resp = await http.get(url if not self._external_client else "/ISAPI/System/deviceInfo")
            if resp.status_code != 200:
                raise Unreachable(f"Device probe returned HTTP {resp.status_code}")
            data = resp.json().get("DeviceInfo", {})
            serial = data.get("serialNumber") or data.get("deviceID")
            model = data.get("model", "Hikvision Terminal")
            firmware = data.get("firmwareVersion")
            return ProbeResult(
                serial=serial,
                model=model,
                firmware=firmware,
                capabilities=[c.value for c in self.CAPABILITIES],
                extra=data,
            )
        except Exception as e:
            if isinstance(e, Unreachable):
                raise
            raise Unreachable(f"Failed to connect to Hikvision terminal: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def fetch_punches(self, since: Checkpoint) -> AsyncIterator[RawPunch]:
        """Fetch attendance punches via ISAPI AcsEvent paging."""
        http, close = self._get_client()
        try:
            position = 0
            max_results = 50
            search_id = "1"
            more_results = True

            cursor_dt = None
            if since.cursor:
                with contextlib.suppress(ValueError):
                    cursor_dt = datetime.fromisoformat(since.cursor)

            while more_results:
                body = {
                    "AcsEventCond": {
                        "searchID": search_id,
                        "searchResultPosition": position,
                        "maxResults": max_results,
                        "major": 5,
                    }
                }
                if since.cursor:
                    body["AcsEventCond"]["startTime"] = since.cursor

                resp = await http.post("/ISAPI/AccessControl/AcsEvent?format=json", json=body)
                if resp.status_code != 200:
                    raise ProtocolError(f"AcsEvent query failed with HTTP {resp.status_code}")

                data = resp.json().get("AcsEvent", {})
                info_list = data.get("InfoList", [])
                if not info_list:
                    break

                for item in info_list:
                    raw_time_str = item.get("time", "")
                    try:
                        punch_dt = datetime.fromisoformat(raw_time_str)
                    except ValueError:
                        punch_dt = datetime.now(UTC)

                    if cursor_dt and punch_dt.replace(tzinfo=None) <= cursor_dt.replace(tzinfo=None):
                        continue

                    minor = item.get("minor", 0)
                    verify_mode: VerifyMode = "other"
                    if minor == 75:
                        verify_mode = "face"
                    elif minor == 1:
                        verify_mode = "card"
                    elif minor == 38:
                        verify_mode = "fingerprint"
                    elif minor == 2:
                        verify_mode = "pin"

                    yield RawPunch(
                        device_pin=str(item.get("employeeNoString") or item.get("cardNo") or "0"),
                        device_local_time=punch_dt,
                        verify_mode=verify_mode,
                        raw=item,
                    )

                num_matches = data.get("numOfMatches", 0)
                if num_matches < max_results or data.get("responseStatusStrg") != "OK":
                    more_results = False
                else:
                    position += num_matches
        finally:
            if close:
                await http.aclose()

    async def list_people(self) -> list[DevicePerson]:
        """List users from Hikvision terminal."""
        http, close = self._get_client()
        try:
            resp = await http.post("/ISAPI/AccessControl/UserInfo/Search?format=json", json={})
            if resp.status_code != 200:
                raise ProtocolError(f"UserInfo search failed with HTTP {resp.status_code}")
            users_data = resp.json().get("UserInfoSearch", {}).get("UserInfo", [])
            people = []
            for u in users_data:
                people.append(
                    DevicePerson(
                        pin=str(u.get("employeeNo", "")),
                        name=u.get("name", ""),
                    )
                )
            return people
        except Exception as e:
            if isinstance(e, ProtocolError):
                raise
            raise ProtocolError(f"Failed to list people: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def upsert_person(self, person: DevicePerson) -> CommandResult:
        """Upsert a user record to Hikvision terminal."""
        http, close = self._get_client()
        try:
            body = {
                "UserInfo": {
                    "employeeNo": person.pin,
                    "name": person.name,
                    "userType": "normal",
                }
            }
            resp = await http.post("/ISAPI/AccessControl/UserInfo/Record?format=json", json=body)
            if resp.status_code in (200, 201):
                return CommandResult(success=True, message=f"Upserted person {person.pin}")
            return CommandResult(success=False, return_code=resp.status_code, message=resp.text)
        except Exception as e:
            raise ProtocolError(f"Failed to upsert person: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def delete_person(self, pin: str) -> CommandResult:
        """Delete a user record from Hikvision terminal."""
        http, close = self._get_client()
        try:
            body = {
                "UserInfoDetail": {
                    "mode": "byEmployeeNo",
                    "EmployeeNoList": [{"employeeNo": pin}],
                }
            }
            resp = await http.put("/ISAPI/AccessControl/UserInfo/Delete?format=json", json=body)
            if resp.status_code == 200:
                return CommandResult(success=True, message=f"Deleted person {pin}")
            return CommandResult(success=False, return_code=resp.status_code, message=resp.text)
        except Exception as e:
            raise ProtocolError(f"Failed to delete person: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def set_time(self, now: datetime) -> CommandResult:
        """Set terminal time via ISAPI."""
        http, close = self._get_client()
        try:
            body = {"Time": {"timeMode": "manual", "localTime": now.isoformat()}}
            resp = await http.put("/ISAPI/System/time", json=body)
            if resp.status_code == 200:
                return CommandResult(success=True, message=f"Set time to {now.isoformat()}")
            return CommandResult(success=False, return_code=resp.status_code, message=resp.text)
        except Exception as e:
            raise ProtocolError(f"Failed to set time: {e}") from e
        finally:
            if close:
                await http.aclose()

    async def health(self) -> HealthReport:
        """Check reachability and time drift."""
        http, close = self._get_client()
        try:
            resp = await http.get("/ISAPI/System/time")
            if resp.status_code != 200:
                return HealthReport(reachable=False, extra={"status_code": resp.status_code})

            data = resp.json().get("Time", {})
            local_time_str = data.get("localTime")
            dev_dt = None
            drift_s = 0
            if local_time_str:
                with contextlib.suppress(ValueError):
                    dev_dt = datetime.fromisoformat(local_time_str)
                    now = datetime.now(UTC)
                    drift_s = int(abs((now.replace(tzinfo=None) - dev_dt.replace(tzinfo=None)).total_seconds()))

            return HealthReport(
                reachable=True,
                serial=self.target.serial,
                time=dev_dt,
                drift_seconds=drift_s,
                log_fill_pct=0,
            )
        except Exception as e:
            return HealthReport(reachable=False, extra={"error": str(e)})
        finally:
            if close:
                await http.aclose()
