# Runbook: Disaster Recovery & Service Restoration

**Service:** Biometric Integration Platform (BIP)  
**Target RPO (Recovery Point Objective):** < 15 minutes  
**Target RTO (Recovery Time Objective):** < 60 minutes  

---

## 1. Architecture Resilience Overview

BIP is designed with an append-only, decoupled architecture that provides natural resilience against catastrophic outages:
1. **Edge Gateways / Terminals Buffering:** Edge Gateways store all unacknowledged punches in a persistent SQLite WAL outbox (`gateway.db`). Gateways can buffer 14+ days of offline punches (100,000+ records) and auto-sync with exponential backoff once upstream connectivity resumes.
2. **Raw Inbox Replay:** All raw uploads are saved in an append-only raw uploads table / S3 bucket prior to normalization. In the event of a downstream worker crash or database failure, raw uploads can be replayed in sequence.
3. **Partitioned Storage:** Historical data is stored in monthly partitioned tables, preventing single-table corruption from affecting active ingestion.

---

## 2. Disaster Scenarios & Recovery Procedures

### Scenario A: Complete Cloud Region Outage (AWS)
1. **Trigger:** Primary AWS region (`ap-south-1`) becomes unresponsive.
2. **Failover Execution:**
   - Deploy Terraform skeleton to standby region (`ap-southeast-1`):
     ```bash
     cd deploy/terraform
     terraform apply -var="aws_region=ap-southeast-1" -var="environment=prod"
     ```
   - Restore Aurora PostgreSQL database from the latest cross-region automated snapshot.
   - Update Route 53 DNS records for `api.bip.example.com` and `edge.bip.example.com` to point to the new Application Load Balancer.
3. **Post-Failover Verification:**
   - Verify health endpoints:
     ```bash
     curl -f https://api.bip.example.com/health
     curl -f https://edge.bip.example.com/health
     ```
   - Ensure Gateways reconnect and drain their local SQLite outboxes.

---

### Scenario B: Database Table Corruption or Erroneous Data Deletion
1. **Recovery from Raw Inbox:**
   If a partition or table suffers data corruption, raw punches can be reprocessed directly from the raw inbox:
   ```bash
   python -m bip.workers.replay_inbox --from-timestamp="2026-10-21T00:00:00Z" --to-timestamp="2026-10-21T12:00:00Z"
   ```
2. **Deduplication Safeguard:**
   Every punch computes a deterministic SHA-256 `dedupe_key`:
   ```
   SHA256(org_id + ":" + device_id + ":" + pin + ":" + timestamp_iso)
   ```
   Replaying raw uploads will NEVER create duplicate punch events in consumer feeds.

---

### Scenario C: Redis Cache Failure
1. **Impact:** Temporary degradation in distributed rate limiting; token bucket falls back to local node memory.
2. **Resolution:**
   - Restart Redis cluster or recreate ElastiCache node.
   - Core API and Edge ingestion operate normally without persistent Redis dependency.
