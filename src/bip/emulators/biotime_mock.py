"""ZKBioTime server mock emulator (ADR-002, section 8.4)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query


def create_biotime_mock_app() -> FastAPI:
    """Create a FastAPI in-memory mock server for ZKBioTime API."""
    app = FastAPI(title="ZKBioTime Mock Server", docs_url=None, redoc_url=None)

    transactions: list[dict[str, Any]] = []
    employees: dict[str, dict[str, Any]] = {}

    @app.post("/mock/add_transaction")
    async def add_mock_transaction(tx: dict[str, Any]) -> dict[str, str]:
        transactions.append(tx)
        return {"status": "ok"}

    @app.post("/api-token-auth/")
    async def token_auth(body: dict[str, Any]) -> dict[str, str]:
        username = body.get("username")
        password = body.get("password")
        if username == "admin" and password == "secret":
            return {"token": "biotime-mock-valid-token"}
        raise HTTPException(status_code=400, detail="Unable to log in with provided credentials.")

    def verify_token(authorization: str = Header(None)) -> bool:
        if not authorization or not authorization.startswith("Token "):
            raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")
        return True

    @app.get("/iclock/api/transactions/")
    async def get_transactions(
        page: int = Query(default=1),
        page_size: int = Query(default=100),
        start_time: str | None = None,
        end_time: str | None = None,
        _: bool = Query(default=True),
    ) -> dict[str, Any]:
        matched = []
        for tx in transactions:
            pt = tx.get("punch_time", "")
            if start_time and pt and pt < start_time:
                continue
            if end_time and pt and pt > end_time:
                continue
            matched.append(tx)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged = matched[start_idx:end_idx]

        return {
            "count": len(matched),
            "next": None if end_idx >= len(matched) else f"/iclock/api/transactions/?page={page + 1}",
            "previous": None if page <= 1 else f"/iclock/api/transactions/?page={page - 1}",
            "data": paged,
        }

    @app.get("/personnel/api/employees/")
    async def get_employees(
        page: int = Query(default=1),
        page_size: int = Query(default=100),
    ) -> dict[str, Any]:
        emp_list = list(employees.values())
        return {
            "count": len(emp_list),
            "next": None,
            "previous": None,
            "data": emp_list,
        }

    @app.post("/personnel/api/employees/")
    async def create_employee(body: dict[str, Any]) -> dict[str, Any]:
        emp_code = body.get("emp_code")
        if not emp_code:
            raise HTTPException(status_code=400, detail="emp_code is required")
        employees[str(emp_code)] = body
        return body

    @app.delete("/personnel/api/employees/{emp_code}/")
    async def delete_employee(emp_code: str) -> dict[str, str]:
        employees.pop(str(emp_code), None)
        return {"status": "deleted"}

    return app
