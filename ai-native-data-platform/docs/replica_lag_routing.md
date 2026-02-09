# Replica lag handling and read/write routing

The platform now supports **read/write routing**:

* Writes -> `PRIMARY_DATABASE_URL` (or `DATABASE_URL`)
* Reads -> healthiest replica under `MAX_REPLICA_LAG_SECONDS` (fallback to primary)

## How lag is estimated

We query:

```sql
SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
```

This is a simple replay timestamp lag proxy.

## Configuration

Environment variables:

* `PRIMARY_DATABASE_URL`
* `REPLICA_DATABASE_URLS` (comma-separated)
* `REPLICA_REGIONS` (optional region mapping)
* `MAX_REPLICA_LAG_SECONDS`
