# Runbook: Gateway Agent Troubleshooting

**Component:** `bip.gateway` Edge Agent  
**Host Environments:** Windows Service (WinSW), Linux (systemd), Raspberry Pi  

---

## 1. Quick Diagnostics Checklist

| Symptom | Probable Cause | Action |
| :--- | :--- | :--- |
| **Gateway status is `offline` in Ops Console** | Network unreachable, host down, or auth failure | Check host internet connection, check `bip-gateway` service logs |
| **Punches not syncing to cloud** | Backlog in local SQLite outbox or auth token expired | Inspect outbox table size; verify Gateway key pair |
| **"Signature rejected" or 401 error** | Ed25519 key mismatch or clock skew > 300 seconds | Synchronize NTP clock; re-pair gateway if key is corrupted |
| **Local Feed on localhost:47800 unreachable** | Service stopped or port conflict | Verify `bip-gateway` is running; check `netstat -ano \| findstr 47800` |

---

## 2. Common Remediation Workflows

### Workflow 1: Resolving Clock Skew Rejection
**Error in logs:** `401 Unauthorized - clock_skew_exceeded: Request timestamp drift exceeds 300s`

1. **Linux / Raspberry Pi:**
   ```bash
   sudo timedatectl set-ntp true
   sudo systemctl restart systemd-timesyncd
   timedatectl status
   ```
2. **Windows:**
   ```powershell
   w32tm /resync /force
   Get-Date
   ```
3. Restart gateway service:
   ```bash
   sudo systemctl restart bip-gateway   # Linux
   # OR
   net stop bip-gateway && net start bip-gateway # Windows
   ```

---

### Workflow 2: Inspecting and Compacting SQLite Outbox
1. **Locate SQLite Outbox:**
   - Default location: `/var/lib/bip-gateway/outbox.db` (Linux) or `C:\ProgramData\bip-gateway\outbox.db` (Windows).
2. **Check Pending Uploads:**
   ```bash
   sqlite3 outbox.db "SELECT count(*), status FROM outbox GROUP BY status;"
   ```
3. **Trigger Manual Immediate Flush:**
   ```bash
   bip-gateway flush-outbox --config /etc/bip-gateway.yaml
   ```
4. **WAL Compaction:**
   ```bash
   sqlite3 outbox.db "PRAGMA wal_checkpoint(TRUNCATE); VACUUM;"
   ```

---

### Workflow 3: Re-Pairing an Inactive Gateway
If a gateway was revoked or its private key was lost:
1. Log in to Ops Console -> `/ops/gateways`.
2. Generate an 8-digit Pairing Code (valid for 15 minutes).
3. On the local gateway terminal:
   ```bash
   bip-gateway pair \
     --edge-url https://edge.bip.example.com \
     --pairing-code 84729103 \
     --config /etc/bip-gateway.yaml
   ```
4. Confirm gateway displays as `active` in the Ops Console.
