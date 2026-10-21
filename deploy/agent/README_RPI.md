# BIP Gateway Deployment on Raspberry Pi

This document outlines deployment of the BIP Gateway Agent on a Raspberry Pi (Pi 3B+, 4, 5, or Zero 2W) running Raspberry Pi OS (Debian bookworm 64-bit recommended).

## 1. Prerequisites
- Raspberry Pi OS Lite (64-bit)
- Network connectivity (static Ethernet IP or reserved DHCP recommended)
- Python 3.12+ (or pre-compiled ARM64 standalone binary)

## 2. Installation Steps

1. Create service user and directories:
   ```bash
   sudo useradd -r -s /bin/false bip-gateway
   sudo mkdir -p /etc/bip-gateway /var/lib/bip-gateway
   sudo chown -R bip-gateway:bip-gateway /var/lib/bip-gateway
   sudo chmod 700 /var/lib/bip-gateway
   ```

2. Install gateway agent:
   ```bash
   # From source / venv:
   sudo python3 -m venv /opt/bip-gateway-venv
   sudo /opt/bip-gateway-venv/bin/pip install --upgrade pip
   sudo /opt/bip-gateway-venv/bin/pip install bip
   sudo ln -sf /opt/bip-gateway-venv/bin/bip-gateway /usr/local/bin/bip-gateway
   ```

3. Pair with BIP Cloud:
   ```bash
   sudo bip-gateway pair --server https://bip.example.com --code <8-digit-code> --config-dir /etc/bip-gateway
   sudo chown -R bip-gateway:bip-gateway /etc/bip-gateway
   sudo chmod 600 /etc/bip-gateway/gateway_ed25519.key
   ```

4. Install and enable systemd service:
   ```bash
   sudo cp deploy/agent/bip-gateway.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now bip-gateway
   ```

5. Verify service status and logs:
   ```bash
   sudo systemctl status bip-gateway
   sudo journalctl -u bip-gateway -f
   ```

## 3. Local Feed Access
LearnX running on the local subnet or same host can access punches at:
`http://127.0.0.1:47800/v1/punches?cursor=`
with token from `/var/lib/bip-gateway/local_token.txt`.
