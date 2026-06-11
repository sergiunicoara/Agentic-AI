# Lessons Learned

Patterns extracted from real debugging sessions on this project. Review before
touching auth, gRPC, or Docker config.

## Auth / OIDC

- **PKCE: one party generates the pair.** The verifier must be presented by
  whoever generated the challenge. First implementation had the backend
  generate its own PKCE pair while the frontend generated another — Google
  rejected every token exchange with 401. In a SPA flow: frontend generates
  verifier+challenge (Web Crypto), backend only stores `state` for CSRF.

- **python-jose needs `access_token` for `at_hash`.** Google ID tokens carry an
  `at_hash` claim; `jwt.decode()` raises `JWTClaimsError` unless you pass the
  access token alongside. Symptom: "No access_token provided to compare against
  at_hash claim."

- **One revocation-checking dependency, zero decode-only paths.** We shipped a
  `get_current_user` that decoded the JWT but skipped the Redis revocation
  check — logged-out tokens kept working on /evals for their full lifetime.
  Every auth dependency must delegate to the single verified path.

- **Enforce policy on every transport, not just REST.** ABAC span filtering
  existed in the REST router while the gRPC live stream forwarded everything —
  a clearance-0 viewer got confidential spans in real time. When adding an
  access-control layer, enumerate all read paths (REST, gRPC, websockets,
  exports) before calling it done.

- **Attributes baked into a JWT go stale.** Role/clearance in the token means
  demotion does nothing until expiry. Track jtis per user in Redis
  (`user_jtis:{id}`) so attribute changes can force-revoke sessions.

- **Don't EXPIRE a shared Redis set per entry.** `SADD revoked_jtis` +
  `EXPIRE` resets the clock for *all* entries on every revoke (and drops young
  entries when it fires). Use per-key TTLs: `SET revoked:{jti} 1 EX ttl`.

- **Never cache JWKS forever.** Providers rotate signing keys; a process-lifetime
  cache breaks all logins until restart. TTL the cache and retry once with a
  forced refresh on signature failure.

## Docker / environment

- **`docker compose restart` does not reload `env_file`.** Env vars are fixed at
  container creation. Use `docker compose up -d` (recreates) after env changes.

- **PowerShell expands `$VAR` inside double-quoted `sh -c "..."` strings** before
  Docker ever sees them — the container check printed an empty value while the
  var was set fine. Single-quote the shell payload.

- **`init_db()` create_all + Alembic fight each other.** Startup `create_all`
  already built the new columns, so `alembic upgrade head` failed on duplicates.
  When both exist, `alembic stamp <head>` records reality instead of replaying it.

- **Verify which checkout you're inspecting.** A grep from the worktree CWD hit
  the stale worktree copy and showed "dead code" that was already removed in the
  main checkout. Pin absolute paths when repo + worktree coexist.

## Process

- **Unauthenticated write paths invalidate the rest of the security story.**
  gRPC `EmitEvent` accepted spans from anyone on :50051 while REST had RBAC,
  audit logging, and ABAC. Audit the write paths first; they're where false
  confidence hides.

- **Record silent policy decisions in code.** Trace *metadata* is listed as
  public while span *contents* are filtered — that was an implicit choice during
  a bugfix ("nothing shown" on the dashboard). Decisions made under debugging
  pressure get a comment + README line, or they become surprises.
