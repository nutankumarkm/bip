# BIP Data Map & Processing Inventory

This document details the categories of personal and biometric data processed by the Biometric Integration Platform (BIP), the processing purposes, legal grounds under GDPR (EU 2016/679) and India Digital Personal Data Protection (DPDP) Act 2023, data flow pathways, retention controls, and technical safeguards.

---

## 1. Data Classification Inventory

| Data Element | Category | Sensitivity | Source | Primary Purpose | Storage Location | Retention Limit |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Card / Badge Number** | Identification | Medium | Terminal Scan | Door access & punch reconciliation | PostgreSQL (`people.card_no`), Edge cache | Org-configured (default 730d) |
| **PIN / Employee ID** | Pseudonymous ID | Low | Terminal Keypad | Primary linkage identifier for consumer systems | PostgreSQL (`people.external_ref`), Outbox | Indefinite until person deletion |
| **Display Name** | Personally Identifiable (PII) | Medium | Consumer HR / SIS | Ops troubleshooting, terminal provisioning | Redacted in logs; PostgreSQL (`people.display_name`) | Overwritten on update / purge on delete |
| **Raw Punch Timestamp** | Attendance Record | Low | Terminal RTC | Raw attendance timeline logging | Partitioned table (`punch_events.punch_time`) | Org-configured (default 730d) |
| **Device Terminal IP / SN** | Metadata | Low | Network Packet | Hardware diagnostics, whitelisting, pairing | Edge store, Gateway SQLite outbox | Replaced on new connection |
| **Raw Biometric Template (Minutiae)** | Special Category (Art. 9) | **Critical** | Terminal Sensor | Local hardware matching ONLY | **NEVER STORED IN BIP** (Stripped at Edge) | Immediate memory discard (0s) |

---

## 2. Special Category Biometric Data Guarantees

Under GDPR Article 9(1) and DPDP Act 2023 Section 3, biometric data processed for uniquely identifying a natural person carries heightened compliance obligations. BIP implements architectural safeguards:

### Zero-Biometric Cloud Storage Architecture
1. **Device-Level Matching:** All biometric recognition (fingerprint minutiae, facial feature vectors) occurs exclusively inside the biometric hardware on-premise.
2. **Template Stripping Pipeline:** When proprietary terminals attempt to transmit template backup streams (e.g., ADMS `TMP`, `FACE`, or `FP_TEMPLATE` tables), the BIP Device Edge parser intercepts and permanently strips the payload before writing to the raw inbox.
3. **Log Redaction:** The structlog logging processor (`src/bip/core/logging.py`) sanitizes all candidate biometric fields (`template`, `tmp`, `fingerprint`, `face_template`, `biometric_data`) replacing them with `***REDACTED***`.

---

## 3. Data Processing Pathways

```
[ Biometric Device (On-Premises) ]
               |
      (Raw Punch Event)
               v
   [ BIP Gateway / Edge API ] --------> [ Edge Template Stripper ]
               |                                       |
    (Scrubbed Metadata Only)                   (Discard Minutiae)
               v
   [ Raw Ingest Inbox (S3 / DB) ]
               v
      [ Normalization Worker ]
               v
 [ Tenant-Partitioned PostgreSQL ] <--- Row-Level Security (RLS) Enforced
               v
 [ Consumer Webhook / REST API ]
  (LearnX SIS / Saptta HR System)
```

---

## 4. Legal Grounds for Processing (GDPR Art. 6 & 9)

- **Legitimate Interest (Art. 6(1)(f)):** Tracking facility access and work attendance verification on behalf of authorized educational institutions and corporate employers.
- **Employment & Social Security Obligations (Art. 9(2)(b)):** Processing of access timestamps necessary for fulfilling employment attendance records.
- **Data Minimization (Art. 5(1)(c)):** BIP restricts data ingestion strictly to `(pin, timestamp, device_id, in_out)`.

---

## 5. Security & Cryptographic Safeguards

- **Transport Encryption:** TLS 1.3 mandated across all external Edge ingestion endpoints and internal microservices.
- **Gateway Signatures:** Ed25519 digital signatures (ADR-009) on every Gateway request with SHA-256 payload digests and clock-skew rejection (< 300s).
- **Tenant Isolation:** Postgres Row-Level Security (`FORCE ROW LEVEL SECURITY`) with `app.current_org_id` session context prevents cross-tenant data access.
- **Audit Logging:** Ops console actions are recorded in an append-only cryptographic hash chain (`src/bip/core/audit.py`) with SHA-256 forward links.
- **Retention Purging:** Automated retention worker (`src/bip/workers/retention.py`) permanently purges historical punch records past the organization's declared retention window.
