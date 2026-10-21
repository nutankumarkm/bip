"""Fake pyzk client emulator for zk_tcp connector testing (ADR-002, section 8.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class FakeAttendanceRecord:
    user_id: str
    timestamp: datetime
    status: int = 0
    punch: int = 0


@dataclass
class FakeZKUser:
    uid: int
    name: str = ""
    privilege: int = 0
    password: str = ""
    group_id: str = "1"
    user_id: str = ""
    card: int = 0


class FakeZKClient:
    """Mock ZK client conforming to pyzk interface for testing without hardware."""

    def __init__(
        self,
        ip: str = "127.0.0.1",
        port: int = 4370,
        timeout: int = 5,
        password: int = 0,
        force_udp: bool = False,
        ommit_ping: bool = False,
    ) -> None:
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.password = password
        self.force_udp = force_udp
        self.ommit_ping = ommit_ping

        self.connected = False
        self.disabled = False
        self.serial_number = "ZK-FAKE-998877"
        self.firmware_version = "Ver 6.60 Dec 20 2020"
        self.device_time = datetime.now(UTC).replace(microsecond=0)
        self.max_att_capacity = 100000
        self.max_user_capacity = 5000

        self._attendance: list[FakeAttendanceRecord] = []
        self._users: dict[str, FakeZKUser] = {}
        self._next_uid = 1
        self.should_fail_connect = False
        self.should_fail_reads = False

    def connect(self) -> bool:
        if self.should_fail_connect:
            raise ConnectionError("Failed to connect to ZK device at {self.ip}:{self.port}")
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def disable_device(self) -> None:
        if not self.connected:
            raise RuntimeError("Device not connected")
        self.disabled = True

    def enable_device(self) -> None:
        if not self.connected:
            raise RuntimeError("Device not connected")
        self.disabled = False

    def get_attendance(self) -> list[FakeAttendanceRecord]:
        if not self.connected:
            raise RuntimeError("Device not connected")
        if self.should_fail_reads:
            raise RuntimeError("Device communication error during get_attendance")
        return list(self._attendance)

    def get_users(self) -> list[FakeZKUser]:
        if not self.connected:
            raise RuntimeError("Device not connected")
        return list(self._users.values())

    def set_user(
        self,
        uid: int = 0,
        name: str = "",
        privilege: int = 0,
        password: str = "",
        group_id: str = "1",
        user_id: str = "",
        card: int = 0,
    ) -> bool:
        if not self.connected:
            raise RuntimeError("Device not connected")
        if not uid:
            uid = self._next_uid
            self._next_uid += 1
        user = FakeZKUser(
            uid=uid,
            name=name,
            privilege=privilege,
            password=password,
            group_id=str(group_id),
            user_id=str(user_id or uid),
            card=card,
        )
        self._users[user.user_id] = user
        return True

    def delete_user(self, uid: int = 0, user_id: str = "") -> bool:
        if not self.connected:
            raise RuntimeError("Device not connected")
        target_key = None
        for k, u in self._users.items():
            if (uid and u.uid == uid) or (user_id and u.user_id == str(user_id)):
                target_key = k
                break
        if target_key:
            del self._users[target_key]
            return True
        return False

    def get_time(self) -> datetime:
        if not self.connected:
            raise RuntimeError("Device not connected")
        return self.device_time

    def set_time(self, timestamp: datetime) -> bool:
        if not self.connected:
            raise RuntimeError("Device not connected")
        self.device_time = timestamp
        return True

    def get_serialnumber(self) -> str:
        if not self.connected:
            raise RuntimeError("Device not connected")
        return self.serial_number

    def get_firmware_version(self) -> str:
        if not self.connected:
            raise RuntimeError("Device not connected")
        return self.firmware_version

    def read_sizes(self) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Device not connected")
        return {
            "users": len(self._users),
            "users_cap": self.max_user_capacity,
            "attlog": len(self._attendance),
            "attlog_cap": self.max_att_capacity,
        }

    # Test helper methods
    def add_punch(self, user_id: str, timestamp: datetime, status: int = 0, punch: int = 0) -> None:
        self._attendance.append(
            FakeAttendanceRecord(
                user_id=str(user_id),
                timestamp=timestamp,
                status=status,
                punch=punch,
            )
        )
