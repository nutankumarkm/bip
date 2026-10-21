"""ADMS/iClock protocol parser — ATTLOG, OPERLOG, user records, command results."""

from __future__ import annotations

import re
from datetime import datetime

from bip.sdk.events import CommandResult, DevicePerson, RawPunch
from bip.sdk.protocols import ParsedUpload

VERIFY_MAP = {
    "0": "pin",
    "1": "fingerprint",
    "2": "fingerprint",
    "3": "pin",
    "4": "card",
    "5": "fingerprint",
    "6": "fingerprint",
    "7": "fingerprint",
    "8": "fingerprint",
    "9": "face",
    "15": "face",
    "200": "other",
}

TEMPLATE_FIELDS = {"TMP", "BIODATA", "Photo", "MinutiaeV10", "FACE"}


def parse_attlog(body: str) -> list[RawPunch]:
    punches: list[RawPunch] = []
    for line in body.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        pin = parts[0].strip()
        try:
            ts = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        status = parts[2].strip() if len(parts) > 2 else "0"
        verify = parts[3].strip() if len(parts) > 3 else "0"
        workcode = parts[4].strip() if len(parts) > 4 else ""

        verify_mode = VERIFY_MAP.get(verify, "other")
        io_state = None
        if status in ("0", "3", "4"):
            io_state = "in"
        elif status in ("1", "5"):
            io_state = "out"

        punches.append(
            RawPunch(
                device_pin=pin,
                device_local_time=ts,
                verify_mode=verify_mode,
                io_state=io_state,
                work_code=workcode or None,
                raw={"line": line},
            )
        )
    return punches


def parse_operlog(body: str) -> ParsedUpload:
    users: list[DevicePerson] = []
    enrolment_counts: dict[str, dict[str, int]] = {}

    for line in body.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("USER "):
            user = _parse_user_line(line)
            if user:
                users.append(user)
        elif line.startswith("FP "):
            _parse_fp_line(line, enrolment_counts)

    return ParsedUpload(users=users, enrolment_counts=enrolment_counts)


def _parse_user_line(line: str) -> DevicePerson | None:
    content = line.removeprefix("USER ").strip()
    fields: dict[str, str] = {}
    for pair in content.split("\t"):
        if "=" in pair:
            key, _, value = pair.partition("=")
            fields[key.strip()] = value.strip()
    pin = fields.get("PIN", "")
    if not pin:
        return None
    return DevicePerson(
        pin=pin,
        name=fields.get("Name", ""),
        card_no=fields.get("Card") or None,
        group=int(fields.get("Grp", "1")),
        privilege=int(fields.get("Pri", "0")),
    )


def _parse_fp_line(line: str, counts: dict[str, dict[str, int]]) -> None:
    content = line.removeprefix("FP ").strip()
    fields: dict[str, str] = {}
    for pair in content.split("\t"):
        if "=" in pair:
            key, _, value = pair.partition("=")
            fields[key.strip()] = value.strip()
    pin = fields.get("PIN", "")
    if not pin:
        return
    if pin not in counts:
        counts[pin] = {"fingerprints": 0, "face": 0}
    fid = fields.get("FID", "")
    if fid:
        counts[pin]["fingerprints"] = counts[pin].get("fingerprints", 0) + 1


def strip_templates(body: str) -> str:
    lines = []
    for line in body.splitlines():
        stripped = line
        for field in TEMPLATE_FIELDS:
            stripped = re.sub(rf"\t{field}=[^\t]*", f"\t{field}=", stripped)
        lines.append(stripped)
    return "\n".join(lines)


def parse_command_results(body: str) -> list[CommandResult]:
    results: list[CommandResult] = []
    for line in body.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        fields: dict[str, str] = {}
        for pair in line.split("&"):
            if "=" in pair:
                key, _, value = pair.partition("=")
                fields[key.strip()] = value.strip()
        cmd_no_str = fields.get("ID", "")
        return_code_str = fields.get("Return", "")
        try:
            cmd_no = int(cmd_no_str) if cmd_no_str else None
            return_code = int(return_code_str) if return_code_str else -1
        except ValueError:
            continue
        results.append(
            CommandResult(
                cmd_no=cmd_no,
                success=return_code == 0,
                return_code=return_code,
                message=fields.get("CMD", ""),
            )
        )
    return results


def render_handshake(
    serial: str,
    attlog_stamp: str = "None",
    operlog_stamp: str = "9999",
    delay: int = 10,
    realtime: int = 1,
    timezone_offset: int = 330,
) -> str:
    return (
        f"GET OPTION FROM: {serial}\n"
        f"ATTLOGStamp={attlog_stamp}\n"
        f"OPERLOGStamp={operlog_stamp}\n"
        f"ATTPHOTOStamp=None\n"
        f"ErrorDelay=30\n"
        f"Delay={delay}\n"
        f"TransTimes=00:00;14:05\n"
        f"TransInterval=1\n"
        f"TransFlag=TransData AttLog OpLog EnrollUser ChgUser\n"
        f"TimeZone={timezone_offset}\n"
        f"Realtime={realtime}\n"
        f"Encrypt=None"
    )


def render_commands(commands: list[tuple[int, str]]) -> str:
    lines = [f"C:{cmd_no}:{cmd_text}" for cmd_no, cmd_text in commands]
    return "\n".join(lines)
