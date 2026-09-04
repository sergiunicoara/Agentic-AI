# Audit remediation — agent-observability

Source: full-repo audit (2026-09-04). All items verified against source before fixing.

## High
- [x] H1 OIDC authorize URL: urlencode params + validate `code_challenge` format
- [x] H2 Bump `python-jose` 3.3.0 → 3.5.0 (CVE-2024-33663 / CVE-2024-33664)
- [x] H3 Stop trusting raw `X-Forwarded-For` (rate limit + audit log); propagate XFF properly through nginx/Envoy
- [x] H4 Real endpoint/gRPC security tests (authn, revocation, RBAC, ABAC on both transports)

## Medium
- [x] M5 gRPC SubscribeEvents double-abort — real reason masked as "Invalid token"
- [x] M6 EmitEvent leaks raw exception text to ingest clients
- [x] M7 `persist_event` upsert wipes trace `outcome` when event omits it
- [x] M8 Audit-log write failure turns a successful mutation into a 500
- [x] M9 nginx buffers the gRPC-Web stream (`proxy_buffering on`, 60s read timeout)
- [x] M10 Keepalive empty events render as blank spans in the live viewer
- [x] M11 Task Outcomes counts events, not tasks
- [x] M12 `subscribeEvents` cancel() never cancels the underlying stream
- [x] M13 Production compose `ports: []` does not unpublish (VERIFIED via `docker compose config`)
- [x] M14 Stray gitlink `.claude/worktrees/...` (mode 160000, no .gitmodules)
- [x] M15 No package-lock.json, `npm install` not `ci`, unverified plugin download
- [x] M16 Backend container runs as root

## Low
- [x] L17 base64url-safe JWT payload decode in useAuth
- [x] L18 401 response interceptor in restClient
- [x] L19 Schema drift: missing `task_id` index, no `created_at` index
- [x] L20 `list_traces` filters after LIMIT/OFFSET; `admin/audit` limit unbounded
- [x] L21 `create_user`: email validation + duplicate → 409
- [x] L22 `_effective_clearance` int() crash; admin self-lockout guard
- [x] L23 Bind OIDC `state` explicitly on the client
- [x] L24 Dead code: `hashed_password`, `_span_resource.agent_name`, discovery cache TTL, emitter sys.path guard
- [x] L25 `datetime.utcnow` deprecated/naive
- [x] L26 Envoy CORS pinned to localhost:5173 — document it as the Vite-dev-server path
- [x] L27 `pip install` → `uv pip install` in backend Dockerfile

## Review

All 27 items fixed. Verified with `pytest` (45 tests, up from 4),
`npm run typecheck`, `docker compose config` for both stacks, and YAML parsing
of every config touched.

**Notable changes beyond a one-line fix**

- `app/api.py` split out of `app/main.py` so the real router/middleware wiring
  can be imported by tests without the OTel exporters.
- `build_trace_upsert` / `build_span_upsert` extracted from `persist_event`, so
  the ON CONFLICT clause is assertable without a live Postgres.
- `app/services/request_context.py` centralises client-IP derivation; the hop
  count is configurable (`TRUSTED_PROXY_HOPS`) because it depends on topology.
- `docker-compose.override.yml` added; port publications moved out of the base
  file. Confirmed by diffing `docker compose config` for dev vs production.
- Migration `0003` drops the dead `hashed_password` column and adds the two
  indexes the models declared but the schema never had.

**Verified, not assumed**

- The production overlay really did leave `5173` and `50051` published
  (`docker compose config` before the change).
- The OIDC injection was reachable: the old concatenation produced two
  `redirect_uri` values, the second attacker-controlled.
- `protoc-gen-grpc-web` checksum computed from the actual 1.5.0 release binary.

**Left alone deliberately**

- `npm run typecheck` reports two pre-existing errors: the generated
  `src/proto/*.js` stubs ship without declarations. Unrelated to the audit and
  unchanged by it; a `proto.d.ts` shim would fix it if wanted.
- Trace listing still filters in Python after the SQL `LIMIT` (now scanning
  forward for a full page). Pushing ABAC into SQL would duplicate the policy in
  two places, which is the failure mode `lessons.md` already records.
