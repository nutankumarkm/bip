"""Tests for Edge ADMS endpoints."""

import pytest
from fastapi.testclient import TestClient

from bip.edge.adms import _store
from bip.edge.app import app


@pytest.fixture(autouse=True)
def reset_store():
    _store.__init__()
    yield


@pytest.mark.unit
class TestEdgeHandshake:
    def test_unknown_serial_returns_handshake(self):
        client = TestClient(app)
        resp = client.get("/iclock/cdata", params={"SN": "UNKNOWN1", "options": "all"})
        assert resp.status_code == 200
        assert "GET OPTION FROM: UNKNOWN1" in resp.text

    def test_unknown_serial_added_to_pending(self):
        client = TestClient(app)
        client.get("/iclock/cdata", params={"SN": "PENDING1", "options": "all"})
        import asyncio

        pending = asyncio.get_event_loop().run_until_complete(_store.get_pending_devices())
        assert any(p["serial"] == "PENDING1" for p in pending)

    def test_registered_device_returns_handshake(self):
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            _store.register_device("KNOWN1", {"id": "dev-1", "status": "active"})
        )
        client = TestClient(app)
        resp = client.get("/iclock/cdata", params={"SN": "KNOWN1", "options": "all"})
        assert resp.status_code == 200
        assert "GET OPTION FROM: KNOWN1" in resp.text


@pytest.mark.unit
class TestEdgeUpload:
    def test_unknown_serial_refused(self):
        client = TestClient(app)
        resp = client.post(
            "/iclock/cdata",
            params={"SN": "UNKNOWN1", "table": "ATTLOG", "Stamp": "2026-10-21"},
            content="10001\t2026-10-21 08:30:00\t0\t1\t\t0\t0",
        )
        assert resp.status_code == 403

    def test_known_device_accepted(self):
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            _store.register_device("KNOWN1", {"id": "dev-1", "status": "active"})
        )
        client = TestClient(app)
        body = "10001\t2026-10-21 08:30:00\t0\t1\t\t0\t0"
        resp = client.post(
            "/iclock/cdata",
            params={"SN": "KNOWN1", "table": "ATTLOG", "Stamp": "2026-10-21"},
            content=body,
        )
        assert resp.status_code == 200
        assert "OK: 1" in resp.text
        assert _store.get_raw_upload_count() == 1

    def test_multi_line_upload(self):
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            _store.register_device("KNOWN2", {"id": "dev-2", "status": "active"})
        )
        client = TestClient(app)
        lines = [f"1000{i}\t2026-10-21 08:{i:02d}:00\t0\t1\t\t0\t0" for i in range(50)]
        body = "\n".join(lines)
        resp = client.post(
            "/iclock/cdata",
            params={"SN": "KNOWN2", "table": "ATTLOG", "Stamp": "2026-10-21"},
            content=body,
        )
        assert resp.status_code == 200
        assert "OK: 50" in resp.text

    def test_templates_stripped(self):
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            _store.register_device("TMPL1", {"id": "dev-3", "status": "active"})
        )
        client = TestClient(app)
        body = "FP PIN=10001\tFID=0\tTMP=base64biometricdata"
        resp = client.post(
            "/iclock/cdata",
            params={"SN": "TMPL1", "table": "OPERLOG", "Stamp": ""},
            content=body,
        )
        assert resp.status_code == 200
        uploads = asyncio.get_event_loop().run_until_complete(_store.get_unprocessed_uploads())
        assert "base64biometricdata" not in uploads[0]["body"]


@pytest.mark.unit
class TestEdgeGetRequest:
    def test_no_commands_returns_ok(self):
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            _store.register_device("NOCMD", {"id": "dev-4", "status": "active"})
        )
        client = TestClient(app)
        resp = client.get("/iclock/getrequest", params={"SN": "NOCMD"})
        assert resp.status_code == 200
        assert resp.text == "OK"


@pytest.mark.unit
class TestEdgeDeviceCmd:
    def test_command_results_parsed(self):
        client = TestClient(app)
        body = "ID=1&Return=0&CMD=DATA UPDATE USERINFO"
        resp = client.post("/iclock/devicecmd", params={"SN": "TEST1"}, content=body)
        assert resp.status_code == 200


@pytest.mark.unit
class TestEdgeMiscEndpoints:
    def test_ping(self):
        client = TestClient(app)
        assert client.get("/iclock/ping").status_code == 200

    def test_registry(self):
        client = TestClient(app)
        assert client.get("/iclock/registry").status_code == 200

    def test_push(self):
        client = TestClient(app)
        assert client.get("/iclock/push").status_code == 200
