# ADR-003: VictoriaMetrics as the Metrics Store

**Status**: Accepted  
**Date**: 2026-07

## Context

The platform needs a time-series metrics store for infrastructure metrics (CPU, memory, latency, error rate). The JD specifically calls out VictoriaMetrics experience. The options were VictoriaMetrics, Prometheus + remote storage, or InfluxDB.

## Decision

VictoriaMetrics (single-node `v1.99.0`) as the primary metrics store, with vmalert for alert evaluation.

## Rationale

- **Prometheus-compatible API** — existing PromQL dashboards, vmalert rules, and OTel Collector's `prometheusremotewrite` exporter all work without change.
- **Lower resource footprint** — VictoriaMetrics typically uses 7–10× less RAM than Prometheus for equivalent cardinality. Relevant when co-locating with Elasticsearch on dev hardware.
- **Remote write target** — the OTel Collector writes directly to VM's `/api/v1/import/prometheus` endpoint. The simulator also pushes metrics via this endpoint, keeping ingestion code simple (plain HTTP, no SDK).
- **Built-in downsampling** — VictoriaMetrics supports retention with automatic downsampling via `-retentionPeriod`. Useful for the 90-day log + metrics retention window implied by the JD.
- **vmalert** — evaluates alert rules natively against VM, pushing to Alertmanager. Rules live in `infra/victoria/vmalert-rules.yml` and are version-controlled alongside the rest of the infra config.

## Trade-offs

- **Single-node** — production at scale requires VictoriaMetrics Cluster. The single-node version has no horizontal write scaling. Migrating later is a deployment change, not a code change.
- **No native Grafana datasource** — uses the Prometheus compatibility shim (works perfectly but loses some VM-specific features like `WITH` templates in Grafana).

## Alternatives Considered

- **Prometheus** — the reference implementation, but higher RAM usage and requires separate long-term storage (Thanos/Cortex) at scale.
- **InfluxDB** — different query language (Flux/InfluxQL), separate ecosystem. OTel Collector support is available but less mature than the Prometheus path.
