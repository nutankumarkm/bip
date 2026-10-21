# Runbook: PostgreSQL Database Maintenance

**Database:** PostgreSQL 16+ / AWS Aurora PostgreSQL  
**Key Features:** Table Partitioning, Row-Level Security (RLS), Retention Management  

---

## 1. Routine Maintenance Schedule

| Frequency | Task | Description |
| :--- | :--- | :--- |
| **Daily (Automated)** | Retention Purge | Run `bip.workers.retention` to delete records past org retention window |
| **Monthly (25th of month)** | Partition Maintenance | Pre-create upcoming monthly partitions (`bip_punch_events_YYYY_MM`) |
| **Weekly** | Vacuum & Analyze | Run `VACUUM ANALYZE` on heavily updated tables (`people`, `devices`, `commands`) |
| **Quarterly** | Index Bloat Check | Inspect B-Tree index bloat and rebuild if bloat exceeds 30% |

---

## 2. Partition Maintenance

### Creating Future Monthly Partitions
The `punch_events` table is partitioned by range on `punch_time`. At least 3 months of future partitions must always exist to prevent inserts into the default partition.

```sql
-- Create partition for December 2026
CREATE TABLE IF NOT EXISTS punch_events_2026_12 PARTITION OF punch_events
    FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

-- Create partition for January 2027
CREATE TABLE IF NOT EXISTS punch_events_2027_01 PARTITION OF punch_events
    FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2027-02-01 00:00:00+00');
```

Automated partition maintenance function:
```sql
SELECT maintain_punch_partitions();
```

### Detaching and Dropping Expired Partitions
Instead of slow row-level `DELETE` statements on large tables, historical partitions older than the maximum retention period can be dropped instantly with zero lock contention:

```sql
-- Step 1: Detach partition from parent table
ALTER TABLE punch_events DETACH PARTITION punch_events_2024_01 CONCURRENTLY;

-- Step 2: Drop detached table
DROP TABLE punch_events_2024_01;
```

---

## 3. Row-Level Security (RLS) Verification

To verify that multi-tenant isolation is active and strictly enforced on all tables:

```sql
-- Check RLS status across all public tables
SELECT 
    schemaname, 
    tablename, 
    rowsecurity, 
    forcerowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
  AND tablename IN ('orgs', 'sites', 'devices', 'people', 'punch_events', 'commands');

-- Test tenant context isolation
SET LOCAL app.current_org_id = 'org_alpha';
SELECT count(*) FROM punch_events; -- Returns ONLY org_alpha punches

SET LOCAL app.current_org_id = 'org_beta';
SELECT count(*) FROM punch_events; -- Returns ONLY org_beta punches
```
