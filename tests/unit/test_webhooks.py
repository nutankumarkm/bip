"""Tests for webhook signing and verification."""

import time

import pytest

from bip.api.webhooks import sign_webhook, verify_webhook


@pytest.mark.unit
class TestWebhookSignature:
    def test_sign_and_verify(self):
        body = '{"type": "punch.created", "data": {}}'
        secret = "test-secret-key"
        ts = int(time.time())
        header = sign_webhook(body, secret, timestamp=ts)
        assert verify_webhook(header, body, secret)

    def test_wrong_secret_fails(self):
        body = '{"type": "punch.created"}'
        header = sign_webhook(body, "correct-secret")
        assert not verify_webhook(header, body, "wrong-secret")

    def test_tampered_body_fails(self):
        body = '{"type": "punch.created"}'
        secret = "test-secret"
        header = sign_webhook(body, secret)
        assert not verify_webhook(header, '{"type": "punch.TAMPERED"}', secret)

    def test_expired_timestamp_fails(self):
        body = '{"type": "punch.created"}'
        secret = "test-secret"
        old_ts = int(time.time()) - 600
        header = sign_webhook(body, secret, timestamp=old_ts)
        assert not verify_webhook(header, body, secret, tolerance_seconds=300)

    def test_header_format(self):
        body = "test"
        secret = "key"
        ts = 1234567890
        header = sign_webhook(body, secret, timestamp=ts)
        assert header.startswith("t=1234567890,v1=")


@pytest.mark.unit
class TestWebhookDelivery:
    def setup_method(self):
        from bip.api.delivery import clear_delivery_logs
        from bip.api.routes.v1 import reset_stores

        reset_stores()
        clear_delivery_logs()

    @pytest.mark.asyncio
    async def test_dispatch_webhook_and_log(self):
        import respx

        with respx.mock:
            route = respx.post("https://software.example.com/api/punches").respond(200, json={"ok": True})
            webhook = {
                "id": "wh_100",
                "org_id": "org_1",
                "name": "LearnX SIS",
                "url": "https://software.example.com/api/punches",
            }
            from bip.api.delivery import dispatch_webhook, get_delivery_logs

            res = await dispatch_webhook(webhook, "whsec_test123", "punch.created", {"device_pin": "5001"})
            assert res["success"] is True
            assert res["status_code"] == 200
            assert route.called
            logs = get_delivery_logs()
            assert len(logs) == 1
            assert logs[0]["webhook_name"] == "LearnX SIS"

    def test_add_test_punch_triggers_webhook_dispatch(self):
        import respx
        from datetime import UTC, datetime

        from bip.api.delivery import get_delivery_logs
        from bip.api.routes.v1 import _webhook_secrets, _webhooks, add_test_punch

        with respx.mock:
            respx.post("https://software.example.com/api/punches").respond(200, json={"ok": True})
            _webhooks["wh_100"] = {
                "id": "wh_100",
                "org_id": "org_1",
                "name": "LearnX SIS",
                "url": "https://software.example.com/api/punches",
                "active": True,
            }
            _webhook_secrets["wh_100"] = "whsec_test123"

            seq = add_test_punch("org_1", "site_1", "dev_1", "1001", datetime.now(UTC))
            assert seq == 1
            logs = get_delivery_logs()
            assert len(logs) == 1
            assert logs[0]["punch_pin"] == "1001"

