# Tenancy isolation model

This platform is multi-tenant by construction: every online request is scoped by `workspace_id`.

## Enforcement layers

1) **Authn/Authz**: API requires `X-Workspace-Id` + `X-API-Key` (`app/auth.py`).
2) **Query scoping**: retrieval SQL joins/filter on `workspace_id`.
3) **Denormalized chunk tenancy**: `document_chunk.workspace_id` is populated at ingestion to avoid relying on joins.

## Optional: Postgres Row Level Security (RLS)

For hardened deployments, enable RLS policies that reference `current_setting('app.workspace_id')` and set that in each request/session.
