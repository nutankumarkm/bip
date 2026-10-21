# Biometric Integration Platform (BIP) Developer Integration Guide

**Audience:** Engineering teams at LearnX (SIS / Education ERP) and Saptta (HRMS / Payroll).  
**Base URL:** `https://api.bip.example.com` (Production) / `http://localhost:8000` (Local Sandbox)  

---

## 1. Overview

BIP is the unified biometric middleware connecting your cloud application (LearnX / Saptta) to heterogeneous biometric attendance hardware fleets (ZKTeco ADMS, Hikvision ISAPI, Matrix COSEC, SQL databases, CSV/Excel imports).

### Core Capabilities
- **Real-Time Punch Delivery:** Webhooks signed with HMAC-SHA256 or cursor-based incremental polling.
- **Biometric Device Agnosticism:** Single unified API across ZKTeco, Hikvision, and legacy SQL timeclocks.
- **Automated Device Provisioning:** Enrolling or removing a student/employee in BIP automatically fans out commands to all biometric hardware terminals across the user's assigned physical sites.
- **Zero Raw Biometric Cloud Storage:** Template stripping guarantees biometric minutiae are never stored in the cloud.

---

## 2. Authentication (OAuth 2.0 Client Credentials)

BIP uses standard OAuth 2.0 Client Credentials flow. Issued JWT tokens expire in 15 minutes. Cache the token until 60 seconds before expiry.

### Step 1: Request Access Token
```bash
curl -X POST https://api.bip.example.com/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=your_partner_client_id" \
  -d "client_secret=your_partner_client_secret"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orgs:read orgs:write punches:read people:write"
}
```

Include the token in all subsequent API requests:
```
Authorization: Bearer eyJhbGciOi...
```

---

## 3. Provisioning People & Biometric Terminals

When a student enrolls in LearnX or an employee is hired in Saptta, sync them to BIP. BIP automatically allocates a unique PIN from the organization's configured PIN range and pushes `set_user` commands to all terminals at the person's assigned sites.

### Upsert Person
```bash
PUT /v1/orgs/{org_id}/people/{external_ref}
Content-Type: application/json
Authorization: Bearer <TOKEN>

{
  "person_type": "employee",
  "display_name": "Priya Sharma",
  "card_no": "984210",
  "active": true,
  "site_ids": ["site_campus_main", "site_building_b"]
}
```

**Response:**
```json
{
  "id": "p_94a7e...",
  "external_ref": "EMP-1049",
  "pin": "10042",
  "display_name": "Priya Sharma",
  "card_no": "984210",
  "active": true,
  "created_at": "2026-10-21T08:30:00Z"
}
```

### De-provisioning / Offboarding
When an employee resigns or a student graduates, call `DELETE`:
```bash
DELETE /v1/orgs/{org_id}/people/{external_ref}
Authorization: Bearer <TOKEN>
```
BIP immediately queues `delete_user` hardware commands across all biometric terminals at their assigned sites.

---

## 4. Ingesting Attendance Punches

You can receive attendance events via **Webhooks** (recommended for real-time alerts) or **Cursor Polling** (recommended for batch sync and reconciliation).

### Option A: Webhooks (Real-Time Push)

#### 1. Register Webhook Endpoint
```bash
POST /v1/orgs/{org_id}/webhooks
Content-Type: application/json
Authorization: Bearer <TOKEN>

{
  "url": "https://api.learnx.com/webhooks/bip",
  "events": ["punch.created"]
}
```
**Response:**
```json
{
  "id": "wh_01",
  "url": "https://api.learnx.com/webhooks/bip",
  "secret": "whsec_38f29e18b4..."
}
```

#### 2. Verify Webhook Signature (Python Example)
Every incoming webhook carries a signature header:
```
BIP-Signature: t=1761142800,v1=6a82...hex_digest
```

```python
import hmac
import hashlib
import time

def verify_bip_webhook(payload_bytes: bytes, header: str, secret: str) -> bool:
    # Parse header: t=<unix_ts>,v1=<hex_signature>
    parts = dict(item.split("=") for item in header.split(","))
    timestamp = parts.get("t")
    signature = parts.get("v1")
    
    # Replay protection: verify timestamp within 300 seconds
    if abs(time.time() - int(timestamp)) > 300:
        return False
        
    canonical = f"{timestamp}.{payload_bytes.decode('utf-8')}"
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)
```

---

### Option B: Incremental Cursor Polling (Batch Stream)

Query punches in strict chronological arrival sequence without pagination drift:

```bash
GET /v1/orgs/{org_id}/punches?cursor=45000&limit=100
Authorization: Bearer <TOKEN>
```

**Response:**
```json
{
  "items": [
    {
      "id": "punch_uuid_1",
      "seq": 45001,
      "device_id": "dev_001",
      "pin": "10042",
      "punch_time": "2026-10-21T08:58:12+05:30",
      "direction": "in",
      "verify_type": "fingerprint"
    }
  ],
  "next_cursor": 45100,
  "has_more": true
}
```
Store `next_cursor` in your database. On your next poll, pass `?cursor=45100`.

---

## 5. Gateway On-Premise Local Feed (LearnX Local Client)

For campus environments requiring local subnet attendance feeds independent of cloud WAN availability, the BIP Gateway provides an ultra-fast local HTTP feed at `http://127.0.0.1:47800`:

```bash
GET http://127.0.0.1:47800/local/punches?cursor=0
Authorization: Bearer <LOCAL_FEED_TOKEN>
```
Local feeds are served directly from the gateway's SQLite outbox in WAL mode with sub-millisecond response latency.

---

## 6. Rate Limiting & Status Codes

BIP enforces token-bucket rate limits per client credentials:
- **Standard Tier:** 120 requests/minute (burst: 150).
- If limit is exceeded, BIP returns `429 Too Many Requests` with a `Retry-After: <seconds>` header.
- Always implement exponential backoff with jitter on 429 responses.
