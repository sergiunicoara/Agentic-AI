# Runbook: Incident Response

## Overview

This runbook covers how to respond to infrastructure alerts surfaced by SmartOps — from first notification through ServiceNow ticket resolution.

---

## 1. Alert Fires (vmalert → Alertmanager)

vmalert evaluates rules every 60 seconds against VictoriaMetrics.  
Alert rules live in [`infra/victoria/vmalert-rules.yml`](../../infra/victoria/vmalert-rules.yml).

| Alert | Threshold | Severity |
|---|---|---|
| HighCPUUsage | CPU > 85% for 5m | warning |
| CriticalCPUUsage | CPU > 95% for 2m | critical |
| HighMemoryUsage | memory > 90% for 5m | warning |
| LowDiskSpace | disk > 80% for 10m | warning |
| HighErrorRate | HTTP error rate > 5% | critical |
| HighP99Latency | p99 > 2000ms for 5m | warning |

Alertmanager routes fire to your configured receiver (email/PagerDuty/Slack — configure in `infra/docker/alertmanager.yml`).

---

## 2. SmartOps Dashboard Check

1. Open SmartOps at `http://localhost:3001` (or production URL).
2. Navigate to **Dashboard** — the affected region will show a red pulse dot on its tab.
3. Click the region tab → verify metric cards for CPU / Memory / P99 / RPS.
4. Cross-reference with Grafana Golden Signals dashboard at `:3002` (port mapped from container).

---

## 3. Trigger AI Root-Cause Analysis

1. Navigate to **AI Insights**.
2. Click **Run AI Scan** — SmartOps runs z-score detection across all regions and metrics.
3. If an anomaly is detected, it appears in the Live Anomalies section with z-score.
4. Click **Trigger RCA** on the anomaly — the alert-to-ticket workflow starts.
5. SmartOps correlates ES error logs + distributed trace spans with the anomaly window.
6. A modal appears with the AI-generated RCA summary, confidence score, correlated evidence, and suggested actions.

---

## 4. Human Approval

Review the RCA modal:

- **Confidence ≥ 80%** → ServiceNow urgency 1 (high). Approve immediately for production incidents.
- **Confidence 60–80%** → urgency 2 (medium). Review correlated logs before approving.
- **Confidence < 60%** → urgency 3 (low). Investigate manually; the AI found limited evidence.

Click **Approve & Create Ticket** to create the ServiceNow incident, or **Reject** to close without a ticket.

---

## 5. ServiceNow Ticket

After approval, SmartOps creates an incident in ServiceNow with:
- `short_description`: first sentence of the RCA summary (≤ 100 chars)
- `description`: full RCA + correlated evidence + suggested actions
- `urgency`: derived from AI confidence
- `cmdb_ci`: `{region}-{metric}` (e.g. `eu-west-smartops_cpu_usage_percent`)

Track the ticket ID in the SmartOps Incident History table.

---

## 6. Remediation

Follow the AI-suggested actions in the RCA. Common actions:

| Symptom | Likely Cause | Action |
|---|---|---|
| CPU > 85% sustained | GC pressure / infinite loop | `kubectl top pods`, check JVM/Node flags, rolling restart |
| Memory > 90% | Memory leak / heap fragmentation | Increase pod memory limit, trigger heap dump |
| P99 > 2s | DB slow queries / cold cache | `EXPLAIN ANALYZE` on recent queries, check connection pool |
| Error rate > 5% | Downstream dependency failure | Check dependency health, enable circuit breaker |

---

## 7. Post-Incident

1. Resolve the ServiceNow ticket with resolution notes.
2. Update `infra/victoria/vmalert-rules.yml` if thresholds need tuning.
3. Add a row to `docs/runbooks/post-incident-log.md` with: date, region, root cause, MTTR, ticket ID.

---

## Escalation

| Severity | Response Time | Escalate To |
|---|---|---|
| critical | 15 min | On-call engineer + engineering manager |
| warning | 1 hour | On-call engineer |
| info | Next business day | Team channel |
