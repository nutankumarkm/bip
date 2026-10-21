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
