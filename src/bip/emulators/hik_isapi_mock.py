"""Hikvision ISAPI mock server emulator (ADR-002, section 8.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException


def create_hik_isapi_mock_app(serial: str = "HIK-ISAPI-998877", model: str = "DS-K1T671MF") -> FastAPI:
    """Create a FastAPI in-memory mock server for Hikvision ISAPI."""
    app = FastAPI(title="Hikvision ISAPI Mock", docs_url=None, redoc_url=None)

    # In-memory mock storage
    events: list[dict[str, Any]] = []
    users: dict[str, dict[str, Any]] = {}
    mock_time = {"time": datetime.now(UTC).isoformat()}

    # Helper method to add events for testing
    @app.post("/mock/add_event")
    async def add_mock_event(event: dict[str, Any]) -> dict[str, str]:
        events.append(event)
        return {"status": "ok"}

    @app.get("/ISAPI/System/deviceInfo")
    async def get_device_info() -> dict[str, Any]:
        return {
          "DeviceInfo": {
            "deviceName": "Access Controller",
            "deviceID": serial,
            "model": model,
            "serialNumber": serial,
            "firmwareVersion": "V3.2.0 build 210816",
          }
        }

    @app.get("/ISAPI/System/time")
    async def get_time() -> dict[str, Any]:
        return {
          "Time": {
            "timeMode": "manual",
            "localTime": mock_time["time"],
            "timeZone": "CST-8:00:00",
          }
        }

    @app.put("/ISAPI/System/time")
    async def set_time(body: dict[str, Any]) -> dict[str, Any]:
        t = body.get("Time", {}).get("localTime")
        if t:
            mock_time["time"] = t
        return {"ResponseStatus": {"statusCode": 1, "statusString": "OK"}}

    @app.post("/ISAPI/AccessControl/AcsEvent")
    async def search_events(body: dict[str, Any]) -> dict[str, Any]:
        cond = body.get("AcsEventCond", {})
        pos = cond.get("searchResultPosition", 0)
        max_res = cond.get("maxResults", 50)
        start_time_str = cond.get("startTime")

        matched = []
        for e in events:
            if start_time_str:
                e_time = e.get("time", "")
                if e_time and e_time < start_time_str:
                    continue
            matched.append(e)

        paged = matched[pos : pos + max_res]
        response_status = "OK" if paged else "NO MATCH"

        return {
          "AcsEvent": {
            "searchID": cond.get("searchID", "1"),
            "responseStatusStrg": response_status,
            "numOfMatches": len(paged),
            "totalMatches": len(matched),
            "InfoList": paged,
          }
        }

    @app.post("/ISAPI/AccessControl/UserInfo/Record")
    @app.put("/ISAPI/AccessControl/UserInfo/Modify")
    async def upsert_user(body: dict[str, Any]) -> dict[str, Any]:
        user_info = body.get("UserInfo", {})
        emp_no = user_info.get("employeeNo")
        if not emp_no:
            raise HTTPException(status_code=400, detail="Missing employeeNo")
        users[str(emp_no)] = user_info
        return {"ResponseStatus": {"statusCode": 1, "statusString": "OK"}}

    @app.post("/ISAPI/AccessControl/UserInfo/Search")
    async def search_users(body: dict[str, Any] | None = None) -> dict[str, Any]:
        user_list = list(users.values())
        return {
          "UserInfoSearch": {
            "responseStatusStrg": "OK",
            "numOfMatches": len(user_list),
            "totalMatches": len(user_list),
            "UserInfo": user_list,
          }
        }

    @app.put("/ISAPI/AccessControl/UserInfo/Delete")
    async def delete_user(body: dict[str, Any]) -> dict[str, Any]:
        detail = body.get("UserInfoDetail", {})
        emp_list = detail.get("EmployeeNoList", [])
        for item in emp_list:
            emp_no = item.get("employeeNo")
            users.pop(str(emp_no), None)
        return {"ResponseStatus": {"statusCode": 1, "statusString": "OK"}}

    return app
