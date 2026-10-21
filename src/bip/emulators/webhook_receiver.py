"""Standalone webhook receiver emulator for BIP demos and testing (M9)."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class WebhookHandler(BaseHTTPRequestHandler):
    secret: str = "test-secret"

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        sig_header = self.headers.get("BIP-Signature", "")
        print(f"\n[Webhook Received] Path: {self.path}")
        print(f"Header BIP-Signature: {sig_header}")

        # Signature verification if secret is provided
        if sig_header:
            try:
                parts = dict(p.split("=", 1) for p in sig_header.split(","))
                ts = parts.get("t", "")
                sig = parts.get("v1", "")
                canonical = f"{ts}.{body.decode('utf-8')}"
                expected = hmac.new(
                    self.secret.encode("utf-8"),
                    canonical.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                valid = hmac.compare_digest(expected, sig)
                print(f"Signature Valid: {valid}")
            except Exception as e:
                print(f"Signature check error: {e}")

        try:
            parsed = json.loads(body)
            print(f"Payload: {json.dumps(parsed, indent=2)}")
        except Exception:
            print(f"Raw Body: {body.decode('utf-8', errors='replace')}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"received"}')

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress default server logs


def run(port: int = 9090, secret: str = "test-secret") -> None:
    WebhookHandler.secret = secret
    server_address = ("", port)
    httpd = HTTPServer(server_address, WebhookHandler)
    print(f"[*] BIP Webhook Receiver listening on http://localhost:{port} (Secret: {secret})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Webhook Receiver stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BIP Webhook Receiver Emulator")
    parser.add_argument("--port", type=int, default=9090, help="Listen port")
    parser.add_argument("--secret", type=str, default="test-secret", help="Webhook HMAC secret")
    args = parser.parse_args()
    run(port=args.port, secret=args.secret)
