---
name: supply-chain-integrity
description: Scans project dependencies, configurations, and imports to detect supply chain risks, pin-less requirements, or malicious packages.
triggers:
  - supply chain
  - dependencies
  - imports
  - requirements
---

# Supply Chain Integrity

## What to look for
- Dependencies without pinned versions or hashes in requirements.txt or pyproject.toml.
- Packages with known vulnerabilities.
- Unverified, untrusted libraries or external APIs.

## Evidence required
- output from pip-audit, safety, or similar database scanners.
- AST analysis identifying risky or dynamically resolved package imports.

## Remediation patterns
- Pin dependencies using strict versions and hashes (e.g. poetry.lock, pip-compile).
- Schedule automated package scanning tasks.
- Keep dependencies updated using tools like dependabot.
