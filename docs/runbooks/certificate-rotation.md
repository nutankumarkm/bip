# Runbook: Secrets & Certificate Rotation

**Scope:** Ed25519 Gateway Keypairs, Consumer Webhook HMAC Secrets, Ops Console TOTP Secrets, Database Credentials  

---

## 1. Secrets Overview & Rotation Cadence

| Credential Type | Usage | Rotation Cadence | Downtime |
| :--- | :--- | :--- | :--- |
| **Gateway Ed25519 Keypair** | Edge Gateway request authentication | Every 180 days or on compromise | Zero downtime (grace overlap) |
| **Webhook HMAC Secrets** | Consumer webhook payload verification | Every 365 days | Zero downtime (dual-sign mode) |
| **Ops Console TOTP Secrets** | Admin 2-factor authentication | Per user as needed | None |
| **Database Master Credentials** | AWS RDS Aurora PostgreSQL | Every 90 days (via AWS Secrets Manager) | Zero downtime |

---

## 2. Gateway Ed25519 Keypair Rotation

BIP supports dual-key transition to allow edge gateways to rotate cryptographic keys without dropping offline uploads.

### Step 1: Request Key Rotation in Ops Console
1. Navigate to `/ops/gateways` -> Select target Gateway.
2. Click **Initiate Key Rotation**.
3. Two-person approval is triggered: a second administrator reviews and approves at `/ops/approvals`.

### Step 2: Push New Public Key via Command Queue
BIP queues a `rotate_key` command to the gateway:
```json
{
  "command": "rotate_key",
  "new_public_key": "base64_encoded_ed25519_pubkey",
  "grace_period_sec": 86400
}
```

### Step 3: Gateway Key Swap
1. The gateway generates a new Ed25519 keypair.
2. It sends a confirmation heartbeat signed with BOTH old and new keys.
3. BIP activates the new public key and archives the previous key.

---

## 3. Webhook HMAC Secret Rollover

When a consumer (e.g., LearnX or Saptta) needs to rotate their webhook signing secret:

1. **Consumer Requests Secret Update:**
   ```bash
   POST /v1/orgs/{org_id}/webhooks/{webhook_id}/rotate-secret
   Authorization: Bearer <CONSUMER_JWT>
   ```
2. **Response contains new secret:**
   ```json
   {
     "webhook_id": "wh_12345",
     "new_secret": "whsec_9876543210fedcba",
     "active_secret": "whsec_1234567890abcdef",
     "grace_period_hours": 24
   }
   ```
3. **Dual Signature Delivery:**
   During the 24-hour grace window, BIP generates two signature headers:
   ```
   BIP-Signature: t=1761142800,v1=hash_with_active_secret
   BIP-Signature-Next: t=1761142800,v1=hash_with_new_secret
   ```
4. Once the consumer updates their receiver application to use the new secret, the old secret is revoked.
