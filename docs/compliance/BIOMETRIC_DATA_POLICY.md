# Biometric Data Governance & Security Policy Draft

**Document ID:** BIP-POL-BIO-001  
**Version:** 1.0  
**Effective Date:** 2026-10-21  
**Classification:** Public / Customer-Facing  

---

## 1. Purpose & Scope

This policy outlines the principles, technical safeguards, and operational rules governing the collection, transmission, processing, and retention of biometric-adjacent identifiers across the Biometric Integration Platform (BIP). This policy applies to all organizations, educational institutions, partner software integrations (e.g. LearnX, Saptta), and internal engineering teams.

---

## 2. Core Principles

### Principle 1: Edge-Only Matching (No Centralized Biometric Repository)
BIP does NOT maintain a centralized cloud repository of biometric templates (fingerprint ridge minutiae, facial geometries, iris scans). 
- Biometric verification occurs strictly at the edge sensor hardware level.
- Raw biometric characteristics are converted on the local terminal into mathematical representations that cannot be reverse-engineered into the original biometric image.

### Principle 2: Template Stripping Guarantee
In the event that an automated terminal firmware transmits proprietary backup payloads or template tables during device synchronization:
- The BIP Device Edge proxy strips, drops, and destroys template records in memory before persistence.
- Zero raw biometric records enter the persistent database layer or object storage.

### Principle 3: Data Minimization & Pseudonymization
The only information stored in BIP for attendance and access records is:
1. Assigned badge/PIN or employee number (`external_ref`).
2. Timestamp of verification (`punch_time`).
3. Hardware terminal identifier (`device_id`).
4. Directionality (`in_out` state).

Individual real-world names are masked in audit traces and logging pipelines.

---

## 3. Data Retention & Automatic Purge Schedule

1. **Active Punch Records:** Retained for the duration configured by the tenant organization (default: 730 days / 24 months).
2. **Automated Purging:** An automated background retention engine (`bip.workers.retention`) runs daily to permanently remove punches whose timestamp falls outside the organization's retention window.
3. **Hardware De-provisioning:** When a person is marked inactive or deleted via the Consumer API (`DELETE /v1/orgs/{org_id}/people/{external_ref}`), deletion commands (`delete_user`) are queued and pushed to all assigned physical biometric terminals across all sites.

---

## 4. Cryptographic Controls & Access Security

- **In-Transit Protection:** Mandatory TLS 1.3 encryption on all public endpoints.
- **Edge Gateway Authentication:** Hardware gateways authenticate using elliptic curve digital signatures (Ed25519) with per-request timestamp freshness validation.
- **Multi-Tenant Row-Level Security (RLS):** All database queries are isolated by tenant identifier (`org_id`). Tenants cannot inspect, query, or leak records across organizational boundaries.
- **Two-Person Ops Console Rule:** High-impact administrative actions (such as gateway revocation or global parameter overrides) require a two-person approval process to eliminate single-operator insider threats.

---

## 5. Security Incident & Breach Notification

In the event of a suspected or confirmed unauthorized access to BIP infrastructure:
1. Affected partner organizations will be notified within **72 hours** in accordance with GDPR Article 33 and DPDP Act provisions.
2. Forensic audit logs will be extracted using the cryptographically verified SHA-256 audit chain.
3. Because BIP does not store raw biometric templates or images, no biometric reconstruction risk exists for enrolled personnel.
