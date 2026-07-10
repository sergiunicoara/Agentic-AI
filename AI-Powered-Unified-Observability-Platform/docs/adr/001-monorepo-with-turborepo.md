# ADR-001: pnpm Workspaces + Turborepo Monorepo

**Status**: Accepted  
**Date**: 2026-07

## Context

SmartOps has three distinct runtime packages (`api`, `web`, `ai-agents`), shared types, infrastructure config, scripts, and E2E tests. The question was whether to keep these as separate repositories or a monorepo.

## Decision

Single monorepo with pnpm workspaces and Turborepo as the task runner.

## Rationale

- **Shared types without publishing** — `@smartops/shared-types` is consumed by both `api` and `web` via `workspace:*`. No versioning ceremony, no npm publish step in the dev loop.
- **Atomic refactors** — renaming a field on `Asset` updates the Drizzle schema, API route, shared type, and frontend SWR call in one commit. Cross-repo changes require coordinated PRs.
- **Turborepo caching** — build/typecheck/test outputs are cached by content hash. A change to `ai-agents` skips rebuilding `web` and `api` unless their inputs changed. CI is fast.
- **Single lock file** — dependency deduplication across packages reduces node_modules size and avoids version skew between packages consuming the same library.

## Trade-offs

- **Blast radius** — a broken typecheck in one package fails CI for all. Mitigated by `--filter` flags and package-level `turbo.json` overrides.
- **Slower initial install** — installing all packages at once takes longer than a single-package install. Acceptable for this project size.
- **IDE complexity** — some IDEs struggle with monorepo TypeScript paths. `paths` aliases in `tsconfig.json` handle most cases.

## Alternatives Considered

- **Separate repos** — discarded; cross-repo type sharing requires publishing to npm or using git submodules, both adding friction.
- **Nx** — more feature-rich but heavier. Turborepo is sufficient for this project size.
